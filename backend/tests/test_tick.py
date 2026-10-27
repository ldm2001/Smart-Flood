import copy
import logging
import math
import pytest
from app.adapters.sim_source import Sim
from app.core.calibration import Sensor, adjustment, waterline
from app.core.model import (
    Conditions,
    Params,
    Underflow,
    baseline,
    depth,
    evolution,
    flux,
    gradient,
)
from app.core.predictor import forecast
from tests.helpers import SENSOR_OK, Script, lapse, readout

START = "/api/experiment/start"
HEAVY = Conditions(90.0)  # 강한 비(90 mm/h), 막힘 없음 조건


# 앱을 만들고 회차를 시작해 (클라이언트, 서비스)를 돌려주는 도우미
def opening(make_client, cfg=None, *, source, body=None):
    client = make_client(cfg, source=source)
    assert client.post(START, json=body or {"rain": "heavy"}).status_code == 200
    return client, client.app.state.service


# 보정 세기 gain 과 보정 항목을 바꾼 설정·계수를 만드는 도우미
def scaling(config, gain, **correction):
    cfg = copy.deepcopy(config)
    cfg["correction"].update(gain=gain, **correction)
    return cfg, Params.config(cfg)



# 대기 중에는 시계가 가도 틱이 없는지 검사(틱 수는 시계를 따름)
def test_no_ticks_while_idle(client, clock, service):
    clock.jump(5.0)
    assert service.catchup() == 0
    assert client.get("/api/state").json()["elapsedSec"] == 0


# 틱 수가 시계를 따르는지 검사
def test_ticks_follow_the_clock(client, clock, service):
    client.post(START, json={})
    clock.jump(3.5)
    assert service.catchup() == 3
    clock.jump(0.5)  # 0.5초를 더 보냄(합 4초)
    assert service.catchup() == 1
    assert client.get("/api/state").json()["elapsedSec"] == 4


# 틱 상한을 두면 나머지는 다음으로 남는지 검사
def test_tick_limit_leaves_the_rest_for_later(client, clock, service):
    client.post(START, json={})
    clock.jump(5.0)
    assert service.catchup(limit=2) == 2
    assert service.catchup() == 3


# 다음 틱까지 남은 초를 알려 주는지 검사
def test_seconds_until_next_tick(client, clock, service):
    assert service.delay() is None  # 대기 중에는 없음(None)이어야 함
    client.post(START, json={})
    clock.jump(0.25)
    assert service.delay() == pytest.approx(0.75)
    clock.jump(0.75)
    assert service.delay() == pytest.approx(0.0)
    service.catchup()
    assert service.delay() == pytest.approx(1.0)


# 상태 시각이 시작 시각 + 모델 경과 초인지 검사
def test_snapshot_time_is_start_time_plus_model_seconds(client, clock, service):
    client.post(START, json={})
    clock.jump(5.5)
    service.catchup()  # 밀린 틱을 처리(5개)
    body = client.get("/api/state").json()
    assert body["timestamp"] == "2026-10-22T10:00:05.000+09:00"
    assert body["predictionMeta"]["basisElapsedSec"] == 5
    assert body["predictionMeta"]["basisTime"] == body["timestamp"]


# 시뮬레이션 회차의 품질은 정상, 출력은 잠금인지 검사
def test_sim_run_reports_valid_quality_and_locked_outputs(client, clock, service):
    client.post(START, json={})
    lapse(clock, service, 3)
    body = client.get("/api/state").json()
    assert body["quality"] == "valid"  # 품질은 정상(valid)이어야 함
    assert body["devices"] == {
        "esp32_1": "online",
        "esp32_2": "online",
        "floatSwitch": "normal",
        "emergencyStop": "normal",
    }
    assert (body["mode"], body["dataSource"], body["outputsLocked"]) == ("live", "sim", True)
    assert body["alerts"] == []



# 입력원을 감싸 폴링마다 (경과 초, 메시지)를 남기는 도우미. 되돌리면 비움
class Tape:
    # 감쌀 입력원을 받음
    def __init__(self, inner):
        self.inner, self.history = inner, []

    # 새 회차에서 입력원을 되돌림
    def origin(self):
        self.inner.origin()  # 속 입력원을 되돌림
        self.history.clear()

    # 관측 메시지를 받아 오고 기록도 남김
    def inbox(self, elapsed_s, cond):
        messages = self.inner.inbox(elapsed_s, cond)
        self.history.append((elapsed_s, copy.deepcopy(messages)))
        return messages  # 받은 메시지를 그대로 반환


# 표시값 검사: 예측·변화율·배수는 모델, A·B 수위는 최근 유효 관측에서 옴
def test_state_shows_the_model_and_the_latest_sim_readings(builder, config, clock, params):
    source = Tape(Sim(config))
    body = {"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}}
    client, service = opening(builder, source=source, body=body)
    sensors = {z: Sensor.config(config["sensors"][z]) for z in "AB"}
    max_age = config["correction"]["max_age_s"]  # 관측을 표시하는 최대 나이(초)
    latest, shown = {}, set()
    for _ in range(30):
        lapse(clock, service, 1)
        state = client.get("/api/state").json()
        model, cond, elapsed = service.state, service.conditions, state["elapsedSec"]

        prediction = forecast(
            model, cond, params, basis_elapsed_s=elapsed, horizons_s=(10, 20, 30), valid_for_s=5
        )
        rates = gradient(model, cond, params)
        for z in "ABC":
            assert state["zones"][z]["rateMmSec"] == pytest.approx(rates[z] * 1000)
            for h in (10, 20, 30):
                expected = prediction.levels_m[z][h] * 1000
                assert state["predictions"][z][str(h)] == pytest.approx(expected)
        flows = flux(model, cond, params)
        assert state["drain"]["volumeL"] == pytest.approx(sum(model.drained_m3.values()) * 1000)
        assert state["drain"]["flowLMin"] == pytest.approx(sum(flows.drains_m3s.values()) * 60000)

        received_at, messages = source.history[-1]
        for message in messages:
            for z in "AB":
                level = waterline(message["readings"][f"dist{z}_mm"], sensors[z])
                if message["sensorStatus"][z] == "ok" and level is not None:
                    latest[z] = (max(0.0, level), received_at)
        for z in "ABC":
            if z in latest and elapsed - latest[z][1] <= max_age:
                expected = (pytest.approx(latest[z][0] * 1000), "simulated")
            else:
                model_mm = depth(z, model.V[z], params) * 1000
                expected = (pytest.approx(model_mm), "estimated")
            zone = state["zones"][z]
            assert (zone["levelMm"], zone["source"]) == expected, (elapsed, z)
            shown.add(zone["source"])
    assert "simulated" in shown


# 유효한 관측은 simulated 로 표시되는지 검사
def test_valid_readings_are_shown_as_simulated(builder, config, clock):
    client, service = opening(
        # A 12 mm, B 7 mm 를 매번 내는 입력원
        builder, source=Script(readout(config, a_mm=12.0, b_mm=7.0))
    )
    lapse(clock, service, 1)
    zones = client.get("/api/state").json()["zones"]
    assert zones["A"]["levelMm"] == pytest.approx(12.0)
    assert zones["B"]["levelMm"] == pytest.approx(7.0)
    assert [zones[z]["source"] for z in "ABC"] == ["simulated", "simulated", "estimated"]



@pytest.mark.parametrize("gain", [1.0, 0.3, 0.0])
# 유효한 새 관측만 한 번, V += g(V_obs - V) 로 보정하는지 검사
def test_fresh_readings_correct_the_model_with_the_configured_gain(
    builder, config, clock, gain
):
    cfg, params = scaling(config, gain)
    readings = readout(config, a_mm=12.0, b_mm=7.0)
    # 그 관측을 매번 내는 입력원으로 시작
    client, service = opening(builder, cfg, source=Script(readings))
    lapse(clock, service, 3)
    expected = baseline(params)
    for _ in range(3):
        expected = evolution(expected, HEAVY, params, 1.0)
        expected, _ = adjustment(expected, {"A": 0.012, "B": 0.007}, gain, params)
    assert service.state.V == pytest.approx(expected.V)
    assert service.state.correction_m3 == pytest.approx(expected.correction_m3)


INVALID_A = {  # A 의 무효 관측 사례: 이름 → (바꿀 관측값, 센서 상태)
    "below-dead-zone": ({"distA_mm": 150.0}, SENSOR_OK),
    "beyond-range": ({"distA_mm": 9_999.0}, SENSOR_OK),
    "missing": ({"distA_mm": None}, SENSOR_OK),
    "nan": ({"distA_mm": math.nan}, SENSOR_OK),
    "sensor-error": ({}, {**SENSOR_OK, "A": "error"}),
}


@pytest.mark.parametrize(("override", "status"), INVALID_A.values(), ids=INVALID_A.keys())
# 무효 관측은 보정에도 표시에도 안 쓰이는지 검사
def test_an_invalid_reading_neither_corrects_nor_shows(
    builder, config, clock, override, status
):
    cfg, params = scaling(config, 1.0)
    readings = {**readout(config, a_mm=12.0, b_mm=7.0), **override}
    client, service = opening(builder, cfg, source=Script(readings, status))
    lapse(clock, service, 1)
    expected = evolution(baseline(params), HEAVY, params, 1.0)
    expected, _ = adjustment(expected, {"B": 0.007}, 1.0, params)
    assert service.state.V == pytest.approx(expected.V)
    zone_a = client.get("/api/state").json()["zones"]["A"]
    model_mm = depth("A", expected.V["A"], params) * 1000  # A 의 모델 수위(mm)
    assert (zone_a["levelMm"], zone_a["source"]) == (pytest.approx(model_mm), "estimated")


# 관측은 한 번만 보정하고 최대 나이 동안 표시되는지 검사
def test_a_reading_corrects_once_and_shows_for_max_age(builder, config, clock):
    cfg, params = scaling(config, 1.0, max_age_s=3.0)
    readings = readout(config, a_mm=12.0, b_mm=7.0)
    client, service = opening(builder, cfg, source=Script(readings, until_s=1.0))
    lapse(clock, service, 1)
    expected = evolution(baseline(params), HEAVY, params, 1.0)
    expected, _ = adjustment(expected, {"A": 0.012, "B": 0.007}, 1.0, params)
    for second in range(2, 6):  # 관측이 끊긴 2~5초마다
        lapse(clock, service, 1)
        expected = evolution(expected, HEAVY, params, 1.0)
        assert service.state.V == pytest.approx(expected.V), second
        zone_a = client.get("/api/state").json()["zones"]["A"]
        if second - 1 <= 3:
            assert (zone_a["levelMm"], zone_a["source"]) == (pytest.approx(12.0), "simulated")
        else:
            model_mm = depth("A", expected.V["A"], params) * 1000  # A 의 모델 수위(mm)
            assert (zone_a["levelMm"], zone_a["source"]) == (pytest.approx(model_mm), "estimated")


# 관측이 없으면 모델만 도는지 검사
def test_without_readings_the_model_runs_alone(builder, clock, params):
    client, service = opening(builder, source=Script(None))
    lapse(clock, service, 5)
    assert service.state == evolution(baseline(params), HEAVY, params, 5.0)
    zones = client.get("/api/state").json()["zones"]
    assert [zones[z]["source"] for z in "ABC"] == ["estimated"] * 3


# 조건 변경이 바꾼 그 초부터 적용되는지 검사
def test_condition_changes_apply_from_the_current_second(builder, clock, params):
    client, service = opening(builder, source=Script(None))
    lapse(clock, service, 3)
    client.post("/api/blockage", json={"type": "full", "location": "INLET-02"})
    lapse(clock, service, 2)
    expected = evolution(baseline(params), HEAVY, params, 3.0)
    expected = evolution(expected, Conditions(90.0, {"INLET-02": "full"}), params, 2.0)
    assert service.state == expected


# 새 회차마다 입력원을 되돌리는지 검사
def test_each_new_run_resets_the_source(builder):
    source = Script(None)  # 되돌린 횟수를 세는 입력원
    client, _ = opening(builder, source=source)  # 회차를 시작(첫 회차)
    client.post(START, json={})
    assert source.resets == 1  # 입력원을 되돌린 횟수는 1 이어야 함
    client.post("/api/experiment/stop", json={})
    client.post(START, json={})  # 다시 시작(새 회차)
    assert source.resets == 2  # 되돌린 횟수가 2 가 되어야 함



FAILING_STAGES = {"step": ("evolution", 1), "forecast": ("forecast", 2)}


@pytest.mark.parametrize(("stage", "errors"), FAILING_STAGES.values(), ids=FAILING_STAGES.keys())
# 틱 계산 오류는 기록하고 회차를 멈추는지 검사
def test_a_tick_error_is_logged_and_stops_the_run(
    builder, clock, monkeypatch, caplog, stage, errors
):
    client, service = opening(builder, source=Script(None))
    lapse(clock, service, 2)

    # 항상 실패하는 가짜 단계 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")

    monkeypatch.setattr(f"app.service.{stage}", wreck)
    clock.jump(1.0)
    with caplog.at_level(logging.ERROR, logger="app.service"):
        assert service.catchup() == 0
    body = client.get("/api/state").json()
    assert (body["runState"], body["elapsedSec"], body["rain"]["state"]) == ("stopped", 2, "OFF")
    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(records) == errors
    assert all(r.exc_info[0] is Underflow for r in records)
