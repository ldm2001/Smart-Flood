from __future__ import annotations

from .model import ZONES, Conditions, Params, State, depth, evolution
from collections.abc import Iterable
from dataclasses import dataclass

ASSUMPTION_RULE = "현재 강우와 막힘이 예측 구간 동안 유지된다"  # 예측이 깔고 있는 가정(문장)


@dataclass(frozen=True)  # 바꿀 수 없는 값 묶음
# 예측 결과(현재 상태는 건드리지 않는다)
class Prediction:
    basis_elapsed_s: float  # 입력 기준 시각(실험 경과 초)
    model_version: str  # 모델 버전
    valid_for_s: float  # 예측이 유효한 기간(초)
    assumptions: dict  # 가정 규칙과 그때 유지한 강우·막힘
    levels_m: dict[str, dict[int, float]]  # 구역 → {몇 초 뒤: 수위 m}


# +10·20·30초 같은 시점의 수위를 예측
def forecast(
    state: State,  # 지금 상태(복사본을 앞으로 돌린다)
    cond: Conditions,  # 강우·막힘 조건
    params: Params,  # 모델 계수
    *,  # 아래는 이름으로만 넘긴다
    basis_elapsed_s: float,  # 입력 기준 시각(초)
    horizons_s: Iterable[int],  # 예측할 시점들(초)
    valid_for_s: float,  # 유효 기간(초)
) -> Prediction:  # 예측 결과를 반환
    levels: dict[str, dict[int, float]] = {z: {} for z in ZONES}  # 구역마다 빈 수위표를 만듦
    future, t = state, 0  # 미래 상태와 지난 시점
    for horizon in sorted({int(h) for h in horizons_s}):  # 시점을 작은 순서로, 중복 없이
        # 지난 시점부터 이번 시점까지 앞으로 돌린다
        future = evolution(future, cond, params, float(horizon - t))
        t = horizon  # 돌린 시점을 기억
        for z in ZONES:  # 구역마다
            levels[z][horizon] = depth(z, future.V[z], params)  # 그 시점의 수위(m)를 적는다
    return Prediction(  # 예측 묶음을 만듦
        basis_elapsed_s=basis_elapsed_s,  # 기준 시각
        model_version=params.model_version,  # 모델 버전
        valid_for_s=valid_for_s,  # 유효 기간
        assumptions={  # 가정 묶음
            "rule": ASSUMPTION_RULE,  # 가정 규칙 문장
            "rain_mm_per_h": cond.rain_mm_per_h,  # 유지한 강우(mm/h)
            "blockage": dict(cond.blockage),  # 유지한 막힘
        },
        levels_m=levels,  # 시점별 수위표
    )
