import importlib
import json
import pytest
import sys
import time
import types

# main.py(보드 층)를 CPython 에서 돌리는 시험. machine·network·secret 을 가짜 모듈로 끼우고
# time.ticks_*·sleep_ms 는 가짜 시계로 바꿈. 전송은 client.delivery 를 기록 함수로 바꿔 받음


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
# late 는 붙지 않고 넘어가는 처음 connect 횟수, joins 는 connect 횟수
class WLAN:
    error = None
    stuck = False
    late = 0
    up = False
    joins = 0

    def __init__(self, mode):
        pass

    def active(self, on):
        pass

    def isconnected(self):
        return WLAN.up

    def connect(self, ssid, password):
        WLAN.joins += 1
        if WLAN.error:
            raise WLAN.error
        if not WLAN.stuck and WLAN.joins > WLAN.late:
            WLAN.up = True

    def disconnect(self):
        WLAN.up = False

    def ifconfig(self):
        return ("192.168.4.2", "255.255.255.0", "192.168.4.1", "8.8.8.8")


# 가짜 시계(ms). pause 가 더함
class Clock:
    def __init__(self):
        self.ms = 0

    def pause(self, ms):
        self.ms += ms


@pytest.fixture
def board(monkeypatch):
    Pin.made, WDT.made = [], []
    WLAN.error, WLAN.stuck, WLAN.late, WLAN.up, WLAN.joins = None, False, 0, False, 0
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
    monkeypatch.setattr(time, "sleep_ms", clock.pause, raising=False)
    monkeypatch.setitem(sys.modules, "machine", machine)
    monkeypatch.setitem(sys.modules, "network", network)
    monkeypatch.setitem(sys.modules, "secret", secret)
    monkeypatch.delitem(sys.modules, "main", raising=False)
    main = importlib.import_module("main")
    sent = []
    monkeypatch.setattr(
        main.client, "delivery", lambda url, body, timeout_s: sent.append((url, body))
    )
    return types.SimpleNamespace(main=main, secret=secret, sent=sent)


# 서버 전송 3회: 끝 슬래시를 뗀 주소 + /api/ingest 로 seq 0·1·2, 릴레이·플로트 핀은 입력,
# 핀 출력 없음, 감시 타이머 8초가 표본마다 먹여지는지 검사
def test_run_sends_to_the_server_without_touching_the_pump(board):
    board.main.startup(cycles=3)
    assert [(url, body["seq"], body["readings"]["distA_mm"]) for url, body in board.sent] == [
        ("http://h:1/api/ingest", 0, 560.0),
        ("http://h:1/api/ingest", 1, 560.0),
        ("http://h:1/api/ingest", 2, 560.0),
    ]
    assert (26, "in", None) in Pin.made and (27, "in", "pull_up") in Pin.made
    assert [(w.timeout, w.fed) for w in WDT.made] == [(8000, 31)]


# 부팅 때 와이파이가 제한 시간 안에 붙지 않거나 드라이버가 OSError 를 내도, 서버 주소와 감시
# 타이머를 두고 보낼 때마다 끊김을 알리는지 검사
@pytest.mark.parametrize("error", [None, OSError("Wifi Invalid Password")])
def test_run_keeps_the_server_when_wifi_fails_at_boot(board, capsys, error):
    WLAN.error, WLAN.stuck = error, error is None
    board.main.startup(cycles=2)
    out = capsys.readouterr().out.splitlines()
    assert board.sent == [] and [w.timeout for w in WDT.made] == [8000]
    assert "wifi" in out[0]
    assert "전송 실패 seq 1: 와이파이 끊김" in out


# 부팅 때 못 붙었어도 보낼 때 다시 붙어 그다음 전송부터 서버로 보내고, 붙은 IP 를 찍는지 검사
def test_run_rejoins_after_a_failed_boot(board, capsys):
    WLAN.late = 1
    board.main.startup(cycles=3)
    out = capsys.readouterr().out.splitlines()
    assert [body["seq"] for _, body in board.sent] == [1, 2]
    assert "전송 실패 seq 0: 와이파이 끊김" in out and "wifi 192.168.4.2" in out


# 도는 중에 와이파이가 끊기면 그 전송은 실패로 알리고, 다시 붙은 뒤 IP 를 찍고 이어 보내는지 검사
def test_run_rejoins_after_a_drop(board, capsys, monkeypatch):
    def dropout(url, body, timeout_s):
        board.sent.append((url, body))
        if body["seq"] == 0:
            WLAN.up = False  # 첫 전송 뒤 끊김

    monkeypatch.setattr(board.main.client, "delivery", dropout)
    board.main.startup(cycles=3)
    out = capsys.readouterr().out.splitlines()
    assert [body["seq"] for _, body in board.sent] == [0, 2]
    assert "전송 실패 seq 1: 와이파이 끊김" in out
    assert out.count("wifi 192.168.4.2") == 2


# 계속 못 붙으면 다시 붙기를 10초에 한 번만 시도하는지 검사
def test_rejoin_waits_ten_seconds_between_tries(board):
    WLAN.stuck = True
    board.main.startup(cycles=12)
    assert WLAN.joins == 3  # 부팅 때 1번, 16초와 26초의 전송 때 1번씩


# SERVER_URL 에 http:// 가 없으면 부팅 때 알리고 서버 없이 도는지 검사
def test_bad_server_url_is_reported_at_boot(board, capsys):
    board.secret.SERVER_URL = "h:1"
    board.main.startup(cycles=1)
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
