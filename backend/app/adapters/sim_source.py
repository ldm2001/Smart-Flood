from __future__ import annotations

import random
from app.core.calibration import (
    OBSERVED_ZONES,
    Load,
    Sensor,
    gap,
)
from app.core.model import (
    Conditions,
    Params,
    baseline,
    depth,
    evolution,
)
from dataclasses import replace

DEVICE_ID = "esp32_1"  # 가상 장치 이름


# 참값 계수: 저장 면적·월류·배수 계수를 ±ratio 로 섞는다
def variant(params: Params, ratio: float, rng: random.Random) -> Params:
    if not 0.0 <= ratio < 1.0:  # 비율은 0 이상 1 미만이어야 함
        raise ValueError(f"섭동 비율은 0 이상 1 미만이어야 한다: {ratio}")  # 아니면 오류를 냄

    # 값 하나를 (1 ± 비율) 배로 변환
    def jitter(value: float) -> float:
        return value * (1.0 + rng.choice((-1.0, 1.0)) * ratio)  # 부호는 rng 가 결정

    # 구역 저장 면적 S 를 흔든다
    zones = {z: replace(zone, S_m2=jitter(zone.S_m2)) for z, zone in params.zones.items()}
    # 연결부 월류 계수 k 를 흔든다
    links = tuple(replace(link, k=jitter(link.k)) for link in params.links)
    # 유입구 배수 계수 Cd 를 흔든다
    inlets = {i: replace(inlet, Cd=jitter(inlet.Cd)) for i, inlet in params.inlets.items()}
    # 바닥·경계 높이와 강우 배분은 그대로 둔다
    return replace(params, zones=zones, links=links, inlets=inlets)


# 가상 센서: 참값 모델로 장치와 같은 값을 낸다(성능 근거 아님)
class Sim:
    # 설정으로 가상 센서를 만듦
    def __init__(self, config: dict) -> None:
        sim = config["sim"]  # sim 설정 부분
        self._seed = sim["seed"]  # 시드(난수 고정값)
        self._noise_mm = float(sim["noise_mm"])  # 거리 잡음 크기(mm)
        self.truth_params = variant(  # 참값 모델 계수: 설정값을 조금 섞은 것
            Params.config(config),  # 설정에서 읽은 계수
            float(sim["truth_perturbation"]),  # 섞는 비율
            random.Random(f"{self._seed}/truth"),  # 참값용 난수(시드 고정)
        )
        # A·B 거리 센서 보정값
        self._sensors = {z: Sensor.config(config["sensors"][z]) for z in OBSERVED_ZONES}
        self._load = Load.config(config["sensors"]["load"])  # 무게 센서 보정값
        self._boots = 0  # 재부팅 횟수
        self.origin()  # 첫 회차를 시작

    # 새 회차: 참값은 마른 상태, 난수는 처음부터
    def origin(self) -> None:
        self._boots += 1  # 재부팅한 것처럼 횟수를 올림
        self._boot_id = f"sim{self._boots}"  # 그래서 bootId 가 바뀐다
        self._noise = random.Random(f"{self._seed}/noise")  # 잡음 난수를 처음으로 되돌린다
        self._seq = 0  # seq 는 1 부터 다시 센다
        self._last_s = 0.0  # 마지막 틱 시각을 0 으로
        self.truth_state = baseline(self.truth_params)  # 참값을 마른 상태로

    # 한 틱 분량의 ingest 형식 메시지를 냄
    def inbox(self, elapsed_s: float, cond: Conditions) -> list[dict]:
        duration_s = elapsed_s - self._last_s  # 지난 틱 이후 흐른 시간(초)
        # 참값을 그 시간만큼 앞으로 돌린다
        self.truth_state = evolution(self.truth_state, cond, self.truth_params, duration_s)
        self._last_s = elapsed_s  # 마지막 틱 시각을 갱신
        self._seq += 1  # 순번을 하나 올림
        readings = {}  # 센서 읽음 값 모음
        for z in OBSERVED_ZONES:  # 수위 센서 구역마다
            level_m = depth(z, self.truth_state.V[z], self.truth_params)  # 참값 수위(m)
            distance = gap(level_m, self._sensors[z])  # 수위를 센서 거리(mm)로 변환
            # 거리에 시드 고정 잡음을 합산
            readings[f"dist{z}_mm"] = distance + self._noise.gauss(0.0, self._noise_mm)
        # 누적 배수량을 무게(g)로 바꿔 빈 통 무게를 합산
        readings["weight_g"] = sum(self.truth_state.drained_m3.values()) * 1e6 + self._load.tare_g
        return [  # 메시지 한 개짜리 목록(C 참값은 밖으로 안 낸다)
            {  # 메시지 본문
                "deviceId": DEVICE_ID,  # 장치 이름
                "bootId": self._boot_id,  # 부팅 ID
                "seq": self._seq,  # 순번
                "tMs": round(elapsed_s * 1000),  # 경과 시간(ms)
                "readings": readings,  # 센서 읽음 값
                "sensorStatus": {"A": "ok", "B": "ok", "load": "ok"},  # 센서 상태는 모두 정상
            }
        ]
