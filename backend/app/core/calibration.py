from __future__ import annotations

import math
from .model import Params, State, storage
from dataclasses import dataclass, replace

OBSERVED_ZONES = ("A", "B")  # 수위 센서가 있는 구역. C 는 관측이 없어 보정하지 않음


@dataclass(frozen=True)  # 바꿀 수 없는 값 묶음
# 수위 센서 보정값(거리 mm → 수위)
class Sensor:
    install_height_mm: float  # 바닥에서 센서까지 높이(mm)
    zero_offset_mm: float  # 영점 오차(mm)
    scale: float  # 배율
    min_range_mm: float  # 가장 가까운 유효 거리(데드존, mm)
    max_range_mm: float  # 가장 먼 유효 거리(mm)

    @classmethod  # 클래스 메서드(인스턴스 없이 부른다)
    # 설정 한 덩어리로 센서 보정값을 만듦
    def config(cls, cfg: dict) -> Sensor:
        return cls(  # 숫자로 바꿔 담는다
            install_height_mm=float(cfg["install_height_mm"]),  # 설치 높이
            zero_offset_mm=float(cfg["zero_offset_mm"]),  # 영점 오차
            scale=float(cfg["scale"]),  # 배율
            min_range_mm=float(cfg["min_range_mm"]),  # 최소 유효 거리
            max_range_mm=float(cfg["max_range_mm"]),  # 최대 유효 거리
        )


@dataclass(frozen=True)  # 바꿀 수 없는 값 묶음
# 무게 센서 보정값
class Load:
    tare_g: float  # 빈 통 무게(g)

    @classmethod  # 클래스 메서드(인스턴스 없이 부른다)
    # 설정 한 덩어리로 무게 보정값을 만듦
    def config(cls, cfg: dict) -> Load:
        return cls(tare_g=float(cfg["tare_g"]))  # 숫자로 바꿔 담는다


# 센서 거리(mm)를 수위(m)로 바꾼다. 무효면 None
def waterline(dist_mm: float, sensor: Sensor) -> float | None:
    # 거리가 [최소, 최대] 밖이거나 유한하지 않으면
    if not (math.isfinite(dist_mm) and sensor.min_range_mm <= dist_mm <= sensor.max_range_mm):
        return None  # 무효로 확인
    # 수위 = (설치 높이 − 거리 − 영점 오차) × 배율, mm 를 m 로
    return (sensor.install_height_mm - dist_mm - sensor.zero_offset_mm) * sensor.scale / 1000.0


# 수위(m)를 센서 거리(mm)로 되돌린다(위 변환의 역)
def gap(level_m: float, sensor: Sensor) -> float:
    # 가상 센서가 장치와 같은 거리 값을 만들 때 기록
    return sensor.install_height_mm - sensor.zero_offset_mm - level_m * 1000.0 / sensor.scale


# 무게(g)를 배수량(m³)으로 바꾼다. 물 1 g = 1 mL
def drainage(weight_g: float, load: Load) -> float:
    return (weight_g - load.tare_g) / 1e6  # (무게 − 빈 통 무게)를 m³ 로


@dataclass(frozen=True)  # 바꿀 수 없는 값 묶음
# 보정 한 건의 기록
class Delta:
    zone: str  # 구역
    before_m3: float  # 보정 전 저장량(m³)
    after_m3: float  # 보정 후 저장량(m³)
    delta_m3: float  # 바뀐 양(m³)


# 관측 수위로 모델 상태를 보정한다. valid 관측만 넘긴다
def adjustment(
    # 상태·관측 수위(m)·이득·모델 계수
    state: State, observed_levels_m: dict[str, float], gain: float, params: Params
) -> tuple[State, tuple[Delta, ...]]:  # 새 상태와 구역별 보정 기록을 반환
    if not 0.0 <= gain <= 1.0:  # 이득은 0~1 사이여야 함
        raise ValueError(f"보정 이득은 0~1 이어야 한다: {gain}")  # 아니면 오류를 냄
    others = set(observed_levels_m) - set(OBSERVED_ZONES)  # 보정 대상이 아닌 구역이 섞였는지 확인
    if others:  # 섞였으면
        # 오류를 낸다(C 는 모델 추정)
        raise ValueError(f"관측 보정 대상이 아니다: {sorted(others)} (C 는 모델 추정)")

    V = dict(state.V)  # 저장량을 복사해 고친다
    records = []  # 구역별 기록 모음
    for zone in OBSERVED_ZONES:  # 수위 센서가 있는 구역마다
        if zone not in observed_levels_m:  # 이번 관측에 없는 구역이면
            continue  # 건너뛴다
        h_obs = observed_levels_m[zone]  # 그 구역 관측 수위
        if not math.isfinite(h_obs):  # 유한하지 않으면
            raise ValueError(f"{zone} 관측 수위가 유한하지 않다: {h_obs}")  # 오류를 냄
        before = V[zone]  # 보정 전 저장량
        # 보정 후 = 전 + 이득 × (관측 저장량 − 전). 음수 수위는 0
        after = before + gain * (storage(zone, max(0.0, h_obs), params) - before)
        V[zone] = after  # 새 저장량을 적는다
        records.append(Delta(zone, before, after, after - before))  # 기록을 모음
    delta = sum(r.delta_m3 for r in records)  # 보정한 양의 합
    # 합을 correction_m3 에 쌓아 새 상태와 기록을 반환
    return replace(state, V=V, correction_m3=state.correction_m3 + delta), tuple(records)
