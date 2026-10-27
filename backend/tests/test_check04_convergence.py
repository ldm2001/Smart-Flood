import pytest
from app.core.model import ZONES, depth
from dataclasses import replace
from tests.scenarios import EXPERIMENT, EXPERIMENT_S, flood, stress, trace

LIMIT_M = 0.001  # 허용 수위 차이(m)


# 두 간격으로 돌려 구역별 수위 차이의 최댓값을 구하는 함수
def spread(params, start_for):
    # 간격 0.1 초와 0.05 초 계수를 만듦
    coarse_p, fine_p = replace(params, dt_s=0.1), replace(params, dt_s=0.05)
    # 굵은 간격으로 시나리오를 돌린다
    coarse = trace(coarse_p, EXPERIMENT, EXPERIMENT_S, start_for(coarse_p))
    # 가는 간격으로 시나리오를 돌린다
    fine = trace(fine_p, EXPERIMENT, EXPERIMENT_S, start_for(fine_p))
    return {  # 구역 이름 → 최대 차이를 반환
        z: max(  # 구역마다 최댓값을 구
            abs(depth(z, c.V[z], params) - depth(z, f.V[z], params))  # 같은 틱의 수위 차이 절댓값
            # 두 목록을 한 쌍씩 짝짓는다(길이가 같아야 함)
            for c, f in zip(coarse, fine, strict=True)
        )
        for z in ZONES  # 모든 구역에 대해
    }


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])  # 사례 세 가지로 반복
# 간격을 절반으로 줄여도 수위가 1 mm 안에서 같은지 검사
def test_halving_dt_moves_levels_at_most_1mm(config, params, case):
    base = stress(config) if case == "stressed" else params  # 가혹 사례만 가혹한 계수를 기록
    start_for = flood if case == "flooded" else (lambda _p: None)  # 물이 찬 사례만 찬 상태에서 시작
    gaps = spread(base, start_for)  # 구역별 최대 차이를 구
    assert all(gap <= LIMIT_M for gap in gaps.values()), gaps  # 모두 허용 차이 이하여야 함
