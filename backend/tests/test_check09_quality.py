from tests.helpers import lapse
from tests.test_check06_devices import LIVE, START, message


# live 에서 돌기 시작한 뒤 관측이 하나도 없으면 invalid 인지 검사
def test_no_observation_is_invalid(client, clock, service):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["quality"] == "invalid"


# A 만 있는 REV16 메시지(B·로드셀 absent)가 valid 인지 검사
def test_absent_sensors_do_not_degrade(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    client.post("/api/ingest", json=message(config, 1))
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["quality"] == "valid"


# 마지막 유효 관측의 나이로 valid(3초까지)·degraded(3~10초)·invalid(10초부터)를 가르는지 검사
def test_quality_follows_the_age_of_the_last_valid_reading(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    client.post("/api/ingest", json=message(config, 1))
    lapse(clock, service, 1)  # 관측 경과 1초
    seen = []
    for _ in range(10):  # 나이 1~10초
        lapse(clock, service, 1)
        seen.append(client.get("/api/state").json()["quality"])
    assert seen == ["valid"] * 3 + ["degraded"] * 6 + ["invalid"]


# B 가 ok 로 오다 absent 로 바뀌면 더는 B 를 기대하지 않아 A 만으로 valid 가 되는지 검사
def test_a_sensor_turning_absent_is_no_longer_expected(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    client.post("/api/ingest", json=message(config, 1, b_mm=40.0))  # A·B 둘 다 ok
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["quality"] == "valid"
    for _ in range(4):  # 4초 동안 메시지가 없어 A·B 관측이 모두 오래됨
        lapse(clock, service, 1)
    assert client.get("/api/state").json()["quality"] == "degraded"
    client.post("/api/ingest", json=message(config, 2))  # 이제 B 는 absent
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["quality"] == "valid"


# A 가 fault 인 메시지는 관측으로 치지 않아 품질이 떨어지고 장치는 online 인지 검사
def test_fault_message_is_not_a_reading(client, clock, service, config):
    client.post("/api/source", json=LIVE)
    client.post(START, json={})
    client.post("/api/ingest", json=message(config, 1))
    lapse(clock, service, 1)
    for seq in range(2, 6):  # 4초 동안 fault 만 옴
        client.post("/api/ingest", json=message(config, seq, status="fault"))
        lapse(clock, service, 1)
    body = client.get("/api/state").json()
    assert (body["quality"], body["devices"]["esp32_1"]) == ("degraded", "online")
