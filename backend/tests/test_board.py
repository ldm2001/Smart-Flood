import copy
import pytest
from app.core.predictor import ASSUMPTION_RULE, TREND_RULE
from tests.helpers import breakage, lapse
from tests.test_check06_devices import message

START = "/api/experiment/start"


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
