import json
import pytest
from tests.helpers import digests, footage, lapse

ID = "EXP-20261022-001"  # 시험용 회차 ID
SOURCE_URL = "/api/source"  # 입력원 바꾸기 주소
STOP_URL = "/api/experiment/stop"  # 실험 종료 주소

SCENARIO = (  # (조작, 뒤에 돌릴 초) 목록. 센 비·완전 막힘·직접 입력을 거쳐 30 틱
    ("/api/experiment/start", {"rain": "heavy"}, 10),  # 센 비로 시작, 10초
    ("/api/blockage", {"type": "full", "location": "INLET-01"}, 10),  # 1번 빗물받이 완전 막힘, 10초
    ("/api/rain", {"mmPerHour": 120}, 10),  # 비를 120 mm/h 로, 10초
    (STOP_URL, {}, 0),  # 종료
)

# 재생 중 강우 변경이 거부될 때의 안내 문구
RAIN_REFUSED = "재생 중에는 강우를 바꿀 수 없다. 입력원을 sim 으로 바꾼 뒤 한다"
# 재생 중 막힘 변경이 거부될 때의 안내 문구
BLOCKAGE_REFUSED = "재생 중에는 막힘을 바꿀 수 없다. 입력원을 sim 으로 바꾼 뒤 한다"
CHANGES = (  # 거부되어야 할 변경들. 기록과 같은 값이든, 끄는 것이든 변경이다
    ("/api/rain", {"intensity": "heavy"}, RAIN_REFUSED),  # 비 프리셋 변경
    ("/api/rain", {"mmPerHour": 45}, RAIN_REFUSED),  # 비를 45 mm/h 로
    ("/api/rain", {"mmPerHour": 0}, RAIN_REFUSED),  # 비 끄기
    ("/api/blockage", {"type": "full", "location": "INLET-01"}, BLOCKAGE_REFUSED),  # 1번 완전 막힘
    # 3번 일부 막힘
    ("/api/blockage", {"type": "partial", "location": "INLET-03"}, BLOCKAGE_REFUSED),
    ("/api/blockage", {"type": "none"}, BLOCKAGE_REFUSED),  # 막힘 없애기
)


# 받은 알림을 모아 두기만 하는 가짜 알림기
class Mailbox:
    # 만들 때
    def __init__(self) -> None:
        self.events: list[dict] = []  # 받은 알림 목록을 비워 둔다

    # 알림을 받는 자리
    def notice(self, event: dict) -> None:
        self.events.append(event)  # 목록에 쌓아 둔다


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 알림기를 내주는 준비물
def notifier():
    return Mailbox()  # 가짜 알림기를 만들어 반환


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 알림기를 꽂고 시나리오를 sim 으로 돌려 기록을 남기고 멈춘 클라이언트
def session(builder, clock, notifier):
    client = builder(notifier=notifier)  # 알림기를 꽂은 앱 클라이언트
    for path, body, seconds in SCENARIO:  # 시나리오 항목을 차례로 실행
        answer(client, path, body)  # 조작 요청을 전송
        lapse(clock, client.app.state.service, seconds)  # 조작 뒤에 정해진 초만큼 틱을 돌린다
    return client  # 클라이언트를 반환


# POST 를 보내 성공을 확인하고 본문을 돌려주는 함수
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})  # 요청을 전송
    assert response.status_code == 200, response.text  # 요청이 성공 필요
    return response.json()  # 응답 본문을 반환



# 알림기는 꽂힌 그대로 서비스가 쓰는지 검사
def test_the_app_hands_the_notifier_to_the_service(session, notifier):
    assert session.app.state.service.notifier is notifier  # 서비스의 알림기가 꽂은 것과 같아야 함


# 재생에서 알림이 불리지 않는지 검사. M5 에서 sim 이 알림을 부른다는 대조 검사와 짝
def test_the_notifier_is_not_called_in_replay(session, clock, notifier):
    before = len(notifier.events)  # sim 회차에서 받은 알림은 세지 않음
    footage(session, clock, ID)  # 기록을 처음부터 끝까지 재생
    answer(session, SOURCE_URL, {"mode": "sim"})  # 입력원을 sim 으로 변환
    answer(session, SOURCE_URL, {"mode": "replay", "logId": ID})  # 다시 기록 재생을 선택
    lapse(clock, session.app.state.service, 5)  # 5 초 돌린다
    answer(session, STOP_URL)  # 도중에 실험을 종료
    assert notifier.events[before:] == []  # 재생 구간에는 받은 알림이 없어야 함



# 재생 내내 강우·막힘 변경이 409 이고 아무것도 바꾸지 않는지 검사
def test_rain_and_blockage_changes_are_409_throughout_the_replay(session, clock):
    service = session.app.state.service  # 앱 안의 서비스를 꺼냄
    clean = digests(footage(session, clock, ID))  # 변경 없이 재생한 기준 해시
    answer(session, SOURCE_URL, {"mode": "sim"})  # 입력원을 sim 으로 변환
    answer(session, SOURCE_URL, {"mode": "replay", "logId": ID})  # 다시 기록 재생을 선택
    bodies = []  # 틱마다 받은 응답을 모을 목록
    for _ in clean:  # 기준 해시 수만큼(틱마다) 반복
        # 변경 전 응답 바이트와 조건을 적어 둔다
        body, conditions = session.get("/api/state").content, service.conditions
        for path, change, detail in CHANGES:  # 거부되어야 할 변경을 모두 전송
            response = session.post(path, json=change)  # 변경 요청을 전송
            # 409 와 거부 문구여야 함
            assert (response.status_code, response.json()) == (409, {"detail": detail}), change
        # 응답 바이트와 조건이 그대로여야 함
        assert (session.get("/api/state").content, service.conditions) == (body, conditions)
        bodies.append(body)  # 응답을 담는다
        lapse(clock, service, 1)  # 시계를 1초 전송
    assert service.delay() is None  # 재생이 끝나 멈췄어야 함
    assert digests(bodies) == clean  # 해시가 기준과 같아야 함



# 재생의 응답은 모두 mode replay, outputsLocked true 인지 검사
def test_every_replay_response_says_replay_with_outputs_locked(session, clock):
    assert session.get("/api/state").json()["mode"] == "live"  # sim 회차의 mode 는 live 다
    # 재생하며 받은 응답을 JSON 으로 읽음
    bodies = [json.loads(body) for body in footage(session, clock, ID)]
    answer(session, SOURCE_URL, {"mode": "sim"})  # 입력원을 sim 으로 변환
    # 기록 재생을 고른 응답도 담는다
    bodies.append(answer(session, SOURCE_URL, {"mode": "replay", "logId": ID}))
    lapse(clock, session.app.state.service, 5)  # 5 초 돌린다
    bodies.append(answer(session, STOP_URL))  # 종료 응답도 담는다
    assert len(bodies) == 30 + 2 + 2  # 재생 응답 32 개 + 고르기·종료 2 개
    # (모드, 입력원, 출력 잠김) 조합을 모음
    seen = {(body["mode"], body["dataSource"], body["outputsLocked"]) for body in bodies}
    assert seen == {("replay", "replay", True)}  # 모두 (replay, replay, 잠김) 하나뿐이어야 함
