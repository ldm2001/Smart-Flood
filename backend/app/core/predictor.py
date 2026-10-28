from __future__ import annotations

from .model import ZONES, Conditions, Params, State, depth, evolution
from collections.abc import Iterable
from dataclasses import dataclass

ASSUMPTION_RULE = "현재 강우와 막힘이 예측 구간 동안 유지된다"  # 예측이 깔고 있는 가정(문장)


@dataclass(frozen=True)
# 예측 결과(현재 상태는 건드리지 않음)
class Prediction:
    basis_elapsed_s: float  # 입력 기준 시각(실험 경과 초)
    model_version: str  # 모델 버전
    valid_for_s: float  # 예측이 유효한 기간(초)
    assumptions: dict  # 가정 규칙과 그때 유지한 강우·막힘
    levels_m: dict[str, dict[int, float]]  # 구역 → {몇 초 뒤: 수위 m}


# +10·20·30초 같은 시점의 수위를 예측
def forecast(
    state: State,  # 지금 상태(복사본을 앞으로 돌림)
    cond: Conditions,
    params: Params,
    *,
    basis_elapsed_s: float,  # 입력 기준 시각(초)
    horizons_s: Iterable[int],  # 예측할 시점들(초)
    valid_for_s: float,  # 유효 기간(초)
) -> Prediction:
    levels: dict[str, dict[int, float]] = {z: {} for z in ZONES}
    future, t = state, 0
    for horizon in sorted({int(h) for h in horizons_s}):
        future = evolution(future, cond, params, float(horizon - t))
        t = horizon
        for z in ZONES:
            levels[z][horizon] = depth(z, future.V[z], params)  # 그 시점의 수위(m)를 적음
    return Prediction(
        basis_elapsed_s=basis_elapsed_s,
        model_version=params.model_version,
        valid_for_s=valid_for_s,
        assumptions={
            "rule": ASSUMPTION_RULE,
            "rain_mm_per_h": cond.rain_mm_per_h,  # 유지한 강우(mm/h)
            "blockage": dict(cond.blockage),
        },
        levels_m=levels,
    )
