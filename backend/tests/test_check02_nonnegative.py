import math
import pytest
from app.core.model import ZONES, Conditions, State, Underflow, baseline, step
from tests.scenarios import flood


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])  # 사례 세 가지로 반복
# 틱마다 저장량이 음수가 아닌지 검사
def test_volumes_stay_nonnegative_every_tick(runs, case):
    _, states = runs[case]  # 사례의 상태 목록만 꺼냄
    # (초, 구역, 저장량) 중 음수인 것을 모음
    negatives = [(t, z, s.V[z]) for t, s in enumerate(states) for z in ZONES if not s.V[z] >= 0.0]
    assert negatives == []  # 하나도 없어야 함


# 비 없이 간격이 크면 음수 대신 정확히 0 이 되는지 검사
def test_limiter_empties_zones_exactly_instead_of_going_negative(params):
    start = flood(params)  # 물이 찬 시작 상태
    end = step(start, Conditions(), params, dt=100.0)  # 비 없이 100 초 한 걸음 감
    assert end.V == {z: 0.0 for z in ZONES}  # 모든 구역이 정확히 0 이어야 함
    # 배수된 양이 처음 저장량과 같아야 함
    assert sum(end.drained_m3.values()) == pytest.approx(sum(start.V.values()), rel=1e-12)


@pytest.mark.parametrize("bad", [-1e-9, math.nan, math.inf])  # 잘못된 저장량 세 가지로 반복
# 잘못된 저장량이면 예외를 내는지 검사
def test_invalid_volume_raises(params, bad):
    state = State(  # 상태 묶음을 만듦
        # A 만 잘못된 값, 나머지는 0, 배수량은 기준 값
        V={"A": bad, "B": 0.0, "C": 0.0}, drained_m3=baseline(params).drained_m3
    )
    with pytest.raises(Underflow):  # Underflow 예외가 나야 함
        step(state, Conditions(rain_mm_per_h=60.0), params)  # 비 속에서 한 걸음 감
