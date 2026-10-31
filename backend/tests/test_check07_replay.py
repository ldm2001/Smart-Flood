import json
import pytest
from tests.helpers import Mailbox, digests, footage, lapse

ID = "EXP-20261022-001"
SOURCE_URL = "/api/source"
STOP_URL = "/api/experiment/stop"

SCENARIO = (  # (조작, 뒤에 돌릴 초) 목록. 센 비·완전 막힘·직접 입력을 거쳐 30 틱
    ("/api/experiment/start", {"rain": "heavy"}, 10),
    ("/api/blockage", {"type": "full", "location": "INLET-01"}, 10),
    ("/api/rain", {"mmPerHour": 120}, 10),
    (STOP_URL, {}, 0),
)

RAIN_REFUSED = "재생 중에는 강우를 바꿀 수 없다. 입력원을 sim 으로 바꾼 뒤 한다"
BLOCKAGE_REFUSED = "재생 중에는 막힘을 바꿀 수 없다. 입력원을 sim 으로 바꾼 뒤 한다"
CHANGES = (
    ("/api/rain", {"intensity": "heavy"}, RAIN_REFUSED),
    ("/api/rain", {"mmPerHour": 45}, RAIN_REFUSED),
    ("/api/rain", {"mmPerHour": 0}, RAIN_REFUSED),
    ("/api/blockage", {"type": "full", "location": "INLET-01"}, BLOCKAGE_REFUSED),
    ("/api/blockage", {"type": "partial", "location": "INLET-03"}, BLOCKAGE_REFUSED),
    ("/api/blockage", {"type": "none"}, BLOCKAGE_REFUSED),
)


@pytest.fixture
# 알림기를 내주는 준비물
def notifier():
    return Mailbox()


@pytest.fixture
# 알림기를 꽂고 시나리오를 sim 으로 돌려 기록을 남기고 멈춘 클라이언트
def session(builder, clock, notifier):
    client = builder(notifier=notifier)
    for path, body, seconds in SCENARIO:
        answer(client, path, body)
        lapse(clock, client.app.state.service, seconds)
    return client


# POST 를 보내 성공을 확인하고 본문을 돌려주는 함수
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})
    assert response.status_code == 200, response.text
    return response.json()



# 알림기는 꽂힌 그대로 서비스가 쓰는지 검사
def test_the_app_hands_the_notifier_to_the_service(session, notifier):
    assert session.app.state.service.notifier is notifier


# 재생에서 알림이 불리지 않는지 검사. M5 에서 sim 이 알림을 부르는 대조 검사와 짝
def test_the_notifier_is_not_called_in_replay(session, clock, notifier):
    before = len(notifier.events)  # sim 회차에서 받은 알림은 세지 않음
    footage(session, clock, ID)
    answer(session, SOURCE_URL, {"mode": "sim"})
    answer(session, SOURCE_URL, {"mode": "replay", "logId": ID})
    lapse(clock, session.app.state.service, 5)
    answer(session, STOP_URL)
    assert notifier.events[before:] == []



# 재생 내내 강우·막힘 변경이 409 이고 아무것도 바꾸지 않는지 검사
def test_rain_and_blockage_changes_are_409_throughout_the_replay(session, clock):
    service = session.app.state.service
    clean = digests(footage(session, clock, ID))
    answer(session, SOURCE_URL, {"mode": "sim"})
    answer(session, SOURCE_URL, {"mode": "replay", "logId": ID})
    bodies = []
    for _ in clean:  # 기준 해시 수만큼(틱마다) 반복
        body, conditions = session.get("/api/state").content, service.conditions
        for path, change, detail in CHANGES:
            response = session.post(path, json=change)
            assert (response.status_code, response.json()) == (409, {"detail": detail}), change
        assert (session.get("/api/state").content, service.conditions) == (body, conditions)
        bodies.append(body)
        lapse(clock, service, 1)
    assert service.delay() is None
    assert digests(bodies) == clean



# 재생의 응답은 모두 mode replay, outputsLocked true 인지 검사
def test_every_replay_response_says_replay_with_outputs_locked(session, clock):
    assert session.get("/api/state").json()["mode"] == "live"  # sim 회차의 mode 는 live
    bodies = [json.loads(body) for body in footage(session, clock, ID)]
    answer(session, SOURCE_URL, {"mode": "sim"})
    bodies.append(answer(session, SOURCE_URL, {"mode": "replay", "logId": ID}))
    lapse(clock, session.app.state.service, 5)
    bodies.append(answer(session, STOP_URL))
    assert len(bodies) == 30 + 2 + 2  # 재생 응답 32 개 + 선택·종료 2 개
    seen = {(body["mode"], body["dataSource"], body["outputsLocked"]) for body in bodies}
    assert seen == {("replay", "replay", True)}  # 모두 (replay, replay, 잠김) 하나뿐이어야 함
