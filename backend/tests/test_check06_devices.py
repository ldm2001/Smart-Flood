import json
import pytest
from app.core.calibration import Sensor, gap
from tests.helpers import footage, lapse

LIVE = {"mode": "live"}
START = "/api/experiment/start"


# REV16 펌웨어 모양의 메시지. 수위센서는 A 하나, B·로드셀은 absent(b_mm 을 주면 B 도 ok)
def message(
    config,
    seq: int,
    *,
    a_mm: float = 40.0,
    status: str = "ok",
    device: str = "esp32_1",
    b_mm: float | None = None,
    switch: str | None = None,  # floatSwitch 값(None 이면 필드를 뺌, 옛 펌웨어)
) -> dict:
    sensor = Sensor.config(config["sensors"]["A"])
    distance = gap(a_mm / 1000, sensor) if status == "ok" else None  # fault 면 값 없음
    side = None if b_mm is None else gap(b_mm / 1000, Sensor.config(config["sensors"]["B"]))
    body = {
        "deviceId": device,
        "bootId": "b1",
        "seq": seq,
        "tMs": seq * 1000,
        "readings": {"distA_mm": distance, "distB_mm": side, "weight_g": None},
        "sensorStatus": {"A": status, "B": "absent" if b_mm is None else "ok", "load": "absent"},
    }
    return body if switch is None else {**body, "floatSwitch": switch}


# live 로 바꾸면 dataSource 가 live 인 대기 상태가 되고, 또 보내도 같은지 검사
def test_live_source_switches_the_data_source(client):
    response = client.post("/api/source", json=LIVE)
    assert response.status_code == 200
    body = response.json()
    assert (body["dataSource"], body["runState"]) == ("live", "idle")
    assert client.post("/api/source", json=LIVE).json() == body


# 회차가 도는 중에는 입력원을 못 바꾸고(409), 멈춘 뒤에는 되는지 검사
def test_switching_the_source_while_running_is_409(client):
    client.post(START, json={})
    assert client.post("/api/source", json=LIVE).status_code == 409
    client.post("/api/experiment/stop", json={})
    assert client.post("/api/source", json=LIVE).status_code == 200


# 받은 메시지에 영수증(장치·순번·입력원)을 주는지 검사
def test_ingest_gives_a_receipt(client, config):
    client.post("/api/source", json=LIVE)
    response = client.post("/api/ingest", json=message(config, 1))
    assert response.status_code == 200
    assert response.json() == {"deviceId": "esp32_1", "seq": 1, "dataSource": "live"}


# 허용 목록에 없는 장치는 422 인지 검사
def test_unknown_device_is_422(client, config):
    response = client.post("/api/ingest", json=message(config, 1, device="esp32_9"))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "deviceId"]


# 모양이 틀린 메시지는 422 인지 검사
def test_malformed_message_is_422(client):
    assert client.post("/api/ingest", json={"deviceId": "esp32_1"}).status_code == 422


# live 에서 받은 A 수위가 다음 tick 에 measured 로 보이고 B·C 는 추정인지 검사
def test_live_reading_shows_as_measured(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    client.post("/api/ingest", json=message(config, 1, a_mm=40.0))
    lapse(clock, service, 1)
    zones = client.get("/api/state").json()["zones"]
    assert (zones["A"]["levelMm"], zones["A"]["source"]) == (40, "measured")
    assert (zones["B"]["source"], zones["C"]["source"]) == ("estimated", "estimated")


# live 수위가 모델 평형보다 훨씬 높아도 회차가 멈추지 않고 변화율이 계약 범위(±20) 안인지 검사
def test_live_level_far_above_the_model_keeps_the_run_going(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    for seq in range(1, 4):  # 보정이 모델 상태를 관측까지 끌어올리는 데 몇 tick 걸림
        client.post("/api/ingest", json=message(config, seq, a_mm=90.0))
        lapse(clock, service, 1)
    body = client.get("/api/state").json()
    assert body["runState"] == "running"
    assert all(-20 <= zone["rateMmSec"] <= 20 for zone in body["zones"].values())


# live 에서 A 실측이 0 부터 약 1 mm/s 로 오르면 모델 수위와 관계없이 주의, 40 mm 부터 침수인지 검사
def test_rising_live_level_raises_the_alert_from_the_measurement(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    stages = {}  # 보낸 A 수위(mm) → 그 tick 뒤 A 경보
    for seq in range(1, 46):
        client.post("/api/ingest", json=message(config, seq, a_mm=float(seq - 1)))
        lapse(clock, service, 1)
        alerts = client.get("/api/state").json()["alerts"]
        stages[seq - 1] = next((a for a in alerts if a["zone"] == "A"), None)
    early = stages[5]  # 5 mm, 1 mm/s 면 한계까지 35 초라 주의
    assert early is not None and early["stage"] == "caution" and early["etaSec"] <= 60
    assert stages[15]["stage"] == "warning"  # 15 mm 면 25 초라 경계
    assert stages[40]["stage"] == "evacuate"  # 한계 40 mm 도달


# 장치 상태: 마지막 수신 뒤 5초 전이면 online, 5초부터 offline. 안 보내는 esp32_2 는 offline
def test_devices_follow_the_last_receipt(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    client.post("/api/ingest", json=message(config, 1))
    lapse(clock, service, 4)
    devices = client.get("/api/state").json()["devices"]
    assert (devices["esp32_1"], devices["esp32_2"]) == ("online", "offline")
    assert (devices["floatSwitch"], devices["emergencyStop"]) == ("unknown", "unknown")
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["devices"]["esp32_1"] == "offline"


# 대기 중에는 tick 이 없어도 마지막 수신 뒤 5초가 지나면 offline 으로 읽히는지 검사
def test_idle_devices_go_offline_without_a_tick(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post("/api/ingest", json=message(config, 1))
    assert client.get("/api/state").json()["devices"]["esp32_1"] == "online"
    lapse(clock, service, 5)
    assert client.get("/api/state").json()["devices"]["esp32_1"] == "offline"


# 허용 목록에 esp32_2 가 없어도 응답이 계약 모양(장치 4개)을 지키는지 검사
def test_devices_keep_the_contract_keys_for_a_short_allowed_list(builder, config):
    short = {**config, "devices": {**config["devices"], "allowed": ["esp32_1"]}}
    client = builder(short)
    client.post("/api/source", json=LIVE)
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["devices"]["esp32_2"] == "offline"


# sim 입력원에서는 메시지를 받아만 두고 상태를 바꾸지 않는지 검사
def test_sim_source_ignores_ingest(client, config):
    before = client.get("/api/state").json()
    response = client.post("/api/ingest", json=message(config, 1))
    assert (response.status_code, response.json()["dataSource"]) == (200, "sim")
    assert client.get("/api/state").json() == before


# live 에서 마지막 메시지의 floatSwitch(low·normal)가 장치 상태에 그대로 나오는지 검사
@pytest.mark.parametrize("value", ["low", "normal"])
def test_live_float_switch_follows_the_last_message(client, config, value):
    client.post("/api/source", json=LIVE)
    response = client.post("/api/ingest", json=message(config, 1, switch=value))
    assert response.status_code == 200
    assert client.get("/api/state").json()["devices"]["floatSwitch"] == value


# 마지막 메시지에 floatSwitch 가 없으면 앞 메시지가 low 였어도 unknown 인지 검사
def test_missing_float_switch_is_unknown(client, config):
    client.post("/api/source", json=LIVE)
    client.post("/api/ingest", json=message(config, 1, switch="low"))
    client.post("/api/ingest", json=message(config, 2))
    assert client.get("/api/state").json()["devices"]["floatSwitch"] == "unknown"


# 보낸 장치가 offline(마지막 수신 뒤 offline_after_s)이 되면 unknown 인지 검사
def test_offline_float_switch_is_unknown(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post("/api/ingest", json=message(config, 1, switch="low"))
    lapse(clock, service, 4)
    assert client.get("/api/state").json()["devices"]["floatSwitch"] == "low"
    lapse(clock, service, 1)
    devices = client.get("/api/state").json()["devices"]
    assert (devices["esp32_1"], devices["floatSwitch"]) == ("offline", "unknown")


# normal·low 가 아닌 글자는 unknown 인지 검사
@pytest.mark.parametrize("value", ["stuck", "LOW", ""])
def test_odd_float_switch_is_unknown(client, config, value):
    client.post("/api/source", json=LIVE)
    assert client.post("/api/ingest", json=message(config, 1, switch=value)).status_code == 200
    assert client.get("/api/state").json()["devices"]["floatSwitch"] == "unknown"


# sim 에서는 low 를 받아도 시뮬레이션 값 normal 인지 검사
def test_sim_float_switch_stays_normal(client, config):
    client.post("/api/ingest", json=message(config, 1, switch="low"))
    devices = client.get("/api/state").json()["devices"]
    assert (devices["floatSwitch"], devices["emergencyStop"]) == ("normal", "normal")


# floatSwitch 가 있든 없든 받고, 기록 원문은 받은 모양 그대로이며 재생에서는 normal 인지 검사
def test_ingest_takes_messages_with_and_without_float_switch(
    client, clock, service, config, journal
):
    client.post("/api/source", json=LIVE)
    log_id = client.post(START, json={}).json()["experimentId"]
    sent = [message(config, 1, switch="low"), message(config, 2)]  # 새 펌웨어, 옛 펌웨어
    for body in sent:
        response = client.post("/api/ingest", json=body)
        assert response.status_code == 200
        assert response.json() == {"deviceId": "esp32_1", "seq": body["seq"], "dataSource": "live"}
    lapse(clock, service, 1)
    client.post("/api/experiment/stop", json={})
    assert [r["raw"] for r in journal.records(log_id) if r["type"] == "obs"] == sent
    states = [json.loads(body) for body in footage(client, clock, log_id)]
    assert {s["devices"]["floatSwitch"] for s in states} == {"normal"}
