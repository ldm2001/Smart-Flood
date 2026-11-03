from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


# 알림이 지킬 약속: 재생 중에는 부르지 않음. 예외를 내도 회차는 이어 감(서버가 종류만 기록)
class Notifier(Protocol):
    # 위험 단계 이벤트 하나를 알림
    def notice(self, event: dict) -> None:
        ...


# 시험 문자를 더 보낼 수 없음(무장 해제·횟수 다 씀). 글은 평서 이유
class Spent(RuntimeError):
    pass


@runtime_checkable  # isinstance 로 무장할 수 있는 알림인지 봄
# 실제 발송을 무장·해제하고 시험 문자를 보내는 알림의 약속. 없으면 stub·해제로 봄
class Switch(Protocol):
    mode: str  # 발송 방식: stub · sms
    armed: bool  # 실제 발송 무장 여부(서버를 켜면 false)
    ready: bool  # 발송 환경 변수가 다 있는지

    # 무장·해제
    def arm(self, on: bool) -> None:
        ...

    # 시험 문자 한 건을 바로 보내고 (가린 번호, 본문)을 돌려줌. 못 보내면 Spent
    def trial(self, at: datetime) -> tuple[str, str]:
        ...
