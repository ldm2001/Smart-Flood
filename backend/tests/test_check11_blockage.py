import pytest
from app.core.model import Conditions, baseline, evolution
from app.core.predictor import forecast
from tests.scenarios import flood

RAINS_MM_PER_H = (30.0, 60.0, 90.0, 150.0)  # 시험할 강우 세기(mm/h)
# A 구역에 속한 빗물받이 조합
A_INLET_SETS = (("INLET-01",), ("INLET-02",), ("INLET-01", "INLET-02"))


# 시작 상태를 종류별로 만드는 함수
def seed(kind, params, rain):
    if kind == "dry":  # 마른 상태면
        return baseline(params)  # 기준 상태를 반환
    if kind == "warm":  # 데운 상태면
        # 막힘 없이 같은 비를 2분 맞힌 상태를 반환
        return evolution(baseline(params), Conditions(rain_mm_per_h=rain), params, 120.0)
    return flood(params)  # 그 밖에는 물이 찬 상태를 반환


@pytest.mark.parametrize("inlets", A_INLET_SETS, ids="+".join)  # 빗물받이 조합 세 가지로 반복
@pytest.mark.parametrize("rain", RAINS_MM_PER_H)  # 강우 세기 네 가지로 반복
@pytest.mark.parametrize("kind", ["dry", "warm", "flooded"])  # 시작 상태 세 가지로 반복
# 막힘이 심할수록 30초 후 A 수위가 오르는지 검사
def test_a_level_after_30s_rises_with_blockage(config, params, kind, rain, inlets):
    state = seed(kind, params, rain)  # 시작 상태를 만듦
    a_30s = []  # 막힘 단계별 30초 후 A 수위를 모을 목록
    for blockage in ("none", "partial", "full"):  # 막힘 단계를 차례로 확인
        # 비와 막힘 조건을 만듦
        cond = Conditions(rain_mm_per_h=rain, blockage={inlet: blockage for inlet in inlets})
        prediction = forecast(  # 30초 후까지 예측
            state,  # 시작 상태
            cond,  # 조건
            params,  # 모델 계수
            basis_elapsed_s=0.0,  # 예측 기준 시각은 0 초
            horizons_s=config["prediction"]["horizons_s"],  # 예측 시점 목록은 설정에서 읽음
            valid_for_s=config["prediction"]["valid_for_s"],  # 예측 유효 시간도 설정에서 읽음
        )
        a_30s.append(prediction.levels_m["A"][30])  # 30초 후 A 수위를 담는다
    assert a_30s[0] < a_30s[1] < a_30s[2], a_30s  # 막힘이 심할수록 수위가 올라야 한다(단조 증가)
