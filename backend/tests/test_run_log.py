import copy
import errno
import json
import logging
import math
import pytest
from app.config import checksum
from app.core.model import Underflow
from app.schemas import Message, encoding
from datetime import date, timedelta
from tests.helpers import SENSOR_OK, START, Script, breakage, lapse, readout

ID = "EXP-20261022-001"
START_URL = "/api/experiment/start"
STOP_URL = "/api/experiment/stop"
RESET_URL = "/api/experiment/reset"
NO_BLOCKAGE = {"type": "none", "location": None}
DISK_FULL = (errno.ENOSPC, "No space left on device")
# 기록을 못 쓸 때 기대하는 503 본문
UNAVAILABLE = {"detail": "실험 기록을 쓸 수 없다: No space left on device"}
# state 줄의 model 항목이 가져야 할 키들
MODEL_KEYS = {"volumesL", "correction", "correctionTotalL", "rainTotalL", "drainedL"}


# 가상 시계 시작 시각에서 seconds 초 뒤의 기록 시각 글자
def stamp(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


# 회차 기록의 모든 줄을 목록으로 읽는 도우미
def lines(experiment_log, experiment_id: str = ID) -> list[dict]:
    return list(experiment_log.records(experiment_id))


# 레코드 중 종류가 kind 인 것만 거르는 도우미
def subset(records: list[dict], kind: str) -> list[dict]:
    return [r for r in records if r["type"] == kind]


# POST 를 보내 성공(200)을 확인하고 본문을 돌려주는 도우미
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})
    assert response.status_code == 200, response.text  # 성공(200)이어야 함
    return response.json()


# 회차를 시작해 seconds 초 돌린 클라이언트와 서비스. kwargs 는 앱 만드는 함수로 감
def session(make_client, clock, *, body=None, seconds=0, **kwargs):
    client = make_client(**kwargs)
    answer(client, START_URL, body)
    service = client.app.state.service
    lapse(clock, service, seconds)
    return client, service


# 기록기 Journal 의 대역. fail 에 OSError 인자를 넣으면 그때부터 쓰기가 그 오류로 실패
class Breaker:
    # 진짜 기록기를 감싸는 대역을 만듦
    def __init__(self, inner) -> None:
        self.inner, self.fail = inner, None  # 속 기록기와 실패 인자(없으면 정상)를 둠

    # 한 줄을 씀. fail 이 있으면 실패
    def entry(self, experiment_id, record):
        if self.fail is not None:
            raise OSError(*self.fail)
        self.inner.entry(experiment_id, record)

    # 여러 줄을 씀. fail 이 있으면 실패
    def batch(self, experiment_id, records):
        if self.fail is not None:
            raise OSError(*self.fail)
        self.inner.batch(experiment_id, records)

    # 기록 목록은 진짜 기록기에서 읽음
    def index(self):
        return self.inner.index()

    # 회차 줄들은 진짜 기록기에서 읽음
    def records(self, experiment_id):
        return self.inner.records(experiment_id)


# 기록 폴더를 읽을 수 없는 대역. 오류에 폴더 경로가 들어 있음
class Blocker(Breaker):
    # 기록 목록을 읽으려 하면
    def index(self):
        raise OSError(errno.EACCES, "Permission denied", str(self.inner.directory))



# 기록할 값 정리: 무한·NaN 은 글자로 쓰는지 검사
def test_json_safe_writes_non_finite_numbers_as_text():
    value = {"a": math.nan, "b": [math.inf, -math.inf, 1.5], "c": {"d": None, "e": "x", "f": 2}}
    assert encoding(value) == {
        "a": "nan",
        "b": ["inf", "-inf", 1.5],  # 무한대는 글자로, 보통 숫자는 그대로
        "c": {"d": None, "e": "x", "f": 2},  # None·글자·정수는 그대로
    }


# 글자로 쓴 NaN·무한대 관측이 읽으면 같은 실수로 돌아오는지 검사
def test_non_finite_readings_written_as_text_read_back_as_the_same_floats():
    raw = {
        "deviceId": "esp32_1",
        "bootId": "b",
        "seq": 1,
        "tMs": 1000,  # 경과 시간(ms)
        "readings": {"distA_mm": math.nan, "distB_mm": math.inf, "weight_g": -math.inf},
        "sensorStatus": {"A": "ok", "B": "ok", "load": "ok"},
    }
    line = json.dumps(encoding(raw), allow_nan=False)  # 다듬어 JSON 한 줄로 씀(NaN 은 허용 안 함)
    readings = Message.model_validate(json.loads(line)).readings
    assert math.isnan(readings.distA_mm)
    assert (readings.distB_mm, readings.weight_g) == (math.inf, -math.inf)


# 설정 해시는 키 순서가 아니라 값을 따르는지 검사
def test_config_hash_follows_the_values_not_the_key_order(config):
    digest = checksum(config)
    assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64
    assert checksum(dict(reversed(list(config.items())))) == digest
    changed = copy.deepcopy(config)
    changed["correction"]["gain"] = 0.31
    assert checksum(changed) != digest


@pytest.mark.parametrize("value", [math.nan, date(2026, 10, 22)], ids=["nan", "date"])
# JSON 에 담을 수 없는 설정은 해시를 못 구하는지 검사
def test_a_config_json_cannot_hold_has_no_hash(config, value):
    cfg = copy.deepcopy(config)
    cfg["calibrated_on"] = value
    with pytest.raises(ValueError):
        checksum(cfg)



# 회차의 줄은 meta 와 start 로 시작하는지 검사(틱마다 obs 다음에 state)
def test_a_run_opens_with_meta_and_its_start_command(builder, clock, journal, config):
    body = {"rain": "heavy", "blockage": {"type": "full", "location": "INLET-02"}}
    client, _ = session(builder, clock, body=body, source=Script(None))
    assert client.get("/api/state").json()["experimentId"] == ID
    meta, start = lines(journal)  # 기록은 두 줄(meta, start)뿐이어야 함
    assert meta == {
        "type": "meta",
        "logVersion": 1,
        "experimentId": ID,
        "dataSource": "sim",
        "startTime": stamp(0),
        "modelVersion": config["model_version"],
        "configHash": checksum(config),
        "config": config,
    }
    assert start == {
        "type": "cmd",
        "kind": "start",
        "elapsedSec": 0.0,
        "receivedAt": stamp(0),
        "rainMmPerHour": 90.0,  # 강한 비 세기(mm/h)
        "blockage": {"type": "full", "location": "INLET-02"},
    }


# 틱마다 obs 줄 다음에 state 줄을 쓰는지 검사
def test_each_tick_writes_its_observations_then_its_state(
    builder, clock, journal, config
):
    # A 20 mm, B 10 mm, 무게 150 g 을 매번 내는 입력원
    source = Script(readout(config, a_mm=20, b_mm=10, weight_g=150))
    client, service = session(builder, clock, source=source)
    for second in (1, 2, 3):
        lapse(clock, service, 1)
        obs, state = lines(journal)[-2:]
        assert (obs["type"], obs["elapsedSec"], obs["receivedAt"]) == ("obs", second, stamp(second))
        assert obs["raw"] == {  # 받은 원본 메시지가 그대로 있어야 함
            "deviceId": "esp32_1",
            "bootId": "test",
            "seq": second,
            "tMs": second * 1000,  # 경과 시간(ms)
            "readings": source.readings,
            "sensorStatus": SENSOR_OK,
        }
        assert obs["levelsMm"] == pytest.approx({"A": 20, "B": 10})  # 변환한 수위(mm)여야 함
        assert obs["drainVolumeL"] == pytest.approx(0.15)  # 150 g 은 배수량 0.15 L
        assert obs["quality"] == {"A": "valid", "B": "valid", "load": "valid"}
        assert (state["type"], state["elapsedSec"]) == ("state", second)
        assert state["state"] == client.get("/api/state").json()
        volumes = service.state.V  # 서비스의 구역별 부피(m³)
        assert state["model"]["volumesL"] == {z: volumes[z] * 1000 for z in "ABC"}
    records = lines(journal)
    assert [r["type"] for r in records] == ["meta", "cmd"] + ["obs", "state"] * 3
    assert all(next(iter(r)) == "type" for r in records)


# state 줄이 보정 내역과 물 수지를 담는지 검사
def test_state_lines_carry_the_correction_and_the_water_balance(
    builder, clock, journal, config, params
):
    source = Script(readout(config, a_mm=20, b_mm=10), until_s=2)
    _, service = session(builder, clock, source=source, seconds=3)
    models = [r["model"] for r in subset(lines(journal), "state")]
    assert len(models) == 3
    for model in models:
        assert set(model) == MODEL_KEYS
        assert set(model["drainedL"]) == set(params.inlets)
    for model in models[:2]:
        assert set(model["correction"]) == {"A", "B"}
        for zone, change in model["correction"].items():
            assert change["afterL"] == model["volumesL"][zone]
            assert change["deltaL"] == pytest.approx(change["afterL"] - change["beforeL"])
    assert models[2]["correction"] == {}
    deltas = [c["deltaL"] for m in models for c in m["correction"].values()]
    final, state = models[-1], service.state
    assert final["correctionTotalL"] == pytest.approx(sum(deltas))
    assert final["rainTotalL"] == pytest.approx(state.rain_m3 * 1000) and final["rainTotalL"] > 0
    assert final["drainedL"] == pytest.approx({i: v * 1000 for i, v in state.drained_m3.items()})



# 도는 동안의 조작이 적용 시각(처리한 마지막 틱의 경과 초)과 함께 기록되는지 검사
def test_controls_during_a_run_are_logged_with_their_apply_time(builder, clock, journal):
    client, service = session(builder, clock, source=Script(None), seconds=2)
    answer(client, "/api/rain", {"intensity": "light"})  # 2초째에 비를 약하게 변환
    # 2초째에 3번을 부분 차단
    answer(client, "/api/blockage", {"type": "partial", "location": "INLET-03"})
    lapse(clock, service, 1)
    answer(client, "/api/rain", {"mmPerHour": 42.5})  # 3초째에 비를 42.5 mm/h 로 변환
    answer(client, "/api/rain", {"mmPerHour": 42.5})
    answer(client, START_URL, {"rain": "heavy"})  # 돌고 있을 때 다시 시작하면 start 줄이 또 남음
    answer(client, STOP_URL)
    # 멈춘 뒤의 조작은 이 회차에 적지 않음. 다음 start 줄이 가져감
    answer(client, "/api/rain", {"intensity": "light"})
    answer(client, RESET_URL)

    records = lines(journal)
    cmds = subset(records, "cmd")
    assert [(c["kind"], c["elapsedSec"]) for c in cmds] == [
        ("start", 0.0),
        ("rain", 2.0),
        ("blockage", 2.0),
        ("rain", 3.0),
        ("rain", 3.0),
        ("start", 3.0),
        ("stop", 3.0),
    ]
    assert records[-1] == cmds[-1] and journal.index() == [ID]
    rain, blockage, start, stop = cmds[1], cmds[2], cmds[5], cmds[6]
    assert (rain["rainMmPerHour"], rain["receivedAt"]) == (30.0, stamp(2))
    assert blockage["blockage"] == {"type": "partial", "location": "INLET-03"}
    assert cmds[3]["rainMmPerHour"] == cmds[4]["rainMmPerHour"] == 42.5
    assert start["rainMmPerHour"] == 90.0
    assert start["blockage"] == {"type": "partial", "location": "INLET-03"}
    base = ["type", "kind", "elapsedSec", "receivedAt"]  # 모든 cmd 줄의 공통 키
    assert (list(rain), list(blockage)) == (base + ["rainMmPerHour"], base + ["blockage"])
    assert (list(stop), stop["receivedAt"]) == (base, stamp(3))


# 도는 중 초기화가 회차의 마지막 줄이 되는지 검사
def test_a_reset_during_a_run_is_its_last_line(builder, clock, journal):
    client, _ = session(  # 약한 비로 시작해 1초 돌림
        builder, clock, body={"rain": "light"}, source=Script(None), seconds=1
    )
    answer(client, RESET_URL)
    last = lines(journal)[-1]
    assert (last["type"], last["kind"], last["elapsedSec"]) == ("cmd", "reset", 1.0)
    answer(client, START_URL)
    start = subset(lines(journal, "EXP-20261022-002"), "cmd")[0]
    assert (start["rainMmPerHour"], start["blockage"]) == (60.0, NO_BLOCKAGE)


# 대기 중 고른 값이 start 줄로 기록에 들어가는지 검사
def test_selections_made_while_idle_reach_the_log_through_the_start_line(
    builder, journal
):
    client = builder(source=Script(None))
    answer(client, "/api/rain", {"intensity": "light"})
    answer(client, "/api/blockage", {"type": "partial", "location": "INLET-01"})
    assert journal.index() == []
    answer(client, START_URL)
    start = subset(lines(journal), "cmd")[0]  # 첫 cmd 줄(start)을 꺼냄
    assert start["rainMmPerHour"] == 30.0
    assert start["blockage"] == {"type": "partial", "location": "INLET-01"}


INVALID_READINGS = {  # 무효 관측 사례: (바꿀 관측값, 바꿀 상태, 무효가 될 센서)
    "distance-nan": ({"distA_mm": math.nan}, {}, "A"),
    "distance-out-of-range": ({"distA_mm": 150.0}, {}, "A"),
    "status-not-ok": ({}, {"B": "error"}, "B"),
    "weight-nan": ({"weight_g": math.nan}, {}, "load"),
    "weight-status-not-ok": ({}, {"load": "error"}, "load"),
}


@pytest.mark.parametrize(
    ("readings", "status", "bad"), INVALID_READINGS.values(), ids=INVALID_READINGS.keys()
)
# 무효 관측도 받은 그대로 적고 그 센서 값은 보정에서 빼는지 검사
def test_an_invalid_reading_is_logged_as_received_and_left_out(
    builder, clock, journal, config, readings, status, bad
):
    good = readout(config, a_mm=20, b_mm=10, weight_g=150)
    source = Script({**good, **readings}, {**SENSOR_OK, **status})
    client, _ = session(builder, clock, source=source, seconds=1)
    obs, state = lines(journal)[-2:]
    assert obs["raw"]["readings"] == encoding(source.readings)
    assert obs["raw"]["sensorStatus"] == source.status  # 센서 상태도 그대로 적혀야 함
    assert obs["quality"] == {s: "invalid" if s == bad else "valid" for s in ("A", "B", "load")}
    values = {**obs["levelsMm"], "load": obs["drainVolumeL"]}
    assert [s for s, value in values.items() if value is None] == [bad]
    assert set(state["model"]["correction"]) == {"A", "B"} - {bad}
    assert client.get("/api/state").json()["runState"] == "running"


# 계산 오류가 나면 event 줄로 기록을 끝내는지 검사
def test_a_calc_error_ends_the_log_with_an_event(
    builder, clock, journal, config, monkeypatch
):
    source = Script(readout(config, a_mm=20, b_mm=10))  # A 20 mm, B 10 mm 를 매번 내는 입력원
    client, service = session(builder, clock, source=source, seconds=1)

    # 항상 실패하는 가짜 계산 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")

    monkeypatch.setattr("app.service.evolution", wreck)
    clock.jump(1.0)
    assert service.catchup() == 0
    records = lines(journal)
    # 실패한 2초 틱의 obs·state 는 없고 그 자리에 event 하나
    assert [r["type"] for r in records] == ["meta", "cmd", "obs", "state", "event"]
    assert records[-1] == {  # 마지막 줄은 event 여야 함
        "type": "event",
        "kind": "calc_error",
        "elapsedSec": 2.0,
        "time": stamp(2),
        "message": "Underflow: A 저장량이 -1.0 m³ 다",
    }
    assert client.get("/api/state").json()["runState"] == "stopped"


# 계약 밖 상태가 나오면 GET 이 깨지지 않고 회차가 멈추는지 검사
def test_a_state_outside_the_contract_stops_the_run_instead_of_breaking_get(
    builder, clock, journal, config
):
    # 설정을 복사. 센서를 높이 달면 관측 수위가 계약 범위(0~500 mm)를 넘을 수 있음
    cfg = copy.deepcopy(config)
    cfg["sensors"]["A"] = {**cfg["sensors"]["A"], "install_height_mm": 900, "max_range_mm": 900}
    source = Script(readout(cfg, a_mm=20, b_mm=10))
    client, service = session(builder, clock, source=source, seconds=1, cfg=cfg)
    # 다음 관측은 A 수위 600 mm 로 계약 범위를 넘음
    source.readings = readout(cfg, a_mm=600, b_mm=10)
    clock.jump(1.0)
    assert service.catchup() == 0
    event = lines(journal)[-1]
    assert (event["type"], event["kind"], event["elapsedSec"]) == ("event", "calc_error", 2.0)
    assert event["message"].startswith("ValidationError: ")
    response = client.get("/api/state")  # 멈춘 화면은 계약을 지킨 마지막 틱의 상태
    assert response.status_code == 200  # 성공(200)이어야 함
    assert (response.json()["runState"], response.json()["elapsedSec"]) == ("stopped", 1)



# 실험 ID: 그 날짜 기록 중 가장 큰 번호 + 1 인지 검사
def test_the_next_id_follows_the_logs_of_that_date(builder, journal):
    for experiment_id in ("EXP-20261022-001", "EXP-20261022-007", "EXP-20261021-012"):
        journal.entry(experiment_id, {"type": "meta"})
    client = builder(source=Script(None))
    assert answer(client, START_URL)["experimentId"] == "EXP-20261022-008"


# 서버를 다시 띄워도 ID 가 겹치지 않는지 검사
def test_ids_stay_unique_across_server_restarts(builder):
    first = builder(source=Script(None))
    assert answer(first, START_URL)["experimentId"] == "EXP-20261022-001"
    second = builder(source=Script(None))
    assert answer(second, START_URL)["experimentId"] == "EXP-20261022-002"



# 기록을 못 쓰면 시작·강우·막힘은 503 거절, 종료·초기화는 적용. 먼저 시작 거절 검사
def test_a_start_the_log_cannot_take_is_503_and_starts_nothing(builder, journal):
    log = Breaker(journal)
    client = builder(source=Script(None), experiment_log=log)
    before = client.get("/api/state").json()
    log.fail = DISK_FULL
    response = client.post(START_URL, json={"rain": "heavy"})
    assert (response.status_code, response.json()) == (503, UNAVAILABLE)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert journal.index() == []
    log.fail = None
    assert answer(client, START_URL)["experimentId"] == ID  # 다시 시작하면 첫 회차 ID 를 받아야 함


# 첫 줄을 쓰다 끊기면 기록도 회차 번호도 남지 않는지 검사
def test_a_start_cut_short_leaves_no_log_and_keeps_the_number(builder, journal, monkeypatch):
    client = builder(source=Script(None))
    before = client.get("/api/state").json()
    breakage(monkeypatch)
    response = client.post(START_URL, json={"rain": "heavy"})
    assert (response.status_code, response.json()) == (503, UNAVAILABLE)
    monkeypatch.undo()
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert journal.index() == []
    assert answer(client, START_URL)["experimentId"] == ID


# 503 사유에 파일 경로가 안 들어가는지 검사
def test_the_503_reason_leaves_out_the_file_path(builder, journal):
    client = builder(source=Script(None), experiment_log=Blocker(journal))
    response = client.post(START_URL, json={})
    assert (response.status_code, response.json()) == (  # 503 과 경로 없는 사유여야 함
        503,
        {"detail": "실험 기록을 쓸 수 없다: Permission denied"},
    )
    assert client.get("/api/state").json()["runState"] == "idle"  # 상태는 대기 그대로여야 함


RUN_CONTROLS = {
    "rain": ("/api/rain", {"mmPerHour": 42.5}),
    "blockage": ("/api/blockage", {"type": "full", "location": "INLET-01"}),
    "start": (
        START_URL,
        {"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-03"}},
    ),
}


@pytest.mark.parametrize(("path", "body"), RUN_CONTROLS.values(), ids=RUN_CONTROLS.keys())
# 기록이 못 받는 조작은 503 이고 아무것도 안 바꾸는지 검사
def test_a_control_the_log_cannot_take_is_503_and_changes_nothing(
    builder, clock, journal, path, body
):
    log = Breaker(journal)
    client, service = session(  # 그 기록기로 회차를 시작해 1초 돌림
        builder, clock, source=Script(None), experiment_log=log, seconds=1
    )
    before, conditions, written = (
        client.get("/api/state").json(),
        service.conditions,
        lines(journal),
    )
    log.fail = DISK_FULL
    response = client.post(path, json=body)
    assert (response.status_code, response.json()) == (503, UNAVAILABLE)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert service.conditions == conditions  # 서비스 조건도 그대로여야 함
    assert lines(journal) == written  # 기록 줄도 그대로여야 함


@pytest.mark.parametrize(
    ("path", "run_state"), [(STOP_URL, "stopped"), (RESET_URL, "idle")], ids=["stop", "reset"]
)
# 기록을 못 써도 정지·초기화는 적용되는지 검사
def test_stop_and_reset_apply_even_when_the_log_cannot_take_them(
    builder, clock, journal, caplog, path, run_state
):
    log = Breaker(journal)
    client, _ = session(  # 그 기록기로 회차를 시작해 1초 돌림
        builder, clock, source=Script(None), experiment_log=log, seconds=1
    )
    written = lines(journal)
    log.fail = DISK_FULL
    with caplog.at_level(logging.WARNING, logger="app.service"):
        assert answer(client, path)["runState"] == run_state
    assert lines(journal) == written
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


# 기록이 못 받는 틱은 회차를 멈추는지 검사
def test_a_tick_the_log_cannot_take_stops_the_run(builder, clock, journal, caplog):
    from app.service import Outage

    log = Breaker(journal)
    client, service = session(  # 그 기록기로 회차를 시작해 1초 돌림
        builder, clock, source=Script(None), experiment_log=log, seconds=1
    )
    written = lines(journal)
    log.fail = DISK_FULL
    clock.jump(1.0)
    with caplog.at_level(logging.WARNING, logger="app.service"):
        assert service.catchup() == 0
    body = client.get("/api/state").json()
    assert (body["runState"], body["elapsedSec"]) == ("stopped", 1)
    assert lines(journal) == written
    # 틱 실패(ERROR) 하나, 그 event 도 못 썼다는 경고(WARNING) 하나
    assert [r.levelno for r in caplog.records] == [logging.ERROR, logging.WARNING]
    error = caplog.records[0].exc_info[1]
    assert isinstance(error, Outage) and isinstance(error.__cause__, OSError)
