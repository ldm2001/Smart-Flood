from __future__ import annotations

import logging
import math
from app.adapters.live import Live
from app.adapters.replay_source import Command, Replay
from app.config import checksum
from app.core.calibration import (
    OBSERVED_ZONES,
    Load,
    Sensor,
    adjustment,
    drainage,
    waterline,
)
from app.core.model import (
    BLOCKAGE_TYPES,
    ZONES,
    Conditions,
    Params,
    State,
    baseline,
    depth,
    evolution,
    flux,
    gradient,
)
from app.core.predictor import Prediction, forecast
from app.ports.clock import KST, Clock
from app.ports.experiment_log import (
    EXPERIMENT_ID,
    Absence,
    Flaw,
    Journal,
)
from app.ports.notifier import Notifier
from app.ports.source import Source
from app.schemas import (
    CONTRACT_HORIZONS_S,
    Message,
    directive,
    event,
    frame,
    header,
    observation,
)
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

STANDBY_ID = "EXP-STANDBY"  # 회차를 시작하기 전 대기 상태의 ID
DEFAULT_RAIN = "medium"
RAIN_PRESET_LABELS = {"light": "약한 강우", "medium": "보통 강우", "heavy": "강한 강우"}
BLOCKAGE_LABELS = {"partial": "부분 막힘", "full": "완전 막힘"}
OBSERVED_SOURCE = {"sim": "simulated", "replay": "replay", "live": "measured"}
SIM_DEVICES = {
    "esp32_1": "online",  # ESP32 1번: 연결됨
    "esp32_2": "online",  # ESP32 2번: 연결됨
    "floatSwitch": "normal",  # 플로트 스위치: 정상
    "emergencyStop": "normal",  # 비상 정지: 정상
}


# 값이 이 실험 구성에서 뜻이 없음(422, 위치 앞에 body)
class Fault(ValueError):
    # 오류 위치와 설명을 받음
    def __init__(self, loc: tuple[str, ...], message: str) -> None:
        super().__init__(message)
        self.loc = loc
        self.message = message


# 지금 상태에서 받을 수 없는 조작(409)
class Conflict(RuntimeError):
    pass


# 실험 기록을 쓸 수 없음(503)
class Outage(RuntimeError):
    pass


@dataclass(frozen=True)
# 한 시점의 실험 상태(SI). 응답은 Board.snapshot 이 만듦
class Snapshot:
    experiment_id: str  # 실험 회차 ID
    run_state: str  # 진행 상태: idle · running · stopped
    data_source: str  # 입력원: sim · replay · live
    timestamp: datetime  # 상태 시각
    elapsed_s: float  # 경과 시간(초)
    levels_m: dict[str, float]  # 표시 수위(m): A·B 는 최근 유효 관측, 없으면 모델
    zone_sources: dict[str, str]  # 구역별 값의 출처
    rates_m_per_s: dict[str, float]  # 구역별 수위 변화율(m/s)
    prediction: Prediction  # 예측 결과
    drained_m3: float  # 누적 배수량(m³)
    drain_flow_m3s: float  # 배수 유량(m³/s)
    rain_on: bool  # 강우 켜짐 여부
    rain_label: str  # 강우 이름
    rain_mm_per_h: float  # 선택한 강우(mm/h). 회차가 멈추면 모델에는 0 이 걸림
    blockage_type: str  # 막힘 종류
    blockage_location: str | None  # 막힌 빗물받이
    blockage_label: str  # 막힘 이름
    devices: dict[str, str]  # 장치 상태
    quality: str  # 데이터 품질
    alerts: tuple = ()  # 경보 목록


# 실험 런타임. fastapi 를 모르고 내부 단위는 SI
class Experiment:
    # 실험 하나를 메모리에 두고 1 Hz 로 tick
    def __init__(
        self,
        config: dict,
        clock: Clock,  # 시계(주입받음)
        source: Source,  # 관측 입력원(주입받음)
        experiment_log: Journal,  # 실험 기록(주입받음)
        notifier: Notifier | None = None,  # 알림(없을 수 있음)
        live: Live | None = None,  # 실장치 입력원(없으면 새로 만듦)
    ) -> None:
        self.clock = clock
        self.source = source
        self.experiment_log = experiment_log
        self._default_source = source
        self._live = Live() if live is None else live  # /api/ingest 가 채우는 입력원
        self.notifier = notifier  # 위험 단계 알림(M5 전에는 부르는 곳이 없음)
        self._config = config
        self._params = Params.config(config)
        self._presets = {k: float(v) for k, v in config["rain_presets_mm_per_h"].items()}
        self._rain_max = float(config["rain_max_mm_per_h"])  # 강우 상한(mm/h)
        self._period_s = 1.0 / float(config["tick_hz"])  # tick 주기(초)
        self._gain = float(config["correction"]["gain"])
        self._max_age_s = float(config["correction"]["max_age_s"])  # 보정에 쓸 관측의 최대 나이(초)
        self._horizons_s = tuple(int(h) for h in config["prediction"]["horizons_s"])
        self._valid_for_s = float(config["prediction"]["valid_for_s"])  # 예측 유효 시간(초)
        self._sensors = {z: Sensor.config(config["sensors"][z]) for z in OBSERVED_ZONES}
        self._load = Load.config(config["sensors"]["load"])
        self._allowed = tuple(str(d) for d in config["devices"]["allowed"])  # 허용 장치 ID
        self._offline_after_s = float(config["devices"]["offline_after_s"])  # 수신 끊김(초)
        self._invalid_after_s = float(config["correction"]["invalid_after_s"])  # 품질 invalid(초)
        self._seen: dict[str, float] = {}  # 장치 → 마지막 수신 시각(단조 초)
        self._absent: frozenset[str] = frozenset()  # 마지막 메시지에서 absent 였던 구역
        self.review()  # 계약대로 응답할 수 있는 구성인지 봄(아니면 기동에서 실패)
        self._config_hash = checksum(config)  # 설정 해시(회차마다 meta 줄에 구성을 그대로 적음)

        self._data_source = "sim"  # 입력원 이름(처음은 시뮬레이션)
        self._replay: Replay | None = None
        self._rain_mm = self._presets[DEFAULT_RAIN]  # 선택한 강우 세기(mm/h)
        self._blockage: tuple[str, str | None] = ("none", None)  # 선택한 막힘(종류, 위치)
        self.rest()
        self.renewal()

    # 계약대로 응답할 수 없는 구성이면 첫 요청이 아니라 기동에서 실패
    def review(self) -> None:
        if set(self._presets) != set(RAIN_PRESET_LABELS):  # 프리셋 이름이 계약과 다르면
            raise ValueError(f"강우 프리셋은 {sorted(RAIN_PRESET_LABELS)} 이어야 한다")
        for name, mm in self._presets.items():
            if not 0.0 <= mm <= self._rain_max:
                raise ValueError(f"강우 프리셋 {name} {mm:g} mm/h 가 상한 밖이다")
        steps = self._period_s / self._params.dt_s  # tick 한 번에 들어가는 dt 걸음 수
        if not (steps >= 1 and math.isclose(steps, round(steps), rel_tol=1e-9)):
            raise ValueError(f"tick 주기 {self._period_s:g} s 가 dt 의 정수배가 아니다")
        if self._horizons_s != CONTRACT_HORIZONS_S:  # 예측 구간이 계약 키와 다르면
            raise ValueError(f"예측 구간은 계약 키 {CONTRACT_HORIZONS_S} 와 같아야 한다")
        if not 0.0 <= self._gain <= 1.0:
            raise ValueError(f"보정 이득은 0~1 이어야 한다: {self._gain}")

    @property  # 속성처럼 읽음(조회)
    # 최근 스냅샷. live 의 장치 상태는 읽는 때로 새로 봄(대기 중에는 tick 이 없음)
    def snapshot(self) -> Snapshot:
        if self._data_source == "live":
            return replace(self._snapshot, devices=self.roster())
        return self._snapshot

    @property
    # 모델 상태
    def state(self) -> State:
        return self._state

    @property
    # 설정 전체
    def config(self) -> dict:
        return self._config

    @property
    # 지금 모델에 걸리는 강우·막힘. 비는 회차가 도는 동안에만 내림
    def conditions(self) -> Conditions:
        kind, location = self._blockage
        rain = self._rain_mm if self._run_state == "running" else 0.0
        return Conditions(rain, {location: kind} if kind != "none" else {})

    # 회차를 시작. 이미 돌고 있으면 선택만 변환
    def launch(
        self, rain: str | None = None, blockage: str | None = None, location: str | None = None
    ) -> None:
        if rain is not None and rain not in self._presets:
            raise Fault(("rain",), f"모르는 강우 프리셋: {rain}")  # 422 오류를 냄
        chosen = self._blockage
        if blockage is not None:
            try:
                chosen = self.jam(blockage, location)
            except Fault as error:
                raise Fault(("blockage", *error.loc), error.message) from None
        rain_mm = self._rain_mm if rain is None else self._presets[rain]  # 강우 세기(mm/h)
        self.refusal("회차를 시작할")  # 재생 중이면 거부(값을 다 본 뒤에)
        if self._run_state == "running":
            self.note("start", rain_mm_per_h=rain_mm, blockage=chosen)
        else:
            self.opening(rain_mm, chosen)
        self._rain_mm, self._blockage = rain_mm, chosen
        self.renewal()

    # 회차를 멈춤. 비는 그치고 마지막 상태가 남음
    def end(self) -> None:
        if self._run_state == "running":
            self.memo("stop")
            self._run_state = "stopped"
        self.renewal()

    # 대기 상태로 돌아가고 강우·막힘 선택을 기본값으로 돌림
    def standby(self) -> None:
        self.refusal("초기화할")
        self.memo("reset")
        if self._run_state != "idle":
            self.rest()
        self._rain_mm = self._presets[DEFAULT_RAIN]
        self._blockage = ("none", None)
        self.renewal()

    # 새 회차를 엶. meta·start 줄을 먼저 쓰고, 쓰지 못하면 아무것도 바꾸지 않음
    def opening(self, rain_mm: float, blockage: tuple[str, str | None]) -> None:
        now = self.clock.now()
        with shield():  # 입출력 오류는 503 으로
            experiment_id = self.serial(now)
            meta = header(  # 첫 줄(meta)을 만듦
                experiment_id=experiment_id,
                data_source=self._data_source,
                start_time=now,
                model_version=self._params.model_version,
                config_hash=self._config_hash,
                config=self._config,
            )
            start = directive("start", 0.0, now, rain_mm_per_h=rain_mm, blockage=blockage)
            self.experiment_log.batch(experiment_id, [meta, start])  # 둘 다 쓰거나 둘 다 안 씀
        self._experiment_id = experiment_id
        self._start_wall = now
        self._t0 = self.clock.monotonic()
        self._ticks = 0
        self._state = baseline(self._params)
        self._latest: dict[str, tuple[float, float]] = {}  # 구역 → (관측 수위 m, 받은 경과 초)
        self._absent = frozenset()
        self.source.origin()
        self._run_state = "running"

    # 대기 상태로 돌림
    def rest(self) -> None:
        self._run_state = "idle"
        self._experiment_id = STANDBY_ID
        self._start_wall = self.clock.now()
        self._t0 = self.clock.monotonic()
        self._ticks = 0
        self._state = baseline(self._params)
        self._latest = {}
        self._absent = frozenset()

    # 그 날짜의 기록 중 가장 큰 번호 + 1. 재시작해도 번호가 겹치지 않음
    def serial(self, now: datetime) -> str:
        date = now.astimezone(KST).strftime("%Y%m%d")  # 한국 날짜 YYYYMMDD
        used = [
            int(match.group(2))
            for experiment_id in self.experiment_log.index()
            if (match := EXPERIMENT_ID.fullmatch(experiment_id)) and match.group(1) == date
        ]
        return f"EXP-{date}-{max(used, default=0) + 1:03d}"

    # 도는 동안의 조작을 적용 시각과 함께 적음. 재생은 기록하지 않음
    def note(self, kind: str, **values) -> None:
        if self._run_state != "running" or self._replay is not None:
            return
        # 조작 줄을 만듦(적용 시각은 처리한 tick 의 경과 초)
        record = directive(kind, self._ticks * self._period_s, self.clock.now(), **values)
        with shield():  # 입출력 오류는 503 으로
            self.experiment_log.entry(self._experiment_id, record)

    # 종료·초기화는 기록하지 못해도 적용(멈추는 조작을 막지 않음)
    def memo(self, kind: str) -> None:
        try:
            self.note(kind)
        except Outage as error:
            log.warning("%s %s 를 기록하지 못했지만 적용한다: %s", self._experiment_id, kind, error)

    # 재생 중이면 거부(값을 다 본 뒤에: 틀린 값은 409 보다 422)
    def refusal(self, what: str) -> None:
        if self._replay is not None:
            raise Conflict(f"재생 중에는 {what} 수 없다. 입력원을 sim 으로 바꾼 뒤 한다")  # 409

    # 강우 변경(프리셋 또는 mm/h 중 하나)
    def rain(self, intensity: str | None = None, mm_per_h: float | None = None) -> None:
        if (intensity is None) == (mm_per_h is None):
            raise Fault((), "intensity 와 mmPerHour 중 하나만 준다")  # 422 오류를 냄
        if intensity is not None:
            if intensity not in self._presets:
                raise Fault(("intensity",), f"모르는 강우 프리셋: {intensity}")  # 422 오류를 냄
            rain_mm = self._presets[intensity]
        else:
            rain_mm = self.rainfall(mm_per_h)
        self.refusal("강우를 바꿀")
        self.note("rain", rain_mm_per_h=rain_mm)
        self._rain_mm = rain_mm
        self.renewal()

    # 직접 준 강우 세기를 검사
    def rainfall(self, mm_per_h: float) -> float:
        if not (math.isfinite(mm_per_h) and 0.0 <= mm_per_h <= self._rain_max):
            message = f"강우는 0~{self._rain_max:g} mm/h 여야 한다: {mm_per_h}"
            raise Fault(("mmPerHour",), message)  # 422 오류를 냄
        return float(mm_per_h)

    # 막힘을 변환
    def blockage(self, kind: str, location: str | None = None) -> None:
        chosen = self.jam(kind, location)
        self.refusal("막힘을 바꿀")
        self.note("blockage", blockage=chosen)
        self._blockage = chosen
        self.renewal()

    # 막힘 선택이 이 구성에서 뜻이 있는지 확인
    def jam(self, kind: str, location: str | None) -> tuple[str, str | None]:
        if kind not in BLOCKAGE_TYPES:
            raise Fault(("type",), f"모르는 막힘 종류: {kind}")  # 422 오류를 냄
        if location is not None and location not in self._params.inlets:
            known = ", ".join(sorted(self._params.inlets))
            raise Fault(("location",), f"모르는 빗물받이: {location} (있는 것: {known})")  # 422
        if kind == "none":
            return ("none", None)
        if location is None:
            raise Fault(("location",), f"{kind} 막힘에는 location 이 필요하다")  # 422 오류를 냄
        return (kind, location)

    # 입력원 변경. replay 는 그 기록을 처음부터 다시 돌림
    def channel(self, mode: str, log_id: str | None = None) -> None:
        if mode not in ("sim", "replay", "live"):
            raise Fault(("mode",), f"모르는 입력원: {mode}")  # 422 오류를 냄
        if mode == "live":
            if self._data_source == "live":
                return
            self.refusal("입력원을 바꿀")  # 재생 중이면 409
            self.switch(self._live, "live")
            return
        if mode == "sim":
            if self._replay is not None:
                self.fallback()
                self.renewal()
            elif self._data_source == "live":
                self.switch(self._default_source, "sim")
            return
        if log_id is None:
            raise Fault(("logId",), "replay 에는 logId 가 필요하다")  # 422 오류를 냄
        if self._replay is not None and log_id == self._experiment_id:
            return
        replay = self.tape(log_id)  # 기록을 읽어 재생 입력원을 만듦
        if self._replay is None and self._run_state == "running":
            raise Conflict("회차가 도는 중에는 재생할 수 없다. 먼저 종료한다")  # 409 오류를 냄
        self.playback(replay)
        self.renewal()

    # sim·live 사이의 전환. 회차가 도는 중이면 409, 아니면 선택을 기본값으로 돌리고 대기 상태로
    def switch(self, source: Source, name: str) -> None:
        if self._run_state == "running":
            raise Conflict("회차가 도는 중에는 입력원을 바꿀 수 없다. 먼저 종료한다")  # 409
        self.source = source
        self._data_source = name
        self.rest()
        self._rain_mm = self._presets[DEFAULT_RAIN]
        self._blockage = ("none", None)
        self.renewal()

    # 기록을 읽어 재생 입력원을 만듦(조작 값은 지금 구성으로 봄)
    def tape(self, log_id: str) -> Replay:
        if not EXPERIMENT_ID.fullmatch(log_id):
            raise Fault(("logId",), f"실험 ID 형식이 아니다: {log_id}")  # 422 오류를 냄
        try:
            with shield():  # 입출력 오류는 503 으로
                replay = Replay(self.experiment_log.records(log_id))
            if replay.experiment_id != log_id:  # meta 의 ID 가 요청과 다르면
                raise Flaw(f"meta 의 실험 ID {replay.experiment_id} 가 파일과 다르다")
            for command in replay.commands:
                self.screen(command)
            self.span(replay)  # 마지막 tick 의 시각이 만들어지는지 확인
        except Absence:
            raise Fault(("logId",), f"그런 실험 기록이 없다: {log_id}") from None  # 422 로 변환
        except Flaw as error:
            raise Fault(("logId",), f"재생할 수 없는 기록: {error}") from None  # 422 오류로 바꿔 냄
        return replay

    # 기록된 조작 값이 지금 구성에서 뜻이 있는지 확인
    def screen(self, command: Command) -> None:
        try:
            if command.rain_mm_per_h is not None:
                self.rainfall(command.rain_mm_per_h)
            if command.blockage is not None:
                self.jam(*command.blockage)
        except Fault as error:
            raise Flaw(f"{command.line}번째 줄: {error.message}") from None

    # 기록 끝 다음의 tick 경계 시각이 만들어지는지 확인. 시작 시각이 늦거나 경과 초가 크면 넘침
    def span(self, replay: Replay) -> None:
        try:
            last_s = math.ceil(replay.end_s / self._period_s) * self._period_s  # 마지막 tick 의 초
            replay.start_time + timedelta(seconds=last_s)
        except OverflowError:
            start = replay.start_time.isoformat()  # 시작 시각(KST, 글자)
            end = f"{replay.end_s:g}"  # 기록 끝의 경과 초(글자)
            reason = f"startTime {start} 에서 기록 끝 {end} 초 뒤의 tick 시각을 만들 수 없다"
            raise Flaw(reason) from None

    # 기록의 처음에서 재생을 시작(시작 시각은 기록의 것)
    def playback(self, replay: Replay) -> None:
        replay.origin()
        self._replay = self.source = replay
        self._data_source = "replay"
        self._experiment_id = replay.experiment_id
        self._start_wall = replay.start_time
        self._t0 = self.clock.monotonic()
        self._ticks = 0
        self._state = baseline(self._params)
        self._latest = {}
        self._run_state = "running"
        self.progress()  # 0 초의 조작을 먼저 적용

    # 재생을 떠나 시뮬레이션 대기 상태로 돌아감
    def fallback(self) -> None:
        self._replay = None
        self.source = self._default_source
        self._data_source = "sim"
        self.rest()
        self._rain_mm = self._presets[DEFAULT_RAIN]
        self._blockage = ("none", None)

    # 재생이면 다음 tick 전에 기록된 조작을 적용. 기록의 끝이면 멈추고 False
    def progress(self) -> bool:
        if self._replay is None:
            return True  # 그대로 진행
        basis_s = self._ticks * self._period_s
        for command in self._replay.orders(basis_s):
            self.effect(command)  # 조작 적용(원래도 다음 tick 부터 걸림)
        if basis_s < self._replay.end_s:
            return True
        self.halt()
        return False

    # 기록된 강우·막힘을 적용(종료·초기화는 기록의 끝으로 반영)
    def effect(self, command: Command) -> None:
        if command.rain_mm_per_h is not None:
            self._rain_mm = command.rain_mm_per_h
        if command.blockage is not None:
            self._blockage = self.jam(*command.blockage)

    # 시계로 보아 밀린 tick 을 처리하고 처리한 수를 반환
    def catchup(self, limit: int | None = None) -> int:
        due = self.backlog() if limit is None else min(self.backlog(), limit)  # 처리할 tick 수
        for done in range(due):  # tick 마다
            try:
                if not self.progress():
                    return done
                self.tick()
            except Exception as error:  # 계산이나 기록이 실패하면
                log.exception(
                    "%s tick %d 처리 실패, 회차를 멈춘다", self._experiment_id, self._ticks + 1
                )
                self.failure(error)  # 회차 기록(event 줄)에 남김
                self.halt()  # 회차를 멈춤(실패한 tick 은 반영하지 않음)
                return done
        return due

    # 실패한 tick 자리에 event 줄을 남김(쓰지 못하면 경고만)
    def failure(self, error: Exception) -> None:
        if self._replay is not None:
            return
        record = event(
            "calc_error",  # 사건 종류: 계산 오류
            (self._ticks + 1) * self._period_s,
            self.clock.now(),
            f"{type(error).__name__}: {error}",
        )
        try:
            with shield():  # 입출력 오류는 503 으로
                self.experiment_log.entry(self._experiment_id, record)  # event 줄을 기록
        except Outage as write_error:
            log.warning("%s 계산 오류를 기록하지 못했다: %s", self._experiment_id, write_error)

    # 실패한 tick 뒤나 재생의 끝에서 멈춤
    def halt(self) -> None:
        self._run_state = "stopped"
        try:
            self.renewal()
        except Exception:
            log.exception("%s 멈춘 상태를 계산하지 못해 마지막 상태를 둔다", self._experiment_id)
            self._snapshot = replace(self._snapshot, run_state="stopped", rain_on=False)

    # 다음 tick 까지 남은 시간(초). 돌고 있지 않으면 None
    def delay(self) -> float | None:
        if self._run_state != "running":
            return None  # 기다릴 tick 이 없음
        due_at = self._t0 + (self._ticks + 1) * self._period_s
        return max(0.0, due_at - self.clock.monotonic())  # 남은 시간(밀렸으면 0)

    # 시계로 보아 밀린 tick 수
    def backlog(self) -> int:
        if self._run_state != "running":
            return 0
        elapsed = self.clock.monotonic() - self._t0  # 시작 후 지난 시간(초)
        return max(0, math.floor(elapsed / self._period_s + 1e-9) - self._ticks)

    # 한 주기를 계산하고 기록. 끝까지 성공해야 상태에 반영
    def tick(self) -> None:
        elapsed = (self._ticks + 1) * self._period_s
        cond = self.conditions
        received_at = self.clock.now()
        observations: list[dict] = []
        readings: dict[str, float] = {}  # 유효한 관측 수위(m)
        absent = self._absent  # 마지막 메시지에서 absent 였던 구역
        for message in self.source.inbox(elapsed, cond):
            levels, drained_m3, quality, absent = self.reading(message)
            observations.append(
                observation(elapsed, received_at, message, levels, drained_m3, quality)
            )
            readings.update({z: h for z, h in levels.items() if h is not None})
        state = evolution(self._state, cond, self._params, self._period_s)
        corrections = ()  # 보정 내역(없으면 비어 있음)
        if readings:
            state, corrections = adjustment(state, readings, self._gain, self._params)
        latest = {**self._latest, **{z: (h, elapsed) for z, h in readings.items()}}
        snapshot = self.capture(state, elapsed, latest, absent)
        record = frame(snapshot, state, corrections)
        if self._replay is None:  # 재생이 아닐 때만 씀(재생도 줄은 만들어 계약을 검사)
            with shield():  # 입출력 오류는 503 으로
                lines = [*observations, record]  # obs 줄들과 state 줄을 한 tick 에 함께
                self.experiment_log.batch(self._experiment_id, lines)  # 다 쓰이거나 하나도 안 쓰임
        self._state, self._latest, self._absent = state, latest, absent
        self._snapshot = snapshot
        self._ticks += 1

    # 관측 메시지를 A·B 수위(m), 배수량(m³), 센서별 품질, absent 구역으로 변환. 무효는 None
    def reading(
        self, message: dict
    ) -> tuple[dict[str, float | None], float | None, dict[str, str], frozenset[str]]:
        msg = Message.model_validate(message)
        levels: dict[str, float | None] = {}  # 구역별 수위(m)
        quality: dict[str, str] = {}
        for z in OBSERVED_ZONES:  # 관측하는 구역(A·B)마다
            distance = getattr(msg.readings, f"dist{z}_mm")  # 수면까지 거리(mm)
            level = None
            if distance is not None and getattr(msg.sensorStatus, z) == "ok":
                level = waterline(distance, self._sensors[z])
            levels[z] = level
            quality[z] = "invalid" if level is None else "valid"
        weight = msg.readings.weight_g  # 배수 무게(g)
        drained_m3 = None
        if weight is not None and msg.sensorStatus.load == "ok" and math.isfinite(weight):
            drained_m3 = drainage(weight, self._load)
        quality["load"] = "invalid" if drained_m3 is None else "valid"
        absent = frozenset(z for z in OBSERVED_ZONES if getattr(msg.sensorStatus, z) == "absent")
        return levels, drained_m3, quality, absent

    # 스냅샷을 새로 만들어 표시값을 갱신
    def renewal(self) -> None:
        elapsed = self._ticks * self._period_s
        self._snapshot = self.capture(self._state, elapsed, self._latest)

    # 상태와 경과 시간으로 스냅샷을 만듦
    def capture(
        self,
        state: State,
        elapsed_s: float,
        latest: dict[str, tuple[float, float]],
        absent: frozenset[str] | None = None,  # absent 구역(없으면 마지막 메시지의 것)
    ) -> Snapshot:
        absent = self._absent if absent is None else absent
        cond = self.conditions
        prediction = forecast(
            state,
            cond,
            self._params,
            basis_elapsed_s=elapsed_s,
            horizons_s=self._horizons_s,  # 예측 구간(초)
            valid_for_s=self._valid_for_s,  # 예측 유효 시간(초)
        )
        flows = flux(state, cond, self._params)
        levels, sources = {}, {}
        for z in ZONES:
            reading = latest.get(z)  # 최근 관측(수위 m, 받은 경과 초)
            if reading is not None and elapsed_s - reading[1] <= self._max_age_s:
                levels[z], sources[z] = max(0.0, reading[0]), OBSERVED_SOURCE[self._data_source]
            else:
                levels[z], sources[z] = depth(z, state.V[z], self._params), "estimated"
        kind, location = self._blockage
        return Snapshot(
            experiment_id=self._experiment_id,
            run_state=self._run_state,
            data_source=self._data_source,
            timestamp=self._start_wall + timedelta(seconds=elapsed_s),
            elapsed_s=elapsed_s,  # 경과 시간(초)
            levels_m=levels,
            zone_sources=sources,
            rates_m_per_s=gradient(state, cond, self._params),
            prediction=prediction,
            drained_m3=sum(state.drained_m3.values()),
            drain_flow_m3s=sum(flows.drains_m3s.values()),
            rain_on=self._run_state == "running" and self._rain_mm > 0,
            rain_label=self.weather(),
            rain_mm_per_h=self._rain_mm,
            blockage_type=kind,
            blockage_location=location,
            blockage_label=self.outlet(),
            devices=self.roster(),
            quality=self.grade(elapsed_s, latest, absent),
        )

    # 장치 메시지를 받아 둠(입력원이 live 일 때 다음 tick 에 쓰임). 모르는 장치는 422
    def intake(self, message: dict) -> None:
        device = message["deviceId"]
        if device not in self._allowed:
            known = ", ".join(self._allowed)  # 허용 장치 목록(글자)
            raise Fault(("deviceId",), f"모르는 장치: {device} (있는 것: {known})")  # 422
        self._seen[device] = self.clock.monotonic()
        self._live.admit(message)
        if self._run_state != "running":
            self.renewal()  # 대기·정지 중에도 장치 상태를 새로 봄

    # 장치 상태. live 는 마지막 수신 뒤 offline_after_s 부터 offline, 그 밖은 시뮬레이션 값
    def roster(self) -> dict[str, str]:
        if self._data_source != "live":
            return dict(SIM_DEVICES)
        now = self.clock.monotonic()
        devices = {}
        for device in ("esp32_1", "esp32_2"):  # 계약의 장치 키. 허용 목록에 없으면 offline
            fresh = device in self._seen and now - self._seen[device] < self._offline_after_s
            devices[device] = "online" if fresh else "offline"
        return {**devices, "floatSwitch": "unknown", "emergencyStop": "unknown"}  # 메시지에 없음

    # 입력 품질. live 는 기대 센서(absent 가 아닌 A·B)의 마지막 유효 관측 나이로 판정
    def grade(
        self, elapsed_s: float, latest: dict[str, tuple[float, float]], absent: frozenset[str]
    ) -> str:
        if self._data_source != "live":
            return "valid"
        expected = [z for z in OBSERVED_ZONES if z not in absent]  # 기대하는 센서
        ages = [elapsed_s - latest[z][1] if z in latest else math.inf for z in expected]
        if ages and all(age <= self._max_age_s for age in ages):
            return "valid"
        if all(age >= self._invalid_after_s for age in ages):  # 기대 센서가 없어도 invalid
            return "invalid"
        return "degraded"

    # 화면에 보일 강우 이름
    def weather(self) -> str:
        if self._rain_mm == 0:
            return "강우 없음"
        for name, mm in self._presets.items():
            if self._rain_mm == mm:
                return RAIN_PRESET_LABELS[name]
        return f"직접 입력 {self._rain_mm:g} mm/h"

    # 화면에 보일 막힘 이름
    def outlet(self) -> str:
        kind, location = self._blockage
        if kind == "none":
            return "정상 배수"
        return f"빗물받이 {numeral(location)} {BLOCKAGE_LABELS[kind]}"


@contextmanager  # with 문에서 쓰는 도구로 만듦
# 기록 입출력 오류를 Outage 로 변환(기록 조회 API 도 씀)
def shield() -> Iterator[None]:
    try:
        yield  # with 안쪽을 여기서 실행
    except OSError as error:
        reason = error.strerror or type(error).__name__  # 이유만 남김(응답에 파일 경로 비노출)
        raise Outage(f"실험 기록을 쓸 수 없다: {reason}") from error  # 503


# INLET-02 → ②. 번호를 읽을 수 없으면 ID 를 그대로 씀
def numeral(inlet_id: str) -> str:
    number = inlet_id.rpartition("-")[2]
    if number.isdecimal() and 1 <= int(number) <= 20:
        return chr(0x2460 + int(number) - 1)
    return inlet_id  # 아니면 ID 를 그대로 씀
