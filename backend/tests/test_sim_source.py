import copy
import json
import pytest
import random
import statistics
from app.adapters.sim_source import Sim, variant
from app.core.calibration import Sensor, gap
from app.core.model import Conditions, baseline, depth, evolution
from app.schemas import Message

HEAVY = Conditions(90.0, {"INLET-02": "partial"})


# 초 수만큼 매초 메시지를 모아 목록으로 주는 도우미
def samples(sim, seconds, cond=HEAVY):
    return [message for t in range(1, seconds + 1) for message in sim.inbox(float(t), cond)]


# 설정에서 A·B 구역의 센서 모델을 만드는 도우미
def gauges(config):
    return {z: Sensor.config(config["sensors"][z]) for z in "AB"}


# 메시지가 장치와 같은 형식인지 검사
def test_messages_use_the_device_format(config):
    first, second = samples(Sim(config), 2)
    for message in (first, second):
        Message.model_validate(message)
        assert set(message) == {"deviceId", "bootId", "seq", "tMs", "readings", "sensorStatus"}
        assert message["deviceId"] == "esp32_1"
        assert set(message["readings"]) == {"distA_mm", "distB_mm", "weight_g"}
        assert message["sensorStatus"] == {"A": "ok", "B": "ok", "load": "ok"}
        json.dumps(message, allow_nan=False)
    assert (first["seq"], first["tMs"]) == (1, 1000)
    assert (second["seq"], second["tMs"]) == (2, 2000)
    assert first["bootId"] == second["bootId"]


# 같은 시드면 메시지가 같은지 검사
def test_same_seed_gives_the_same_messages(config):
    assert samples(Sim(config), 20) == samples(Sim(config), 20)


# 초기화하면 새 부팅으로 같은 측정값이 다시 나오는지 검사
def test_reset_replays_the_readings_under_a_new_boot(config):
    sim = Sim(config)
    first = samples(sim, 10)
    sim.origin()
    second = samples(sim, 10)
    assert [m["readings"] for m in second] == [m["readings"] for m in first]
    assert {m["bootId"] for m in first} == {"sim1"}
    assert {m["bootId"] for m in second} == {"sim2"}
    assert [m["seq"] for m in second] == list(range(1, 11))


# 시드가 다르면 측정값이 다른지 검사
def test_another_seed_gives_other_readings(config):
    cfg = copy.deepcopy(config)
    cfg["sim"]["seed"] += 1
    mine = [m["readings"] for m in samples(Sim(cfg), 10)]
    assert mine != [m["readings"] for m in samples(Sim(config), 10)]



# 설정한 섭동 비율이 명세 범위인지 검사
def test_configured_perturbation_is_in_the_spec_range(config):
    assert 0.10 <= config["sim"]["truth_perturbation"] <= 0.20


# 참값 모델이 저장 면적·월류 계수·배수 계수를 ±비율만큼 바꾸는지 검사
def test_truth_model_perturbs_storage_weirs_and_inlets(config, params):
    ratio = config["sim"]["truth_perturbation"]
    truth = Sim(config).truth_params
    for z, base in params.zones.items():
        mine = truth.zones[z]
        assert abs(mine.S_m2 / base.S_m2 - 1) == pytest.approx(ratio)
        assert (mine.share, mine.z_m) == (base.share, base.z_m)  # 비율·바닥 높이는 그대로여야 함
    for mine, base in zip(truth.links, params.links, strict=True):  # 연결(월류)마다 확인
        assert abs(mine.k / base.k - 1) == pytest.approx(ratio)
        assert (mine.from_zone, mine.to_zone, mine.sill_m) == (
            base.from_zone,
            base.to_zone,
            base.sill_m,
        )
    for inlet_id, base in params.inlets.items():
        mine = truth.inlets[inlet_id]
        assert abs(mine.Cd / base.Cd - 1) == pytest.approx(ratio)
        assert (mine.zone, mine.area_m2) == (base.zone, base.area_m2)  # 구역·단면적은 그대로여야 함
    unchanged = ("open_ratio", "model_area_m2", "dt_s", "model_version")
    assert [getattr(truth, a) for a in unchanged] == [getattr(params, a) for a in unchanged]


@pytest.mark.parametrize("ratio", [1.0, -0.1])
# 섭동 비율이 0 ~ 1 범위를 벗어나면 거절하는지 검사
def test_perturbation_ratio_must_be_in_zero_to_one(params, ratio):
    with pytest.raises(ValueError):
        variant(params, ratio, random.Random(0))  # 비율이 1.0 이나 -0.1 이면


# 참값이 핵심 모델을 조건대로 돌린 결과인지 검사
def test_truth_runs_the_core_model_under_the_conditions(config):
    sim = Sim(config)
    samples(sim, 30)
    truth = sim.truth_params
    assert sim.truth_state == evolution(baseline(truth), HEAVY, truth, 30.0)


# 측정값이 센서를 거친 참값인지 검사
def test_readings_are_the_truth_seen_through_the_sensors(config):
    cfg = copy.deepcopy(config)
    cfg["sim"]["noise_mm"] = 0.0
    sim, sensors = Sim(cfg), gauges(cfg)
    for t in range(1, 31):  # 1초부터 30초까지
        [message] = sim.inbox(float(t), HEAVY)
        truth = sim.truth_state
        for z in "AB":
            level = depth(z, truth.V[z], sim.truth_params)
            expected = gap(level, sensors[z])
            assert message["readings"][f"dist{z}_mm"] == pytest.approx(expected)
        weight = sum(truth.drained_m3.values()) * 1e6 + cfg["sensors"]["load"]["tare_g"]
        assert message["readings"]["weight_g"] == pytest.approx(weight)


# 마른 상태의 측정값에 시드 고정 가우스 잡음이 실리는지 검사
def test_dry_readings_carry_seeded_gaussian_noise(config):
    messages = samples(Sim(config), 2000, Conditions())
    noise = config["sim"]["noise_mm"]
    for z, sensor in gauges(config).items():
        dry = gap(0.0, sensor)
        errors = [m["readings"][f"dist{z}_mm"] - dry for m in messages]
        assert abs(statistics.fmean(errors)) < 0.1
        assert abs(statistics.stdev(errors) - noise) < 0.05


# 무게에 용기 무게가 들어가는지 검사
def test_weight_includes_the_tare(config):
    cfg = copy.deepcopy(config)
    cfg["sensors"]["load"]["tare_g"] = 40.0
    [message] = Sim(cfg).inbox(1.0, Conditions())
    assert message["readings"]["weight_g"] == pytest.approx(40.0)
