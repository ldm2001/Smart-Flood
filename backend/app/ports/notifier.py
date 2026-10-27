from __future__ import annotations

from typing import Protocol


# 알림이 지킬 약속: 재생 중에는 부르지 않음
class Notifier(Protocol):
    # 위험 단계 이벤트 하나를 알린다
    def notice(self, event: dict) -> None:
        ...  # 본문은 비워 둔다
