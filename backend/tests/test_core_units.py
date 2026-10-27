import copy
import math
import pytest
from app.core.calibration import (
    Load,
    Sensor,
    adjustment,
    drainage,
    gap,
    waterline,
)
from app.core.model import (
    ZONES,
    Conditions,
    Params,
    baseline,
    depth,
    evolution,
    flux,
    gradient,
    storage,
)
from app.core.predictor import forecast
from dataclasses import replace

G = 9.81  # 중력가속도(m/s²)


# 구역별 수위(m)로 상태를 만드는 도우미
def point(params, **levels_m):
    return replace(  # 마른 초기 상태에서 부피만 바꾼 사본을 만듦
        baseline(params),  # 마른 초기 상태
        # 구역별 수위를 부피로 바꿔 넣는다(안 준 구역은 0)
        V={z: storage(z, levels_m.get(z, 0.0), params) for z in ZONES},
    )


# 두 구역을 잇는 월류 통로를 찾는 도우미
def bridge(flows, a, b):
    # 방향과 상관없이 a·b 를 잇는 통로 하나를 선택
    (link,) = [lf for lf in flows.links if {lf.src, lf.dst} == {a, b}]
    return link  # 그 통로를 반환



# 3.2 강우 유입: 60 mm/h 는 0.48 L/min 이고 면적 비율로 나뉘는지 검사
def test_rain_60mm_per_h_is_0_48_l_per_min_split_by_share(params):
    # 마른 상태에 60 mm/h 비를 주고 유량을 구
    flows = flux(baseline(params), Conditions(rain_mm_per_h=60.0), params)
    total = sum(flows.rain_m3s.values())  # 구역별 강우 유입을 모두 합산
    assert total * 1000 * 60 == pytest.approx(0.48)  # 합계가 0.48 L/min 이어야 함
    shares = {"A": 0.40, "B": 0.35, "C": 0.25}  # 구역별 면적 비율
    # 구역별 유입이 합계 × 비율이어야 함
    assert flows.rain_m3s == pytest.approx({z: total * s for z, s in shares.items()})



# 3.3 월류: C 에서 B 로 자유 월류가 흐르는지 검사
def test_free_overflow_from_c_to_b(params):
    # C 수면 0.070 이 경계 0.065 보다 0.005 높다. B 는 비어 s = 1
    flows = flux(point(params, C=0.010), Conditions(), params)
    link = bridge(flows, "C", "B")  # C–B 통로를 찾음
    assert (link.src, link.dst) == ("C", "B")  # 흐름 방향이 C → B 여야 함
    assert link.q_m3s == pytest.approx(0.55 * 0.005**1.5)  # 유량이 0.55 × 수두^1.5 여야 함


# 하류가 잠기면 월류가 줄어드는지 검사
def test_submerged_overflow_is_reduced(params):
    # C 수면 0.070, B 수면 0.067: 수두 0.005, 하류 잠김 0.002
    flows = flux(point(params, B=0.047, C=0.010), Conditions(), params)
    s = (1 - (0.002 / 0.005) ** 1.5) ** 0.385  # 잠김 보정 계수 s
    # 자유 월류 유량에 s 를 곱한 값이어야 함
    assert bridge(flows, "C", "B").q_m3s == pytest.approx(0.55 * 0.005**1.5 * s)


# 설정과 반대로 A 에서 B 로 거꾸로 흐르는지 검사
def test_reverse_overflow_from_a_to_b(params):
    # A 수면 0.040 이 B 수면 0.030 보다 높다: 설정의 B→A 와 반대로 흐른다
    flows = flux(point(params, A=0.040, B=0.010), Conditions(), params)
    link = bridge(flows, "A", "B")  # A–B 통로를 찾음
    s = (1 - (0.005 / 0.015) ** 1.5) ** 0.385  # 잠김 보정 계수 s
    assert (link.src, link.dst) == ("A", "B")  # 흐름 방향이 A → B 여야 함
    assert link.q_m3s == pytest.approx(0.55 * 0.015**1.5 * s)  # 유량이 0.55 × 수두^1.5 × s 여야 함


# 문턱 아래이거나 수면이 같으면 월류가 없는지 검사
def test_no_overflow_below_sill_or_between_equal_surfaces(params):
    # B·C 수위가 문턱보다 낮은 상태
    below = flux(point(params, B=0.004, C=0.004), Conditions(), params)
    assert [lf.q_m3s for lf in below.links] == [0.0, 0.0]  # 두 통로 모두 유량 0 이어야 함
    # A·B 수면이 둘 다 0.040 으로 같은 상태
    equal = flux(point(params, A=0.040, B=0.020), Conditions(), params)
    assert bridge(equal, "A", "B").q_m3s == pytest.approx(0.0, abs=1e-9)  # A–B 유량이 0 이어야 함



# 3.4 배수: 막힘별 오리피스 식을 따르는지 검사
def test_drain_follows_orifice_formula_per_blocked_inlet(params):
    state = point(params, A=0.020, B=0.010)  # A 20 mm, B 10 mm 상태
    # 2번은 부분 막힘, 3번은 완전 막힘
    cond = Conditions(blockage={"INLET-02": "partial", "INLET-03": "full"})
    drains = flux(state, cond, params).drains_m3s  # 빗물받이별 배수량을 구
    orifice = 0.6 * 0.00030  # 오리피스 식에 쓰는 계수 0.6 × 면적 0.0003
    # C 에는 빗물받이가 없어 셋뿐이어야 함
    assert set(drains) == {"INLET-01", "INLET-02", "INLET-03"}
    # 1번은 막힘 없음(열림 1.0)
    assert drains["INLET-01"] == pytest.approx(orifice * 1.0 * math.sqrt(2 * G * 0.020))
    # 2번은 부분 막힘(열림 0.45)
    assert drains["INLET-02"] == pytest.approx(orifice * 0.45 * math.sqrt(2 * G * 0.020))
    # 3번은 완전 막힘(열림 0.08), B 수위 기준
    assert drains["INLET-03"] == pytest.approx(orifice * 0.08 * math.sqrt(2 * G * 0.010))



@pytest.mark.parametrize(  # 입력 검증. 잘못된 조건마다 반복
    "kwargs",  # 조건 인자 이름
    # 음수 비, 숫자 아님(NaN), 모르는 막힘 종류
    [{"rain_mm_per_h": -1.0}, {"rain_mm_per_h": math.nan}, {"blockage": {"INLET-02": "half"}}],
)
# 잘못된 조건은 값 오류로 거부되는지 검사
def test_invalid_conditions_rejected(kwargs):
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        Conditions(**kwargs)  # 잘못된 조건을 만듦


# 모르는 빗물받이는 거부되는지 검사
def test_unknown_inlet_rejected(params):
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        # 없는 9번 빗물받이를 막았다고 반환
        flux(baseline(params), Conditions(blockage={"INLET-09": "full"}), params)


# 계산 간격에 안 맞는 시간은 거부되는지 검사
def test_advance_rejects_duration_off_the_dt_grid(params):
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        evolution(baseline(params), Conditions(), params, 0.25)  # 0.25 초는 계산 간격에 안 맞는다


@pytest.mark.parametrize(  # 망가뜨리는 방법마다 반복
    "mutate",  # 설정을 망가뜨리는 함수
    [  # 망가진 설정 사례들
        lambda c: c["zones"]["A"].update(share=0.5),  # 구역 비율 합이 1.1 이 됨
        lambda c: c["zones"]["B"].update(S_m2=0.0),  # B 구역 면적이 0
        # 없는 구역 D 로 가는 통로
        lambda c: c["links"].append({"from": "C", "to": "D", "sill_m": 0.1, "k": 0.5}),
        lambda c: c["inlets"]["INLET-01"].update(zone="D"),  # 빗물받이가 없는 구역 D 에 속
        lambda c: c["blockage_open_ratio"].update(partial=1.5),  # 열림 비율이 1 을 넘는다
        lambda c: c.update(dt_s=0),  # 계산 간격이 0
    ],
)
# 망가진 설정은 거부되는지 검사
def test_bad_config_rejected(config, mutate):
    cfg = copy.deepcopy(config)  # 설정을 깊은 복사
    mutate(cfg)  # 복사본을 망가뜨린다
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        Params.config(cfg)  # 모델 계수로 읽어 들인다



# 수위 변화율(API rateMmSec)이 순유입 ÷ 저류 면적인지 검사
def test_level_rates_are_net_inflow_over_storage_area(params):
    # A 2 mm, B 10 mm, C 10 mm. B→A, C→B 로 월류가 생김
    state = point(params, A=0.002, B=0.010, C=0.010)
    # 90 mm/h 비, 2번 부분 막힘
    cond = Conditions(rain_mm_per_h=90.0, blockage={"INLET-02": "partial"})
    rain = 90.0 / 3.6e6 * 0.48  # 전체 강우 유입(m³/s) = 비 세기 × 집수 면적 0.48 m²
    q_ba = 0.55 * 0.005**1.5  # B→A 월류량. A 수면 0.002 는 경계 아래라 s = 1
    q_cb = 0.55 * 0.005**1.5  # C→B 월류량. B 수면 0.030 도 C–B 경계 0.065 아래
    orifice = 0.6 * 0.00030  # 오리피스 계수 × 면적
    # A 배수량: 1번(열림)과 2번(부분 막힘)의 합
    drain_a = orifice * (1.0 + 0.45) * math.sqrt(2 * G * 0.002)
    drain_b = orifice * 1.0 * math.sqrt(2 * G * 0.010)  # B 배수량: 3번(막히지 않음)
    rates = gradient(state, cond, params)  # 구역별 수위 변화율(m/s)을 구
    assert rates == pytest.approx(  # 손으로 계산한 값과 같아야 함
        {  # 구역별 기대 변화율
            # A: 비 + B→A 월류 − 배수, 나누기 저류 면적 0.10
            "A": (rain * 0.40 + q_ba - drain_a) / 0.10,
            # B: 비 + C→B 월류 − B→A 월류 − 배수, 면적 0.10
            "B": (rain * 0.35 + q_cb - q_ba - drain_b) / 0.10,
            "C": (rain * 0.25 - q_cb) / 0.08,  # C: 비 − C→B 월류, 면적 0.08
        }
    )


# 비가 없는 마른 상태면 변화율이 0 인지 검사
def test_level_rates_are_zero_when_dry_without_rain(params):
    assert gradient(baseline(params), Conditions(), params) == {  # 마른 상태에 비가 없으면 변화율은
        "A": 0.0,  # A 는 0
        "B": 0.0,  # B 는 0
        "C": 0.0,  # C 는 0
    }


# 수위 → 부피 → 수위로 돌아오면 같은지 검사
def test_level_volume_round_trip(params):
    for z in ZONES:  # 구역마다
        # 수위 31.2 mm 를 부피로 바꿨다가 되돌린다
        assert depth(z, storage(z, 0.0312, params), params) == pytest.approx(
            0.0312  # 원래 수위와 같아야 함
        )



# 3.6 예측: 사본으로 돌리고 메타를 남기는지 검사
def test_prediction_runs_on_a_copy_and_records_metadata(config, params):
    # 90 mm/h 비로 60초 진행한 상태
    state = evolution(baseline(params), Conditions(rain_mm_per_h=90.0), params, 60.0)
    # 예측에 쓸 조건: 같은 비, 2번 완전 막힘
    cond = Conditions(rain_mm_per_h=90.0, blockage={"INLET-02": "full"})
    before = copy.deepcopy(state)  # 예측 전 상태를 복사해 둔다
    p = forecast(  # 예측
        # 기준 60초, 10·20·30초 뒤, 유효 5초
        state, cond, params, basis_elapsed_s=60.0, horizons_s=[10, 20, 30], valid_for_s=5.0
    )
    assert state == before  # 원래 상태는 안 바뀌어야 함
    for horizon in (10, 20, 30):  # 예측 시점마다
        future = evolution(state, cond, params, float(horizon))  # 실제로 그만큼 진행시켜 확인
        assert {z: p.levels_m[z][horizon] for z in ZONES} == {  # 예측 수위가
            z: depth(z, future.V[z], params) for z in ZONES  # 진행 결과의 수위와 같아야 함
        }
    # 기준 경과 초와 유효 시간(초)이 기록돼야 함
    assert (p.basis_elapsed_s, p.valid_for_s) == (60.0, 5.0)
    assert p.model_version == config["model_version"]  # 모델 버전이 설정과 같아야 함
    assert p.assumptions["rain_mm_per_h"] == 90.0  # 가정한 비 세기가 기록돼야 함
    assert p.assumptions["blockage"] == {"INLET-02": "full"}  # 가정한 막힘이 기록돼야 함



@pytest.fixture  # 4.3 센서 값 변환(결과는 SI). 테스트마다 새로 만드는 준비물
# A 구역 거리 센서 설정을 만드는 준비물
def probe(config):
    return Sensor.config(config["sensors"]["A"])  # 설정 파일의 A 센서 항목을 읽어 반환


# 거리를 수위로 바꾸는 식을 검사
def test_distance_to_level(probe):
    assert waterline(412.0, probe) == pytest.approx(0.188)  # (600 − 412 − 0) × 1.0 mm = 0.188 m
    assert waterline(200.0, probe) == pytest.approx(0.400)  # 범위 끝 200 mm 도 유효(0.400 m)
    assert waterline(600.0, probe) == 0.0  # 설치 높이와 같은 600 mm 는 수위 0


OUTSIDE = {  # 범위 밖 거리 사례: 이름 → 센서에서 거리를 뽑는 식(설정 값을 베껴 쓰지 않는다)
    "far-below-min": lambda s: s.min_range_mm - 50.0,  # 사각지대 한참 안쪽
    "below-min": lambda s: s.min_range_mm - 0.1,  # 최소 범위보다 조금 가까움
    "beyond-max": lambda s: s.max_range_mm + 0.1,  # 최대 범위보다 조금 멈
    "nan": lambda s: math.nan,  # 숫자가 아님
}


@pytest.mark.parametrize("edge", OUTSIDE.values(), ids=OUTSIDE.keys())  # 범위 밖 사례마다 반복
# 범위 밖 거리는 무효인지 검사
def test_distance_outside_range_is_invalid(probe, edge):
    assert waterline(edge(probe), probe) is None  # 무효(None)여야 함


# 영점 보정값과 배율이 적용되는지 검사
def test_zero_offset_and_scale_apply(probe):
    sensor = replace(probe, zero_offset_mm=5.0, scale=1.1)  # 영점 5 mm, 배율 1.1 로 바꾼 센서
    # (600 − 412 − 5) × 1.1 mm 를 m 로 바꾼 값이어야 함
    assert waterline(412.0, sensor) == pytest.approx((600 - 412 - 5) * 1.1 / 1000)


# 수위에서 거리로 되돌리는 식이 보정의 역인지 검사
def test_distance_from_level_inverts_the_calibration(probe):
    assert gap(0.188, probe) == pytest.approx(412.0)  # 수위 0.188 m 는 거리 412 mm
    sensor = replace(probe, zero_offset_mm=5.0, scale=1.1)  # 영점·배율을 바꾼 센서
    for level_m in (0.0, 0.0312, 0.25):  # 수위 몇 개로 반복
        dist = gap(level_m, sensor)  # 수위를 거리로 변환
        # 다시 수위로 바꾸면 처음 값이어야 함
        assert waterline(dist, sensor) == pytest.approx(level_m)


# 무게를 배수량으로 바꾸는 식을 검사
def test_weight_to_drained_volume(config):
    load = Load.config(config["sensors"]["load"])  # 설정의 무게 센서 항목을 읽음
    assert drainage(1840.0, load) == pytest.approx(1.84e-3)  # 1840 g = 1.84 L = 1.84e-3 m³
    # 빈 통 무게 40 g 을 빼면 1.80 L
    assert drainage(1840.0, replace(load, tare_g=40.0)) == pytest.approx(1.80e-3)



# 3.7 관측 보정: 모델이 관측 쪽으로 움직이는지 검사
def test_correction_moves_model_toward_observation(params):
    state = point(params, A=0.020, B=0.010, C=0.005)  # A 20 mm, B 10 mm, C 5 mm 상태
    # A 관측 30 mm, 보정 비율 0.3 으로 보결정
    corrected, records = adjustment(state, {"A": 0.030}, 0.3, params)
    # A 부피: 0.002 + 0.3 × (0.003 − 0.002) = 0.0023 m³
    assert corrected.V["A"] == pytest.approx(0.0023)
    # 관측 안 한 B·C 는 그대로여야 함
    assert (corrected.V["B"], corrected.V["C"]) == (state.V["B"], state.V["C"])
    (record,) = records  # 기록이 정확히 하나여야 함
    # 기록에 구역과 보정 전후 부피가 있어야 함
    assert (record.zone, record.before_m3, record.after_m3) == ("A", state.V["A"], corrected.V["A"])
    assert record.delta_m3 == pytest.approx(0.0003)  # 변화량이 0.0003 m³ 여야 함
    assert corrected.correction_m3 == pytest.approx(0.0003)  # 누적 보정량도 0.0003 m³ 여야 함


# C 구역은 보정하지 않는지 검사
def test_c_is_never_corrected(params):
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        adjustment(baseline(params), {"C": 0.010}, 0.3, params)  # C 관측을 주면 거부


# 음수 관측은 마른 것으로 치는지 검사
def test_negative_observation_counts_as_dry(params):
    state = point(params, A=0.010)  # A 10 mm 상태
    corrected, _ = adjustment(state, {"A": -0.002}, 0.3, params)  # A 관측 −2 mm 로 보결정
    # 관측을 0 으로 보아 0.3 만큼 0 쪽으로 감
    assert corrected.V["A"] == pytest.approx(state.V["A"] * 0.7)
