import ingest
import level

# 센서 노드의 순수 부분. 시각·ADC·네트워크는 board 객체가 제공:
#   read_mv() → 전압 mV, post(body) → 서버 전송(실패는 예외), now_ms() → 시각,
#   sleep_ms(ms), diff(a, b) → a - b, add(t, ms) → t + ms(보드는 ticks 함수), log(text), keepalive()
SAMPLE_MS = 100  # 표본 주기
SEND_MS = 1000  # 전송 주기


# 노드 상태: 보정 직선, 이동평균 전압, 메시지 순번
class Node:
    def __init__(
        self, boot, line=None, device=ingest.DEVICE_ID, height_mm=ingest.INSTALL_HEIGHT_MM
    ):
        self.boot = boot
        self.line = line if line is not None else level.Line()
        self.device = device
        self.height_mm = height_mm
        self.mv = None
        self.seq = 0

    # 표본 하나 반영(이동평균)
    def sample(self, mv):
        self.mv = level.smooth(self.mv, mv)

    # 현재 수위(mm). 표본이 없거나 센서 이상이면 None
    def depth(self):
        if self.mv is None or level.fault(self.mv):
            return None
        return level.mm(self.mv, self.line)

    # 서버 메시지 하나. 순번 증가
    def message(self, t_ms):
        body = ingest.message(self.boot, self.seq, t_ms, self.depth(), self.device, self.height_mm)
        self.seq += 1
        return body


# 100 ms 마다 표본, 시작 1 s 뒤부터 1 s 마다 전송. 두 주기는 따로 세어 읽기나 전송이 느려도
# 전송 간격은 1 s. 전송 실패는 log 로 알리고 계속. cycles 는 전송 시도 횟수 제한
def loop(node, board, cycles=None, sample_ms=SAMPLE_MS, send_ms=SEND_MS):
    due = board.now_ms()
    send_due = board.add(due, send_ms)
    sent = 0
    while cycles is None or sent < cycles:
        now = board.now_ms()
        wait = board.diff(due, now)
        if wait > 0:
            board.sleep_ms(wait)
            continue
        if -wait > sample_ms:  # 많이 늦었으면 몰아서 따라가지 않고 지금부터 다시 셈
            due = now
        node.sample(board.read_mv())
        now = board.now_ms()
        if board.diff(now, send_due) >= 0:
            body = node.message(now)
            try:
                board.post(body)
            except Exception as error:
                board.log("전송 실패 seq {}: {}".format(body["seq"], error))
            sent += 1
            send_due = board.add(send_due, send_ms)
            now = board.now_ms()
            if board.diff(now, send_due) > 0:  # 전송이 주기를 넘겼으면 밀린 전송을 몰아 보내지 않음
                send_due = board.add(now, send_ms)
        board.keepalive()
        due = board.add(due, sample_ms)
