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
    return replace(
        baseline(params),
        V={z: storage(z, levels_m.get(z, 0.0), params) for z in ZONES},
    )


# 두 구역을 잇는 월류 통로를 찾는 도우미
def bridge(flows, a, b):
    (link,) = [lf for lf in flows.links if {lf.src, lf.dst} == {a, b}]
    return link



# 3.2 강우 유입: 60 mm/h 는 0.48 L/min 이고 면적 비율로 나뉘는지 검사
def test_rain_60mm_per_h_is_0_48_l_per_min_split_by_share(params):
    flows = flux(baseline(params), Conditions(rain_mm_per_h=60.0), params)
    total = sum(flows.rain_m3s.values())
    assert total * 1000 * 60 == pytest.approx(0.48)  # 합계가 0.48 L/min 이어야 함
    shares = {"A": 0.40, "B": 0.35, "C": 0.25}
    assert flows.rain_m3s == pytest.approx({z: total * s for z, s in shares.items()})



# 3.3 월류: C 에서 B 로 자유 월류가 흐르는지 검사
def test_free_overflow_from_c_to_b(params):
    # C 수면 0.070 이 경계 0.065 보다 0.005 높음. B 는 비어 s = 1
    flows = flux(point(params, C=0.010), Conditions(), params)
    link = bridge(flows, "C", "B")
    assert (link.src, link.dst) == ("C", "B")  # 흐름 방향이 C → B 여야 함
    assert link.q_m3s == pytest.approx(0.55 * 0.005**1.5)  # 유량이 0.55 × 수두^1.5 여야 함


# 하류가 잠기면 월류가 줄어드는지 검사
def test_submerged_overflow_is_reduced(params):
    # C 수면 0.070, B 수면 0.067: 수두 0.005, 하류 잠김 0.002
    flows = flux(point(params, B=0.047, C=0.010), Conditions(), params)
    s = (1 - (0.002 / 0.005) ** 1.5) ** 0.385
    assert bridge(flows, "C", "B").q_m3s == pytest.approx(0.55 * 0.005**1.5 * s)


# 설정과 반대로 A 에서 B 로 거꾸로 흐르는지 검사
def test_reverse_overflow_from_a_to_b(params):
    # A 수면 0.040 이 B 수면 0.030 보다 높음: 설정의 B→A 와 반대로 흐름
    flows = flux(point(params, A=0.040, B=0.010), Conditions(), params)
    link = bridge(flows, "A", "B")
    s = (1 - (0.005 / 0.015) ** 1.5) ** 0.385
    assert (link.src, link.dst) == ("A", "B")  # 흐름 방향이 A → B 여야 함
    assert link.q_m3s == pytest.approx(0.55 * 0.015**1.5 * s)  # 유량이 0.55 × 수두^1.5 × s 여야 함


# 문턱 아래이거나 수면이 같으면 월류가 없는지 검사
def test_no_overflow_below_sill_or_between_equal_surfaces(params):
    below = flux(point(params, B=0.004, C=0.004), Conditions(), params)
    assert [lf.q_m3s for lf in below.links] == [0.0, 0.0]
    equal = flux(point(params, A=0.040, B=0.020), Conditions(), params)
    assert bridge(equal, "A", "B").q_m3s == pytest.approx(0.0, abs=1e-9)



# 3.4 배수: 막힘별 오리피스 식을 따르는지 검사
def test_drain_follows_orifice_formula_per_blocked_inlet(params):
    state = point(params, A=0.020, B=0.010)
    cond = Conditions(blockage={"INLET-02": "partial", "INLET-03": "full"})
    drains = flux(state, cond, params).drains_m3s
    orifice = 0.6 * 0.00030  # 오리피스 식에 쓰는 계수 0.6 × 면적 0.0003
    assert set(drains) == {"INLET-01", "INLET-02", "INLET-03"}
    assert drains["INLET-01"] == pytest.approx(orifice * 1.0 * math.sqrt(2 * G * 0.020))
    assert drains["INLET-02"] == pytest.approx(orifice * 0.45 * math.sqrt(2 * G * 0.020))
    assert drains["INLET-03"] == pytest.approx(orifice * 0.08 * math.sqrt(2 * G * 0.010))



@pytest.mark.parametrize(
    "kwargs",
    [{"rain_mm_per_h": -1.0}, {"rain_mm_per_h": math.nan}, {"blockage": {"INLET-02": "half"}}],
)
# 잘못된 조건은 값 오류로 거부되는지 검사
def test_invalid_conditions_rejected(kwargs):
    with pytest.raises(ValueError):
        Conditions(**kwargs)


# 모르는 빗물받이는 거부되는지 검사
def test_unknown_inlet_rejected(params):
    with pytest.raises(ValueError):
        flux(baseline(params), Conditions(blockage={"INLET-09": "full"}), params)


# 계산 간격에 안 맞는 시간은 거부되는지 검사
def test_advance_rejects_duration_off_the_dt_grid(params):
    with pytest.raises(ValueError):
        evolution(baseline(params), Conditions(), params, 0.25)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["zones"]["A"].update(share=0.5),  # 구역 비율 합이 1.1 이 됨
        lambda c: c["zones"]["B"].update(S_m2=0.0),
        lambda c: c["links"].append({"from": "C", "to": "D", "sill_m": 0.1, "k": 0.5}),
        lambda c: c["inlets"]["INLET-01"].update(zone="D"),
        lambda c: c["blockage_open_ratio"].update(partial=1.5),
        lambda c: c.update(dt_s=0),
    ],
)
# 망가진 설정은 거부되는지 검사
def test_bad_config_rejected(config, mutate):
    cfg = copy.deepcopy(config)
    mutate(cfg)
    with pytest.raises(ValueError):
        Params.config(cfg)



# 수위 변화율(API rateMmSec)이 순유입 ÷ 저류 면적인지 검사
def test_level_rates_are_net_inflow_over_storage_area(params):
    # A 2 mm, B 10 mm, C 10 mm. B→A, C→B 로 월류가 생김
    state = point(params, A=0.002, B=0.010, C=0.010)
    cond = Conditions(rain_mm_per_h=90.0, blockage={"INLET-02": "partial"})
    rain = 90.0 / 3.6e6 * 0.48  # 전체 강우 유입(m³/s) = 비 세기 × 집수 면적 0.48 m²
    q_ba = 0.55 * 0.005**1.5  # B→A 월류량. A 수면 0.002 는 경계 아래라 s = 1
    q_cb = 0.55 * 0.005**1.5  # C→B 월류량. B 수면 0.030 도 C–B 경계 0.065 아래
    orifice = 0.6 * 0.00030  # 오리피스 계수 × 면적
    drain_a = orifice * (1.0 + 0.45) * math.sqrt(2 * G * 0.002)
    drain_b = orifice * 1.0 * math.sqrt(2 * G * 0.010)  # B 배수량: 3번(막히지 않음)
    rates = gradient(state, cond, params)  # 구역별 수위 변화율(m/s)을 구
    assert rates == pytest.approx(
        {
            # A: 비 + B→A 월류 − 배수, 나누기 저류 면적 0.10
            "A": (rain * 0.40 + q_ba - drain_a) / 0.10,
            # B: 비 + C→B 월류 − B→A 월류 − 배수, 면적 0.10
            "B": (rain * 0.35 + q_cb - q_ba - drain_b) / 0.10,
            "C": (rain * 0.25 - q_cb) / 0.08,  # C: 비 − C→B 월류, 면적 0.08
        }
    )


# 비가 없는 마른 상태면 변화율이 0 인지 검사
def test_level_rates_are_zero_when_dry_without_rain(params):
    assert gradient(baseline(params), Conditions(), params) == {
        "A": 0.0,
        "B": 0.0,
        "C": 0.0,
    }


# 수위 → 부피 → 수위로 돌아오면 같은지 검사
def test_level_volume_round_trip(params):
    for z in ZONES:
        # 수위 31.2 mm 를 부피로 바꿨다가 되돌림
        assert depth(z, storage(z, 0.0312, params), params) == pytest.approx(
            0.0312
        )



# 3.6 예측: 사본으로 돌리고 메타를 남기는지 검사
def test_prediction_runs_on_a_copy_and_records_metadata(config, params):
    state = evolution(baseline(params), Conditions(rain_mm_per_h=90.0), params, 60.0)
    cond = Conditions(rain_mm_per_h=90.0, blockage={"INLET-02": "full"})
    before = copy.deepcopy(state)
    p = forecast(
        state, cond, params, basis_elapsed_s=60.0, horizons_s=[10, 20, 30], valid_for_s=5.0
    )
    assert state == before
    for horizon in (10, 20, 30):
        future = evolution(state, cond, params, float(horizon))
        assert {z: p.levels_m[z][horizon] for z in ZONES} == {
            z: depth(z, future.V[z], params) for z in ZONES
        }
    assert (p.basis_elapsed_s, p.valid_for_s) == (60.0, 5.0)
    assert p.model_version == config["model_version"]
    assert p.assumptions["rain_mm_per_h"] == 90.0
    assert p.assumptions["blockage"] == {"INLET-02": "full"}



@pytest.fixture  # 4.3 센서 값 변환(결과는 SI). 테스트마다 새로 만드는 준비물
# A 구역 거리 센서 설정을 만드는 준비물
def probe(config):
    return Sensor.config(config["sensors"]["A"])


# 거리를 수위로 바꾸는 식을 검사
def test_distance_to_level(probe):
    assert waterline(412.0, probe) == pytest.approx(0.188)  # (600 − 412 − 0) × 1.0 mm = 0.188 m
    assert waterline(200.0, probe) == pytest.approx(0.400)  # 범위 끝 200 mm 도 유효(0.400 m)
    assert waterline(600.0, probe) == 0.0


OUTSIDE = {  # 범위 밖 거리 사례: 이름 → 센서에서 거리를 뽑는 식(설정 값을 베껴 쓰지 않음)
    "far-below-min": lambda s: s.min_range_mm - 50.0,
    "below-min": lambda s: s.min_range_mm - 0.1,
    "beyond-max": lambda s: s.max_range_mm + 0.1,
    "nan": lambda s: math.nan,
}


@pytest.mark.parametrize("edge", OUTSIDE.values(), ids=OUTSIDE.keys())
# 범위 밖 거리는 무효인지 검사
def test_distance_outside_range_is_invalid(probe, edge):
    assert waterline(edge(probe), probe) is None  # 무효(None)여야 함


# 설치 높이보다 먼 거리(바닥 아래)는 범위 안이면 수위 0 인지 검사. 설정값에 기대지 않고 센서를 만듦
def test_distance_beyond_the_install_height_reads_as_dry():
    sensor = Sensor(
        install_height_mm=600.0, zero_offset_mm=0.0, scale=1.0,
        min_range_mm=200.0, max_range_mm=650.0,  # 최대 범위가 설치 높이보다 멂
    )
    assert waterline(601.0, sensor) == 0.0
    assert waterline(650.0, sensor) == 0.0


# 센서 보정값이 유한하지 않으면 수위도 NaN 으로 남는지 검사(0 으로 바뀌면 뒤에서 거를 수 없음)
def test_a_nan_sensor_value_keeps_the_level_nan(probe):
    assert math.isnan(waterline(412.0, replace(probe, install_height_mm=math.nan)))


# 영점 보정값과 배율이 적용되는지 검사
def test_zero_offset_and_scale_apply(probe):
    sensor = replace(probe, zero_offset_mm=5.0, scale=1.1)
    assert waterline(412.0, sensor) == pytest.approx((600 - 412 - 5) * 1.1 / 1000)


# 수위에서 거리로 되돌리는 식이 보정의 역인지 검사
def test_distance_from_level_inverts_the_calibration(probe):
    assert gap(0.188, probe) == pytest.approx(412.0)
    sensor = replace(probe, zero_offset_mm=5.0, scale=1.1)
    for level_m in (0.0, 0.0312, 0.25):
        dist = gap(level_m, sensor)
        assert waterline(dist, sensor) == pytest.approx(level_m)


# 무게를 배수량으로 바꾸는 식을 검사
def test_weight_to_drained_volume(config):
    load = Load.config(config["sensors"]["load"])
    assert drainage(1840.0, load) == pytest.approx(1.84e-3)  # 1840 g = 1.84 L = 1.84e-3 m³
    assert drainage(1840.0, replace(load, tare_g=40.0)) == pytest.approx(1.80e-3)



# 3.7 관측 보정: 모델이 관측 쪽으로 움직이는지 검사
def test_correction_moves_model_toward_observation(params):
    state = point(params, A=0.020, B=0.010, C=0.005)
    corrected, records = adjustment(state, {"A": 0.030}, 0.3, params)
    # A 부피: 0.002 + 0.3 × (0.003 − 0.002) = 0.0023 m³
    assert corrected.V["A"] == pytest.approx(0.0023)
    assert (corrected.V["B"], corrected.V["C"]) == (state.V["B"], state.V["C"])
    (record,) = records
    assert (record.zone, record.before_m3, record.after_m3) == ("A", state.V["A"], corrected.V["A"])
    assert record.delta_m3 == pytest.approx(0.0003)
    assert corrected.correction_m3 == pytest.approx(0.0003)


# C 구역은 보정하지 않는지 검사
def test_c_is_never_corrected(params):
    with pytest.raises(ValueError):
        adjustment(baseline(params), {"C": 0.010}, 0.3, params)


# 음수 관측은 마른 것으로 치는지 검사
def test_negative_observation_counts_as_dry(params):
    state = point(params, A=0.010)
    corrected, _ = adjustment(state, {"A": -0.002}, 0.3, params)
    # 관측을 0 으로 보아 0.3 만큼 0 쪽으로 감
    assert corrected.V["A"] == pytest.approx(state.V["A"] * 0.7)
