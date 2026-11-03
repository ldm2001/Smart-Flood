import hashlib
import hmac
import httpx
import json
import pytest
import socket
from app.adapters.solapi import URL, Keys, Refusal, Solapi, header, keys, missing, wire
from app.core.message import LIMIT
from datetime import datetime, timedelta, timezone

KEY = "TESTKEY" + "0" * 9  # 가짜 키(문서의 NCS 모양과 다름)
SECRET = "TESTSECRET" + "1" * 22  # 가짜 시크릿
SENDER = "0" + "2" + "9302266"  # 가짜 발신번호(조립)
TO = "010" + "1234" + "5678"  # 가짜 허용 번호(조립해 스캔에 안 걸림)
OTHER = "010" + "8765" + "4321"  # 허용 목록 밖 번호
SALT = "s" * 32  # 고정 salt
NOW = datetime(2026, 11, 3, 16, 30, 5, tzinfo=timezone(timedelta(hours=9)))  # 한국 시각


# 호출을 기록하고 정해 둔 상태(또는 예외)를 돌려주는 가짜 전송
class Fake:
    def __init__(self, status=200, error=None):
        self.status, self.error, self.calls = status, error, []

    def __call__(self, url, headers, content, timeout):
        self.calls.append((url, headers, content, timeout))
        if self.error is not None:
            raise self.error
        return self.status


# 가짜 전송을 끼운 발송기와 가짜 전송
def sender(status=200, error=None):
    fake = Fake(status, error)
    keys = Keys(KEY, SECRET, SENDER, (TO,))
    return Solapi(keys, post=fake, clock=lambda: NOW, salt=lambda: SALT), fake


# 비밀·번호가 글에 없는지 검사
def clean(words: str):
    for value in (KEY, SECRET, SENDER, TO, OTHER, TO[-8:], OTHER[-8:]):
        assert value not in words


# 머리글 형식과 서명(hmac 로 다시 계산)
def test_header():
    date = "2026-11-03T07:30:05Z"
    signature = hmac.new(SECRET.encode(), (date + SALT).encode(), hashlib.sha256).hexdigest()
    expected = f"HMAC-SHA256 apiKey={KEY}, date={date}, salt={SALT}, signature={signature}"
    assert header(KEY, SECRET, date, SALT) == expected
    assert len(signature) == 64


# 허용 번호 한 건: 주소·머리글·본문 JSON·제한 초
def test_send():
    solapi, fake = sender()
    solapi.send("010-" + "1234" + "-5678", "[SMARTFLOOD시연] 테스트 문자입니다 16:30")
    [(url, headers, content, timeout)] = fake.calls
    assert url == URL == "https://api.solapi.com/messages/v4/send-many/detail"
    assert timeout == 5.0
    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"] == header(KEY, SECRET, "2026-11-03T07:30:05Z", SALT)
    body = json.loads(content.decode("utf-8"))
    message = {"to": TO, "from": SENDER, "text": "[SMARTFLOOD시연] 테스트 문자입니다 16:30"}
    assert body == {"messages": [{**message, "type": "SMS", "autoTypeDetect": False}]}
    assert "시연".encode() in content  # ensure_ascii=False 라 한글 그대로


# 요청마다 새 salt 를 씀(기본 salt 는 32자 16진수)
def test_default_salt():
    fake = Fake()
    solapi = Solapi(Keys(KEY, SECRET, SENDER, (TO,)), post=fake, clock=lambda: NOW)
    solapi.send(TO, "a")
    solapi.send(TO, "b")
    salts = [h["Authorization"].split("salt=")[1].split(",")[0] for _, h, _, _ in fake.calls]
    assert salts[0] != salts[1] and all(len(s) == 32 for s in salts)


# 허용 목록 밖 번호는 HTTP 호출이 한 번도 없음
@pytest.mark.parametrize("to", [OTHER, "", "abc", TO + "0", TO[1:]])
def test_not_allowed(to):
    solapi, fake = sender()
    with pytest.raises(Refusal) as caught:
        solapi.send(to, "본문")
    assert fake.calls == []
    assert str(caught.value) == "허용 번호가 아니다"
    clean(str(caught.value))


# 90바이트를 넘거나 cp949 로 못 쓰는 본문은 HTTP 호출 없이 거절
@pytest.mark.parametrize("body", ["가" * 46, "A" * (LIMIT + 1), "홍수\U0001f30a"])
def test_bad_body(body):
    solapi, fake = sender()
    with pytest.raises(Refusal):
        solapi.send(TO, body)
    assert fake.calls == []


# 2xx 가 아니면 Refusal("HTTP 상태"), 재시도 없음
@pytest.mark.parametrize("status", [199, 300, 400, 401, 403, 500])
def test_status(status):
    solapi, fake = sender(status=status)
    with pytest.raises(Refusal) as caught:
        solapi.send(TO, "본문")
    assert str(caught.value) == f"HTTP {status}"
    assert len(fake.calls) == 1
    clean(str(caught.value))


# 2xx 는 성공
@pytest.mark.parametrize("status", [200, 201, 299])
def test_success(status):
    solapi, fake = sender(status=status)
    solapi.send(TO, "본문")
    assert len(fake.calls) == 1


# 전송 예외는 종류 이름만 담은 Refusal, 원 예외 글·연결 없음, 재시도 없음
def test_error():
    error = TimeoutError(f"boom {KEY} {SECRET} {TO}")
    solapi, fake = sender(error=error)
    with pytest.raises(Refusal) as caught:
        solapi.send(TO, "본문")
    assert str(caught.value) == "TimeoutError"
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert len(fake.calls) == 1
    clean(str(caught.value) + repr(caught.value))


# 환경 변수 읽기: 넷 다 있어야 함, 빈 값·공백·누락은 None, 쉼표 구분·빈 항목 버림
def test_keys():
    env = {
        "SOLAPI_API_KEY": f" {KEY} ",
        "SOLAPI_API_SECRET": SECRET,
        "SOLAPI_SENDER": "02-" + "930-" + "2266",
        "SMS_ALLOWED_TO": f" 010-{TO[3:7]}-{TO[7:]} , ,{OTHER},",
    }
    read = keys(env)
    assert read == Keys(KEY, SECRET, SENDER, (TO, OTHER))
    assert missing(env) == []
    for name in env:
        assert keys({**env, name: ""}) is None
        assert keys({**env, name: "   "}) is None
        assert keys({k: v for k, v in env.items() if k != name}) is None
        assert missing({**env, name: ""}) == [name]
    assert keys({**env, "SMS_ALLOWED_TO": " , ,"}) is None
    assert keys({}) is None


# repr·str 에 값이 안 보임
def test_keys_repr():
    shown = repr(Keys(KEY, SECRET, SENDER, (TO,))) + str(Keys(KEY, SECRET, SENDER, (TO,)))
    assert shown == "Keys()Keys()"
    clean(shown)


# 시험 중에는 바깥 연결·이름 풀이가 막힘(문서용 주소 192.0.2.1, 실제로 닿지 않는 곳)
def test_offline():
    from tests.conftest import Offline

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        with pytest.raises(Offline):
            sock.connect(("192.0.2.1", 443))
        with pytest.raises(Offline):
            sock.connect_ex(("192.0.2.1", 443))
    with pytest.raises(Offline):
        socket.getaddrinfo("example.invalid", 443)
    with pytest.raises(Offline):
        socket.gethostbyname("example.invalid")
    assert socket.getaddrinfo("127.0.0.1", 80)  # 같은 컴퓨터는 허용


# 기본 전송은 httpx 한 번. 시험에서는 닿지 않는 주소(.invalid)로도 이름 풀이에서 막힘
def test_default_post_offline():
    assert Solapi(Keys(KEY, SECRET, SENDER, (TO,))).post is wire
    with pytest.raises(httpx.ConnectError) as caught:
        wire("https://example.invalid/", {}, b"", 0.5)
    assert "차단" in str(caught.value)
