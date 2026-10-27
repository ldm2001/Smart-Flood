from __future__ import annotations

import logging
import math
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

log = logging.getLogger(__name__)  # 이 모듈의 로거

STANDBY_ID = "EXP-STANDBY"  # 회차를 시작하기 전 대기 상태의 ID
DEFAULT_RAIN = "medium"  # 처음 강우 프리셋
# 프리셋의 화면 이름
RAIN_PRESET_LABELS = {"light": "약한 강우", "medium": "보통 강우", "heavy": "강한 강우"}
BLOCKAGE_LABELS = {"partial": "부분 막힘", "full": "완전 막힘"}  # 막힘의 화면 이름
# A·B 표시 출처: 입력원별
OBSERVED_SOURCE = {"sim": "simulated", "replay": "replay", "live": "measured"}
SIM_DEVICES = {  # 시뮬레이션 장치 상태
    "esp32_1": "online",  # ESP32 1번: 연결됨
    "esp32_2": "online",  # ESP32 2번: 연결됨
    "floatSwitch": "normal",  # 플로트 스위치: 정상
    "emergencyStop": "normal",  # 비상 정지: 정상
}


# 값이 이 실험 구성에서 뜻이 없다(422, 위치 앞에 body)
class Fault(ValueError):
    # 오류 위치와 설명을 받음
    def __init__(self, loc: tuple[str, ...], message: str) -> None:
        super().__init__(message)  # 부모에게 설명을 넘긴다
        self.loc = loc  # 오류 위치
        self.message = message  # 오류 설명


# 아직 구현하지 않은 기능(501)
class Lack(RuntimeError):
    pass  # 내용 없이 이름만 둔다


# 지금 상태에서 받을 수 없는 조작(409)
class Conflict(RuntimeError):
    pass  # 내용 없이 이름만 둔다


# 실험 기록을 쓸 수 없다(503)
class Outage(RuntimeError):
    pass  # 내용 없이 이름만 둔다


@dataclass(frozen=True)  # 바꿀 수 없는 값 묶음
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


# 실험 런타임. fastapi 를 모르고 내부 단위는 SI 다
class Experiment:
    # 실험 하나를 메모리에 두고 1 Hz 로 tick
    def __init__(
        self,  # 자기 자신
        config: dict,  # 설정
        clock: Clock,  # 시계(주입받는다)
        source: Source,  # 관측 입력원(주입받는다)
        experiment_log: Journal,  # 실험 기록(주입받는다)
        notifier: Notifier | None = None,  # 알림(없을 수 있다)
    ) -> None:  # 돌려주는 값은 없다
        self.clock = clock  # 시계
        self.source = source  # 지금 쓰는 입력원
        self.experiment_log = experiment_log  # 실험 기록
        self._default_source = source  # 재생을 떠나면 돌아올 입력원
        self.notifier = notifier  # 위험 단계 알림(M5 전에는 부르는 곳이 없다)
        self._config = config  # 설정 전체
        self._params = Params.config(config)  # 모델 계수
        # 프리셋별 강우 세기(mm/h)
        self._presets = {k: float(v) for k, v in config["rain_presets_mm_per_h"].items()}
        self._rain_max = float(config["rain_max_mm_per_h"])  # 강우 상한(mm/h)
        self._period_s = 1.0 / float(config["tick_hz"])  # tick 주기(초)
        self._gain = float(config["correction"]["gain"])  # 보정 이득
        self._max_age_s = float(config["correction"]["max_age_s"])  # 보정에 쓸 관측의 최대 나이(초)
        # 예측 구간(초)
        self._horizons_s = tuple(int(h) for h in config["prediction"]["horizons_s"])
        self._valid_for_s = float(config["prediction"]["valid_for_s"])  # 예측 유효 시간(초)
        # 관측 구역별 거리 센서 변환
        self._sensors = {z: Sensor.config(config["sensors"][z]) for z in OBSERVED_ZONES}
        self._load = Load.config(config["sensors"]["load"])  # 무게 센서 변환
        self.review()  # 계약대로 응답할 수 있는 구성인지 본다(아니면 기동에서 실패)
        self._config_hash = checksum(config)  # 설정 해시(회차마다 meta 줄에 구성을 그대로 적는다)

        self._data_source = "sim"  # 입력원 이름(처음은 시뮬레이션)
        self._replay: Replay | None = None  # 재생 중이면 그 입력원
        self._rain_mm = self._presets[DEFAULT_RAIN]  # 선택한 강우 세기(mm/h)
        self._blockage: tuple[str, str | None] = ("none", None)  # 선택한 막힘(종류, 위치)
        self.rest()  # 대기 상태로 시작
        self.renewal()  # 스냅샷을 새로 만듦

    # 계약대로 응답할 수 없는 구성이면 첫 요청이 아니라 기동에서 실패
    def review(self) -> None:
        if set(self._presets) != set(RAIN_PRESET_LABELS):  # 프리셋 이름이 계약과 다르면
            raise ValueError(f"강우 프리셋은 {sorted(RAIN_PRESET_LABELS)} 이어야 한다")  # 오류를 냄
        for name, mm in self._presets.items():  # 프리셋마다
            if not 0.0 <= mm <= self._rain_max:  # 강우 상한 밖이면
                raise ValueError(f"강우 프리셋 {name} {mm:g} mm/h 가 상한 밖이다")  # 오류를 냄
        steps = self._period_s / self._params.dt_s  # tick 한 번에 들어가는 dt 걸음 수
        # 1 이상의 정수가 아니면
        if not (steps >= 1 and math.isclose(steps, round(steps), rel_tol=1e-9)):
            # 오류를 냄
            raise ValueError(f"tick 주기 {self._period_s:g} s 가 dt 의 정수배가 아니다")
        if self._horizons_s != CONTRACT_HORIZONS_S:  # 예측 구간이 계약 키와 다르면
            # 오류를 냄
            raise ValueError(f"예측 구간은 계약 키 {CONTRACT_HORIZONS_S} 와 같아야 한다")
        if not 0.0 <= self._gain <= 1.0:  # 보정 이득이 0~1 밖이면
            raise ValueError(f"보정 이득은 0~1 이어야 한다: {self._gain}")  # 오류를 냄

    @property  # 속성처럼 읽는다(조회)
    # 최근 스냅샷
    def snapshot(self) -> Snapshot:
        return self._snapshot  # 저장된 스냅샷을 반환

    @property  # 속성처럼 읽음
    # 모델 상태
    def state(self) -> State:
        return self._state  # 저장된 상태를 반환

    @property  # 속성처럼 읽음
    # 설정 전체
    def config(self) -> dict:
        return self._config  # 설정을 반환

    @property  # 속성처럼 읽음
    # 지금 모델에 걸리는 강우·막힘. 비는 회차가 도는 동안에만 내림
    def conditions(self) -> Conditions:
        kind, location = self._blockage  # 막힘 종류와 위치
        # 회차가 도는 중에만 비가 내림
        rain = self._rain_mm if self._run_state == "running" else 0.0
        return Conditions(rain, {location: kind} if kind != "none" else {})  # 막힘이 없으면 빈 조건

    # 회차를 시작한다. 이미 돌고 있으면 선택만 변환
    def launch(
        # 강우 프리셋, 막힘 종류, 막힘 위치(모두 선택)
        self, rain: str | None = None, blockage: str | None = None, location: str | None = None
    ) -> None:  # 돌려주는 값은 없다
        if rain is not None and rain not in self._presets:  # 모르는 프리셋이면
            raise Fault(("rain",), f"모르는 강우 프리셋: {rain}")  # 422 오류를 냄
        chosen = self._blockage  # 막힘은 지금 선택을 기본으로
        if blockage is not None:  # 막힘을 새로 골랐으면
            try:  # 값을 검사
                chosen = self.jam(blockage, location)  # 막힘 선택을 확인
            except Fault as error:  # 뜻이 없는 값이면
                # 위치 앞에 blockage 를 붙여 다시 냄
                raise Fault(("blockage", *error.loc), error.message) from None
        rain_mm = self._rain_mm if rain is None else self._presets[rain]  # 강우 세기(mm/h)
        self.refusal("회차를 시작할")  # 재생 중이면 거부한다(값을 다 본 뒤에)
        if self._run_state == "running":  # 이미 돌고 있으면
            self.note("start", rain_mm_per_h=rain_mm, blockage=chosen)  # 선택 변경을 start 로 기록
        else:  # 아니면
            self.opening(rain_mm, chosen)  # 새 회차를 연다
        self._rain_mm, self._blockage = rain_mm, chosen  # 선택을 저장
        self.renewal()  # 스냅샷을 새로 만듦

    # 회차를 멈춘다. 비는 그치고 마지막 상태가 남음
    def end(self) -> None:
        if self._run_state == "running":  # 돌고 있으면
            self.memo("stop")  # 종료를 기록
            self._run_state = "stopped"  # 멈춤 상태로
        self.renewal()  # 스냅샷을 새로 만듦

    # 대기 상태로 돌아가고 강우·막힘 선택을 기본값으로 돌린다
    def standby(self) -> None:
        self.refusal("초기화할")  # 재생 중이면 거부
        self.memo("reset")  # 초기화를 기록
        if self._run_state != "idle":  # 대기 상태가 아니면
            self.rest()  # 대기 상태로 돌린다
        self._rain_mm = self._presets[DEFAULT_RAIN]  # 강우를 기본값으로
        self._blockage = ("none", None)  # 막힘을 없음으로
        self.renewal()  # 스냅샷을 새로 만듦

    # 새 회차를 연다. meta·start 줄을 먼저 쓰고, 쓰지 못하면 아무것도 바꾸지 않음
    def opening(self, rain_mm: float, blockage: tuple[str, str | None]) -> None:
        now = self.clock.now()  # 지금 시각
        with shield():  # 입출력 오류는 503 으로
            experiment_id = self.serial(now)  # 새 회차 ID
            meta = header(  # 첫 줄(meta)을 만듦
                experiment_id=experiment_id,  # 회차 ID
                data_source=self._data_source,  # 입력원
                start_time=now,  # 시작 시각
                model_version=self._params.model_version,  # 모델 버전
                config_hash=self._config_hash,  # 설정 해시
                config=self._config,  # 설정 전체
            )
            # 시작 조작 줄을 만듦
            start = directive("start", 0.0, now, rain_mm_per_h=rain_mm, blockage=blockage)
            # 두 줄을 한 번에 쓴다(한 줄만 남지 않게)
            self.experiment_log.batch(experiment_id, [meta, start])
        self._experiment_id = experiment_id  # 회차 ID 를 변환
        self._start_wall = now  # 시작 시각
        self._t0 = self.clock.monotonic()  # 시작 기준 시계값
        self._ticks = 0  # tick 횟수를 0 으로
        self._state = baseline(self._params)  # 마른 상태에서 시작
        self._latest: dict[str, tuple[float, float]] = {}  # 구역 → (관측 수위 m, 받은 경과 초)
        self.source.origin()  # 입력원을 처음 위치로 돌린다
        self._run_state = "running"  # 돌아가는 중으로

    # 대기 상태로 돌린다
    def rest(self) -> None:
        self._run_state = "idle"  # 대기 상태로
        self._experiment_id = STANDBY_ID  # 대기 ID
        self._start_wall = self.clock.now()  # 시작 시각을 지금으로
        self._t0 = self.clock.monotonic()  # 시작 기준 시계값
        self._ticks = 0  # tick 횟수를 0 으로
        self._state = baseline(self._params)  # 마른 상태로
        self._latest = {}  # 관측 기록을 비운다

    # 그 날짜의 기록 중 가장 큰 번호 + 1. 재시작해도 번호가 겹치지 않음
    def serial(self, now: datetime) -> str:
        date = now.astimezone(KST).strftime("%Y%m%d")  # 한국 날짜 YYYYMMDD
        used = [  # 그 날짜에 이미 쓴 번호들
            int(match.group(2))  # 번호 부분
            for experiment_id in self.experiment_log.index()  # 기록된 회차 ID 마다
            # 형식이 맞고 같은 날짜인 것만
            if (match := EXPERIMENT_ID.fullmatch(experiment_id)) and match.group(1) == date
        ]
        return f"EXP-{date}-{max(used, default=0) + 1:03d}"  # 가장 큰 번호 다음을 반환

    # 도는 동안의 조작을 적용 시각과 함께 적는다. 재생은 기록하지 않음
    def note(self, kind: str, **values) -> None:
        if self._run_state != "running" or self._replay is not None:  # 돌고 있지 않거나 재생 중이면
            return  # 적지 않음
        # 조작 줄을 만든다(적용 시각은 처리한 tick 의 경과 초)
        record = directive(kind, self._ticks * self._period_s, self.clock.now(), **values)
        with shield():  # 입출력 오류는 503 으로
            self.experiment_log.entry(self._experiment_id, record)  # 조작 줄을 기록

    # 종료·초기화는 기록하지 못해도 적용한다(멈추는 조작을 막지 않음)
    def memo(self, kind: str) -> None:
        try:  # 기록을 시도
            self.note(kind)  # 조작을 적는다
        except Outage as error:  # 기록을 쓸 수 없으면
            # 경고만 남기고 적용
            log.warning("%s %s 를 기록하지 못했지만 적용한다: %s", self._experiment_id, kind, error)

    # 재생 중이면 거부한다(값을 다 본 뒤에: 틀린 값은 409 보다 422)
    def refusal(self, what: str) -> None:
        if self._replay is not None:  # 재생 중이면
            # 409 오류를 냄
            raise Conflict(f"재생 중에는 {what} 수 없다. 입력원을 sim 으로 바꾼 뒤 한다")

    # 강우를 바꾼다(프리셋 또는 mm/h 중 하나)
    def rain(self, intensity: str | None = None, mm_per_h: float | None = None) -> None:
        if (intensity is None) == (mm_per_h is None):  # 둘 다 주거나 둘 다 안 주면
            raise Fault((), "intensity 와 mmPerHour 중 하나만 준다")  # 422 오류를 냄
        if intensity is not None:  # 프리셋을 줬으면
            if intensity not in self._presets:  # 모르는 프리셋이면
                raise Fault(("intensity",), f"모르는 강우 프리셋: {intensity}")  # 422 오류를 냄
            rain_mm = self._presets[intensity]  # 프리셋의 세기
        else:  # 아니면
            rain_mm = self.rainfall(mm_per_h)  # 직접 준 세기를 검사
        self.refusal("강우를 바꿀")  # 재생 중이면 거부
        self.note("rain", rain_mm_per_h=rain_mm)  # 강우 조작을 기록
        self._rain_mm = rain_mm  # 선택을 저장
        self.renewal()  # 스냅샷을 새로 만듦

    # 직접 준 강우 세기를 검사
    def rainfall(self, mm_per_h: float) -> float:
        # 유한하지 않거나 상한 밖이면
        if not (math.isfinite(mm_per_h) and 0.0 <= mm_per_h <= self._rain_max):
            message = f"강우는 0~{self._rain_max:g} mm/h 여야 한다: {mm_per_h}"  # 오류 설명
            raise Fault(("mmPerHour",), message)  # 422 오류를 냄
        return float(mm_per_h)  # 실수로 반환

    # 막힘을 변환
    def blockage(self, kind: str, location: str | None = None) -> None:
        chosen = self.jam(kind, location)  # 막힘 선택을 확인
        self.refusal("막힘을 바꿀")  # 재생 중이면 거부
        self.note("blockage", blockage=chosen)  # 막힘 조작을 기록
        self._blockage = chosen  # 선택을 저장
        self.renewal()  # 스냅샷을 새로 만듦

    # 막힘 선택이 이 구성에서 뜻이 있는지 확인
    def jam(self, kind: str, location: str | None) -> tuple[str, str | None]:
        if kind not in BLOCKAGE_TYPES:  # 모르는 종류이면
            raise Fault(("type",), f"모르는 막힘 종류: {kind}")  # 422 오류를 냄
        if location is not None and location not in self._params.inlets:  # 모르는 빗물받이이면
            known = ", ".join(sorted(self._params.inlets))  # 있는 빗물받이 목록
            # 422 오류를 냄
            raise Fault(("location",), f"모르는 빗물받이: {location} (있는 것: {known})")
        if kind == "none":  # 막힘 없음이면
            return ("none", None)  # 위치 없이 반환
        if location is None:  # 막힘인데 위치가 없으면
            raise Fault(("location",), f"{kind} 막힘에는 location 이 필요하다")  # 422 오류를 냄
        return (kind, location)  # 종류와 위치를 반환

    # 입력원을 바꾼다. replay 는 그 기록을 처음부터 다시 돌린다
    def channel(self, mode: str, log_id: str | None = None) -> None:
        if mode not in ("sim", "replay", "live"):  # 모르는 입력원이면
            raise Fault(("mode",), f"모르는 입력원: {mode}")  # 422 오류를 냄
        if mode == "live":  # 실측 입력원이면
            raise Lack("live 입력원은 아직 구현되지 않았다")  # 아직 없는 기능이라 501 오류를 냄
        if mode == "sim":  # 시뮬레이션이면
            if self._replay is not None:  # 재생 중이었다면
                self.fallback()  # 재생을 떠나 대기 상태로 감
                self.renewal()  # 스냅샷을 새로 만듦
            return  # 끝냄
        if log_id is None:  # 재생인데 기록 ID 가 없으면
            raise Fault(("logId",), "replay 에는 logId 가 필요하다")  # 422 오류를 냄
        if self._replay is not None and log_id == self._experiment_id:  # 이미 재생 중인 기록이면
            return  # 그대로 둔다
        replay = self.tape(log_id)  # 기록을 읽어 재생 입력원을 만듦
        # 회차가 도는 중에 재생을 시작하려면
        if self._replay is None and self._run_state == "running":
            raise Conflict("회차가 도는 중에는 재생할 수 없다. 먼저 종료한다")  # 409 오류를 냄
        self.playback(replay)  # 재생으로 변환
        self.renewal()  # 스냅샷을 새로 만듦

    # 기록을 읽어 재생 입력원을 만든다(조작 값은 지금 구성으로 본다)
    def tape(self, log_id: str) -> Replay:
        if not EXPERIMENT_ID.fullmatch(log_id):  # 회차 ID 형식이 아니면
            raise Fault(("logId",), f"실험 ID 형식이 아니다: {log_id}")  # 422 오류를 냄
        try:  # 기록을 읽어 점검
            with shield():  # 입출력 오류는 503 으로
                # 기록 줄들로 재생 입력원을 만듦
                replay = Replay(self.experiment_log.records(log_id))
            if replay.experiment_id != log_id:  # meta 의 ID 가 요청과 다르면
                # 기록 형식 오류를 냄
                raise Flaw(f"meta 의 실험 ID {replay.experiment_id} 가 파일과 다르다")
            for command in replay.commands:  # 기록된 조작마다
                self.screen(command)  # 지금 구성으로 값을 확인
        except Absence:  # 그런 기록이 없으면
            # 422 오류로 바꿔 냄
            raise Fault(("logId",), f"그런 실험 기록이 없다: {log_id}") from None
        except Flaw as error:  # 기록 형식이 틀렸으면
            raise Fault(("logId",), f"재생할 수 없는 기록: {error}") from None  # 422 오류로 바꿔 냄
        return replay  # 재생 입력원을 반환

    # 기록된 조작 값이 지금 구성에서 뜻이 있는지 확인
    def screen(self, command: Command) -> None:
        try:  # 값을 검사
            if command.rain_mm_per_h is not None:  # 강우를 바꾼 조작이면
                self.rainfall(command.rain_mm_per_h)  # 강우 세기를 검사
            if command.blockage is not None:  # 막힘을 바꾼 조작이면
                self.jam(*command.blockage)  # 막힘 선택을 검사
        except Fault as error:  # 뜻이 없는 값이면
            # 몇 번째 줄인지 붙여 기록 오류로 냄
            raise Flaw(f"{command.line}번째 줄: {error.message}") from None

    # 기록의 처음에서 재생을 시작한다(시작 시각은 기록의 것)
    def playback(self, replay: Replay) -> None:
        replay.origin()  # 재생을 처음 위치로 돌린다
        self._replay = self.source = replay  # 재생 입력원을 기록
        self._data_source = "replay"  # 입력원 이름을 재생으로
        self._experiment_id = replay.experiment_id  # 기록의 회차 ID
        self._start_wall = replay.start_time  # 기록의 시작 시각
        self._t0 = self.clock.monotonic()  # 시작 기준 시계값
        self._ticks = 0  # tick 횟수를 0 으로
        self._state = baseline(self._params)  # 마른 상태에서 시작
        self._latest = {}  # 관측 기록을 비운다
        self._run_state = "running"  # 돌아가는 중으로
        self.progress()  # 0 초의 조작을 먼저 건다

    # 재생을 떠나 시뮬레이션 대기 상태로 돌아감
    def fallback(self) -> None:
        self._replay = None  # 재생을 끝냄
        self.source = self._default_source  # 원래 입력원으로
        self._data_source = "sim"  # 입력원 이름을 시뮬레이션으로
        self.rest()  # 대기 상태로 돌린다
        self._rain_mm = self._presets[DEFAULT_RAIN]  # 강우를 기본값으로
        self._blockage = ("none", None)  # 막힘을 없음으로

    # 재생이면 다음 tick 전에 기록된 조작을 건다. 기록의 끝이면 멈추고 False
    def progress(self) -> bool:
        if self._replay is None:  # 재생이 아니면
            return True  # 그대로 진행
        basis_s = self._ticks * self._period_s  # 지금까지 처리한 경과 초
        for command in self._replay.orders(basis_s):  # 그 시점까지 기록된 조작마다
            self.effect(command)  # 조작을 건다(원래도 다음 tick 부터 걸렸다)
        if basis_s < self._replay.end_s:  # 기록의 끝 전이면
            return True  # 진행
        self.halt()  # 기록의 끝이라 멈춘다
        return False  # 더 진행하지 않음

    # 기록된 강우·막힘을 건다(종료·초기화는 기록의 끝으로 반영된다)
    def effect(self, command: Command) -> None:
        if command.rain_mm_per_h is not None:  # 강우가 있으면
            self._rain_mm = command.rain_mm_per_h  # 강우를 변환
        if command.blockage is not None:  # 막힘이 있으면
            self._blockage = self.jam(*command.blockage)  # 막힘을 변환

    # 시계로 보아 밀린 tick 을 처리하고 처리한 수를 반환
    def catchup(self, limit: int | None = None) -> int:
        # 처리할 tick 수(상한이 있으면 그만큼만)
        due = self.backlog() if limit is None else min(self.backlog(), limit)
        for done in range(due):  # tick 마다
            try:  # 처리를 시도
                if not self.progress():  # 재생이 끝났으면
                    return done  # 여기까지 처리한 수를 반환
                self.tick()  # 한 주기를 계산하고 기록
            except Exception as error:  # 계산이나 기록이 실패하면
                log.exception(  # 서버 로그에 남김
                    # 회차 ID 와 실패한 tick 번호
                    "%s tick %d 처리 실패, 회차를 멈춘다", self._experiment_id, self._ticks + 1
                )
                self.failure(error)  # 회차 기록(event 줄)에 남김
                self.halt()  # 회차를 멈춘다(실패한 tick 은 반영하지 않는다)
                return done  # 여기까지 처리한 수를 반환
        return due  # 전부 처리했다

    # 실패한 tick 자리에 event 줄을 남긴다(쓰지 못하면 경고만)
    def failure(self, error: Exception) -> None:
        if self._replay is not None:  # 재생이면
            return  # 기록에 쓰지 않는다(서버 로그에는 남았다)
        record = event(  # event 줄을 만듦
            "calc_error",  # 사건 종류: 계산 오류
            (self._ticks + 1) * self._period_s,  # 실패한 tick 의 경과 초
            self.clock.now(),  # 지금 시각
            f"{type(error).__name__}: {error}",  # 오류 이름과 설명
        )
        try:  # 기록을 시도
            with shield():  # 입출력 오류는 503 으로
                self.experiment_log.entry(self._experiment_id, record)  # event 줄을 기록
        except Outage as write_error:  # 기록도 쓸 수 없으면
            # 경고만 남김
            log.warning("%s 계산 오류를 기록하지 못했다: %s", self._experiment_id, write_error)

    # 실패한 tick 뒤나 재생의 끝에서 멈춘다
    def halt(self) -> None:
        self._run_state = "stopped"  # 멈춤 상태로
        try:  # 멈춘 상태를 계산
            self.renewal()  # 스냅샷을 새로 만듦
        except Exception:  # 계산할 수 없으면
            # 서버 로그에 남김
            log.exception("%s 멈춘 상태를 계산하지 못해 마지막 상태를 둔다", self._experiment_id)
            # 마지막 상태에 멈춤만 표시
            self._snapshot = replace(self._snapshot, run_state="stopped", rain_on=False)

    # 다음 tick 까지 남은 시간(초). 돌고 있지 않으면 None
    def delay(self) -> float | None:
        if self._run_state != "running":  # 돌고 있지 않으면
            return None  # 기다릴 tick 이 없다
        due_at = self._t0 + (self._ticks + 1) * self._period_s  # 다음 tick 이 올 시각
        return max(0.0, due_at - self.clock.monotonic())  # 남은 시간(밀렸으면 0)

    # 시계로 보아 밀린 tick 수
    def backlog(self) -> int:
        if self._run_state != "running":  # 돌고 있지 않으면
            return 0  # 밀린 것이 없다
        elapsed = self.clock.monotonic() - self._t0  # 시작 후 지난 시간(초)
        # 지나야 할 tick 수에서 처리한 수를 제외
        return max(0, math.floor(elapsed / self._period_s + 1e-9) - self._ticks)

    # 한 주기를 계산하고 기록한다. 끝까지 성공해야 상태에 반영
    def tick(self) -> None:
        elapsed = (self._ticks + 1) * self._period_s  # 이번 tick 이 끝나는 경과 초
        cond = self.conditions  # 지금 걸린 강우·막힘
        received_at = self.clock.now()  # 받은 시각
        observations: list[dict] = []  # 이번 관측 기록 줄들
        readings: dict[str, float] = {}  # 유효한 관측 수위(m)
        for message in self.source.inbox(elapsed, cond):  # 입력원이 내준 메시지마다
            levels, drained_m3, quality = self.reading(message)  # 수위·배수량·품질로 변환
            observations.append(  # 관측 기록 줄을 모음
                # 관측 줄을 만듦
                observation(elapsed, received_at, message, levels, drained_m3, quality)
            )
            # 유효한 수위만 모음
            readings.update({z: h for z, h in levels.items() if h is not None})
        state = evolution(self._state, cond, self._params, self._period_s)  # 모델을 한 주기 진행
        corrections = ()  # 보정 내역(없으면 비어 있다)
        if readings:  # 유효한 관측이 있으면
            # 관측으로 저장량을 보결정
            state, corrections = adjustment(state, readings, self._gain, self._params)
        # 최근 관측을 갱신
        latest = {**self._latest, **{z: (h, elapsed) for z, h in readings.items()}}
        snapshot = self.capture(state, elapsed, latest)  # 스냅샷을 만듦
        record = frame(snapshot, state, corrections)  # 상태 줄을 만듦
        if self._replay is None:  # 재생이 아닐 때만 쓴다(재생도 줄은 만들어 계약을 검사)
            with shield():  # 입출력 오류는 503 으로
                for line in (*observations, record):  # obs 줄들과 state 줄을 한 tick 에 함께
                    # 줄을 쓴다(실패한 tick 에는 event 줄만 남는다)
                    self.experiment_log.entry(self._experiment_id, line)
        # 끝까지 성공했으니 상태에 반영
        self._state, self._latest, self._snapshot = state, latest, snapshot
        self._ticks += 1  # 처리한 tick 을 센다

    # 관측 메시지를 A·B 수위(m), 배수량(m³), 센서별 품질로 바꾼다. 무효는 None
    def reading(
        self, message: dict  # 받은 관측 메시지
    ) -> tuple[dict[str, float | None], float | None, dict[str, str]]:  # 수위, 배수량, 품질을 반환
        msg = Message.model_validate(message)  # 메시지 모양을 검증
        levels: dict[str, float | None] = {}  # 구역별 수위(m)
        quality: dict[str, str] = {}  # 센서별 품질
        for z in OBSERVED_ZONES:  # 관측하는 구역(A·B)마다
            distance = getattr(msg.readings, f"dist{z}_mm")  # 수면까지 거리(mm)
            level = None  # 기본은 무효
            # 값이 있고 센서가 정상이면
            if distance is not None and getattr(msg.sensorStatus, z) == "ok":
                level = waterline(distance, self._sensors[z])  # 거리를 수위로 변환
            levels[z] = level  # 구역의 수위를 적는다
            quality[z] = "invalid" if level is None else "valid"  # 수위가 없으면 무효
        weight = msg.readings.weight_g  # 배수 무게(g)
        drained_m3 = None  # 기본은 무효
        # 값이 있고 유한하고 센서가 정상이면
        if weight is not None and msg.sensorStatus.load == "ok" and math.isfinite(weight):
            drained_m3 = drainage(weight, self._load)  # 무게를 배수량으로 변환
        quality["load"] = "invalid" if drained_m3 is None else "valid"  # 배수량이 없으면 무효
        return levels, drained_m3, quality  # 해석한 결과를 반환

    # 스냅샷을 새로 만들어 표시값을 갱신
    def renewal(self) -> None:
        elapsed = self._ticks * self._period_s  # 처리한 tick 의 경과 초
        # 지금 상태로 스냅샷을 만듦
        self._snapshot = self.capture(self._state, elapsed, self._latest)

    # 상태와 경과 시간으로 스냅샷을 만듦
    def capture(
        # 상태, 경과 초, 구역별 최근 관측
        self, state: State, elapsed_s: float, latest: dict[str, tuple[float, float]]
    ) -> Snapshot:  # 스냅샷을 반환
        cond = self.conditions  # 지금 걸린 강우·막힘
        prediction = forecast(  # 예측을 계산
            state,  # 현재 상태
            cond,  # 유지된다고 가정할 조건
            self._params,  # 모델 계수
            basis_elapsed_s=elapsed_s,  # 예측 기준 경과 초
            horizons_s=self._horizons_s,  # 예측 구간(초)
            valid_for_s=self._valid_for_s,  # 예측 유효 시간(초)
        )
        flows = flux(state, cond, self._params)  # 현재 유량
        levels, sources = {}, {}  # 표시 수위와 출처
        for z in ZONES:  # 구역마다
            reading = latest.get(z)  # 최근 관측(수위 m, 받은 경과 초)
            # 관측이 있고 너무 오래되지 않았으면
            if reading is not None and elapsed_s - reading[1] <= self._max_age_s:
                # 관측 수위를 쓴다(음수는 0 으로)
                levels[z], sources[z] = max(0.0, reading[0]), OBSERVED_SOURCE[self._data_source]
            else:  # 아니면
                # 모델 수위를 쓰고 추정으로 표시
                levels[z], sources[z] = depth(z, state.V[z], self._params), "estimated"
        kind, location = self._blockage  # 막힘 종류와 위치
        return Snapshot(  # 스냅샷을 만듦
            experiment_id=self._experiment_id,  # 회차 ID
            run_state=self._run_state,  # 진행 상태
            data_source=self._data_source,  # 입력원
            timestamp=self._start_wall + timedelta(seconds=elapsed_s),  # 시작 시각 + 경과 시간
            elapsed_s=elapsed_s,  # 경과 시간(초)
            levels_m=levels,  # 표시 수위
            zone_sources=sources,  # 값의 출처
            rates_m_per_s=gradient(state, cond, self._params),  # 수위 변화율
            prediction=prediction,  # 예측 결과
            drained_m3=sum(state.drained_m3.values()),  # 누적 배수량
            drain_flow_m3s=sum(flows.drains_m3s.values()),  # 배수 유량
            # 회차가 돌고 비가 오면 켜짐
            rain_on=self._run_state == "running" and self._rain_mm > 0,
            rain_label=self.weather(),  # 강우 이름
            rain_mm_per_h=self._rain_mm,  # 선택한 강우
            blockage_type=kind,  # 막힘 종류
            blockage_location=location,  # 막힌 빗물받이
            blockage_label=self.outlet(),  # 막힘 이름
            devices=dict(SIM_DEVICES),  # 장치 상태
            quality="valid",  # 품질은 유효
        )

    # 화면에 보일 강우 이름
    def weather(self) -> str:
        if self._rain_mm == 0:  # 비가 없으면
            return "강우 없음"  # 강우 없음으로
        for name, mm in self._presets.items():  # 프리셋마다
            if self._rain_mm == mm:  # 세기가 같으면
                return RAIN_PRESET_LABELS[name]  # 프리셋 이름으로
        return f"직접 입력 {self._rain_mm:g} mm/h"  # 아니면 직접 입력으로

    # 화면에 보일 막힘 이름
    def outlet(self) -> str:
        kind, location = self._blockage  # 막힘 종류와 위치
        if kind == "none":  # 막힘이 없으면
            return "정상 배수"  # 정상 배수로
        return f"빗물받이 {numeral(location)} {BLOCKAGE_LABELS[kind]}"  # 번호와 막힘 이름을 붙임


@contextmanager  # with 문에서 쓰는 도구로 만듦
# 기록 입출력 오류를 Outage 로 바꾼다(기록 조회 API 도 쓴다)
def shield() -> Iterator[None]:
    try:  # 안쪽 코드를 실행
        yield  # with 안쪽을 여기서 실행
    except OSError as error:  # 입출력 오류가 나면
        # 이유만 남긴다(응답에 파일 경로를 내보내지 않는다)
        reason = error.strerror or type(error).__name__
        # 503 오류를 낸다(원래 오류는 __cause__ 에 남는다)
        raise Outage(f"실험 기록을 쓸 수 없다: {reason}") from error


# INLET-02 → ②. 번호를 읽을 수 없으면 ID 를 그대로 기록
def numeral(inlet_id: str) -> str:
    number = inlet_id.rpartition("-")[2]  # 마지막 번호 부분
    if number.isdecimal() and 1 <= int(number) <= 20:  # 1~20 번이면
        return chr(0x2460 + int(number) - 1)  # 동그라미 숫자로 변환
    return inlet_id  # 아니면 ID 를 그대로
