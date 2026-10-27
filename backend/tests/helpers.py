import errno
import hashlib
import json
import math
from app.core.calibration import Sensor, gap
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 테스트 기준 시각(한국 2026-10-22 10:00)
START = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone(timedelta(hours=9)))
SENSOR_OK = {"A": "ok", "B": "ok", "load": "ok"}  # 센서가 모두 정상인 상태 표시


# 가상 시계를 1초씩 움직이며 밀린 틱을 처리하는 함수
def lapse(clock, service, seconds: int) -> None:
    for _ in range(seconds):  # 초 수만큼 반복
        clock.jump(1.0)  # 시계를 1초 앞으로 전송
        service.catchup()  # 밀린 틱을 처리


# A·B 수위가 a_mm·b_mm 로 읽히는 거리 값을 만듦
def readout(config, *, a_mm: float, b_mm: float, weight_g: float = 0.0) -> dict:
    sensor = {z: Sensor.config(config["sensors"][z]) for z in "AB"}  # A·B 센서 설정을 구역별로 만듦
    return {  # 관측 값 묶음을 반환
        "distA_mm": gap(a_mm / 1000, sensor["A"]),  # A 수위를 센서 거리로 변환
        "distB_mm": gap(b_mm / 1000, sensor["B"]),  # B 수위를 센서 거리로 변환
        "weight_g": weight_g,  # 하중 값은 그대로 둔다
    }


# 입력원 Source 의 가짜. until_s 까지 호출마다 같은 메시지를 냄
class Script:
    # 만들 때 받을 값들
    def __init__(
        # 관측값(없으면 None), 센서 상태, 끝 시각
        self, readings: dict | None, status: dict = SENSOR_OK, *, until_s: float = math.inf
    ) -> None:  # 반환은 없다
        # 받은 값을 그대로 저장
        self.readings, self.status, self.until_s = readings, status, until_s
        self.seq = self.resets = 0  # 순번과 되돌린 횟수를 0 에서 시작

    # 새 실험 회차를 시작
    def origin(self) -> None:
        self.seq = 0  # 순번을 0 으로 되돌린다
        self.resets += 1  # 되돌린 횟수를 센다

    # 해당 초까지 도착한 관측 메시지 목록을 반환
    def inbox(self, elapsed_s, cond):
        if self.readings is None or elapsed_s > self.until_s:  # 관측값이 없거나 끝 시각이 지났으면
            return []  # 아무것도 내지 않음
        self.seq += 1  # 순번을 하나 올림
        return [  # 메시지 하나짜리 목록을 반환
            {  # 메시지 한 건
                "deviceId": "esp32_1",  # 장치 ID
                "bootId": "test",  # 부팅 ID
                "seq": self.seq,  # 순번
                "tMs": round(elapsed_s * 1000),  # 경과 시간(ms)
                "readings": dict(self.readings),  # 센서 값 복사본(매번 같다)
                "sensorStatus": dict(self.status),  # 센서 상태 복사본(매번 같다)
            }
        ]


# 기록 파일에서 state 레코드의 상태만 순서대로 모으는 함수
def chronicle(experiment_log, experiment_id: str) -> list[dict]:
    # 종류가 state 인 레코드의 상태를 추출
    return [r["state"] for r in experiment_log.records(experiment_id) if r["type"] == "state"]


# 원래 /api/state 가 재생에서 보일 모양. 입력원 표시만 다르다
def echo(state: dict) -> dict:
    zones = {  # 구역마다 출처 표시를 바꾼 사본을 만듦
        # 출처가 simulated 이면 replay 로, 아니면 그대로 둔다
        z: {**zone, "source": "replay" if zone["source"] == "simulated" else zone["source"]}
        for z, zone in state["zones"].items()  # 모든 구역을 하나씩 확인
    }
    # 모드·입력원을 replay 로 바꾼 상태를 반환
    return {**state, "mode": "replay", "dataSource": "replay", "zones": zones}


# 기록 파일을 edit(레코드 목록) 결과로 다시 쓴다. 글자 줄은 그대로 기록
def revision(experiment_log, edit, experiment_id: str) -> None:
    path = experiment_log.directory / f"{experiment_id}.jsonl"  # 기록 파일 경로를 만듦
    # 파일을 줄마다 JSON 으로 읽음
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    # 고친 목록을 줄로 바꾼다. 글자는 그대로, 나머지는 JSON 으로
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in edit(records)]
    # 줄바꿈을 붙여 파일에 다시 기록
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


# 기록을 처음부터 끝까지 재생하며 받은 /api/state 바이트를 모음
def footage(client, clock, log_id: str, *, max_ticks: int = 1000) -> list[bytes]:
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    # sim 으로 바꿨다가 기록을 고른다. 같은 기록도 처음부터 다시
    for body in ({"mode": "sim"}, {"mode": "replay", "logId": log_id}):
        response = client.post("/api/source", json=body)  # 입력원 전환을 요청
        assert response.status_code == 200, response.text  # 요청이 성공 필요
    bodies = [client.get("/api/state").content]  # 재생을 시작한 0초의 상태를 먼저 받음
    for _ in range(max_ticks):  # 최대 횟수까지 틱을 돌린다
        if service.delay() is None:  # 돌고 있지 않으면 재생이 끝난 것이다
            return bodies  # 모은 바이트를 반환
        lapse(clock, service, 1)  # 시계를 1초 보내 틱을 처리
        bodies.append(client.get("/api/state").content)  # 그때의 상태 바이트를 담는다
    # 끝나지 않으면 오류를 냄
    raise AssertionError(f"{max_ticks} tick 이 지나도 재생이 끝나지 않았다")


# 바이트마다 SHA-256 해시를 만드는 함수
def digests(bodies: list[bytes]) -> list[str]:
    return [hashlib.sha256(body).hexdigest() for body in bodies]  # 해시 16진수 문자열 목록을 반환


# 받은 것의 앞 절반만 쓰고 디스크가 찼다고 알리는 파일 대역
class Clip:
    # 진짜 파일을 감싼다
    def __init__(self, inner) -> None:
        self.inner = inner  # 속 파일을 둔다

    # 앞 절반만 쓰고 오류를 냄
    def write(self, data):
        self.inner.write(data[: len(data) // 2])  # 절반을 진짜로 기록
        raise OSError(errno.ENOSPC, "No space left on device")  # 디스크가 찼다고 알린다

    # with 문에 들어가면 자기를 반환
    def __enter__(self):
        return self  # 대역을 반환

    # with 문에서 나가면 속 파일의 마무리를 기록
    def __exit__(self, *crash):
        return self.inner.__exit__(*crash)  # 속 파일을 닫는다

    # 나머지 기능은 속 파일에 넘긴다
    def __getattr__(self, name):
        return getattr(self.inner, name)  # 속 파일의 같은 이름을 반환


# 이어쓰기로 여는 파일만 Clip 으로 바꾼다. 읽기는 그대로 둔다
def breakage(monkeypatch) -> None:
    origin = Path.open  # 원래 열기 함수를 기억

    # 이어쓰기면 대역으로 감싸 주는 열기 함수
    def surrogate(self, mode="r", *args, **kwargs):
        handle = origin(self, mode, *args, **kwargs)  # 먼저 진짜로 연다
        # 이어쓰기 모드면 절반만 쓰는 대역으로 감싼다
        return Clip(handle) if "a" in mode else handle

    monkeypatch.setattr(Path, "open", surrogate)  # 열기 함수를 바꿔 둔다
