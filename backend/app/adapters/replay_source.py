from __future__ import annotations

import math
from app.core.model import Conditions
from app.ports.clock import KST
from app.ports.experiment_log import Flaw
from app.schemas import LOG_VERSION, Message
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pydantic import ValidationError

COMMAND_KINDS = ("start", "rain", "blockage", "stop", "reset")
ENDING_KINDS = ("stop", "reset")
TIMED_TYPES = ("cmd", "obs", "state")  # 경과 초가 줄지 않는 줄. 나머지(event 등)는 건너뜀


@dataclass(frozen=True)
# 기록된 조작 한 건. 적용 시각 다음 tick 부터 걸림
class Command:
    line: int  # 기록의 몇 번째 줄인지. meta 가 1
    kind: str  # 조작 종류
    elapsed_s: float  # 적용 시각(경과 초)
    rain_mm_per_h: float | None = None  # 강우(mm/h). 해당 없으면 None
    blockage: tuple[str, str | None] | None = None  # 막힘(종류, 위치). 해당 없으면 None


# 재생 입력원: 기록 한 회차의 관측·조작을 시각에 맞춰 다시 내보냄
class Replay:
    # 기록 줄들로 만듦. 읽을 수 없으면 Flaw(줄 번호가 앞에 붙음)
    def __init__(self, records: Iterable[dict]) -> None:
        observations: list[tuple[float, dict]] = []  # (시각, 관측 원문) 목록
        commands: list[Command] = []
        latest_s = last_state_s = 0.0  # 가장 최근 경과 초, 마지막 state 줄의 경과 초
        line = 0  # 줄 번호(빈 기록이면 0)
        for line, record in enumerate(records, start=1):
            kind = record.get("type")
            if line == 1:
                self.meta(record)
                continue
            if kind == "meta":
                raise defect(line, "meta 줄이 또 있다")
            if kind not in TIMED_TYPES:  # 시각이 붙는 줄(cmd·obs·state)이 아니면
                continue
            latest_s = seconds(line, record, latest_s)  # 경과 초를 읽음(줄어들면 오류)
            if kind == "cmd":
                # 조작을 모음(첫 조작은 0 초 start 여야 함)
                commands.append(order(line, record, latest_s, first=not commands))
            elif kind == "obs":
                observations.append((latest_s, payload(line, record)))  # (시각, 원문)을 모음
            else:
                last_state_s = latest_s
        if line == 0:
            raise Flaw("기록이 비어 있다")
        if not commands:
            raise Flaw("기록에 start 조작이 없다")
        self.commands = tuple(commands)  # 조작을 바꿀 수 없는 묶음으로 굳힘
        ending = next((c.elapsed_s for c in commands if c.kind in ENDING_KINDS), None)
        self.end_s = last_state_s if ending is None else ending  # 종료 조작 없으면 마지막 state
        self._observations = observations
        self.origin()

    # 첫 줄(meta)을 읽어 실험 ID 와 시작 시각을 얻음
    def meta(self, record: dict) -> None:
        if record.get("type") != "meta":
            raise defect(1, "첫 줄이 meta 가 아니다")
        version = record.get("logVersion")
        if version != LOG_VERSION:
            raise defect(1, f"기록 형식 {version!r} 판은 읽을 수 없다 (읽는 판: {LOG_VERSION})")
        experiment_id = record.get("experimentId")
        if not isinstance(experiment_id, str):
            raise defect(1, f"experimentId 가 글자가 아니다: {experiment_id!r}")
        start_time = record.get("startTime")  # 시작 시각(글자)
        try:
            parsed = datetime.fromisoformat(start_time)
        except (TypeError, ValueError):
            raise defect(1, f"startTime 이 ISO 8601 시각이 아니다: {start_time!r}") from None
        if parsed.utcoffset() is None:
            raise defect(1, f"startTime 에 시간대가 없다: {start_time!r}")
        try:
            moment = parsed.astimezone(KST)
        except OverflowError:  # 바꿀 수 없을 만큼 이르거나 늦으면
            raise defect(1, f"startTime 을 KST 로 바꿀 수 없다: {start_time!r}") from None
        self.experiment_id = experiment_id
        self.start_time = moment

    # 기록의 처음으로 돌아감
    def origin(self) -> None:
        self._obs_done = 0
        self._commands_done = 0

    # 경과 초까지 기록된 관측 중 아직 안 내보낸 것(cond 는 안 씀)
    def inbox(self, elapsed_s: float, cond: Conditions) -> list[dict]:
        due = []
        while self._obs_done < len(self._observations):
            obs_s, raw = self._observations[self._obs_done]
            if obs_s > elapsed_s:
                break
            due.append(raw)
            self._obs_done += 1
        return due

    # 적용 시각이 경과 초까지인 조작 중 아직 안 내보낸 것
    def orders(self, elapsed_s: float) -> list[Command]:
        due = []
        while self._commands_done < len(self.commands):
            command = self.commands[self._commands_done]
            if command.elapsed_s > elapsed_s:
                break
            due.append(command)
            self._commands_done += 1
        return due


# 줄 번호를 앞에 붙인 오류를 만듦
def defect(line: int, reason: str) -> Flaw:
    return Flaw(f"{line}번째 줄: {reason}")  # "몇 번째 줄: 이유" 꼴


# 유한한 JSON 숫자인가. 불리언·글자("nan" 등)는 숫자가 아님
def number(value) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # 실수로 담을 수 없을 만큼 큰 정수면
        return False


# 줄의 경과 초를 읽음. 앞 줄보다 작으면 오류
def seconds(line: int, record: dict, previous_s: float) -> float:
    value = record.get("elapsedSec")
    if not (number(value) and value >= 0):
        raise defect(line, f"elapsedSec 가 0 이상의 숫자가 아니다: {value!r}")
    if value < previous_s:
        raise defect(line, f"elapsedSec {value!r} 가 앞 줄의 {previous_s!r} 보다 작다")
    return float(value)


# cmd 줄을 조작으로 읽음. 모양만 봄(강우 범위 등은 서비스가 봄)
def order(line: int, record: dict, elapsed_s: float, *, first: bool) -> Command:
    kind = record.get("kind")
    if kind not in COMMAND_KINDS:
        raise defect(line, f"모르는 조작: {kind!r}")
    if first and not (kind == "start" and elapsed_s == 0):  # 첫 조작이 0 초의 start 가 아니면
        raise defect(line, f"첫 조작이 0 초의 start 가 아니다: {kind} {elapsed_s:g} s")
    rain_mm_per_h = blockage = None
    if kind in ("start", "rain"):
        value = record.get("rainMmPerHour")
        if not number(value):
            raise defect(line, f"{kind} 의 rainMmPerHour 가 숫자가 아니다: {value!r}")
        rain_mm_per_h = float(value)
    if kind in ("start", "blockage"):
        blockage = plug(line, kind, record.get("blockage"))
    return Command(line, kind, elapsed_s, rain_mm_per_h, blockage)


# 막힘 값(종류, 위치)을 읽음
def plug(line: int, kind: str, value) -> tuple[str, str | None]:
    if not isinstance(value, dict):
        raise defect(line, f"{kind} 의 blockage 가 객체가 아니다: {value!r}")
    blockage_type, location = value.get("type"), value.get("location")
    if not (isinstance(blockage_type, str) and (location is None or isinstance(location, str))):
        raise defect(line, f"{kind} 의 blockage 를 읽을 수 없다: {value!r}")
    return blockage_type, location  # (종류, 위치)를 반환


# obs 줄의 관측 원문. ingest 형식인지 보고 원문 그대로 반환
def payload(line: int, record: dict) -> dict:
    raw = record.get("raw")
    if not isinstance(raw, dict):
        raise defect(line, "obs 줄에 관측 원문(raw)이 없다")
    try:
        Message.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise defect(line, f"관측 원문을 읽을 수 없다: {where} {first['msg']}") from None
    return raw  # 원문 그대로 반환
