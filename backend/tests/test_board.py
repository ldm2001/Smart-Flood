import copy
import json
import pytest
from app.core.predictor import ASSUMPTION_RULE, TREND_RULE
from tests.helpers import Mailbox, Script, breakage, chronicle, footage, lapse, readout, revision
from tests.test_check06_devices import message
from tests.test_replay import tapes

START = "/api/experiment/start"
ROSTER = {  # 시뮬레이션·재생의 장치 상태(늘 연결·정상)
    "esp32_1": "online",
    "esp32_2": "online",
    "floatSwitch": "normal",
    "emergencyStop": "normal",
}
SOURCE_EDITS = {  # meta 의 dataSource 를 고치는 방법(이름 → meta 를 받아 고친 meta)
    "missing": lambda meta: {k: v for k, v in meta.items() if k != "dataSource"},
    "unknown": lambda meta: {**meta, "dataSource": "board"},
    "not-text": lambda meta: {**meta, "dataSource": 1},
}


# 보드 메시지 하나(running 은 보드 회차가 열려 있는지)
def board(config, seq: int, running: bool, **kwargs) -> dict:
    return {**message(config, seq, **kwargs), "running": running}


# A 를 0 mm 부터 1 mm/s 로 top mm 까지 보내고 마지막 tick 까지 처리. 첫 메시지가 회차를 엶
def ramp(client, clock, service, config, top: int) -> dict:
    for seq in range(1, top + 2):
        client.post("/api/ingest", json=board(config, seq, True, a_mm=float(seq - 1)))
        lapse(clock, service, 1)
    return client.get("/api/state").json()


# 대기 중인 sim 에서 보드가 회차를 시작하면 live 로 바꾸고 회차를 열어 그 메시지부터 쓰는지 검사
def test_board_start_opens_a_live_run(client, clock, service, config):
    response = client.post("/api/ingest", json=board(config, 1, True, a_mm=12.0))
    assert response.status_code == 200
    assert response.json()["dataSource"] == "live"
    lapse(clock, service, 1)
    body = client.get("/api/state").json()
    assert (body["dataSource"], body["runState"]) == ("live", "running")
    assert body["zones"]["A"]["levelMm"] == pytest.approx(12.0, abs=0.01)
    assert body["zones"]["A"]["source"] == "measured"


# 같은 running 이 이어지면 그대로, 보드가 정지하면 따라 연 회차를 닫고
# 다시 시작하면 새 회차인지 검사
def test_board_stop_closes_the_followed_run(client, clock, service, config):
    client.post("/api/ingest", json=board(config, 1, True))
    first = client.get("/api/state").json()["experimentId"]
    lapse(clock, service, 1)
    client.post("/api/ingest", json=board(config, 2, True))
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["experimentId"] == first
    client.post("/api/ingest", json=board(config, 3, False))
    body = client.get("/api/state").json()
    assert (body["runState"], body["experimentId"]) == ("stopped", first)
    client.post("/api/ingest", json=board(config, 4, True))
    body = client.get("/api/state").json()
    assert body["runState"] == "running" and body["experimentId"] != first


# sim 회차가 도는 중이면 보드 시작을 따라가지 않는지 검사
def test_board_start_never_interrupts_a_sim_run(client, clock, service, config):
    run = client.post(START, json={}).json()["experimentId"]
    response = client.post("/api/ingest", json=board(config, 1, True))
    assert response.json()["dataSource"] == "sim"
    body = client.get("/api/state").json()
    assert (body["dataSource"], body["runState"], body["experimentId"]) == ("sim", "running", run)


# 재생 중이면 보드 시작을 따라가지 않는지 검사
def test_board_start_leaves_a_replay_alone(client, clock, service, config):
    log_id = client.post(START, json={}).json()["experimentId"]
    lapse(clock, service, 2)
    client.post("/api/experiment/stop", json={})
    assert client.post("/api/source", json={"mode": "replay", "logId": log_id}).status_code == 200
    client.post("/api/ingest", json=board(config, 1, True))
    assert client.get("/api/state").json()["dataSource"] == "replay"


# /ops 에서 연 live 회차는 보드 정지로 닫지 않는지 검사(손으로 닫음)
def test_board_stop_leaves_an_ops_run_open(client, clock, service, config):
    client.post("/api/source", json={"mode": "live"})
    run = client.post(START, json={}).json()["experimentId"]
    client.post("/api/ingest", json=board(config, 1, True))
    client.post("/api/ingest", json=board(config, 2, False))
    body = client.get("/api/state").json()
    assert (body["runState"], body["experimentId"]) == ("running", run)


# 따라 연 회차를 손으로 멈추고 재생을 돌리면 보드 정지가 재생을 멈추지 않는지 검사
def test_board_stop_leaves_a_later_replay_running(client, clock, service, config):
    client.post("/api/ingest", json=board(config, 1, True))
    log_id = client.get("/api/state").json()["experimentId"]
    lapse(clock, service, 3)
    client.post("/api/experiment/stop", json={})
    client.post("/api/source", json={"mode": "replay", "logId": log_id})
    running = client.get("/api/state").json()["runState"]
    client.post("/api/ingest", json=board(config, 2, False))
    body = client.get("/api/state").json()
    assert (body["dataSource"], body["runState"]) == ("replay", running)


# live.follow 가 false 거나 live 가 없으면 running 을 봐도 입력원과 회차를 그대로 두는지 검사
@pytest.mark.parametrize(
    "damage",
    [lambda c: c["live"].update(follow=False), lambda c: c.pop("live")],
    ids=["follow-false", "no-live"],
)
def test_follow_off_ignores_the_board(builder, config, damage):
    cfg = copy.deepcopy(config)
    damage(cfg)
    client = builder(cfg)
    client.post("/api/ingest", json=board(config, 1, True))
    body = client.get("/api/state").json()
    assert (body["dataSource"], body["runState"]) == ("sim", "idle")


# live.follow 가 true·false 가 아니거나 live 가 표가 아니면 기동에서 실패하는지 검사
@pytest.mark.parametrize(
    "damage",
    [
        lambda c: c["live"].update(follow="yes"),
        lambda c: c["live"].update(follow=1),
        lambda c: c["live"].update(follow=None),
        lambda c: c.update(live=True),
    ],
    ids=["text", "number", "null", "not-a-table"],
)
def test_follow_must_be_a_bool(builder, config, damage):
    cfg = copy.deepcopy(config)
    damage(cfg)
    with pytest.raises(ValueError):
        builder(cfg)


# 회차를 열 기록을 쓰지 못하면 경고만 남기고 영수증은 주며, 다음 메시지에서 다시 여는지 검사
def test_board_start_retries_after_a_write_failure(client, clock, service, config, monkeypatch):
    with monkeypatch.context() as patch:
        breakage(patch)
        response = client.post("/api/ingest", json=board(config, 1, True))
        assert response.status_code == 200
        assert client.get("/api/state").json()["runState"] == "idle"
    client.post("/api/ingest", json=board(config, 2, True))
    assert client.get("/api/state").json()["runState"] == "running"


# running 은 선택 필드라 있으면 기록 원문에 남고 없으면 빠지며, 참·거짓이 아니면 422 인지 검사
def test_running_is_an_optional_flag(client, clock, service, config, journal):
    sent = [board(config, 1, True), message(config, 2)]  # 새 펌웨어, 옛 펌웨어
    for body in sent:
        assert client.post("/api/ingest", json=body).status_code == 200
    log_id = client.get("/api/state").json()["experimentId"]
    lapse(clock, service, 1)
    client.post("/api/experiment/stop", json={})
    assert [r["raw"] for r in journal.records(log_id) if r["type"] == "obs"] == sent
    assert client.post("/api/ingest", json=board(config, 3, "yes")).status_code == 422


# live 에서 센서 없는 B·C 는 A 수면 높이에서 판정해 보드의 z 70·110 mm 와 같은 도달 초인지 검사
def test_zones_without_a_sensor_follow_the_a_surface(client, clock, service, config):
    body = ramp(client, clock, service, config, 30)
    zones, alerts = body["zones"], {a["zone"]: a for a in body["alerts"]}
    assert zones["A"]["levelMm"] == pytest.approx(30.0, abs=0.01)
    assert zones["B"]["levelMm"] == pytest.approx(10.0, abs=0.01)  # 30 − 바닥 20
    assert zones["C"]["levelMm"] == 0  # 30 − 바닥 60 은 0 으로 표시
    assert (zones["B"]["source"], zones["C"]["source"]) == ("estimated", "estimated")
    assert alerts["B"]["stage"] == "caution" and abs(alerts["B"]["etaSec"] - 40) <= 1  # (70−30)/1
    assert "C" not in alerts  # (110 − 30) / 1 = 80 초라 정상


# live 에서 A 가 신선하면 예측은 수위 + 실측 기울기 × 시간이고 3 초 넘게 끊기면 모델인지 검사
def test_live_predictions_extend_the_measured_rise(client, clock, service, config):
    body = ramp(client, clock, service, config, 20)
    a, b = body["predictions"]["A"], body["predictions"]["B"]
    assert a == pytest.approx({"10": 30.0, "20": 40.0, "30": 50.0}, abs=0.01)
    assert b == pytest.approx({"10": 10.0, "20": 20.0, "30": 30.0}, abs=0.01)
    assert body["predictionMeta"]["assumptions"]["rule"] == TREND_RULE
    lapse(clock, service, 4)  # A 메시지 없이 4 초
    later = client.get("/api/state").json()
    assert later["predictionMeta"]["assumptions"]["rule"] == ASSUMPTION_RULE


# live 회차에서는 수위가 내려가도 단계가 내려가지 않는지 검사(보드와 같음)
def test_live_stages_never_fall_during_a_run(client, clock, service, config):
    ramp(client, clock, service, config, 45)
    for seq in range(47, 67):  # 0 mm 로 20 초
        client.post("/api/ingest", json=board(config, seq, True, a_mm=0.0))
        lapse(clock, service, 1)
    alerts = {a["zone"]: a["stage"] for a in client.get("/api/state").json()["alerts"]}
    assert alerts["A"] == "evacuate"


# 실측 표본이 5 개가 안 되면 가파르게 올라도 기울기를 0 으로 보아 미리 경보하지 않는지 검사
def test_live_needs_five_samples_before_the_slope_counts(client, clock, service, config):
    for seq, a_mm in enumerate((0.0, 10.0, 20.0, 30.0), start=1):  # 10 mm/s, 표본 4 개
        client.post("/api/ingest", json=board(config, seq, True, a_mm=a_mm))
        lapse(clock, service, 1)
    assert client.get("/api/state").json()["alerts"] == []
    client.post("/api/ingest", json=board(config, 5, True, a_mm=35.0))
    lapse(clock, service, 1)
    stages = {a["zone"]: a["stage"] for a in client.get("/api/state").json()["alerts"]}
    assert stages["A"] == "warning"  # 표본 5 개부터 기울기를 씀


# 보드 회차 하나를 기록하고 실험 ID 를 돌려줌
# A 를 45 mm 까지 올리고 0 mm 로 20 초, 메시지 없이 gap 초 뒤 보드 정지
def tide(client, clock, service, config, gap: int = 0) -> str:
    ramp(client, clock, service, config, 45)  # 첫 메시지가 회차를 엶(seq 1~46)
    for seq in range(47, 67):  # 0 mm 로 20 초
        client.post("/api/ingest", json=board(config, seq, True, a_mm=0.0))
        lapse(clock, service, 1)
    lapse(clock, service, gap)
    client.post("/api/ingest", json=board(config, 67, False))  # 보드 정지가 회차를 닫음
    return client.get("/api/state").json()["experimentId"]


# 보드 회차 state 줄이 재생에서 보일 모양. 입력원 표시·품질·장치만 다름
def replica(state: dict) -> dict:
    zones = {
        z: {**zone, "source": "replay" if zone["source"] == "measured" else zone["source"]}
        for z, zone in state["zones"].items()
    }
    marks = {"mode": "replay", "dataSource": "replay", "quality": "valid", "devices": ROSTER}
    return {**state, **marks, "zones": zones}


# 기록의 meta 줄(첫 줄)을 edit 결과로 바꿈
def label(journal, log_id: str, edit) -> None:
    revision(journal, lambda records: [edit(records[0]), *records[1:]], log_id)


# 보드 회차 기록을 재생하면 경보가 tick 마다 기록의 state 줄과 같은지 검사
# 실측 수위로 단계가 오르고, 수위가 0 으로 내려가도 회차 동안 단계가 남아야 함
def test_a_board_run_replays_with_its_recorded_alerts(client, clock, service, config, journal):
    log_id = tide(client, clock, service, config)
    states = chronicle(journal, log_id)
    last = {a["zone"]: a["stage"] for a in states[-1]["alerts"]}
    assert states[-1]["zones"]["A"]["levelMm"] == pytest.approx(0.0, abs=0.01)
    assert last["A"] == "evacuate"  # 0 mm 에서도 침수가 남음
    recorded = [s["alerts"] for s in states]
    replayed = [json.loads(body)["alerts"] for body in footage(client, clock, log_id)]
    assert replayed == [[], *recorded, recorded[-1]]  # 0 초, tick 마다, 기록 끝에서 멈춘 상태


# 보드 회차 재생도 재생 표시(입력원·구역 출처 replay, 품질 valid, 시뮬레이션 장치)는 그대로이고
# 나머지는 기록과 같으며, 기록을 쓰지 않고 알리지도 않는지 검사
def test_a_board_run_replay_keeps_the_replay_marks(builder, clock, config, journal):
    mailbox = Mailbox()
    client = builder(notifier=mailbox)
    service = client.app.state.service
    log_id = tide(client, clock, service, config, gap=5)  # 끊긴 5 초에 degraded·offline 이 남음
    ended, states = client.get("/api/state").json(), chronicle(journal, log_id)
    assert {s["quality"] for s in states} == {"valid", "degraded"}
    assert {s["devices"]["esp32_1"] for s in states} == {"online", "offline"}
    assert "measured" in {s["zones"]["A"]["source"] for s in states}
    sent, files = list(mailbox.events), tapes(journal)
    assert sent  # 기록할 때는 단계 전환을 알림
    bodies = [json.loads(body) for body in footage(client, clock, log_id)]
    assert bodies[1:] == [*map(replica, states), replica(ended)]
    assert {(b["mode"], b["dataSource"], b["quality"]) for b in bodies} == {
        ("replay", "replay", "valid")
    }
    assert all(b["devices"] == ROSTER for b in bodies)
    assert tapes(journal) == files and mailbox.events == sent


@pytest.mark.parametrize("edit", SOURCE_EDITS.values(), ids=SOURCE_EDITS.keys())
# meta 의 dataSource 가 없거나 모르는 값이면 보드 회차 기록도 전처럼 모델로 판정해 재생하는지 검사
# 전에는 모든 재생이 모델 판정이었고, sim 기록의 재생은 지금도 그러함
def test_a_board_log_without_a_known_source_replays_as_before(
    client, clock, service, config, journal, edit
):
    log_id = tide(client, clock, service, config)
    label(journal, log_id, lambda meta: {**meta, "dataSource": "sim"})
    model = footage(client, clock, log_id)  # 모델 판정의 재생
    label(journal, log_id, edit)
    bodies = footage(client, clock, log_id)
    assert bodies == model
    rules = {json.loads(body)["predictionMeta"]["assumptions"]["rule"] for body in bodies}
    assert rules == {ASSUMPTION_RULE}  # 실측 추세 예측이 한 번도 없음


# 보드 회차 재생을 떠나 sim 으로 돌아가면 판정 기준도 지금 입력원으로 돌아오는지 검사
def test_leaving_a_board_replay_returns_to_the_current_source(builder, clock, config):
    client = builder(source=Script(readout(config, a_mm=30.0, b_mm=10.0)))
    service = client.app.state.service
    log_id = tide(client, clock, service, config)
    assert service.basis == "live"
    footage(client, clock, log_id)
    assert service.basis == "live"  # 재생 중에는 기록한 입력원
    client.post("/api/source", json={"mode": "sim"})
    assert service.basis == "sim"
    client.post(START, json={})
    lapse(clock, service, 6)  # A·B 관측이 tick 마다 들어옴
    body = client.get("/api/state").json()
    assert (body["dataSource"], body["runState"]) == ("sim", "running")
    assert body["predictionMeta"]["assumptions"]["rule"] == ASSUMPTION_RULE  # 모델 판정
