import importlib
import json
import pytest
import sys
import time
import types

# main.py(보드 층)를 CPython 에서 돌리는 시험. machine·network·secret 을 가짜 모듈로 끼우고
# time.ticks_*·sleep_ms 는 가짜 시계로 바꿈. 전송은 client.send 를 기록 함수로 바꿔 받음


# 가짜 핀: 설정만 기록하고, 출력(value)이 불리면 실패
class Pin:
    IN = "in"
    OUT = "out"
    PULL_UP = "pull_up"
    made = []

    def __init__(self, number, mode=None, pull=None):
        Pin.made.append((number, mode, pull))

    def value(self, *args):
        raise AssertionError("핀 출력이 있었음: " + repr(args))


# 가짜 ADC: 491.52 mV → 수위 40 mm → distA 560.0
class ADC:
    ATTN_11DB = 3

    def __init__(self, pin):
        pass

    def atten(self, level):
        pass

    def read_uv(self):
        return 491520


# 가짜 감시 타이머: 만든 것과 먹인 횟수 기록
class WDT:
    made = []

    def __init__(self, timeout):
        self.timeout = timeout
        self.fed = 0
        WDT.made.append(self)

    def feed(self):
        self.fed += 1


# 가짜 WLAN: connect 가 바로 붙음. error 면 connect 가 그 예외를 내고, stuck 이면 영영 붙지 않음
class WLAN:
    error = None
    stuck = False
    up = False

    def __init__(self, mode):
        pass

    def active(self, on):
        pass

    def isconnected(self):
        return WLAN.up

    def connect(self, ssid, password):
        if WLAN.error:
            raise WLAN.error
        if not WLAN.stuck:
            WLAN.up = True

    def ifconfig(self):
        return ("192.168.4.2", "255.255.255.0", "192.168.4.1", "8.8.8.8")


# 가짜 시계(ms). sleep_ms 가 더함
class Clock:
    def __init__(self):
        self.ms = 0

    def sleep_ms(self, ms):
        self.ms += ms


@pytest.fixture
def board(monkeypatch):
    Pin.made, WDT.made = [], []
    WLAN.error, WLAN.stuck, WLAN.up = None, False, False
    machine = types.ModuleType("machine")
    machine.Pin, machine.ADC, machine.WDT = Pin, ADC, WDT
    network = types.ModuleType("network")
    network.STA_IF, network.WLAN = 0, WLAN
    secret = types.ModuleType("secret")
    secret.STA_SSID, secret.STA_PASS, secret.SERVER_URL = "lab", "pass1234", "http://h:1/"
    clock = Clock()
    monkeypatch.setattr(time, "ticks_ms", lambda: clock.ms, raising=False)
    monkeypatch.setattr(time, "ticks_diff", lambda a, b: a - b, raising=False)
    monkeypatch.setattr(time, "ticks_add", lambda t, ms: t + ms, raising=False)
    monkeypatch.setattr(time, "sleep_ms", clock.sleep_ms, raising=False)
    monkeypatch.setitem(sys.modules, "machine", machine)
    monkeypatch.setitem(sys.modules, "network", network)
    monkeypatch.setitem(sys.modules, "secret", secret)
    monkeypatch.delitem(sys.modules, "main", raising=False)
    main = importlib.import_module("main")
    sent = []
    monkeypatch.setattr(main.client, "send", lambda url, body, timeout_s: sent.append((url, body)))
    return types.SimpleNamespace(main=main, secret=secret, sent=sent)


# 서버 전송 3회: 끝 슬래시를 뗀 주소 + /api/ingest 로 seq 0·1·2, 릴레이·플로트 핀은 입력,
# 핀 출력 없음, 감시 타이머 8초가 표본마다 먹여지는지 검사
def test_run_sends_to_the_server_without_touching_the_pump(board):
    board.main.run(cycles=3)
    assert [(url, body["seq"], body["readings"]["distA_mm"]) for url, body in board.sent] == [
        ("http://h:1/api/ingest", 0, 560.0),
        ("http://h:1/api/ingest", 1, 560.0),
        ("http://h:1/api/ingest", 2, 560.0),
    ]
    assert (26, "in", None) in Pin.made and (27, "in", "pull_up") in Pin.made
    assert [(w.timeout, w.fed) for w in WDT.made] == [(8000, 30)]


# 와이파이가 제한 시간 안에 붙지 않거나 드라이버가 OSError 를 내면, 감시 타이머 없이 REPL 출력으로
# 넘어가는지 검사
@pytest.mark.parametrize("error", [None, OSError("Wifi Invalid Password")])
def test_run_falls_back_to_printing_when_wifi_fails(board, capsys, error):
    WLAN.error, WLAN.stuck = error, error is None
    board.main.run(cycles=1)
    out = capsys.readouterr().out.splitlines()
    assert board.sent == [] and WDT.made == []
    assert "wifi" in out[0]
    assert json.loads(out[-1])["seq"] == 0


# SERVER_URL 에 http:// 가 없으면 부팅 때 알리고 서버 없이 도는지 검사
def test_bad_server_url_is_reported_at_boot(board, capsys):
    board.secret.SERVER_URL = "h:1"
    board.main.run(cycles=1)
    out = capsys.readouterr().out
    assert board.sent == [] and "SERVER_URL" in out
    assert json.loads(out.splitlines()[-1])["seq"] == 0


# secret.py 가 깨져 있어도(문법 오류) 부팅이 멈추지 않고 알린 뒤 설정 없이 가는지 검사
def test_broken_secret_is_reported_and_ignored(board, tmp_path, monkeypatch, capsys):
    (tmp_path / "secret.py").write_text('STA_PASS = "abc\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "secret")
    monkeypatch.delitem(sys.modules, "main")
    main = importlib.import_module("main")
    assert main.secret is None
    assert "secret.py" in capsys.readouterr().out
