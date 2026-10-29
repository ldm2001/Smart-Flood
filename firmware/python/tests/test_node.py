import node
import pytest


# 가짜 보드: 시각은 sleep 과 read_mv 의 cost 로만 흐르고, 보낸 메시지·로그·잠든 시간을 기록
class Fake:
    def __init__(self, mv=480.0, fail=(), cost_ms=0):
        self.mv = mv
        self.fail = set(fail)
        self.cost_ms = cost_ms
        self.t = 0
        self.sent = []
        self.logs = []
        self.sleeps = []
        self.fed = 0

    def read_mv(self):
        self.t += self.cost_ms
        return self.mv

    def post(self, body):
        if body["seq"] in self.fail:
            raise OSError("끊김")
        self.sent.append(body)

    def now_ms(self):
        return self.t

    def sleep_ms(self, ms):
        self.sleeps.append(ms)
        self.t += ms

    def diff(self, a, b):
        return a - b

    def add(self, t, ms):
        return t + ms

    def log(self, text):
        self.logs.append(text)

    def keepalive(self):
        self.fed += 1


# 표본을 이동평균해 수위를 내고, 센서 이상이면 None 인지 검사
def test_depth_follows_the_samples():
    sensor = node.Node("b")
    assert sensor.depth() is None
    sensor.sample(480.0)
    assert sensor.depth() == pytest.approx(10.0)
    broken = node.Node("b")
    broken.sample(100.0)
    assert broken.depth() is None


# 메시지마다 순번이 오르고 넘겨준 시각이 들어가는지 검사
def test_message_counts_up():
    sensor = node.Node("b")
    sensor.sample(480.0)
    first, second = sensor.message(900), sensor.message(1900)
    assert (first["seq"], first["tMs"], first["readings"]["distA_mm"]) == (0, 900, 590.0)
    assert (second["seq"], second["tMs"]) == (1, 1900)


# 100 ms 마다 표본, 10 표본마다 전송, 표본마다 keepalive 인지 검사
def test_loop_sends_once_a_second():
    board = Fake()
    node.loop(node.Node("b"), board, cycles=2)
    assert [body["seq"] for body in board.sent] == [0, 1]
    assert board.sent[1]["tMs"] - board.sent[0]["tMs"] == 1000
    assert board.fed == 20
    assert board.sleeps == [100] * 19


# 전송이 실패해도 로그만 남기고 다음 전송을 이어 가는지 검사
def test_loop_survives_a_failed_post():
    board = Fake(fail={0})
    node.loop(node.Node("b"), board, cycles=2)
    assert [body["seq"] for body in board.sent] == [1]
    assert len(board.logs) == 1 and "끊김" in board.logs[0]


# 표본 읽기가 주기보다 오래 걸리면 몰아서 따라가지 않고 지금부터 다시 세는지 검사
def test_loop_resyncs_when_behind():
    board = Fake(cost_ms=250)
    node.loop(node.Node("b"), board, cycles=2)
    assert board.sleeps == []
    assert board.sent[1]["tMs"] - board.sent[0]["tMs"] == 2500
