import pytest
from app.core.model import ZONES, depth
from dataclasses import replace
from tests.scenarios import EXPERIMENT, EXPERIMENT_S, flood, stress, trace

LIMIT_M = 0.001  # 허용 수위 차이(m)


# 두 간격으로 돌려 구역별 수위 차이의 최댓값을 구하는 함수
def spread(params, start_for):
    coarse_p, fine_p = params, replace(params, dt_s=params.dt_s / 2)  # 설정 dt 와 그 절반
    coarse = trace(coarse_p, EXPERIMENT, EXPERIMENT_S, start_for(coarse_p))
    fine = trace(fine_p, EXPERIMENT, EXPERIMENT_S, start_for(fine_p))
    return {  # 구역 이름 → 최대 차이를 반환
        z: max(
            abs(depth(z, c.V[z], params) - depth(z, f.V[z], params))
            for c, f in zip(coarse, fine, strict=True)
        )
        for z in ZONES
    }


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])
# 간격을 절반으로 줄여도 수위가 1 mm 안에서 같은지 검사
def test_halving_dt_moves_levels_at_most_1mm(config, params, case):
    base = stress(config) if case == "stressed" else params
    start_for = flood if case == "flooded" else (lambda _p: None)
    gaps = spread(base, start_for)
    assert all(gap <= LIMIT_M for gap in gaps.values()), gaps
