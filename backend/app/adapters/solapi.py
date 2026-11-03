from __future__ import annotations

import hashlib
import hmac
import httpx
import json
import secrets
from app.core.message import LIMIT, digits, size
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

# 발송 주소. 공식 문서(solapi.com/developers/api/messages)의 현행 발송 API, 한 건도 이 주소
URL = "https://api.solapi.com/messages/v4/send-many/detail"
NAMES = ("SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER", "SMS_ALLOWED_TO")  # 환경 변수
STAMP = "%Y-%m-%dT%H:%M:%SZ"  # 서명 시각 형식(ISO 8601 UTC, 문서 예시와 같은 모양)

Post = Callable[[str, dict[str, str], bytes, float], int]  # (주소, 머리글, 본문, 제한 초) → 상태


# SOLAPI 접속 정보. 값이 repr·로그에 안 보이게 모든 필드 repr=False. 번호는 숫자만
@dataclass(frozen=True)
class Keys:
    key: str = field(repr=False)
    secret: str = field(repr=False)
    sender: str = field(repr=False)
    allowed: tuple[str, ...] = field(repr=False)  # 허용 수신번호들


# 보내지 못함. 글에는 키·번호 없이 사유만
class Refusal(Exception):
    pass


# 비었거나 없는 환경 변수 이름 목록(값은 안 봄)
def missing(environ: Mapping[str, str]) -> list[str]:
    return [name for name in NAMES if not environ.get(name, "").strip()]


# 환경 변수에서 접속 정보를 읽음. 넷 중 하나라도 없거나 비면 None. 허용 번호는 쉼표 구분
def keys(environ: Mapping[str, str]) -> Keys | None:
    if missing(environ):
        return None
    key, secret, sender, listed = (environ[name].strip() for name in NAMES)
    allowed = tuple(d for d in (digits(part.strip()) for part in listed.split(",")) if d)
    if not allowed or not digits(sender):  # 숫자가 하나도 없으면 빈 값과 같음
        return None
    return Keys(key, secret, digits(sender), allowed)


# Authorization 머리글. 서명은 secret 을 열쇠로 한 date+salt 의 HMAC-SHA256 16진수
def header(key: str, secret: str, date: str, salt: str) -> str:
    signature = hmac.new(secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    return f"HMAC-SHA256 apiKey={key}, date={date}, salt={salt}, signature={signature}"


# 기본 전송: httpx 로 한 번 POST 하고 상태 코드만 돌려줌. 재시도·리다이렉트 없음
def wire(url: str, headers: dict[str, str], content: bytes, timeout: float) -> int:
    return httpx.post(url, headers=headers, content=content, timeout=timeout).status_code


# UTC 지금 시각
def utc() -> datetime:
    return datetime.now(UTC)


# 요청마다 새 salt(32자, 문서 조건 12~64바이트)
def nonce() -> str:
    return secrets.token_hex(16)


# SOLAPI 단문 발송기. 허용 번호에만, 요청은 한 번만(중복 발송 방지로 재시도 없음)
class Solapi:
    def __init__(
        self,
        keys: Keys,
        post: Post | None = None,
        timeout_s: float = 5.0,
        clock: Callable[[], datetime] | None = None,
        salt: Callable[[], str] | None = None,
    ) -> None:
        self.keys = keys
        self.post = post or wire
        self.timeout_s = timeout_s
        self.clock = clock or utc
        self.salt = salt or nonce

    # 한 건 발송. 허용 번호가 아니거나, 길거나, 실패하면 Refusal
    def send(self, to: str, body: str) -> None:
        number = digits(to)
        if number not in self.keys.allowed:  # HTTP 호출 전에 거름
            raise Refusal("허용 번호가 아니다")
        try:
            length = size(body)
        except UnicodeEncodeError:
            raise Refusal("cp949 로 쓸 수 없는 글자가 있다") from None
        if length > LIMIT:
            raise Refusal(f"본문이 {LIMIT}바이트를 넘는다({length}바이트)")
        date = self.clock().astimezone(UTC).strftime(STAMP)
        headers = {
            "Authorization": header(self.keys.key, self.keys.secret, date, self.salt()),
            "Content-Type": "application/json",
        }
        message = {"to": number, "from": self.keys.sender, "text": body, "type": "SMS"}
        message["autoTypeDetect"] = False  # 90바이트 단문으로만(장문 자동 전환 없음)
        content = json.dumps({"messages": [message]}, ensure_ascii=False).encode("utf-8")
        try:
            status = self.post(URL, headers, content, self.timeout_s)
        except Exception as error:  # 원 예외 글에는 주소·값이 섞일 수 있어 종류 이름만
            raise Refusal(type(error).__name__) from None
        if not 200 <= status < 300:
            raise Refusal(f"HTTP {status}")
