from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# 기본 알림: 보내지 않고 서버 로그에만 남김. 네트워크·파일 입출력 없음
class Stub:
    # 사건 글을 WARNING 으로 남김(uvicorn 기본 설정에서는 INFO 가 안 보임)
    def notice(self, event: dict) -> None:
        log.warning("알림(기록만): %s", event["message"])
