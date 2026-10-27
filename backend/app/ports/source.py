from __future__ import annotations

from app.core.model import Conditions
from typing import Protocol


# 관측 입력원이 지킬 약속: 가상 센서·재생·실센서가 같은 꼴
class Source(Protocol):
    # 새 실험 회차를 시작
    def origin(self) -> None:
        ...  # 본문은 비워 둔다

    # 해당 초까지 도착한 관측 메시지를 돌려준다(조건은 가상 센서만 쓴다)
    def inbox(self, elapsed_s: float, cond: Conditions) -> list[dict]:
        ...  # 본문은 비워 둔다
