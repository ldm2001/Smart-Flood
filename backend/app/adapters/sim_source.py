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

DEVICE_ID = "esp32_1"


# 참값 계수: 저장 면적·월류·배수 계수를 ±ratio 로 섞음
def variant(params: Params, ratio: float, rng: random.Random) -> Params:
    if not 0.0 <= ratio < 1.0:
        raise ValueError(f"섭동 비율은 0 이상 1 미만이어야 한다: {ratio}")

    # 값 하나를 (1 ± 비율) 배로 변환
    def jitter(value: float) -> float:
        return value * (1.0 + rng.choice((-1.0, 1.0)) * ratio)

    zones = {z: replace(zone, S_m2=jitter(zone.S_m2)) for z, zone in params.zones.items()}
    links = tuple(replace(link, k=jitter(link.k)) for link in params.links)
    inlets = {i: replace(inlet, Cd=jitter(inlet.Cd)) for i, inlet in params.inlets.items()}
    return replace(params, zones=zones, links=links, inlets=inlets)


# 가상 센서: 참값 모델로 장치와 같은 값을 냄(성능 근거 아님)
class Sim:
    # 설정으로 가상 센서를 만듦
    def __init__(self, config: dict) -> None:
        sim = config["sim"]
        self._seed = sim["seed"]  # 시드(난수 고정값)
        self._noise_mm = float(sim["noise_mm"])  # 거리 잡음 크기(mm)
        self.truth_params = variant(  # 참값 모델 계수: 설정값을 조금 섞은 것
            Params.config(config),
            float(sim["truth_perturbation"]),
            random.Random(f"{self._seed}/truth"),  # 참값용 난수(시드 고정)
        )
        self._sensors = {z: Sensor.config(config["sensors"][z]) for z in OBSERVED_ZONES}
        self._load = Load.config(config["sensors"]["load"])
        self._boots = 0
        self.origin()

    # 새 회차: 참값은 마른 상태, 난수는 처음부터
    def origin(self) -> None:
        self._boots += 1
        self._boot_id = f"sim{self._boots}"  # 그래서 bootId 가 바뀜
        self._noise = random.Random(f"{self._seed}/noise")  # 잡음 난수를 처음으로 되돌림
        self._seq = 0  # seq 는 1 부터 다시 셈
        self._last_s = 0.0
        self.truth_state = baseline(self.truth_params)

    # 한 틱 분량의 ingest 형식 메시지를 냄
    def inbox(self, elapsed_s: float, cond: Conditions) -> list[dict]:
        duration_s = elapsed_s - self._last_s  # 지난 틱 이후 흐른 시간(초)
        self.truth_state = evolution(self.truth_state, cond, self.truth_params, duration_s)
        self._last_s = elapsed_s
        self._seq += 1
        readings = {}
        for z in OBSERVED_ZONES:
            level_m = depth(z, self.truth_state.V[z], self.truth_params)  # 참값 수위(m)
            distance = gap(level_m, self._sensors[z])  # 수위를 센서 거리(mm)로 변환
            readings[f"dist{z}_mm"] = distance + self._noise.gauss(0.0, self._noise_mm)
        # 누적 배수량을 무게(g)로 바꿔 빈 통 무게를 합산
        readings["weight_g"] = sum(self.truth_state.drained_m3.values()) * 1e6 + self._load.tare_g
        return [  # 메시지 한 개짜리 목록(C 참값은 밖으로 안 냄)
            {
                "deviceId": DEVICE_ID,
                "bootId": self._boot_id,
                "seq": self._seq,
                "tMs": round(elapsed_s * 1000),  # 경과 시간(ms)
                "readings": readings,
                "sensorStatus": {"A": "ok", "B": "ok", "load": "ok"},
            }
        ]
