import importlib.util
import pytest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "sms.py"  # 수동 발송 스크립트
TO = "010" + "1234" + "5678"  # 가짜 허용 번호(조립해 스캔에 안 걸림)
SENDER = "010" + "0000" + "0000"  # 가짜 발신번호
ENV = {"SOLAPI_API_KEY": "key", "SOLAPI_API_SECRET": "secret", "SOLAPI_SENDER": SENDER}  # 가짜 값


# Solapi 대신. send(to, body) 의 번호만 모음
class Phone:
    def __init__(self, sent: list[str]) -> None:
        self.sent = sent

    def send(self, to: str, body: str) -> None:
        self.sent.append(to)


# scripts/sms.py 를 모듈로 읽음. 환경 변수는 가짜 값, 발송은 받은 번호만 sent 에 모음
@pytest.fixture
def sms(monkeypatch):
    spec = importlib.util.spec_from_file_location("sms", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {**ENV, "SMS_ALLOWED_TO": TO}.items():
        monkeypatch.setenv(name, value)
    module.sent = []  # 보낸 번호
    monkeypatch.setattr(module, "Solapi", lambda keys: Phone(module.sent))
    return module


# config.yaml 의 notifier.mode 를 바꿈
def mode(monkeypatch, module, value: str) -> None:
    monkeypatch.setattr(module, "settings", lambda: {"notifier": {"mode": value}})


# --send 가 없으면 mode 와 관계없이 보내지 않음
def test_preview(sms, monkeypatch):
    mode(monkeypatch, sms, "sms")
    assert sms.main([]) == 0
    assert sms.sent == []


# mode 가 stub 이면 --send 여도 보내지 않고 2
def test_stub(sms, monkeypatch, capsys):
    mode(monkeypatch, sms, "stub")
    assert sms.main(["--send"]) == 2
    assert sms.sent == []
    assert "notifier.mode 가 sms 가 아님" in capsys.readouterr().out


# mode 가 sms 이고 --send 면 첫 허용 번호로 한 건. 출력에는 가린 번호만
def test_send(sms, monkeypatch, capsys):
    mode(monkeypatch, sms, "sms")
    assert sms.main(["--send"]) == 0
    assert sms.sent == [TO]
    assert TO not in capsys.readouterr().out


# 환경 변수가 없으면 이름만 찍고 2
def test_absent(sms, monkeypatch, capsys):
    mode(monkeypatch, sms, "sms")
    monkeypatch.delenv("SOLAPI_API_SECRET")
    assert sms.main(["--send"]) == 2
    assert sms.sent == []
    assert "SOLAPI_API_SECRET" in capsys.readouterr().out
