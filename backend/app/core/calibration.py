from __future__ import annotations

import math
from .model import Params, State, storage
from dataclasses import dataclass, replace

OBSERVED_ZONES = ("A", "B")  # 수위 센서가 있는 구역. C 는 관측이 없어 보정하지 않음


@dataclass(frozen=True)
# 수위 센서 보정값(거리 mm → 수위)
class Sensor:
    install_height_mm: float  # 바닥에서 센서까지 높이(mm)
    zero_offset_mm: float  # 영점 오차(mm)
    scale: float  # 배율
    min_range_mm: float  # 가장 가까운 유효 거리(데드존, mm)
    max_range_mm: float  # 가장 먼 유효 거리(mm)

    @classmethod  # 클래스 메서드(인스턴스 없이 부름)
    # 설정 한 덩어리로 센서 보정값을 만듦
    def config(cls, cfg: dict) -> Sensor:
        return cls(
            install_height_mm=float(cfg["install_height_mm"]),
            zero_offset_mm=float(cfg["zero_offset_mm"]),
            scale=float(cfg["scale"]),
            min_range_mm=float(cfg["min_range_mm"]),
            max_range_mm=float(cfg["max_range_mm"]),
        )


@dataclass(frozen=True)
# 무게 센서 보정값
class Load:
    tare_g: float  # 빈 통 무게(g)

    @classmethod  # 클래스 메서드(인스턴스 없이 부름)
    # 설정 한 덩어리로 무게 보정값을 만듦
    def config(cls, cfg: dict) -> Load:
        return cls(tare_g=float(cfg["tare_g"]))


# 센서 거리(mm)를 수위(m)로 변환. 무효면 None, 설치 높이보다 먼 거리(바닥 아래)는 0
def waterline(dist_mm: float, sensor: Sensor) -> float | None:
    if not (math.isfinite(dist_mm) and sensor.min_range_mm <= dist_mm <= sensor.max_range_mm):
        return None
    level_m = (sensor.install_height_mm - dist_mm - sensor.zero_offset_mm) * sensor.scale / 1000.0
    return 0.0 if level_m < 0.0 else level_m  # 음수(바닥 아래)만 0. NaN 은 그대로(뒤에서 거름)


# 수위(m)를 센서 거리(mm)로 되돌림(위 변환의 역)
def gap(level_m: float, sensor: Sensor) -> float:
    return sensor.install_height_mm - sensor.zero_offset_mm - level_m * 1000.0 / sensor.scale


# 무게(g)를 배수량(m³)으로 변환. 물 1 g = 1 mL
def drainage(weight_g: float, load: Load) -> float:
    return (weight_g - load.tare_g) / 1e6  # (무게 − 빈 통 무게)를 m³ 로 변환


@dataclass(frozen=True)
# 보정 한 건의 기록
class Delta:
    zone: str  # 구역
    before_m3: float  # 보정 전 저장량(m³)
    after_m3: float  # 보정 후 저장량(m³)
    delta_m3: float  # 바뀐 양(m³)


# 관측 수위로 모델 상태를 보정. valid 관측만 넘김
def adjustment(
    state: State, observed_levels_m: dict[str, float], gain: float, params: Params
) -> tuple[State, tuple[Delta, ...]]:  # 새 상태와 구역별 보정 기록을 반환
    if not 0.0 <= gain <= 1.0:
        raise ValueError(f"보정 이득은 0~1 이어야 한다: {gain}")
    others = set(observed_levels_m) - set(OBSERVED_ZONES)  # 보정 대상이 아닌 구역이 섞였는지 확인
    if others:
        raise ValueError(f"관측 보정 대상이 아니다: {sorted(others)} (C 는 모델 추정)")

    V = dict(state.V)
    records = []
    for zone in OBSERVED_ZONES:
        if zone not in observed_levels_m:
            continue
        h_obs = observed_levels_m[zone]
        if not math.isfinite(h_obs):
            raise ValueError(f"{zone} 관측 수위가 유한하지 않다: {h_obs}")
        before = V[zone]
        after = before + gain * (storage(zone, max(0.0, h_obs), params) - before)
        V[zone] = after
        records.append(Delta(zone, before, after, after - before))
    delta = sum(r.delta_m3 for r in records)
    return replace(state, V=V, correction_m3=state.correction_m3 + delta), tuple(records)
