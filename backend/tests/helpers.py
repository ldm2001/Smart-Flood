import errno
import hashlib
import io
import json
import math
from app.core.calibration import Sensor, gap
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 테스트 기준 시각(한국 2026-10-22 10:00)
START = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone(timedelta(hours=9)))
SENSOR_OK = {"A": "ok", "B": "ok", "load": "ok"}


# 가상 시계를 1초씩 움직이며 밀린 틱을 처리하는 함수
def lapse(clock, service, seconds: int) -> None:
    for _ in range(seconds):
        clock.jump(1.0)
        service.catchup()


# A·B 수위가 a_mm·b_mm 로 읽히는 거리 값을 만듦
def readout(config, *, a_mm: float, b_mm: float, weight_g: float = 0.0) -> dict:
    sensor = {z: Sensor.config(config["sensors"][z]) for z in "AB"}
    return {
        "distA_mm": gap(a_mm / 1000, sensor["A"]),
        "distB_mm": gap(b_mm / 1000, sensor["B"]),
        "weight_g": weight_g,  # 하중 값은 그대로 둠
    }


# 입력원 Source 의 가짜. until_s 까지 호출마다 같은 메시지를 냄
class Script:
    # 만들 때 받을 값들
    def __init__(
        self, readings: dict | None, status: dict = SENSOR_OK, *, until_s: float = math.inf
    ) -> None:
        self.readings, self.status, self.until_s = readings, status, until_s
        self.seq = self.resets = 0  # 순번과 되돌린 횟수를 0 에서 시작

    # 새 실험 회차를 시작
    def origin(self) -> None:
        self.seq = 0  # 순번을 0 으로 되돌림
        self.resets += 1  # 되돌린 횟수를 셈

    # 해당 초까지 도착한 관측 메시지 목록을 반환
    def inbox(self, elapsed_s, cond):
        if self.readings is None or elapsed_s > self.until_s:
            return []
        self.seq += 1
        return [
            {
                "deviceId": "esp32_1",
                "bootId": "test",
                "seq": self.seq,
                "tMs": round(elapsed_s * 1000),  # 경과 시간(ms)
                "readings": dict(self.readings),  # 센서 값 복사본(매번 같음)
                "sensorStatus": dict(self.status),  # 센서 상태 복사본(매번 같음)
            }
        ]


# 알림 Notifier 의 가짜. 받은 사건을 모아 두기만 함
class Mailbox:
    # 만들 때 빈 목록
    def __init__(self) -> None:
        self.events: list[dict] = []

    # 사건 하나를 받아 둠
    def notice(self, event: dict) -> None:
        self.events.append(event)


# 기록 파일에서 state 레코드의 상태만 순서대로 모으는 함수
def chronicle(experiment_log, experiment_id: str) -> list[dict]:
    return [r["state"] for r in experiment_log.records(experiment_id) if r["type"] == "state"]


# 원래 /api/state 가 재생에서 보일 모양. 입력원 표시만 다름
def echo(state: dict) -> dict:
    zones = {
        z: {**zone, "source": "replay" if zone["source"] == "simulated" else zone["source"]}
        for z, zone in state["zones"].items()
    }
    return {**state, "mode": "replay", "dataSource": "replay", "zones": zones}


# 기록 파일을 edit(레코드 목록) 결과로 다시 씀. 글자 줄은 그대로 씀
def revision(experiment_log, edit, experiment_id: str) -> None:
    path = experiment_log.directory / f"{experiment_id}.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in edit(records)]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


# 기록을 처음부터 끝까지 재생하며 받은 /api/state 바이트를 모음
def footage(client, clock, log_id: str, *, max_ticks: int = 1000) -> list[bytes]:
    service = client.app.state.service
    for body in ({"mode": "sim"}, {"mode": "replay", "logId": log_id}):
        response = client.post("/api/source", json=body)
        assert response.status_code == 200, response.text
    bodies = [client.get("/api/state").content]  # 재생을 시작한 0초의 상태를 먼저 받음
    for _ in range(max_ticks):
        if service.delay() is None:
            return bodies
        lapse(clock, service, 1)
        bodies.append(client.get("/api/state").content)
    raise AssertionError(f"{max_ticks} tick 이 지나도 재생이 끝나지 않았다")


# 바이트마다 SHA-256 해시를 만드는 함수
def digests(bodies: list[bytes]) -> list[str]:
    return [hashlib.sha256(body).hexdigest() for body in bodies]  # 해시 16진수 문자열 목록을 반환


# 받은 것의 앞 절반만 쓰고 디스크가 찼다고 알리는 파일 대역
class Clip:
    # 진짜 파일을 감쌈
    def __init__(self, inner) -> None:
        self.inner = inner

    # 앞 절반만 쓰고 오류를 냄
    def write(self, data):
        self.inner.write(data[: len(data) // 2])
        raise OSError(errno.ENOSPC, "No space left on device")

    # with 문에 들어가면 자기를 반환
    def __enter__(self):
        return self

    # with 문에서 나가면 속 파일의 마무리를 호출
    def __exit__(self, *crash):
        return self.inner.__exit__(*crash)

    # 나머지 기능은 속 파일에 넘김
    def __getattr__(self, name):
        return getattr(self.inner, name)


# 이어쓰기로 여는 파일만 Clip 으로 교체. 읽기는 그대로 둠
def breakage(monkeypatch) -> None:
    origin = Path.open

    # 이어쓰기면 대역으로 감싸 주는 열기 함수
    def surrogate(self, mode="r", *args, **kwargs):
        handle = origin(self, mode, *args, **kwargs)  # 먼저 진짜로 엶
        return Clip(handle) if "a" in mode else handle

    monkeypatch.setattr(Path, "open", surrogate)


# 남은 자리(room 바이트)까지만 디스크에 쓰고 그 뒤는 가득 찼다고 알리는 날 파일 대역. 버퍼 아래에 둠
class Jam(io.RawIOBase):
    # 진짜 날 파일(FileIO)과 남은 자리를 받음
    def __init__(self, inner, room: int) -> None:
        super().__init__()
        self.inner, self.room = inner, room

    # 쓸 수 있는 파일임
    def writable(self) -> bool:
        return True

    # 위치를 옮길 수 있는 파일임
    def seekable(self) -> bool:
        return True

    # 남은 자리 안이면 다 쓰고, 넘치면 남은 자리만큼만 쓴 뒤 오류
    def write(self, data) -> int:
        chunk = bytes(data)
        if len(chunk) <= self.room:
            self.room -= len(chunk)
            return self.inner.write(chunk)
        self.inner.write(chunk[: self.room])
        self.room = 0
        raise OSError(errno.ENOSPC, "No space left on device")

    # 지금 위치는 속 파일의 것
    def tell(self) -> int:
        return self.inner.tell()

    # 위치 옮기기는 속 파일에 넘김
    def seek(self, offset: int, whence: int = 0) -> int:
        return self.inner.seek(offset, whence)

    # 자르기는 속 파일에 넘김
    def truncate(self, size=None) -> int:
        return self.inner.truncate(size)

    # 속 파일도 함께 닫음
    def close(self) -> None:
        self.inner.close()
        super().close()


# 이어쓰기로 여는 파일을 Jam 위의 진짜 BufferedWriter 로 교체. 디스크에 room 바이트만 남은 상황
def shortage(monkeypatch, room: int) -> None:
    origin = Path.open

    # 이어쓰기면 자리가 모자란 날 파일 위에 버퍼를 얹어 주는 열기 함수
    def surrogate(self, mode="r", *args, **kwargs):
        if "a" not in mode:
            return origin(self, mode, *args, **kwargs)
        return io.BufferedWriter(Jam(io.FileIO(str(self), mode), room))

    monkeypatch.setattr(Path, "open", surrogate)
