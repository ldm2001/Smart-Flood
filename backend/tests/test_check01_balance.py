import pytest
from app.core.calibration import adjustment
from app.core.model import baseline, depth, evolution, step
from tests.scenarios import EXPERIMENT, EXPERIMENT_S, climate, downpour, flood

TOL_M3 = 1e-9  # 허용 오차(m³)
EXTERNAL_OVERFLOW_M3 = 0.0  # 모형 밖으로 넘치는 경계가 없어 외부 월류는 0 이다


# 시작·끝 상태로 물수지 잔차를 구하는 함수
def residual(start, end, rain_m3):
    drained = sum(end.drained_m3.values()) - sum(start.drained_m3.values())  # 이 구간에 배수된 양
    stored = sum(end.V.values()) - sum(start.V.values())  # 이 구간에 저장량이 바뀐 양
    corrected = end.correction_m3 - start.correction_m3  # 관측 보정량도 물수지 항이다(3.7)
    # 내린 비 − 배수 − 외부월류 − 저장 변화 + 보정
    return rain_m3 - drained - EXTERNAL_OVERFLOW_M3 - stored + corrected


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])  # 사례 세 가지로 반복
# 실험 전체에서 물이 보존되는지 검사
def test_experiment_conserves_water(runs, case):
    params, states = runs[case]  # 사례의 계수와 상태 목록을 꺼냄
    rain = downpour(EXPERIMENT, EXPERIMENT_S, params.model_area_m2)  # 식으로 구한 누적 강우량
    # 잔차 절댓값이 허용 오차 이하여야 함
    assert abs(residual(states[0], states[-1], rain)) <= TOL_M3


@pytest.mark.parametrize("case", ["default", "stressed", "flooded"])  # 사례 세 가지로 반복
# 모델이 센 강우 유입이 식과 같은지 검사
def test_rain_inflow_matches_spec_formula(runs, case):
    params, states = runs[case]  # 사례의 계수와 상태 목록을 꺼냄
    rain = downpour(EXPERIMENT, EXPERIMENT_S, params.model_area_m2)  # 식으로 구한 누적 강우량
    # 모델이 센 강우량 증가분이 식과 같아야 함
    assert abs((states[-1].rain_m3 - states[0].rain_m3) - rain) <= TOL_M3


# 한 걸음이 커서 비례 축소가 일어나도 물이 보존되는지 검사(3.5)
def test_limiter_step_conserves_water(params):
    start = flood(params)  # 물이 찬 시작 상태
    end = step(start, climate(EXPERIMENT, 0), params, dt=100.0)  # 간격 100 초로 한 걸음 감
    rain = 60.0 / 3.6e6 * params.model_area_m2 * 100.0  # 그 동안 내린 비의 양(60 mm/h)
    assert abs(residual(start, end, rain)) <= TOL_M3  # 잔차가 허용 오차 이하여야 함


# 관측 보정을 섞어도 물이 보존되는지 검사
def test_experiment_with_observation_correction_conserves_water(config, params):
    state = start = baseline(params)  # 시작 상태를 기억해 둔다
    for t in range(EXPERIMENT_S):  # 실험 시간 동안 1초씩 반복
        state = evolution(state, climate(EXPERIMENT, t), params, 1.0)  # 한 걸음 계산
        observed = {  # 가짜 관측 수위(m)를 만듦
            "A": depth("A", state.V["A"], params) * 1.2 + 0.001,  # A 는 실제보다 20 % 높게 + 1 mm
            "B": depth("B", state.V["B"], params) * 0.8,  # B 는 실제보다 20 % 낮게
        }
        # 관측에 맞게 상태를 보결정
        state, _ = adjustment(state, observed, config["correction"]["gain"], params)
    rain = downpour(EXPERIMENT, EXPERIMENT_S, params.model_area_m2)  # 식으로 구한 누적 강우량
    assert state.correction_m3 != 0.0  # 보정이 실제로 일어났어야 함
    assert abs(residual(start, state, rain)) <= TOL_M3  # 잔차가 허용 오차 이하여야 함
