import node
import pytest


# 가짜 보드: 시각은 pause, voltage 의 cost_ms, delivery 의 delivery_ms 로만 흐르고,
# 보낸 메시지·로그·잠든 시간을 기록
class Fake:
    def __init__(self, mv=480.0, fail=(), cost_ms=0, delivery_ms=0):
        self.mv = mv
        self.fail = set(fail)
        self.cost_ms = cost_ms
        self.delivery_ms = delivery_ms
        self.t = 0
        self.sent = []
        self.logs = []
        self.sleeps = []
        self.fed = 0

    def voltage(self):
        self.t += self.cost_ms
        return self.mv

    def delivery(self, body):
        self.t += self.delivery_ms
        if body["seq"] in self.fail:
            raise OSError("끊김")
        self.sent.append(body)

    def clock(self):
        return self.t

    def pause(self, ms):
        self.sleeps.append(ms)
        self.t += ms

    def span(self, a, b):
        return a - b

    def deadline(self, t, ms):
        return t + ms

    def journal(self, text):
        self.logs.append(text)

    def heartbeat(self):
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


# NaN 표본은 그 메시지를 이상(null)으로 보내고, 다음 정상 표본에서 수위가 돌아오는지 검사
def test_nan_sample_reports_fault_then_recovers():
    sensor = node.Node("b")
    sensor.sample(float("nan"))
    assert sensor.depth() is None
    assert sensor.message(0)["sensorStatus"]["A"] == "fault"
    sensor.sample(480.0)
    assert sensor.depth() == pytest.approx(10.0)


# 메시지마다 순번이 오르고 넘겨준 시각이 들어가는지 검사
def test_message_counts_up():
    sensor = node.Node("b")
    sensor.sample(480.0)
    first, second = sensor.message(900), sensor.message(1900)
    assert (first["seq"], first["tMs"], first["readings"]["distA_mm"]) == (0, 900, 590.0)
    assert (second["seq"], second["tMs"]) == (1, 1900)


# 100 ms 마다 표본, 시작 1 s 뒤부터 1 s 마다 전송, 표본마다 heartbeat 인지 검사
def test_loop_sends_once_a_second():
    board = Fake()
    node.loop(node.Node("b"), board, cycles=2)
    assert [(body["seq"], body["tMs"]) for body in board.sent] == [(0, 1000), (1, 2000)]
    assert board.fed == 21
    assert board.sleeps == [100] * 20


# 전송이 실패해도 로그만 남기고 다음 전송을 이어 가는지 검사
def test_loop_survives_a_failed_post():
    board = Fake(fail={0})
    node.loop(node.Node("b"), board, cycles=2)
    assert [body["seq"] for body in board.sent] == [1]
    assert len(board.logs) == 1 and "끊김" in board.logs[0]


# 표본 읽기가 주기보다 오래 걸리면 표본은 몰아서 따라가지 않고 전송은 1 s 간격인지 검사
def test_loop_resyncs_when_behind():
    board = Fake(cost_ms=250)
    node.loop(node.Node("b"), board, cycles=2)
    assert board.sleeps == []
    assert [body["tMs"] for body in board.sent] == [1000, 2000]


# 읽기가 1 s 씩 막혀도(표준입력 줄 읽기) 읽을 때마다 보내는지 검사
def test_loop_sends_every_read_when_reads_block():
    board = Fake(cost_ms=1000)
    node.loop(node.Node("b"), board, cycles=3)
    assert [body["tMs"] for body in board.sent] == [1000, 2000, 3000]


# 전송이 600 ms 걸려도 다음 전송이 1 s 뒤인지 검사
def test_loop_keeps_the_period_after_a_slow_post():
    board = Fake(delivery_ms=600)
    node.loop(node.Node("b"), board, cycles=3)
    assert [body["tMs"] for body in board.sent] == [1000, 2000, 3000]


# 전송이 주기보다 오래 걸리면 밀린 전송을 몰아 보내지 않고 끝난 때부터 1 s 뒤에 보내는지 검사
def test_loop_does_not_burst_after_a_long_post():
    board = Fake(delivery_ms=2500)
    node.loop(node.Node("b"), board, cycles=2)
    assert [body["tMs"] for body in board.sent] == [1000, 4500]
