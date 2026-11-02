from __future__ import annotations

from app.core.model import Conditions
from collections import deque

KEEP = 120  # 받아 두는 메시지 수 상한(1 Hz 두 분). 넘치면 오래된 것부터 버림


# 실장치 입력원: /api/ingest 로 받은 메시지를 다음 tick 에 내보냄. 시각은 서비스가 봄
class Live:
    # 보관 상한을 받음
    def __init__(self, keep: int = KEEP) -> None:
        self._queue: deque[dict] = deque(maxlen=keep)

    # 새 회차를 시작. 그전에 받아 둔 메시지는 버림
    def origin(self) -> None:
        self._queue.clear()

    # 장치가 보낸 메시지를 받아 둠
    def admit(self, message: dict) -> None:
        self._queue.append(message)

    # 지난 tick 뒤에 받은 메시지를 받은 순서대로 모두 내보냄
    def inbox(self, elapsed_s: float, cond: Conditions) -> list[dict]:
        batch = list(self._queue)
        self._queue.clear()
        return batch
