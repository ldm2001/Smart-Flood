import argparse
import client
import ingest
import json
import level
import node
import os
import sys
import time

# 맥에서 보드 없이 노드를 돌리는 실행기. 가짜 센서(--mm/--ramp)나 표준입력의 mV 줄을 읽어
# 서버(/api/ingest)에 보냄. 서버 주소가 없으면 메시지를 JSON 줄로 찍음
# 보드(main.py)와 같은 node.loop 를 돌리므로 서버 쪽 경로를 보드 없이 미리 확인할 수 있음


# 수위(mm)→전압(mV). level.mm 의 역함수. 가짜 센서가 씀
def volts(mm, line=None):
    line = level.Line() if line is None else line
    return (mm - line.offset) / line.slope


# 가짜 센서: start_mm 에서 초당 ramp_mm 씩 오르는 수위의 전압을 돌려주는 함수를 만듦
def fake(start_mm, ramp_mm, clock=time.monotonic):
    start = clock()

    def voltage():
        return volts(start_mm + ramp_mm * (clock() - start))

    return voltage


# 줄 흐름(표준입력)을 mV 로 읽는 전압 함수를 만듦. "482 mV" 처럼 mV 토큰이 있으면 그 앞 숫자,
# 없으면 첫 토큰이 숫자인 줄만 받음. 줄이 올 때까지 기다리고, 흐름이 끝나면 마지막 값을
# 유지함(처음부터 없으면 0 mV = 센서 이상)
def lines(stream):
    last = [0.0]

    def voltage():
        for text in stream:
            parts = text.split()
            if not parts:
                continue
            token = parts[0]
            if "mV" in parts[1:]:
                token = parts[parts.index("mV") - 1]
            try:
                last[0] = float(token)
            except ValueError:
                continue
            break
        return last[0]

    return voltage


# 명령행 선택지
def options(argv):
    parser = argparse.ArgumentParser(description="맥에서 센서 노드를 돌려 서버로 보냄")
    parser.add_argument(
        "--server", default="", type=client.base, help="서버 주소(http://…). 비우면 찍기만 함"
    )
    parser.add_argument("--mm", type=float, default=40.0, help="가짜 센서 시작 수위(mm)")
    parser.add_argument("--ramp", type=float, default=0.0, help="가짜 센서 수위 변화(mm/s)")
    parser.add_argument("--stdin", action="store_true", help="표준입력의 mV 줄을 센서 값으로 읽음")
    parser.add_argument("--seconds", type=int, help="보낼 횟수(초). 비우면 멈출 때까지")
    parser.add_argument("--device", default=ingest.DEVICE_ID, help="deviceId")
    return parser.parse_args(argv)


# 맥 보드 층. 시각은 time.monotonic(시작 기준 ms), 전송은 client.delivery
# 서버 주소가 없으면 메시지를 out 에 JSON 줄로 찍음(서버 없이 메시지 모양 확인용)
class Mac:
    def __init__(
        self, server, probe, clock=time.monotonic, out=sys.stdout, poster=client.delivery
    ):
        self.server = server
        self.probe = probe
        self.source = clock  # 초 단위 시계. clock 메서드와 겹치지 않게 따로 둠
        self.out = out
        self.poster = poster
        self.start = clock()

    def voltage(self):
        return self.probe()

    def delivery(self, body):
        if not self.server:
            self.out.write(json.dumps(body) + "\n")
            self.out.flush()
            return
        self.poster(self.server + ingest.PATH, body, 0.4)

    def clock(self):
        return int((self.source() - self.start) * 1000)

    def pause(self, ms):
        time.sleep(ms / 1000.0)

    def span(self, a, b):
        return a - b

    def deadline(self, t, ms):
        return t + ms

    def journal(self, text):
        sys.stderr.write(text + "\n")

    def heartbeat(self):
        pass


# 명령행 실행. --seconds 가 있으면 그만큼 보내고 끝남
def main(argv=None):
    opts = options(sys.argv[1:] if argv is None else argv)
    probe = lines(sys.stdin) if opts.stdin else fake(opts.mm, opts.ramp)
    board = Mac(opts.server, probe)
    sensor = node.Node(ingest.bootid(os.urandom(4)), device=opts.device)
    node.loop(sensor, board, cycles=opts.seconds)


if __name__ == "__main__":
    main()
