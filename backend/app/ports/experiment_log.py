from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Protocol

EXPERIMENT_ID = re.compile(r"EXP-([0-9]{8})-([0-9]{3,})")  # 아스키 숫자만, EXP-STANDBY 제외


# 그런 회차 기록이 없을 때의 오류
class Absence(LookupError):
    pass


# 기록 한 줄을 읽을 수 없을 때의 오류
class Flaw(ValueError):
    pass


# 실험 기록이 지킬 약속: 쓰기·목록·읽기
class Journal(Protocol):
    # 회차 기록 끝에 한 건을 붙임(앞 내용은 건드리지 않음)
    def entry(self, experiment_id: str, record: dict) -> None:
        ...

    # 회차 기록 끝에 여러 건을 붙임(다 쓰이거나 하나도 안 쓰임)
    def batch(self, experiment_id: str, records: list[dict]) -> None:
        ...

    # 기록이 있는 회차 ID 를 날짜·번호 순으로 반환
    def index(self) -> list[str]:
        ...

    # 회차 기록을 앞에서부터 돌려줌(없으면 Absence, 깨진 줄은 Flaw)
    def records(self, experiment_id: str) -> Iterator[dict]:
        ...
