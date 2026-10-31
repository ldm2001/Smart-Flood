from __future__ import annotations

import logging
from collections import deque

log = logging.getLogger(__name__)
KEEP = 120  # 받아 두는 사건 수 상한. 넘치면 오래된 것부터 버림


# 기본 알림: 보내지 않고 서버 로그에 남기며 최근 사건을 받아 둠. 네트워크·파일 입출력 없음
class Stub:
    # 보관 상한을 받음
    def __init__(self, keep: int = KEEP) -> None:
        self.events: deque[dict] = deque(maxlen=keep)

    # 사건 하나를 받아 둠
    def notice(self, event: dict) -> None:
        self.events.append(event)
        log.info("알림(기록만): %s", event["message"])
