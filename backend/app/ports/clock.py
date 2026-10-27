from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

KST = timezone(timedelta(hours=9), "KST")  # 한국 시간대(UTC+9)를 만듦


# 시계가 지킬 약속: 실시계와 가상 시계를 바꿔 끼운다
class Clock(Protocol):
    # tick 간격을 재는 초를 돌려준다(뒤로 가지 않는다)
    def monotonic(self) -> float:
        ...  # 본문은 비워 둔다

    # 한국 시각을 돌려준다(실험 시작 표시용)
    def now(self) -> datetime:
        ...  # 본문은 비워 둔다
