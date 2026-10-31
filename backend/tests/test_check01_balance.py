import pytest
from app.core.calibration import adjustment
from app.core.model import baseline, depth, evolution, step
from tests.scenarios import EXPERIMENT, EXPERIMENT_S, climate, downpour, flood

TOL_M3 = 1e-9  # 허용 오차(m³)
EXTERNAL_OVERFLOW_M3 = 0.0


# 시작·끝 상태로 물수지 잔차를 구하는 함수
def residual(start, end, rain_m3):
    drained = sum(end.drained_m3.values()) - sum(start.drained_m3.values())
    stored = sum(end.V.values()) - sum(start.V.values())
    corrected = end.correction_m3 - start.correction_m3  # 관측 보정량도 물수지 항(3.7)
    return rain_m3 - drained - EXTERNAL_OVERFLOW_M3 - stored + corrected


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])
# 실험 전체에서 물이 보존되는지 검사
def test_experiment_conserves_water(runs, case):
    params, states = runs[case]
    rain = downpour(EXPERIMENT, EXPERIMENT_S, params.model_area_m2)
    assert abs(residual(states[0], states[-1], rain)) <= TOL_M3


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])
# 모델이 센 강우 유입이 식과 같은지 검사
def test_rain_inflow_matches_spec_formula(runs, case):
    params, states = runs[case]
    rain = downpour(EXPERIMENT, EXPERIMENT_S, params.model_area_m2)
    assert abs((states[-1].rain_m3 - states[0].rain_m3) - rain) <= TOL_M3


# 한 걸음이 커서 비례 축소가 일어나도 물이 보존되는지 검사(3.5)
def test_limiter_step_conserves_water(params):
    start = flood(params)
    end = step(start, climate(EXPERIMENT, 0), params, dt=100.0)
    rain = 60.0 / 3.6e6 * params.model_area_m2 * 100.0  # 그 동안 내린 비의 양(60 mm/h)
    assert abs(residual(start, end, rain)) <= TOL_M3


# 관측 보정을 섞어도 물이 보존되는지 검사
def test_experiment_with_observation_correction_conserves_water(config, params):
    state = start = baseline(params)
    for t in range(EXPERIMENT_S):  # 실험 시간 동안 1초씩 반복
        state = evolution(state, climate(EXPERIMENT, t), params, 1.0)
        observed = {  # 가짜 관측 수위(m)를 만듦
            "A": depth("A", state.V["A"], params) * 1.2 + 0.001,  # A 는 실제보다 20 % 높게 + 1 mm
            "B": depth("B", state.V["B"], params) * 0.8,  # B 는 실제보다 20 % 낮게
        }
        state, _ = adjustment(state, observed, config["correction"]["gain"], params)
    rain = downpour(EXPERIMENT, EXPERIMENT_S, params.model_area_m2)
    assert state.correction_m3 != 0.0
    assert abs(residual(start, state, rain)) <= TOL_M3
