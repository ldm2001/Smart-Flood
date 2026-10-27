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

COMMAND_KINDS = ("start", "rain", "blockage", "stop", "reset")  # 알려진 조작 종류
ENDING_KINDS = ("stop", "reset")  # 재생을 끝내는 조작
TIMED_TYPES = ("cmd", "obs", "state")  # 경과 초가 줄지 않는 줄. 나머지(event 등)는 건너뛴다


@dataclass(frozen=True)  # 바꿀 수 없는 값 묶음
# 기록된 조작 한 건. 적용 시각 다음 tick 부터 걸림
class Command:
    line: int  # 기록의 몇 번째 줄인지. meta 가 1 이다
    kind: str  # 조작 종류
    elapsed_s: float  # 적용 시각(경과 초)
    rain_mm_per_h: float | None = None  # 강우(mm/h). 해당 없으면 None
    blockage: tuple[str, str | None] | None = None  # 막힘(종류, 위치). 해당 없으면 None


# 재생 입력원: 기록 한 회차의 관측·조작을 시각에 맞춰 다시 내전송
class Replay:
    # 기록 줄들로 만든다. 읽을 수 없으면 Flaw(줄 번호가 앞에 붙는다)
    def __init__(self, records: Iterable[dict]) -> None:
        observations: list[tuple[float, dict]] = []  # (시각, 관측 원문) 목록
        commands: list[Command] = []  # 조작 목록
        latest_s = last_state_s = 0.0  # 가장 최근 경과 초, 마지막 state 줄의 경과 초
        line = 0  # 줄 번호(빈 기록이면 0)
        for line, record in enumerate(records, start=1):  # 기록을 1 번 줄부터 읽음
            kind = record.get("type")  # 줄 종류
            if line == 1:  # 첫 줄은
                self.meta(record)  # meta 로 읽음
                continue  # 다음 줄로
            if kind == "meta":  # meta 가 또 나오면
                raise defect(line, "meta 줄이 또 있다")  # 오류를 냄
            if kind not in TIMED_TYPES:  # 시각이 붙는 줄(cmd·obs·state)이 아니면
                continue  # 건너뛴다
            latest_s = seconds(line, record, latest_s)  # 경과 초를 읽는다(줄어들면 오류)
            if kind == "cmd":  # 조작 줄이면
                # 조작을 모은다(첫 조작은 0 초 start 여야 함)
                commands.append(order(line, record, latest_s, first=not commands))
            elif kind == "obs":  # 관측 줄이면
                observations.append((latest_s, payload(line, record)))  # (시각, 원문)을 모음
            else:  # 그 밖에는 state 줄이다
                last_state_s = latest_s  # 재생이 끝나는 시각만 결정
        if line == 0:  # 줄이 하나도 없으면
            raise Flaw("기록이 비어 있다")  # 오류를 냄
        if not commands:  # 조작이 없으면
            raise Flaw("기록에 start 조작이 없다")  # 오류를 냄
        self.commands = tuple(commands)  # 조작을 바꿀 수 없는 묶음으로 굳힌다
        # 첫 종료·초기화 조작의 시각(없으면 None)
        ending = next((c.elapsed_s for c in commands if c.kind in ENDING_KINDS), None)
        # 재생이 멈출 시각. 종료 조작이 없으면 마지막 state(없으면 0)
        self.end_s = last_state_s if ending is None else ending
        self._observations = observations  # 관측 목록을 보관
        self.origin()  # 재생 위치를 처음으로 돌린다

    # 첫 줄(meta)을 읽어 실험 ID 와 시작 시각을 얻음
    def meta(self, record: dict) -> None:
        if record.get("type") != "meta":  # meta 가 아니면
            raise defect(1, "첫 줄이 meta 가 아니다")  # 오류를 냄
        version = record.get("logVersion")  # 기록 형식 판
        if version != LOG_VERSION:  # 읽는 판과 다르면
            # 오류를 냄
            raise defect(1, f"기록 형식 {version!r} 판은 읽을 수 없다 (읽는 판: {LOG_VERSION})")
        experiment_id = record.get("experimentId")  # 실험 ID
        if not isinstance(experiment_id, str):  # 글자가 아니면
            raise defect(1, f"experimentId 가 글자가 아니다: {experiment_id!r}")  # 오류를 냄
        start_time = record.get("startTime")  # 시작 시각(글자)
        try:  # ISO 8601 로 읽어 확인
            parsed = datetime.fromisoformat(start_time)  # 시각으로 변환
        except (TypeError, ValueError):  # 읽을 수 없으면
            # 오류를 냄
            raise defect(1, f"startTime 이 ISO 8601 시각이 아니다: {start_time!r}") from None
        if parsed.utcoffset() is None:  # 시간대가 없으면
            raise defect(1, f"startTime 에 시간대가 없다: {start_time!r}")  # 오류를 냄
        try:  # 시작 시각을 KST 로 맞춤
            moment = parsed.astimezone(KST)  # 시간대를 KST 로 변환
        except OverflowError:  # 바꿀 수 없을 만큼 이르거나 늦으면
            # 오류를 냄
            raise defect(1, f"startTime 을 KST 로 바꿀 수 없다: {start_time!r}") from None
        self.experiment_id = experiment_id  # 실험 ID 를 보관
        self.start_time = moment  # 시작 시각을 보관

    # 기록의 처음으로 돌아감
    def origin(self) -> None:
        self._obs_done = 0  # 내보낸 관측 수를 0 으로
        self._commands_done = 0  # 내보낸 조작 수를 0 으로

    # 경과 초까지 기록된 관측 중 아직 안 내보낸 것(cond 는 안 쓴다)
    def inbox(self, elapsed_s: float, cond: Conditions) -> list[dict]:
        due = []  # 이번에 내보낼 관측
        while self._obs_done < len(self._observations):  # 남은 관측이 있는 동안
            obs_s, raw = self._observations[self._obs_done]  # 다음 관측의 시각과 원문
            if obs_s > elapsed_s:  # 아직 때가 아니면
                break  # 멈춘다
            due.append(raw)  # 내보낼 목록에 담는다
            self._obs_done += 1  # 내보낸 수를 하나 올림
        return due  # 내보낼 관측을 반환

    # 적용 시각이 경과 초까지인 조작 중 아직 안 내보낸 것
    def orders(self, elapsed_s: float) -> list[Command]:
        due = []  # 이번에 내보낼 조작
        while self._commands_done < len(self.commands):  # 남은 조작이 있는 동안
            command = self.commands[self._commands_done]  # 다음 조작
            if command.elapsed_s > elapsed_s:  # 아직 때가 아니면
                break  # 멈춘다
            due.append(command)  # 내보낼 목록에 담는다
            self._commands_done += 1  # 내보낸 수를 하나 올림
        return due  # 내보낼 조작을 반환


# 줄 번호를 앞에 붙인 오류를 만듦
def defect(line: int, reason: str) -> Flaw:
    return Flaw(f"{line}번째 줄: {reason}")  # "몇 번째 줄: 이유" 꼴


# 유한한 JSON 숫자인가. 불리언·글자("nan" 등)는 숫자가 아니다
def number(value) -> bool:
    # 정수나 실수가 아니거나 불리언이면
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False  # 숫자가 아니다
    try:  # 실수로 바꿀 수 있어야 유한한지 볼 수 있다
        return math.isfinite(value)  # 유한한지 확인
    except OverflowError:  # 실수로 담을 수 없을 만큼 큰 정수면
        return False  # 유한하지 않다고 확인


# 줄의 경과 초를 읽는다. 앞 줄보다 작으면 오류
def seconds(line: int, record: dict, previous_s: float) -> float:
    value = record.get("elapsedSec")  # 경과 초 값
    if not (number(value) and value >= 0):  # 0 이상의 숫자가 아니면
        raise defect(line, f"elapsedSec 가 0 이상의 숫자가 아니다: {value!r}")  # 오류를 냄
    if value < previous_s:  # 앞 줄보다 작으면
        raise defect(line, f"elapsedSec {value!r} 가 앞 줄의 {previous_s!r} 보다 작다")  # 오류를 냄
    return float(value)  # 실수로 반환


# cmd 줄을 조작으로 읽는다. 모양만 본다(강우 범위 등은 서비스가 본다)
def order(line: int, record: dict, elapsed_s: float, *, first: bool) -> Command:
    kind = record.get("kind")  # 조작 종류
    if kind not in COMMAND_KINDS:  # 모르는 종류면
        raise defect(line, f"모르는 조작: {kind!r}")  # 오류를 냄
    if first and not (kind == "start" and elapsed_s == 0):  # 첫 조작이 0 초의 start 가 아니면
        raise defect(line, f"첫 조작이 0 초의 start 가 아니다: {kind} {elapsed_s:g} s")  # 오류를 냄
    rain_mm_per_h = blockage = None  # 강우·막힘은 기본 없음
    if kind in ("start", "rain"):  # start·rain 이면
        value = record.get("rainMmPerHour")  # 강우 값을 읽음
        if not number(value):  # 숫자가 아니면
            raise defect(line, f"{kind} 의 rainMmPerHour 가 숫자가 아니다: {value!r}")  # 오류를 냄
        rain_mm_per_h = float(value)  # 실수로 변환
    if kind in ("start", "blockage"):  # start·blockage 이면
        blockage = plug(line, kind, record.get("blockage"))  # 막힘을 읽음
    return Command(line, kind, elapsed_s, rain_mm_per_h, blockage)  # 조작 한 건을 만들어 반환


# 막힘 값(종류, 위치)을 읽음
def plug(line: int, kind: str, value) -> tuple[str, str | None]:
    if not isinstance(value, dict):  # 객체가 아니면
        raise defect(line, f"{kind} 의 blockage 가 객체가 아니다: {value!r}")  # 오류를 냄
    blockage_type, location = value.get("type"), value.get("location")  # 종류와 위치
    # 종류는 글자, 위치는 글자 또는 없음이어야 함
    if not (isinstance(blockage_type, str) and (location is None or isinstance(location, str))):
        raise defect(line, f"{kind} 의 blockage 를 읽을 수 없다: {value!r}")  # 아니면 오류를 냄
    return blockage_type, location  # (종류, 위치)를 반환


# obs 줄의 관측 원문. ingest 형식인지 보고 원문 그대로 반환
def payload(line: int, record: dict) -> dict:
    raw = record.get("raw")  # 원문
    if not isinstance(raw, dict):  # 객체가 아니면
        raise defect(line, "obs 줄에 관측 원문(raw)이 없다")  # 오류를 냄
    try:  # ingest 형식인지 검사
        Message.model_validate(raw)  # 메시지 모양으로 읽어 확인
    except ValidationError as error:  # 맞지 않으면
        first = error.errors()[0]  # 첫 오류를 꺼냄
        where = ".".join(str(part) for part in first["loc"])  # 오류 위치를 점으로 이어 기록
        # 위치와 이유로 오류를 냄
        raise defect(line, f"관측 원문을 읽을 수 없다: {where} {first['msg']}") from None
    return raw  # 원문 그대로 반환
