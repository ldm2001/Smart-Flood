import math
import pytest
from app.core.model import Underflow
from tests.helpers import (
    Script,
    chronicle,
    echo,
    lapse,
    readout,
    revision,
)

ID = "EXP-20261022-001"  # 첫 회차 ID
SECOND_ID = "EXP-20261022-002"  # 둘째 회차 ID
START_URL = "/api/experiment/start"  # 실험 시작 주소
STOP_URL = "/api/experiment/stop"  # 실험 정지 주소
RESET_URL = "/api/experiment/reset"  # 실험 초기화 주소
SOURCE_URL = "/api/source"  # 입력원 선택 주소


# POST 를 보내 성공(200)을 확인하고 본문을 돌려주는 도우미
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})  # 본문이 없으면 빈 객체로 전송
    assert response.status_code == 200, response.text  # 성공(200)이어야 함
    return response.json()  # 응답 본문을 반환


# 기록을 골라 재생을 시작하는 도우미
def screening(client, log_id: str = ID) -> dict:
    # 재생 모드와 기록 ID 로 입력원을 변환
    return answer(client, SOURCE_URL, {"mode": "replay", "logId": log_id})


# 기록 폴더의 파일 이름별 바이트를 모으는 도우미
def tapes(experiment_log) -> dict[str, bytes]:
    # 파일을 이름순으로 읽어 이름 → 바이트로 묶음
    return {p.name: p.read_bytes() for p in sorted(experiment_log.directory.iterdir())}


# 기록 하나를 남기고 멈춘 클라이언트. 첫 틱 전과 도중에 강우·막힘을 바꾸며 5초 돌린다
def capture(make_client, clock, **kwargs):
    client = make_client(**kwargs)  # 클라이언트를 만듦
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    answer(client, START_URL, {"rain": "light"})  # 약한 비로 시작
    answer(client, "/api/rain", {"intensity": "medium"})  # 첫 틱 전에 비를 보통으로 변환
    lapse(clock, service, 2)  # 2초를 전송
    answer(client, "/api/rain", {"mmPerHour": 120})  # 비를 120 mm/h 로 변환
    lapse(clock, service, 1)  # 1초를 전송
    # 2번 빗물받이를 완전히 차단
    answer(client, "/api/blockage", {"type": "full", "location": "INLET-02"})
    lapse(clock, service, 2)  # 2초를 전송
    answer(client, STOP_URL)  # 정지
    return client  # 멈춘 클라이언트를 반환



# 같은 입력, 같은 모델: 원래 회차의 틱을 그대로 다시 내는지 검사
def test_a_replay_runs_the_model_again_on_the_recorded_inputs(builder, clock, journal):
    client = capture(builder, clock)  # 기록 하나를 남김
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    # 기록된 상태들과 멈춘 마지막 상태
    states, ended = chronicle(journal, ID), client.get("/api/state").json()
    files = tapes(journal)  # 재생 전 기록 파일을 잡아 둔다
    assert len(states) == 5  # 5초 돌았으니 상태 5개여야 함
    body = screening(client)  # 그 기록을 재생
    # 같은 회차 ID, 실행 중, 경과 0 이어야 함
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "running", 0)
    # 모드·입력원은 replay, 출력은 잠겨야 함
    assert (body["mode"], body["dataSource"], body["outputsLocked"]) == ("replay", "replay", True)
    for expected in states:  # 기록된 상태마다
        assert service.delay() is not None  # 다음 틱이 남아 있어야 함
        lapse(clock, service, 1)  # 1초를 전송
        # 재생 상태가 기록과 같아야 한다(입력원 표시만 다르다)
        assert client.get("/api/state").json() == echo(expected)
    lapse(clock, service, 3)  # 3초를 더 보내 끝까지 감
    assert client.get("/api/state").json() == echo(ended)  # 끝 상태도 원래 멈춘 상태와 같아야 함
    assert service.delay() is None  # 더 돌 틱이 없어야 함
    assert tapes(journal) == files  # 재생은 기록 파일을 바꾸지 않아야 함


# 글자로 기록된 숫자 값이 재생에서도 같은 숫자인지 검사
def test_readings_logged_as_text_replay_as_the_same_numbers(
    builder, clock, journal, config  # 준비물 이름들
):
    # A 거리는 숫자 아님(NaN)인 관측값
    readings = {**readout(config, a_mm=20, b_mm=10), "distA_mm": math.nan}
    client = builder(source=Script(readings))  # 그 값만 내는 가짜 입력원으로 앱을 만듦
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    answer(client, START_URL)  # 시작
    lapse(clock, service, 2)  # 2초를 전송
    answer(client, STOP_URL)  # 정지
    # 기록 파일에는 NaN 이 글자 nan 으로 남아야 함
    assert '"distA_mm":"nan"' in (journal.directory / f"{ID}.jsonl").read_text()
    states = chronicle(journal, ID)  # 기록된 상태들
    screening(client)  # 그 기록을 재생
    for expected in states:  # 기록된 상태마다
        lapse(clock, service, 1)  # 1초를 전송
        body = client.get("/api/state").json()  # 재생 상태를 읽음
        assert body == echo(expected)  # 기록과 같아야 함
        # A 는 관측이 무효라 추정, B 는 재생 출처여야 함
        assert [body["zones"][z]["source"] for z in "AB"] == ["estimated", "replay"]



# 끝은 기록된 종료·초기화 시점. 초기화된 회차의 재생이 거기서 멈추는지 검사
def test_a_replay_of_a_reset_run_stops_at_the_reset(builder, clock):
    client = builder()  # 앱을 만듦
    answer(client, START_URL)  # 시작
    lapse(clock, client.app.state.service, 3)  # 3초를 전송
    answer(client, RESET_URL)  # 초기화
    screening(client)  # 그 기록을 재생
    lapse(clock, client.app.state.service, 5)  # 5초를 보내도
    body = client.get("/api/state").json()  # 재생 상태를 읽음
    # 3초에서 멈춘 같은 회차여야 함
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "stopped", 3)


# 종료 줄이 없으면 마지막 state 줄까지 재생하는지 검사
def test_a_run_cut_off_without_a_stop_replays_up_to_its_last_state(builder, clock):
    first = builder()  # 첫 앱을 만듦
    answer(first, START_URL)  # 시작
    lapse(clock, first.app.state.service, 3)  # 3초를 전송
    second = builder()  # 회차 도중에 서버가 꺼졌다가 다시 뜬 앱
    screening(second)  # 남은 기록을 재생
    lapse(clock, second.app.state.service, 5)  # 5초를 전송
    body = second.get("/api/state").json()  # 재생 상태를 읽음
    # 마지막 state 의 3초에서 멈춰야 함
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "stopped", 3)


# 첫 틱 전에 멈춘 회차가 정지로 재생되는지 검사
def test_a_run_stopped_before_its_first_tick_replays_as_stopped(builder):
    client = builder()  # 앱을 만듦
    answer(client, START_URL)  # 시작
    answer(client, STOP_URL)  # 바로 정지
    body = screening(client)  # 그 기록을 재생
    # 경과 0 에서 정지 상태여야 함
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "stopped", 0)


# 정지가 재생을 그 자리에서 끝내고 기록은 안 쓰는지 검사
def test_stop_ends_a_replay_where_it_is_and_writes_nothing(builder, clock, journal):
    client = capture(builder, clock)  # 기록 하나를 남김
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    files = tapes(journal)  # 기록 파일을 잡아 둔다
    screening(client)  # 그 기록을 재생
    lapse(clock, service, 2)  # 2초를 전송
    body = answer(client, STOP_URL)  # 정지
    # 2초에서 멈추고 입력원은 replay 여야 함
    assert (body["runState"], body["elapsedSec"], body["dataSource"]) == ("stopped", 2, "replay")
    lapse(clock, service, 3)  # 3초를 더 보내도
    assert client.get("/api/state").json() == body  # 상태가 그대로여야 함
    assert tapes(journal) == files  # 기록 파일은 바뀌지 않아야 함


# 재생 중 틱이 실패하면 재생이 멈추고 기록은 안 쓰는지 검사
def test_a_failed_tick_stops_the_replay_and_writes_nothing(
    builder, clock, journal, monkeypatch  # 준비물 이름들
):
    client = capture(builder, clock)  # 기록 하나를 남김
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    files = tapes(journal)  # 기록 파일을 잡아 둔다
    screening(client)  # 그 기록을 재생
    lapse(clock, service, 2)  # 2초를 전송

    # 항상 실패하는 가짜 계산 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")  # 저장량 음수 오류를 냄

    monkeypatch.setattr("app.service.evolution", wreck)  # 서비스의 계산을 가짜로 변환
    clock.jump(1.0)  # 시계를 1초 전송
    assert service.catchup() == 0  # 처리된 틱은 0 이어야 함
    body = client.get("/api/state").json()  # 재생 상태를 읽음
    # 2초에서 멈추고 입력원은 replay 여야 함
    assert (body["runState"], body["elapsedSec"], body["dataSource"]) == ("stopped", 2, "replay")
    assert tapes(journal) == files  # 기록 파일은 바뀌지 않아야 함


REFUSED_IN_REPLAY = {  # 재생 중에는 종료 말고는 409. 값이 틀린 요청은 409 보다 먼저 422 다
    "start": (START_URL, {}),  # 시작
    "reset": (RESET_URL, {}),  # 초기화
    "rain": ("/api/rain", {"intensity": "heavy"}),  # 비 바꾸기
    "blockage": ("/api/blockage", {"type": "full", "location": "INLET-01"}),  # 막힘 바꾸기
}


# 재생 중(2초)과 재생 끝(9초) 두 경우로 반복
@pytest.mark.parametrize("seconds", [2, 9], ids=["running", "ended"])
# 거부되는 요청마다 반복
@pytest.mark.parametrize(("path", "body"), REFUSED_IN_REPLAY.values(), ids=REFUSED_IN_REPLAY.keys())
# 재생 중 정지 말고는 조작이 409 인지 검사
def test_controls_other_than_stop_are_409_in_replay(
    builder, clock, journal, path, body, seconds  # 준비물과 사례 이름들
):
    client = capture(builder, clock)  # 기록 하나를 남김
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    files = tapes(journal)  # 기록 파일을 잡아 둔다
    screening(client)  # 그 기록을 재생
    lapse(clock, service, seconds)  # 사례의 초만큼 전송
    # 요청 전 상태와 서비스 조건을 잡아 둔다
    before, conditions = client.get("/api/state").json(), service.conditions
    response = client.post(path, json=body)  # 조작을 전송
    assert response.status_code == 409, response.text  # 409 여야 함
    # 사유가 "재생 중에는 " 으로 시작 필요
    assert response.json()["detail"].startswith("재생 중에는 ")
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert service.conditions == conditions  # 서비스 조건도 그대로여야 함
    assert tapes(journal) == files  # 기록 파일도 그대로여야 함


# 재생 중 잘못된 값은 409 보다 먼저 422 인지 검사
def test_a_bad_control_in_replay_is_422_before_409(builder, clock):
    client = capture(builder, clock)  # 기록 하나를 남김
    screening(client)  # 그 기록을 재생
    # 없는 9번 빗물받이를 막는 요청을 전송
    response = client.post("/api/blockage", json={"type": "full", "location": "INLET-09"})
    assert response.status_code == 422  # 422 여야 함
    # 위치가 body → location 이어야 함
    assert response.json()["detail"][0]["loc"] == ["body", "location"]


# 회차가 돌고 있으면 재생을 시작할 수 없는지 검사
def test_a_replay_cannot_start_while_a_run_is_running(builder, clock):
    client = capture(builder, clock)  # 기록 하나를 남김
    answer(client, START_URL)  # 새 회차를 시작
    lapse(clock, client.app.state.service, 1)  # 1초를 전송
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다
    response = client.post(SOURCE_URL, json={"mode": "replay", "logId": ID})  # 재생으로 바꾸려
    assert response.status_code == 409  # 409 여야 함
    assert isinstance(response.json()["detail"], str)  # 사유가 글자여야 함
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함



# 입력원 바꾸기: sim 을 고르면 재생을 떠나 대기로 가는지 검사
def test_choosing_sim_leaves_the_replay_for_standby(builder, clock, journal):
    client = capture(builder, clock)  # 기록 하나를 남김
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    screening(client)  # 그 기록을 재생
    lapse(clock, service, 2)  # 2초를 전송
    body = answer(client, SOURCE_URL, {"mode": "sim"})  # sim 으로 변환
    assert body == builder().get("/api/state").json()  # 새로 띄운 앱의 대기 상태와 같아야 함
    # 대기 ID, idle, sim 이어야 함
    assert (body["experimentId"], body["runState"], body["dataSource"]) == (
        "EXP-STANDBY",  # 대기용 ID
        "idle",  # 실행 상태는 idle
        "sim",  # 입력원은 sim
    )
    answer(client, START_URL)  # 새로 시작
    lapse(clock, service, 1)  # 1초를 전송
    body = client.get("/api/state").json()  # 상태를 읽음
    # 둘째 회차 ID, sim 입력원, live 모드여야 함
    assert (body["experimentId"], body["dataSource"], body["mode"]) == (SECOND_ID, "sim", "live")
    assert body["zones"]["A"]["source"] == "simulated"  # A 출처가 simulated 여야 함
    # 기록 첫 줄의 입력원이 sim 이어야 함
    assert next(journal.records(SECOND_ID))["dataSource"] == "sim"


# 같은 기록을 다시 고르면 아무것도 안 바뀌는지 검사
def test_choosing_the_same_log_again_changes_nothing(builder, clock):
    client = capture(builder, clock)  # 기록 하나를 남김
    screening(client)  # 그 기록을 재생
    lapse(clock, client.app.state.service, 2)  # 2초를 전송
    before = client.get("/api/state").json()  # 지금 상태를 잡아 둔다
    assert screening(client) == before  # 같은 기록을 다시 고른 응답이 그대로여야 함
    assert client.get("/api/state").json() == before  # 상태도 그대로여야 함


# 다른 기록을 고르면 그 기록을 처음부터 재생하는지 검사
def test_choosing_another_log_replays_that_one_from_its_start(builder, clock, journal):
    client = capture(builder, clock)  # 첫 기록을 남김
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    answer(client, START_URL, {"rain": "heavy"})  # 강한 비로 둘째 회차를 시작
    lapse(clock, service, 2)  # 2초를 전송
    answer(client, STOP_URL)  # 정지
    second = chronicle(journal, SECOND_ID)  # 둘째 기록의 상태들
    screening(client, ID)  # 첫 기록을 재생
    lapse(clock, service, 3)  # 3초를 전송
    body = screening(client, SECOND_ID)  # 둘째 기록으로 변환
    # 둘째 회차가 0초부터 실행 중이어야 함
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (SECOND_ID, "running", 0)
    for expected in second:  # 둘째 기록의 상태마다
        lapse(clock, service, 1)  # 1초를 전송
        assert client.get("/api/state").json() == echo(expected)  # 재생 상태가 기록과 같아야 함



# 재생 못 하는 기록 만들기: kind 조작 줄의 값을 바꾸는 편집을 반환
def patch(kind: str, **values):
    # 레코드 목록을 고치는 안쪽 함수
    def alteration(records):
        # kind 조작 줄만 값을 덮어쓰고 나머지는 그대로 둔다
        return [{**r, **values} if r["type"] == "cmd" and r["kind"] == kind else r for r in records]

    return alteration  # 편집 함수를 반환


# 재생을 거부하면 422 와 이유가 오고 상태는 그대로인지 확인하는 도우미
def refusal(client, log_id: str, message: str) -> None:
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다
    # 그 기록을 재생하려
    response = client.post(SOURCE_URL, json={"mode": "replay", "logId": log_id})
    assert response.status_code == 422, response.text  # 422 여야 함
    [error] = response.json()["detail"]  # 오류가 정확히 하나여야 함
    assert error["loc"] == ["body", "logId"]  # 위치가 body → logId 여야 함
    assert error["msg"].startswith(message)  # 메시지가 기대한 글로 시작 필요
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함


@pytest.mark.parametrize(  # 기록 ID 사례마다 반복
    ("log_id", "message"),  # (기록 ID, 메시지) 이름
    [  # ID 사례 목록
        ("EXP-1", "실험 ID 형식이 아니다"),  # 너무 짧은 ID
        ("../logs/EXP-20261022-001", "실험 ID 형식이 아니다"),  # 경로를 타고 나가는 ID
        ("EXP-STANDBY", "실험 ID 형식이 아니다"),  # 대기용 ID 는 기록이 아니다
        ("EXP-20261022-009", "그런 실험 기록이 없다"),  # 형식은 맞지만 없는 기록
    ],
    ids=["short", "path", "standby", "missing"],  # 사례 이름
)
# 기록을 가리키지 않는 ID 는 422 인지 검사
def test_a_log_id_that_names_no_log_is_422(builder, clock, log_id, message):
    # 기록을 남긴 뒤 그 ID 로 재생을 요청해 거부를 확인
    refusal(capture(builder, clock), log_id, message)


BAD_LOGS = {  # 재생할 수 없는 망가진 기록을 만드는 편집들
    "meta-only": lambda records: records[:1],  # 시작 줄을 못 쓴 회차는 meta 만 남는다(T3)
    # 중간에 깨진 JSON 줄이 끼어든다
    "broken-line": lambda records: [*records[:3], "{", *records[3:]],
    # meta 의 회차 ID 가 파일 이름과 다르다
    "other-id": lambda records: [{**records[0], "experimentId": SECOND_ID}, *records[1:]],
    "rain-over-max": patch("rain", rainMmPerHour=999.0),  # 비 세기가 최댓값을 넘는다
    # 없는 9번 빗물받이를 차단
    "unknown-inlet": patch("blockage", blockage={"type": "full", "location": "INLET-09"}),
    # 모르는 막힘 종류
    "unknown-blockage": patch("blockage", blockage={"type": "half", "location": "INLET-02"}),
    "huge-number": lambda records: [  # obs 줄의 경과 초가 실수로 담을 수 없을 만큼 크다
        # obs 줄만 경과 초를 400 자리 정수로 변환
        {**r, "elapsedSec": int("9" * 400)} if r["type"] == "obs" else r
        for r in records  # 모든 줄을 하나씩 확인
    ],
    "late-start": lambda records: [  # meta 의 시작 시각이 KST 로 바꿀 수 없을 만큼 늦다
        {**records[0], "startTime": "9999-12-31T23:59:59+00:00"},  # 첫 줄의 시작 시각만 변환
        *records[1:],  # 나머지는 그대로 둔다
    ],
}


@pytest.mark.parametrize("edit", BAD_LOGS.values(), ids=BAD_LOGS.keys())  # 망가뜨리는 편집마다 반복
# 재생할 수 없는 기록은 422 인지 검사
def test_a_log_that_cannot_be_replayed_is_422(builder, clock, journal, edit):
    client = capture(builder, clock)  # 기록 하나를 남김
    revision(journal, edit, ID)  # 그 기록 파일을 망가뜨린다
    refusal(client, ID, "재생할 수 없는 기록: ")  # 재생을 거부하는지 확인



# 기록을 읽다 입출력 오류가 나면 503 인지 검사(쓰기 실패와 같은 응답)
def test_a_log_that_cannot_be_read_is_503(builder, clock, journal, monkeypatch):
    client = capture(builder, clock)  # 기록 하나를 남김
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다

    # 읽기를 막는 가짜 기록 읽기 함수
    def lockout(experiment_id):
        raise PermissionError(13, "Permission denied")  # 권한 오류를 냄
        yield  # 이 줄 때문에 생성기가 된다: 첫 줄을 읽을 때 실패

    monkeypatch.setattr(journal, "records", lockout)  # 기록 읽기를 가짜로 변환
    response = client.post(SOURCE_URL, json={"mode": "replay", "logId": ID})  # 그 기록을 재생하려
    assert response.status_code == 503  # 503 이어야 함
    # 사유에 오류 설명이 담겨야 함
    assert response.json() == {"detail": "실험 기록을 쓸 수 없다: Permission denied"}
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
