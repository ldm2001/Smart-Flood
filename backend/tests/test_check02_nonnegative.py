import math
import pytest
from app.core.model import ZONES, Conditions, State, Underflow, baseline, step
from tests.scenarios import flood


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])
# 틱마다 저장량이 음수가 아닌지 검사
def test_volumes_stay_nonnegative_every_tick(runs, case):
    _, states = runs[case]
    negatives = [(t, z, s.V[z]) for t, s in enumerate(states) for z in ZONES if not s.V[z] >= 0.0]
    assert negatives == []


# 비 없이 간격이 크면 음수 대신 정확히 0 이 되는지 검사
def test_limiter_empties_zones_exactly_instead_of_going_negative(params):
    start = flood(params)
    end = step(start, Conditions(), params, dt=100.0)
    assert end.V == {z: 0.0 for z in ZONES}
    assert sum(end.drained_m3.values()) == pytest.approx(sum(start.V.values()), rel=1e-12)


@pytest.mark.parametrize("bad", [-1e-9, math.nan, math.inf])
# 잘못된 저장량이면 예외를 내는지 검사
def test_invalid_volume_raises(params, bad):
    state = State(
        V={"A": bad, "B": 0.0, "C": 0.0}, drained_m3=baseline(params).drained_m3
    )
    with pytest.raises(Underflow):
        step(state, Conditions(rain_mm_per_h=60.0), params)
