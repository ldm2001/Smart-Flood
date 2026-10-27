import copy
import json
import pytest
import random
import statistics
from app.adapters.sim_source import Sim, variant
from app.core.calibration import Sensor, gap
from app.core.model import Conditions, baseline, depth, evolution
from app.schemas import Message

HEAVY = Conditions(90.0, {"INLET-02": "partial"})  # 강한 비에 2번 빗물받이가 일부 막힌 조건


# 초 수만큼 매초 메시지를 모아 목록으로 주는 도우미
def samples(sim, seconds, cond=HEAVY):
    # 1초부터 끝 초까지 받은 메시지를 이어 담는다
    return [message for t in range(1, seconds + 1) for message in sim.inbox(float(t), cond)]


# 설정에서 A·B 구역의 센서 모델을 만드는 도우미
def gauges(config):
    return {z: Sensor.config(config["sensors"][z]) for z in "AB"}  # 구역마다 센서 모델을 만듦


# 메시지가 장치와 같은 형식인지 검사
def test_messages_use_the_device_format(config):
    first, second = samples(Sim(config), 2)  # 메시지 두 개를 받음
    for message in (first, second):  # 둘 다 확인
        Message.model_validate(message)  # 메시지 모델이 받아야 함
        # 최상위 키가 장치 형식과 같아야 함
        assert set(message) == {"deviceId", "bootId", "seq", "tMs", "readings", "sensorStatus"}
        assert message["deviceId"] == "esp32_1"  # 장치 ID 는 esp32_1
        # 측정값 키는 거리 A·B 와 무게
        assert set(message["readings"]) == {"distA_mm", "distB_mm", "weight_g"}
        # 센서 상태는 모두 정상
        assert message["sensorStatus"] == {"A": "ok", "B": "ok", "load": "ok"}
        json.dumps(message, allow_nan=False)  # NaN 없이 JSON 으로 쓸 수 있어야 함
    assert (first["seq"], first["tMs"]) == (1, 1000)  # 첫 메시지는 순번 1, 1000 ms
    assert (second["seq"], second["tMs"]) == (2, 2000)  # 둘째 메시지는 순번 2, 2000 ms
    assert first["bootId"] == second["bootId"]  # 부팅 ID 는 같아야 함


# 같은 시드면 메시지가 같은지 검사
def test_same_seed_gives_the_same_messages(config):
    # 두 번 만든 입력원의 메시지가 같아야 함
    assert samples(Sim(config), 20) == samples(Sim(config), 20)


# 초기화하면 새 부팅으로 같은 측정값이 다시 나오는지 검사
def test_reset_replays_the_readings_under_a_new_boot(config):
    sim = Sim(config)  # 입력원을 만듦
    first = samples(sim, 10)  # 첫 회차 메시지를 받음
    sim.origin()  # 초기화
    second = samples(sim, 10)  # 둘째 회차 메시지를 받음
    assert [m["readings"] for m in second] == [m["readings"] for m in first]  # 측정값은 같아야 함
    assert {m["bootId"] for m in first} == {"sim1"}  # 첫 부팅 ID 는 sim1
    assert {m["bootId"] for m in second} == {"sim2"}  # 둘째 부팅 ID 는 sim2
    assert [m["seq"] for m in second] == list(range(1, 11))  # 순번은 1 부터 다시 시작 필요


# 시드가 다르면 측정값이 다른지 검사
def test_another_seed_gives_other_readings(config):
    cfg = copy.deepcopy(config)  # 설정을 복사
    cfg["sim"]["seed"] += 1  # 시드를 하나 올림
    mine = [m["readings"] for m in samples(Sim(cfg), 10)]  # 바뀐 시드의 측정값을 모음
    # 원래 시드의 측정값과 달라야 함
    assert mine != [m["readings"] for m in samples(Sim(config), 10)]



# 설정한 섭동 비율이 명세 범위인지 검사
def test_configured_perturbation_is_in_the_spec_range(config):
    assert 0.10 <= config["sim"]["truth_perturbation"] <= 0.20  # 섭동 비율이 0.10 ~ 0.20 이어야 함


# 참값 모델이 저장 면적·월류 계수·배수 계수를 ±비율만큼 바꾸는지 검사
def test_truth_model_perturbs_storage_weirs_and_inlets(config, params):
    ratio = config["sim"]["truth_perturbation"]  # 섭동 비율을 꺼냄
    truth = Sim(config).truth_params  # 참값 모델 인자를 꺼냄
    for z, base in params.zones.items():  # 구역마다 확인
        mine = truth.zones[z]  # 참값의 구역 인자
        # 저장 면적이 비율만큼 달라야 함
        assert abs(mine.S_m2 / base.S_m2 - 1) == pytest.approx(ratio)
        assert (mine.share, mine.z_m) == (base.share, base.z_m)  # 비율·바닥 높이는 그대로여야 함
    for mine, base in zip(truth.links, params.links, strict=True):  # 연결(월류)마다 확인
        assert abs(mine.k / base.k - 1) == pytest.approx(ratio)  # 월류 계수가 비율만큼 달라야 함
        # 연결 양끝·문턱 높이는 그대로여야 함
        assert (mine.from_zone, mine.to_zone, mine.sill_m) == (
            base.from_zone,  # 출발 구역
            base.to_zone,  # 도착 구역
            base.sill_m,  # 문턱 높이
        )
    for inlet_id, base in params.inlets.items():  # 빗물받이마다 확인
        mine = truth.inlets[inlet_id]  # 참값의 빗물받이 인자
        assert abs(mine.Cd / base.Cd - 1) == pytest.approx(ratio)  # 배수 계수가 비율만큼 달라야 함
        assert (mine.zone, mine.area_m2) == (base.zone, base.area_m2)  # 구역·단면적은 그대로여야 함
    # 바뀌면 안 되는 인자 이름들
    unchanged = ("open_ratio", "model_area_m2", "dt_s", "model_version")
    # 그 인자들은 원래 값과 같아야 함
    assert [getattr(truth, a) for a in unchanged] == [getattr(params, a) for a in unchanged]


@pytest.mark.parametrize("ratio", [1.0, -0.1])  # 비율 사례 두 가지로 반복
# 섭동 비율이 0 ~ 1 범위를 벗어나면 거절하는지 검사
def test_perturbation_ratio_must_be_in_zero_to_one(params, ratio):
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        variant(params, ratio, random.Random(0))  # 비율이 1.0 이나 -0.1 이면


# 참값이 핵심 모델을 조건대로 돌린 결과인지 검사
def test_truth_runs_the_core_model_under_the_conditions(config):
    sim = Sim(config)  # 입력원을 만듦
    samples(sim, 30)  # 30초 치 메시지를 받음
    truth = sim.truth_params  # 참값 모델 인자를 꺼냄
    # 참값 상태가 같은 조건으로 30초 진행한 결과와 같아야 함
    assert sim.truth_state == evolution(baseline(truth), HEAVY, truth, 30.0)


# 측정값이 센서를 거친 참값인지 검사
def test_readings_are_the_truth_seen_through_the_sensors(config):
    cfg = copy.deepcopy(config)  # 설정을 복사
    cfg["sim"]["noise_mm"] = 0.0  # 잡음을 끈다
    sim, sensors = Sim(cfg), gauges(cfg)  # 입력원과 구역별 센서 모델을 만듦
    for t in range(1, 31):  # 1초부터 30초까지
        [message] = sim.inbox(float(t), HEAVY)  # 그 초의 메시지를 받음
        truth = sim.truth_state  # 참값 상태를 꺼냄
        for z in "AB":  # A·B 구역마다
            level = depth(z, truth.V[z], sim.truth_params)  # 참값 부피로 수위를 구
            expected = gap(level, sensors[z])  # 센서가 재는 거리를 구
            # 메시지 거리가 그 값이어야 함
            assert message["readings"][f"dist{z}_mm"] == pytest.approx(expected)
        # 무게는 배수 부피(m³)를 g 으로 바꾸고 용기 무게를 더한 값
        weight = sum(truth.drained_m3.values()) * 1e6 + cfg["sensors"]["load"]["tare_g"]
        # 메시지 무게가 그 값이어야 함
        assert message["readings"]["weight_g"] == pytest.approx(weight)


# 마른 상태의 측정값에 시드 고정 가우스 잡음이 실리는지 검사
def test_dry_readings_carry_seeded_gaussian_noise(config):
    messages = samples(Sim(config), 2000, Conditions())  # 비 없는 조건으로 2000개를 받음
    noise = config["sim"]["noise_mm"]  # 설정된 잡음 크기
    for z, sensor in gauges(config).items():  # A·B 센서마다
        dry = gap(0.0, sensor)  # 마른 수위의 센서 거리
        # 메시지 거리와 마른 거리의 오차를 모음
        errors = [m["readings"][f"dist{z}_mm"] - dry for m in messages]
        assert abs(statistics.fmean(errors)) < 0.1  # 오차 평균은 0 에 가까워야 함
        assert abs(statistics.stdev(errors) - noise) < 0.05  # 오차 표준편차는 설정 잡음과 같아야 함


# 무게에 용기 무게가 들어가는지 검사
def test_weight_includes_the_tare(config):
    cfg = copy.deepcopy(config)  # 설정을 복사
    cfg["sensors"]["load"]["tare_g"] = 40.0  # 용기 무게를 40 g 으로 둔다
    [message] = Sim(cfg).inbox(1.0, Conditions())  # 첫 메시지를 받음
    # 비 없는 상태의 무게가 40 g 이어야 함
    assert message["readings"]["weight_g"] == pytest.approx(40.0)
