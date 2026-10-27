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

START = "/api/experiment/start"  # 실험 시작 주소
HEAVY = Conditions(90.0)  # 강한 비(90 mm/h), 막힘 없음 조건


# 앱을 만들고 회차를 시작해 (클라이언트, 서비스)를 돌려주는 도우미
def opening(make_client, cfg=None, *, source, body=None):
    client = make_client(cfg, source=source)  # 주어진 입력원으로 앱을 만듦
    # 본문이 없으면 강한 비로 시작하고, 성공(200)이어야 함
    assert client.post(START, json=body or {"rain": "heavy"}).status_code == 200
    return client, client.app.state.service  # 클라이언트와 앱 안의 서비스를 반환


# 보정 세기 gain 과 보정 항목을 바꾼 설정·계수를 만드는 도우미
def scaling(config, gain, **correction):
    cfg = copy.deepcopy(config)  # 설정을 깊은 복사
    cfg["correction"].update(gain=gain, **correction)  # 보정 항목에 세기와 나머지 값을 넣음
    return cfg, Params.config(cfg)  # 설정과 그 모델 계수를 반환



# 대기 중에는 시계가 가도 틱이 없는지 검사(틱 수는 시계를 따른다)
def test_no_ticks_while_idle(client, clock, service):
    clock.jump(5.0)  # 시계를 5초 전송
    assert service.catchup() == 0  # 처리된 틱은 0 이어야 함
    assert client.get("/api/state").json()["elapsedSec"] == 0  # 경과 시간은 0 이어야 함


# 틱 수가 시계를 따르는지 검사
def test_ticks_follow_the_clock(client, clock, service):
    client.post(START, json={})  # 시작
    clock.jump(3.5)  # 시계를 3.5초 전송
    assert service.catchup() == 3  # 틱은 3개여야 함
    clock.jump(0.5)  # 0.5초를 더 보낸다(합 4초)
    assert service.catchup() == 1  # 틱이 1개 더 나와야 함
    assert client.get("/api/state").json()["elapsedSec"] == 4  # 경과 시간은 4초여야 함


# 틱 상한을 두면 나머지는 다음으로 남는지 검사
def test_tick_limit_leaves_the_rest_for_later(client, clock, service):
    client.post(START, json={})  # 시작
    clock.jump(5.0)  # 시계를 5초 전송
    assert service.catchup(limit=2) == 2  # 상한 2 면 2개만 처리 필요
    assert service.catchup() == 3  # 남은 3개는 다음에 처리 필요


# 다음 틱까지 남은 초를 알려 주는지 검사
def test_seconds_until_next_tick(client, clock, service):
    assert service.delay() is None  # 대기 중에는 없음(None)이어야 함
    client.post(START, json={})  # 시작
    clock.jump(0.25)  # 시계를 0.25초 전송
    assert service.delay() == pytest.approx(0.75)  # 0.75초가 남아야 함
    clock.jump(0.75)  # 0.75초를 더 전송
    assert service.delay() == pytest.approx(0.0)  # 틱 시각이 되어 0초여야 함
    service.catchup()  # 밀린 틱을 처리
    assert service.delay() == pytest.approx(1.0)  # 다음 틱까지 1초여야 함


# 상태 시각이 시작 시각 + 모델 경과 초인지 검사
def test_snapshot_time_is_start_time_plus_model_seconds(client, clock, service):
    client.post(START, json={})  # 시작
    clock.jump(5.5)  # 시계를 5.5초 전송
    service.catchup()  # 밀린 틱을 처리한다(5개)
    body = client.get("/api/state").json()  # 상태를 읽음
    # 시각은 시작 시각 + 5초여야 한다(남은 0.5초는 틱이 아니다)
    assert body["timestamp"] == "2026-10-22T10:00:05.000+09:00"
    assert body["predictionMeta"]["basisElapsedSec"] == 5  # 예측 기준 경과 초는 5 여야 함
    # 예측 기준 시각은 상태 시각과 같아야 함
    assert body["predictionMeta"]["basisTime"] == body["timestamp"]


# 시뮬레이션 회차의 품질은 정상, 출력은 잠금인지 검사
def test_sim_run_reports_valid_quality_and_locked_outputs(client, clock, service):
    client.post(START, json={})  # 시작
    lapse(clock, service, 3)  # 3초를 전송
    body = client.get("/api/state").json()  # 상태를 읽음
    assert body["quality"] == "valid"  # 품질은 정상(valid)이어야 함
    assert body["devices"] == {  # 장치 상태가 모두 정상이어야 함
        "esp32_1": "online",  # 1번 보드는 온라인
        "esp32_2": "online",  # 2번 보드는 온라인
        "floatSwitch": "normal",  # 플로트 스위치는 정상
        "emergencyStop": "normal",  # 비상 정지는 정상
    }
    # 모드 live, 입력원 sim, 출력 잠금이어야 함
    assert (body["mode"], body["dataSource"], body["outputsLocked"]) == ("live", "sim", True)
    assert body["alerts"] == []  # 경보는 없어야 함



# 입력원을 감싸 폴링마다 (경과 초, 메시지)를 남기는 도우미. 되돌리면 비운다
class Tape:
    # 감쌀 입력원을 받음
    def __init__(self, inner):
        self.inner, self.history = inner, []  # 속 입력원과 빈 기록 목록을 둔다

    # 새 회차에서 입력원을 되돌린다
    def origin(self):
        self.inner.origin()  # 속 입력원을 되돌린다
        self.history.clear()  # 기록을 비운다

    # 관측 메시지를 받아 오고 기록도 남김
    def inbox(self, elapsed_s, cond):
        messages = self.inner.inbox(elapsed_s, cond)  # 속 입력원에서 메시지를 받음
        self.history.append((elapsed_s, copy.deepcopy(messages)))  # 경과 초와 메시지 복사본을 기록
        return messages  # 받은 메시지를 그대로 반환


# 표시값 검사: 예측·변화율·배수는 모델, A·B 수위는 최근 유효 관측에서 옴
def test_state_shows_the_model_and_the_latest_sim_readings(builder, config, clock, params):
    source = Tape(Sim(config))  # 시뮬레이션 입력원을 감싼다
    # 강한 비와 2번 부분 막힘으로 시작할 본문
    body = {"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}}
    client, service = opening(builder, source=source, body=body)  # 회차를 시작
    sensors = {z: Sensor.config(config["sensors"][z]) for z in "AB"}  # A·B 센서 설정을 만듦
    max_age = config["correction"]["max_age_s"]  # 관측을 표시하는 최대 나이(초)
    latest, shown = {}, set()  # 구역별 최근 유효 관측과 표시된 출처 모음
    for _ in range(30):  # 30초 동안 반복
        lapse(clock, service, 1)  # 1초를 전송
        state = client.get("/api/state").json()  # 그 초의 상태를 읽음
        # 서비스의 모델 상태, 조건, 경과 초
        model, cond, elapsed = service.state, service.conditions, state["elapsedSec"]

        prediction = forecast(  # 같은 입력으로 예측을 직접 계산
            # 모델, 조건, 계수, 기준 초, 10·20·30초 뒤, 유효 5초
            model, cond, params, basis_elapsed_s=elapsed, horizons_s=(10, 20, 30), valid_for_s=5
        )
        rates = gradient(model, cond, params)  # 수위 변화율을 직접 계산
        for z in "ABC":  # 세 구역마다
            # 변화율(mm/s)이 모델 값 × 1000 이어야 함
            assert state["zones"][z]["rateMmSec"] == pytest.approx(rates[z] * 1000)
            for h in (10, 20, 30):  # 예측 시점마다
                expected = prediction.levels_m[z][h] * 1000  # 예측 수위를 mm 로 변환
                # 응답의 예측이 같아야 함
                assert state["predictions"][z][str(h)] == pytest.approx(expected)
        flows = flux(model, cond, params)  # 유입·배수 흐름을 직접 계산
        # 누적 배수량(L)이 모델 합 × 1000 이어야 함
        assert state["drain"]["volumeL"] == pytest.approx(sum(model.drained_m3.values()) * 1000)
        # 배수 유량(L/min)이 모델 합 × 60000 이어야 함
        assert state["drain"]["flowLMin"] == pytest.approx(sum(flows.drains_m3s.values()) * 60000)

        received_at, messages = source.history[-1]  # 이번 틱에 받은 마지막 메시지 기록
        for message in messages:  # 메시지마다
            for z in "AB":  # A·B 구역마다
                # 거리 값을 수위로 변환
                level = waterline(message["readings"][f"dist{z}_mm"], sensors[z])
                # 센서가 정상이고 수위가 유효하면
                if message["sensorStatus"][z] == "ok" and level is not None:
                    # 0 아래는 0 으로 올려 최근 관측으로 둔다
                    latest[z] = (max(0.0, level), received_at)
        for z in "ABC":  # 세 구역마다
            # 최근 관측이 있고 나이가 최대 나이 이내면
            if z in latest and elapsed - latest[z][1] <= max_age:
                # 그 관측 수위와 출처 simulated 여야 함
                expected = (pytest.approx(latest[z][0] * 1000), "simulated")
            else:  # 아니면
                model_mm = depth(z, model.V[z], params) * 1000  # 모델 수위를 mm 로 구
                # 모델 수위와 출처 estimated 여야 함
                expected = (pytest.approx(model_mm), "estimated")
            zone = state["zones"][z]  # 응답의 구역 값
            # 수위와 출처가 기대와 같아야 함
            assert (zone["levelMm"], zone["source"]) == expected, (elapsed, z)
            shown.add(zone["source"])  # 표시된 출처를 모음
    assert "simulated" in shown  # simulated 가 한 번은 나와야 함


# 유효한 관측은 simulated 로 표시되는지 검사
def test_valid_readings_are_shown_as_simulated(builder, config, clock):
    client, service = opening(  # 회차를 시작
        # A 12 mm, B 7 mm 를 매번 내는 입력원
        builder, source=Script(readout(config, a_mm=12.0, b_mm=7.0))
    )
    lapse(clock, service, 1)  # 1초를 전송
    zones = client.get("/api/state").json()["zones"]  # 구역별 값을 읽음
    assert zones["A"]["levelMm"] == pytest.approx(12.0)  # A 수위가 12 mm 여야 함
    assert zones["B"]["levelMm"] == pytest.approx(7.0)  # B 수위가 7 mm 여야 함
    # 출처는 A·B 가 simulated, C 가 estimated 여야 함
    assert [zones[z]["source"] for z in "ABC"] == ["simulated", "simulated", "estimated"]



@pytest.mark.parametrize("gain", [1.0, 0.3, 0.0])  # 보정 세기마다 반복
# 유효한 새 관측만 한 번, V += g(V_obs - V) 로 보정하는지 검사
def test_fresh_readings_correct_the_model_with_the_configured_gain(
    builder, config, clock, gain  # 준비물과 보정 세기
):
    cfg, params = scaling(config, gain)  # 그 세기로 설정과 계수를 만듦
    readings = readout(config, a_mm=12.0, b_mm=7.0)  # A 12 mm, B 7 mm 관측값
    # 그 관측을 매번 내는 입력원으로 시작
    client, service = opening(builder, cfg, source=Script(readings))
    lapse(clock, service, 3)  # 3초를 전송
    expected = baseline(params)  # 처음 상태에서 출발해 직접 계산
    for _ in range(3):  # 3초 동안 반복
        expected = evolution(expected, HEAVY, params, 1.0)  # 모델을 1초 진행
        # A·B 관측 수위(m)로 보결정
        expected, _ = adjustment(expected, {"A": 0.012, "B": 0.007}, gain, params)
    assert service.state.V == pytest.approx(expected.V)  # 구역별 저장량이 같아야 함
    # 누적 보정량도 같아야 함
    assert service.state.correction_m3 == pytest.approx(expected.correction_m3)


INVALID_A = {  # A 의 무효 관측 사례: 이름 → (바꿀 관측값, 센서 상태)
    "below-dead-zone": ({"distA_mm": 150.0}, SENSOR_OK),  # 사각지대 안쪽의 너무 가까운 거리
    "beyond-range": ({"distA_mm": 9_999.0}, SENSOR_OK),  # 어떤 측정 범위보다도 먼 거리
    "missing": ({"distA_mm": None}, SENSOR_OK),  # 거리 값이 없음
    "nan": ({"distA_mm": math.nan}, SENSOR_OK),  # 거리 값이 NaN
    "sensor-error": ({}, {**SENSOR_OK, "A": "error"}),  # 센서 상태가 오류
}


# 무효 사례마다 반복
@pytest.mark.parametrize(("override", "status"), INVALID_A.values(), ids=INVALID_A.keys())
# 무효 관측은 보정에도 표시에도 안 쓰이는지 검사
def test_an_invalid_reading_neither_corrects_nor_shows(
    builder, config, clock, override, status  # 준비물과 사례의 관측값·센서 상태
):
    cfg, params = scaling(config, 1.0)  # 보정 세기 1.0 설정
    # 정상 관측에 A 의 무효 값을 덮어기록
    readings = {**readout(config, a_mm=12.0, b_mm=7.0), **override}
    # 그 관측과 센서 상태를 내는 입력원으로 시작
    client, service = opening(builder, cfg, source=Script(readings, status))
    lapse(clock, service, 1)  # 1초를 전송
    expected = evolution(baseline(params), HEAVY, params, 1.0)  # 모델을 1초 진행
    expected, _ = adjustment(expected, {"B": 0.007}, 1.0, params)  # 유효한 B 관측만으로 보결정
    assert service.state.V == pytest.approx(expected.V)  # A 는 보정되지 않아 저장량이 같아야 함
    zone_a = client.get("/api/state").json()["zones"]["A"]  # 응답의 A 구역 값
    model_mm = depth("A", expected.V["A"], params) * 1000  # A 의 모델 수위(mm)
    # 모델 수위와 estimated 로 표시돼야 함
    assert (zone_a["levelMm"], zone_a["source"]) == (pytest.approx(model_mm), "estimated")


# 관측은 한 번만 보정하고 최대 나이 동안 표시되는지 검사
def test_a_reading_corrects_once_and_shows_for_max_age(builder, config, clock):
    cfg, params = scaling(config, 1.0, max_age_s=3.0)  # 보정 세기 1.0, 표시 최대 나이 3초 설정
    readings = readout(config, a_mm=12.0, b_mm=7.0)  # A 12 mm, B 7 mm 관측값
    # 1초까지만 관측을 내는 입력원으로 시작
    client, service = opening(builder, cfg, source=Script(readings, until_s=1.0))
    lapse(clock, service, 1)  # 1초를 전송
    expected = evolution(baseline(params), HEAVY, params, 1.0)  # 모델을 1초 진행
    # 그 관측으로 한 번 보결정
    expected, _ = adjustment(expected, {"A": 0.012, "B": 0.007}, 1.0, params)
    for second in range(2, 6):  # 관측이 끊긴 2~5초마다
        lapse(clock, service, 1)  # 1초를 전송
        expected = evolution(expected, HEAVY, params, 1.0)  # 보정 없이 모델만 1초 진행
        # 같은 관측으로 또 보정하지 않아야 함
        assert service.state.V == pytest.approx(expected.V), second
        zone_a = client.get("/api/state").json()["zones"]["A"]  # 응답의 A 구역 값
        if second - 1 <= 3:  # 관측 나이가 최대 나이 3초 이내면
            # 관측 수위 12 mm 와 simulated 여야 함
            assert (zone_a["levelMm"], zone_a["source"]) == (pytest.approx(12.0), "simulated")
        else:  # 넘으면
            model_mm = depth("A", expected.V["A"], params) * 1000  # A 의 모델 수위(mm)
            # 모델 수위와 estimated 여야 함
            assert (zone_a["levelMm"], zone_a["source"]) == (pytest.approx(model_mm), "estimated")


# 관측이 없으면 모델만 도는지 검사
def test_without_readings_the_model_runs_alone(builder, clock, params):
    client, service = opening(builder, source=Script(None))  # 관측 없는 입력원으로 시작
    lapse(clock, service, 5)  # 5초를 전송
    # 모델만 5초 진행한 상태와 같아야 함
    assert service.state == evolution(baseline(params), HEAVY, params, 5.0)
    zones = client.get("/api/state").json()["zones"]  # 구역별 값을 읽음
    # 모든 구역의 출처가 estimated 여야 함
    assert [zones[z]["source"] for z in "ABC"] == ["estimated"] * 3


# 조건 변경이 바꾼 그 초부터 적용되는지 검사
def test_condition_changes_apply_from_the_current_second(builder, clock, params):
    client, service = opening(builder, source=Script(None))  # 관측 없는 입력원으로 시작
    lapse(clock, service, 3)  # 3초를 전송
    # 2번 빗물받이를 완전히 차단
    client.post("/api/blockage", json={"type": "full", "location": "INLET-02"})
    lapse(clock, service, 2)  # 2초를 더 전송
    expected = evolution(baseline(params), HEAVY, params, 3.0)  # 처음 3초는 막힘 없는 조건으로 진행
    # 다음 2초는 2번 완전 막힘 조건으로 진행
    expected = evolution(expected, Conditions(90.0, {"INLET-02": "full"}), params, 2.0)
    assert service.state == expected  # 서비스 상태가 그와 같아야 함


# 새 회차마다 입력원을 되돌리는지 검사
def test_each_new_run_resets_the_source(builder):
    source = Script(None)  # 되돌린 횟수를 세는 입력원
    client, _ = opening(builder, source=source)  # 회차를 시작한다(첫 회차)
    client.post(START, json={})  # 돌고 있을 때 다시 시작해도 새 회차가 아니다
    assert source.resets == 1  # 입력원을 되돌린 횟수는 1 이어야 함
    client.post("/api/experiment/stop", json={})  # 정지
    client.post(START, json={})  # 다시 시작한다(새 회차)
    assert source.resets == 2  # 되돌린 횟수가 2 가 되어야 함



# 고장 낼 단계: (서비스 함수 이름, 오류 로그 수). 예측이 고장 나면 로그가 하나 더 남음
FAILING_STAGES = {"step": ("evolution", 1), "forecast": ("forecast", 2)}


# 고장 낼 단계마다 반복
@pytest.mark.parametrize(("stage", "errors"), FAILING_STAGES.values(), ids=FAILING_STAGES.keys())
# 틱 계산 오류는 기록하고 회차를 멈추는지 검사
def test_a_tick_error_is_logged_and_stops_the_run(
    builder, clock, monkeypatch, caplog, stage, errors  # 준비물과 단계 사례
):
    client, service = opening(builder, source=Script(None))  # 관측 없는 입력원으로 시작
    lapse(clock, service, 2)  # 2초를 전송

    # 항상 실패하는 가짜 단계 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")  # 저장량 음수 오류를 냄

    monkeypatch.setattr(f"app.service.{stage}", wreck)  # 서비스가 부르는 그 단계를 가짜로 변환
    clock.jump(1.0)  # 시계를 1초 전송
    with caplog.at_level(logging.ERROR, logger="app.service"):  # 오류 로그를 붙잡음
        assert service.catchup() == 0  # 처리된 틱은 0 이어야 함
    body = client.get("/api/state").json()  # 상태를 읽음
    # 정지 상태, 마지막 정상 틱인 2초, 비 꺼짐이어야 함
    assert (body["runState"], body["elapsedSec"], body["rain"]["state"]) == ("stopped", 2, "OFF")
    records = [r for r in caplog.records if r.levelno >= logging.ERROR]  # 오류 이상의 로그만 모음
    assert len(records) == errors  # 로그 수가 단계별 기대와 같아야 함
    # 모두 저장량 음수 오류에서 나온 것이어야 함
    assert all(r.exc_info[0] is Underflow for r in records)
