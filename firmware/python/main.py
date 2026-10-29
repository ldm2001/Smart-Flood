import client
import ingest
import json
import level
import machine
import network
import node
import os
import time

# ESP32 보드 층(MicroPython). 공용 모듈(level·ingest·client·node)은 맥에서 pytest 로 검증하고,
# 이 파일만 보드 API(machine·network)를 다룸. 접속 정보는 secret.py(저장소에 없음)에서 읽음
# 1단계 범위: 수위 읽기와 1 Hz /api/ingest 전송만. 펌프 제어·예측·단계·웹 페이지·ntfy 는 아직 없음
# 릴레이 핀은 입력(Hi-Z)으로 두어 꺼진 상태. 펌프 출력 없음

try:
    import secret
except ImportError:
    secret = None

LEVEL_PIN = 34  # KIT0139 변환보드 출력(ADC1). REV16 핀 배치
RELAY_PIN = 26  # 펌프 릴레이(active-low). 입력으로 두어 켜지지 않게 함
FLOAT_PIN = 27  # 플로트 스위치(풀업, 닫히면 LOW). 1단계에서는 읽지 않음
READS = 64  # 표본 하나에 평균하는 ADC 읽기 횟수
WIFI_WAIT_MS = 15000  # 와이파이 접속 대기
WDT_MS = 8000  # 전송 중 멈춤 대비 감시 타이머. 서버로 보낼 때만 켬


# 설정값. secret.py 가 없거나 항목이 비면 빈 문자열
def setting(name):
    return getattr(secret, name, "") if secret else ""


# 와이파이 접속. 성공이면 IP 문자열, 실패면 None
def connect(ssid, password, wait_ms=WIFI_WAIT_MS):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        due = time.ticks_add(time.ticks_ms(), wait_ms)
        while not wlan.isconnected():
            if time.ticks_diff(due, time.ticks_ms()) <= 0:
                return None
            time.sleep_ms(100)
    return wlan.ifconfig()[0]


# 보드 층: ADC 64회 평균 전압, ticks 기반 시각, 전송은 client.send(주소가 없으면 REPL 에 찍음)
class Esp:
    def __init__(self, server, watchdog=None):
        self.server = server
        self.watchdog = watchdog
        self.adc = machine.ADC(machine.Pin(LEVEL_PIN))
        self.adc.atten(machine.ADC.ATTN_11DB)
        machine.Pin(RELAY_PIN, machine.Pin.IN)  # 릴레이는 끔. 펌프 출력 없음
        machine.Pin(FLOAT_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

    def read_mv(self):
        return level.mean([self.adc.read_uv() / 1000.0 for _ in range(READS)])

    def post(self, body):
        if not self.server:
            print(json.dumps(body))
            return
        client.send(self.server + ingest.PATH, body, 0.4)

    def now_ms(self):
        return time.ticks_ms()

    def sleep_ms(self, ms):
        time.sleep_ms(ms)

    def diff(self, a, b):
        return time.ticks_diff(a, b)

    def add(self, t, ms):
        return time.ticks_add(t, ms)

    def log(self, text):
        print(text)

    def keepalive(self):
        if self.watchdog:
            self.watchdog.feed()


# 부팅 후 실행. 와이파이와 서버 주소가 있으면 서버로 보내고, 없으면 REPL 에 메시지를 찍음
def run(cycles=None):
    server = setting("SERVER_URL")
    ssid = setting("STA_SSID")
    if server and ssid:
        ip = connect(ssid, setting("STA_PASS"))
        print("wifi", ip if ip else "접속 실패. 서버로 보내지 않고 REPL 에 찍음")
        if ip is None:
            server = ""
    elif server:
        print("STA_SSID 가 비어 있어 서버로 보내지 않음")
        server = ""
    watchdog = machine.WDT(timeout=WDT_MS) if server else None
    board = Esp(server, watchdog)
    sensor = node.Node(ingest.boot_id(os.urandom(4)))
    node.loop(sensor, board, cycles=cycles)


if __name__ == "__main__":
    run()
