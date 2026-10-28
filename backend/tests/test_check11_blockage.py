import pytest
from app.core.model import Conditions, baseline, evolution
from app.core.predictor import forecast
from tests.scenarios import flood

RAINS_MM_PER_H = (30.0, 60.0, 90.0, 150.0)  # 시험할 강우 세기(mm/h)
A_INLET_SETS = (("INLET-01",), ("INLET-02",), ("INLET-01", "INLET-02"))


# 시작 상태를 종류별로 만드는 함수
def seed(kind, params, rain):
    if kind == "dry":
        return baseline(params)
    if kind == "warm":
        return evolution(baseline(params), Conditions(rain_mm_per_h=rain), params, 120.0)
    return flood(params)


@pytest.mark.parametrize("inlets", A_INLET_SETS, ids="+".join)
@pytest.mark.parametrize("rain", RAINS_MM_PER_H)
@pytest.mark.parametrize("kind", ["dry", "warm", "flooded"])
# 막힘이 심할수록 30초 후 A 수위가 오르는지 검사
def test_a_level_after_30s_rises_with_blockage(config, params, kind, rain, inlets):
    state = seed(kind, params, rain)
    a_30s = []
    for blockage in ("none", "partial", "full"):
        cond = Conditions(rain_mm_per_h=rain, blockage={inlet: blockage for inlet in inlets})
        prediction = forecast(  # 30초 후까지 예측
            state,
            cond,
            params,
            basis_elapsed_s=0.0,
            horizons_s=config["prediction"]["horizons_s"],
            valid_for_s=config["prediction"]["valid_for_s"],
        )
        a_30s.append(prediction.levels_m["A"][30])
    assert a_30s[0] < a_30s[1] < a_30s[2], a_30s  # 막힘이 심할수록 수위가 올라야 함(단조 증가)
