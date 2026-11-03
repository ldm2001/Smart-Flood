# 수동 시험 발송. backend 폴더에서 python3 scripts/sms.py (보내지 않고 문안만)
# --send 면 한 건 보냄. config.yaml 의 notifier.mode 가 sms 가 아니면 보내지 않음
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # app 을 가져오려고 backend 를 넣음

from app.adapters.solapi import Refusal, Solapi, keys, missing  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.message import mask, size, trial  # noqa: E402

EPILOG = "환경 변수 불러오기 예: set -a && . ./.env && set +a"  # 도움말 끝 안내


# 명령 인자 해석기
def parser() -> argparse.ArgumentParser:
    found = argparse.ArgumentParser(
        description="SOLAPI 시험 문자 한 건. 기본은 문안과 가린 번호만 출력",
        epilog=EPILOG,
    )
    found.add_argument(
        "--send", action="store_true", help="첫 허용 번호로 실제 한 건 발송(mode 가 sms 일 때만)"
    )
    return found


# 진입점. 0 성공, 1 발송 거절, 2 설정 없음·mode 가 sms 아님
def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    absent = missing(os.environ)
    read = keys(os.environ)
    if absent or read is None:
        names = ", ".join(absent) or "SOLAPI_SENDER 또는 SMS_ALLOWED_TO(숫자 없음)"
        print(f"설정 없음: {names}")  # 이름만, 값은 안 찍음
        return 2
    to = read.allowed[0]
    body = trial(datetime.now().astimezone())  # 이 컴퓨터 시간대 기준 HH:MM
    print(f"받는 번호: {mask(to)}")
    print(f"문안({size(body)}바이트): {body}")
    if not args.send:
        print("보내지 않음(--send 를 주면 한 건 발송)")
        return 0
    if settings()["notifier"]["mode"] != "sms":
        print("보내지 않음: config.yaml 의 notifier.mode 가 sms 가 아님")
        return 2
    try:
        Solapi(read).send(to, body)
    except Refusal as refusal:
        print(f"못 보냄: {refusal}")  # Refusal 글에는 키·번호가 없음
        return 1
    print("보냄(SOLAPI 접수)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
