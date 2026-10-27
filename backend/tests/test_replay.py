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

ID = "EXP-20261022-001"
SECOND_ID = "EXP-20261022-002"
START_URL = "/api/experiment/start"
STOP_URL = "/api/experiment/stop"
RESET_URL = "/api/experiment/reset"
SOURCE_URL = "/api/source"


# POST 를 보내 성공(200)을 확인하고 본문을 돌려주는 도우미
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})
    assert response.status_code == 200, response.text  # 성공(200)이어야 함
    return response.json()


# 기록을 골라 재생을 시작하는 도우미
def screening(client, log_id: str = ID) -> dict:
    return answer(client, SOURCE_URL, {"mode": "replay", "logId": log_id})


# 기록 폴더의 파일 이름별 바이트를 모으는 도우미
def tapes(experiment_log) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(experiment_log.directory.iterdir())}


# 기록 하나를 남기고 멈춘 클라이언트. 첫 틱 전과 도중에 강우·막힘을 바꾸며 5초 돌림
def capture(make_client, clock, **kwargs):
    client = make_client(**kwargs)
    service = client.app.state.service
    answer(client, START_URL, {"rain": "light"})
    answer(client, "/api/rain", {"intensity": "medium"})  # 첫 틱 전에 비를 보통으로 변환
    lapse(clock, service, 2)
    answer(client, "/api/rain", {"mmPerHour": 120})
    lapse(clock, service, 1)
    answer(client, "/api/blockage", {"type": "full", "location": "INLET-02"})
    lapse(clock, service, 2)
    answer(client, STOP_URL)
    return client



# 같은 입력, 같은 모델: 원래 회차의 틱을 그대로 다시 내는지 검사
def test_a_replay_runs_the_model_again_on_the_recorded_inputs(builder, clock, journal):
    client = capture(builder, clock)
    service = client.app.state.service
    states, ended = chronicle(journal, ID), client.get("/api/state").json()
    files = tapes(journal)
    assert len(states) == 5
    body = screening(client)
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "running", 0)
    assert (body["mode"], body["dataSource"], body["outputsLocked"]) == ("replay", "replay", True)
    for expected in states:
        assert service.delay() is not None
        lapse(clock, service, 1)
        assert client.get("/api/state").json() == echo(expected)
    lapse(clock, service, 3)
    assert client.get("/api/state").json() == echo(ended)
    assert service.delay() is None
    assert tapes(journal) == files


# 글자로 기록된 숫자 값이 재생에서도 같은 숫자인지 검사
def test_readings_logged_as_text_replay_as_the_same_numbers(
    builder, clock, journal, config
):
    readings = {**readout(config, a_mm=20, b_mm=10), "distA_mm": math.nan}
    client = builder(source=Script(readings))
    service = client.app.state.service
    answer(client, START_URL)
    lapse(clock, service, 2)
    answer(client, STOP_URL)
    assert '"distA_mm":"nan"' in (journal.directory / f"{ID}.jsonl").read_text()
    states = chronicle(journal, ID)
    screening(client)
    for expected in states:
        lapse(clock, service, 1)
        body = client.get("/api/state").json()
        assert body == echo(expected)
        assert [body["zones"][z]["source"] for z in "AB"] == ["estimated", "replay"]



# 끝은 기록된 종료·초기화 시점. 초기화된 회차의 재생이 거기서 멈추는지 검사
def test_a_replay_of_a_reset_run_stops_at_the_reset(builder, clock):
    client = builder()
    answer(client, START_URL)
    lapse(clock, client.app.state.service, 3)
    answer(client, RESET_URL)
    screening(client)
    lapse(clock, client.app.state.service, 5)
    body = client.get("/api/state").json()
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "stopped", 3)


# 종료 줄이 없으면 마지막 state 줄까지 재생하는지 검사
def test_a_run_cut_off_without_a_stop_replays_up_to_its_last_state(builder, clock):
    first = builder()
    answer(first, START_URL)
    lapse(clock, first.app.state.service, 3)
    second = builder()
    screening(second)
    lapse(clock, second.app.state.service, 5)
    body = second.get("/api/state").json()
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "stopped", 3)


# 첫 틱 전에 멈춘 회차가 정지로 재생되는지 검사
def test_a_run_stopped_before_its_first_tick_replays_as_stopped(builder):
    client = builder()
    answer(client, START_URL)
    answer(client, STOP_URL)
    body = screening(client)
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (ID, "stopped", 0)


# 정지가 재생을 그 자리에서 끝내고 기록은 안 쓰는지 검사
def test_stop_ends_a_replay_where_it_is_and_writes_nothing(builder, clock, journal):
    client = capture(builder, clock)
    service = client.app.state.service
    files = tapes(journal)
    screening(client)
    lapse(clock, service, 2)
    body = answer(client, STOP_URL)
    assert (body["runState"], body["elapsedSec"], body["dataSource"]) == ("stopped", 2, "replay")
    lapse(clock, service, 3)
    assert client.get("/api/state").json() == body  # 상태가 그대로여야 함
    assert tapes(journal) == files


# 재생 중 틱이 실패하면 재생이 멈추고 기록은 안 쓰는지 검사
def test_a_failed_tick_stops_the_replay_and_writes_nothing(
    builder, clock, journal, monkeypatch
):
    client = capture(builder, clock)
    service = client.app.state.service
    files = tapes(journal)
    screening(client)
    lapse(clock, service, 2)

    # 항상 실패하는 가짜 계산 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")

    monkeypatch.setattr("app.service.evolution", wreck)
    clock.jump(1.0)
    assert service.catchup() == 0
    body = client.get("/api/state").json()
    assert (body["runState"], body["elapsedSec"], body["dataSource"]) == ("stopped", 2, "replay")
    assert tapes(journal) == files


REFUSED_IN_REPLAY = {  # 재생 중에는 종료 말고는 409. 값이 틀린 요청은 409 보다 먼저 422
    "start": (START_URL, {}),
    "reset": (RESET_URL, {}),
    "rain": ("/api/rain", {"intensity": "heavy"}),
    "blockage": ("/api/blockage", {"type": "full", "location": "INLET-01"}),
}


@pytest.mark.parametrize("seconds", [2, 9], ids=["running", "ended"])
@pytest.mark.parametrize(("path", "body"), REFUSED_IN_REPLAY.values(), ids=REFUSED_IN_REPLAY.keys())
# 재생 중 정지 말고는 조작이 409 인지 검사
def test_controls_other_than_stop_are_409_in_replay(
    builder, clock, journal, path, body, seconds
):
    client = capture(builder, clock)
    service = client.app.state.service
    files = tapes(journal)
    screening(client)
    lapse(clock, service, seconds)
    before, conditions = client.get("/api/state").json(), service.conditions
    response = client.post(path, json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"].startswith("재생 중에는 ")
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert service.conditions == conditions  # 서비스 조건도 그대로여야 함
    assert tapes(journal) == files  # 기록 파일도 그대로여야 함


# 재생 중 잘못된 값은 409 보다 먼저 422 인지 검사
def test_a_bad_control_in_replay_is_422_before_409(builder, clock):
    client = capture(builder, clock)
    screening(client)
    response = client.post("/api/blockage", json={"type": "full", "location": "INLET-09"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "location"]


# 회차가 돌고 있으면 재생을 시작할 수 없는지 검사
def test_a_replay_cannot_start_while_a_run_is_running(builder, clock):
    client = capture(builder, clock)
    answer(client, START_URL)
    lapse(clock, client.app.state.service, 1)
    before = client.get("/api/state").json()
    response = client.post(SOURCE_URL, json={"mode": "replay", "logId": ID})
    assert response.status_code == 409
    assert isinstance(response.json()["detail"], str)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함



# 입력원 변경: sim 을 고르면 재생을 떠나 대기로 가는지 검사
def test_choosing_sim_leaves_the_replay_for_standby(builder, clock, journal):
    client = capture(builder, clock)
    service = client.app.state.service
    screening(client)
    lapse(clock, service, 2)
    body = answer(client, SOURCE_URL, {"mode": "sim"})
    assert body == builder().get("/api/state").json()
    assert (body["experimentId"], body["runState"], body["dataSource"]) == (
        "EXP-STANDBY",
        "idle",
        "sim",
    )
    answer(client, START_URL)
    lapse(clock, service, 1)
    body = client.get("/api/state").json()
    assert (body["experimentId"], body["dataSource"], body["mode"]) == (SECOND_ID, "sim", "live")
    assert body["zones"]["A"]["source"] == "simulated"
    assert next(journal.records(SECOND_ID))["dataSource"] == "sim"


# 같은 기록을 다시 고르면 아무것도 안 바뀌는지 검사
def test_choosing_the_same_log_again_changes_nothing(builder, clock):
    client = capture(builder, clock)
    screening(client)
    lapse(clock, client.app.state.service, 2)
    before = client.get("/api/state").json()
    assert screening(client) == before  # 같은 기록을 다시 고른 응답이 그대로여야 함
    assert client.get("/api/state").json() == before  # 상태도 그대로여야 함


# 다른 기록을 고르면 그 기록을 처음부터 재생하는지 검사
def test_choosing_another_log_replays_that_one_from_its_start(builder, clock, journal):
    client = capture(builder, clock)
    service = client.app.state.service
    answer(client, START_URL, {"rain": "heavy"})
    lapse(clock, service, 2)
    answer(client, STOP_URL)
    second = chronicle(journal, SECOND_ID)
    screening(client, ID)
    lapse(clock, service, 3)
    body = screening(client, SECOND_ID)
    assert (body["experimentId"], body["runState"], body["elapsedSec"]) == (SECOND_ID, "running", 0)
    for expected in second:
        lapse(clock, service, 1)
        assert client.get("/api/state").json() == echo(expected)



# 재생 못 하는 기록 만듦: kind 조작 줄의 값을 바꾸는 편집을 반환
def patch(kind: str, **values):
    # 레코드 목록을 고치는 안쪽 함수
    def alteration(records):
        return [{**r, **values} if r["type"] == "cmd" and r["kind"] == kind else r for r in records]

    return alteration


# 재생을 거부하면 422 와 이유가 오고 상태는 그대로인지 확인하는 도우미
def refusal(client, log_id: str, message: str) -> None:
    before = client.get("/api/state").json()
    response = client.post(SOURCE_URL, json={"mode": "replay", "logId": log_id})
    assert response.status_code == 422, response.text
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "logId"]  # 위치가 body → logId 여야 함
    assert error["msg"].startswith(message)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함


@pytest.mark.parametrize(
    ("log_id", "message"),  # (기록 ID, 메시지) 이름
    [
        ("EXP-1", "실험 ID 형식이 아니다"),
        ("../logs/EXP-20261022-001", "실험 ID 형식이 아니다"),
        ("EXP-STANDBY", "실험 ID 형식이 아니다"),
        ("EXP-20261022-009", "그런 실험 기록이 없다"),
    ],
    ids=["short", "path", "standby", "missing"],
)
# 기록을 가리키지 않는 ID 는 422 인지 검사
def test_a_log_id_that_names_no_log_is_422(builder, clock, log_id, message):
    refusal(capture(builder, clock), log_id, message)


BAD_LOGS = {
    "meta-only": lambda records: records[:1],  # 시작 줄을 못 쓴 회차는 meta 만 남음(T3)
    # 중간에 깨진 JSON 줄이 끼어듦
    "broken-line": lambda records: [*records[:3], "{", *records[3:]],
    # meta 의 회차 ID 가 파일 이름과 다름
    "other-id": lambda records: [{**records[0], "experimentId": SECOND_ID}, *records[1:]],
    "rain-over-max": patch("rain", rainMmPerHour=999.0),
    "unknown-inlet": patch("blockage", blockage={"type": "full", "location": "INLET-09"}),
    "unknown-blockage": patch("blockage", blockage={"type": "half", "location": "INLET-02"}),
    "huge-number": lambda records: [  # obs 줄의 경과 초가 실수로 담을 수 없을 만큼 큼
        {**r, "elapsedSec": int("9" * 400)} if r["type"] == "obs" else r
        for r in records
    ],
    "late-start": lambda records: [  # meta 의 시작 시각이 KST 로 바꿀 수 없을 만큼 늦음
        {**records[0], "startTime": "9999-12-31T23:59:59+00:00"},
        *records[1:],  # 나머지는 그대로 둠
    ],
}


@pytest.mark.parametrize("edit", BAD_LOGS.values(), ids=BAD_LOGS.keys())
# 재생할 수 없는 기록은 422 인지 검사
def test_a_log_that_cannot_be_replayed_is_422(builder, clock, journal, edit):
    client = capture(builder, clock)
    revision(journal, edit, ID)
    refusal(client, ID, "재생할 수 없는 기록: ")



# 기록을 읽다 입출력 오류가 나면 503 인지 검사(쓰기 실패와 같은 응답)
def test_a_log_that_cannot_be_read_is_503(builder, clock, journal, monkeypatch):
    client = capture(builder, clock)
    before = client.get("/api/state").json()

    # 읽기를 막는 가짜 기록 읽기 함수
    def lockout(experiment_id):
        raise PermissionError(13, "Permission denied")
        yield  # 이 줄 때문에 생성기가 됨: 첫 줄을 읽을 때 실패

    monkeypatch.setattr(journal, "records", lockout)
    response = client.post(SOURCE_URL, json={"mode": "replay", "logId": ID})
    assert response.status_code == 503
    assert response.json() == {"detail": "실험 기록을 쓸 수 없다: Permission denied"}
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
