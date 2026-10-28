from app.core.calibration import Sensor, gap
from tests.helpers import lapse

LIVE = {"mode": "live"}
START = "/api/experiment/start"


# REV16 펌웨어 모양의 메시지. 수위센서는 A 하나, B·로드셀은 absent
def message(
    config, seq: int, *, a_mm: float = 40.0, status: str = "ok", device: str = "esp32_1"
) -> dict:
    sensor = Sensor.config(config["sensors"]["A"])
    distance = gap(a_mm / 1000, sensor) if status == "ok" else None  # fault 면 값 없음
    return {
        "deviceId": device,
        "bootId": "b1",
        "seq": seq,
        "tMs": seq * 1000,
        "readings": {"distA_mm": distance, "distB_mm": None, "weight_g": None},
        "sensorStatus": {"A": status, "B": "absent", "load": "absent"},
    }


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


# sim 입력원에서는 메시지를 받아만 두고 상태를 바꾸지 않는지 검사
def test_sim_source_ignores_ingest(client, config):
    before = client.get("/api/state").json()
    response = client.post("/api/ingest", json=message(config, 1))
    assert (response.status_code, response.json()["dataSource"]) == (200, "sim")
    assert client.get("/api/state").json() == before
