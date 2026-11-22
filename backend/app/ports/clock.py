from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

KST = timezone(timedelta(hours=9), "KST")  # 한국 시간대(UTC+9)를 만듦


# 시계가 지킬 약속: 실시계와 가상 시계를 바꿔 끼움
class Clock(Protocol):
    # tick 간격을 재는 초를 돌려줌(뒤로 가지 않음)
    def monotonic(self) -> float:
        ...

    # 한국 시각을 돌려줌(실험 시작 표시용)
    def now(self) -> datetime:
        ...
