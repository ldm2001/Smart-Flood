import json
import logging
import pytest
from app.core.model import Underflow
from tests.helpers import lapse, revision

ID = "EXP-20261022-001"
SECOND_ID = "EXP-20261022-002"
META_FIELDS = ("experimentId", "startTime", "dataSource", "modelVersion", "configHash")


# 회차 하나를 seconds 초 돌리고 멈추는 도우미
def trial(client, clock, seconds: int = 2, **start) -> None:
    assert client.post("/api/experiment/start", json=start).status_code == 200
    lapse(clock, client.app.state.service, seconds)
    assert client.post("/api/experiment/stop", json={}).status_code == 200


# 회차 기록 파일 경로를 주는 도우미
def location(experiment_log, experiment_id: str = ID):
    return experiment_log.directory / f"{experiment_id}.jsonl"


# 다음 틱의 계산을 일부러 실패시키는 도우미. 회차가 멈추고 calc_error 이벤트가 남음
def sabotage(client, clock, monkeypatch) -> None:
    # 계산 대신 오류를 내는 가짜 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")

    monkeypatch.setattr("app.service.evolution", wreck)
    lapse(clock, client.app.state.service, 1)
    monkeypatch.undo()  # 가짜를 원래대로 되돌림


# 열 수 없는 기록을 흉내 내는 가짜 읽기 함수
def lockout(*args):
    raise PermissionError(13, "Permission denied")
    yield  # 생성기로 만듦: 첫 줄을 읽을 때 실패



# 사전에서 한 필드만 빼는 도우미
def omission(record: dict, field: str) -> dict:
    return {key: value for key, value in record.items() if key != field}


# 첫 줄이 깨진 기록을 내려받으면 빈 200 이 아니라 503 인지 검사
def test_a_log_whose_first_line_is_broken_is_503(builder, clock, journal):
    client = builder()
    trial(client, clock)
    revision(journal, lambda records: ["{", *records[1:]], ID)  # 첫 줄을 JSON 이 아닌 글자로 변환
    response = client.get(f"/api/logs/{ID}")
    assert response.status_code == 503, response.text
    assert str(journal.directory) not in response.json()["detail"]


@pytest.mark.parametrize("field", META_FIELDS)
# meta 에 필드가 빠진 기록이 목록에서 빠지는지 검사
def test_a_log_whose_meta_misses_a_field_is_left_out(builder, clock, journal, field):
    client = builder()
    trial(client, clock)
    revision(journal, lambda records: [omission(records[0], field), *records[1:]], ID)
    assert client.get("/api/logs").json() == {"logs": []}


# 목록이 날짜, 번호 순으로 meta 의 필드만 주는지 검사
def test_the_list_gives_each_log_its_meta_fields_in_order(builder, clock, journal):
    client = builder()
    trial(client, clock)
    trial(client, clock, rain="heavy")
    response = client.get("/api/logs")
    assert response.status_code == 200  # 성공(200)이어야 함
    logs = response.json()["logs"]
    assert [entry["experimentId"] for entry in logs] == [ID, SECOND_ID]
    metas = [next(journal.records(i)) for i in (ID, SECOND_ID)]  # 각 기록의 첫 줄(meta)을 직접 읽음
    assert logs == [{key: meta[key] for key in META_FIELDS} for meta in metas]


# 첫 회차 전에는 목록이 비었는지 검사
def test_the_list_is_empty_before_the_first_run(builder):
    assert builder().get("/api/logs").json() == {"logs": []}


# 진행 중인 회차도 목록에 나오는지 검사
def test_the_list_includes_the_run_in_progress(builder, clock):
    client = builder()
    client.post("/api/experiment/start", json={})
    lapse(clock, client.app.state.service, 1)
    assert [entry["experimentId"] for entry in client.get("/api/logs").json()["logs"]] == [ID]


# 다른 회차 ID 를 지닌 기록으로 바꾸는 도우미
def stranger(lines: list[str]) -> str:
    meta = {**json.loads(lines[0]), "experimentId": SECOND_ID}
    return "".join(line + "\n" for line in [json.dumps(meta), *lines[1:]])


NO_READABLE_META = {
    "broken": lambda lines: "".join(line + "\n" for line in ["{", *lines[1:]]),
    "not-meta": lambda lines: "".join(line + "\n" for line in lines[1:]),  # 첫 줄(meta)이 없음
    "other-id": stranger,
    "empty": lambda lines: "",
    "being-written": lambda lines: lines[0][:20],
}


@pytest.mark.parametrize("edit", NO_READABLE_META.values(), ids=NO_READABLE_META.keys())
# 읽을 수 있는 meta 가 없는 기록은 목록에서 빠지는지 검사
def test_a_log_without_a_readable_meta_is_left_out_of_the_list(
    builder, clock, journal, caplog, edit
):
    client = builder()
    trial(client, clock)
    trial(client, clock)
    path = location(journal)
    path.write_text(edit(path.read_text(encoding="utf-8").splitlines()), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):
        response = client.get("/api/logs")
    assert response.status_code == 200  # 성공(200)이어야 함
    assert [entry["experimentId"] for entry in response.json()["logs"]] == [SECOND_ID]
    assert ID in caplog.text


# 열 수 없는 기록은 목록에서 빠지는지 검사
def test_a_log_that_cannot_be_opened_is_left_out_of_the_list(
    builder, clock, journal, caplog, monkeypatch
):
    client = builder()
    trial(client, clock)
    trial(client, clock)
    read = journal.records
    monkeypatch.setattr(journal, "records", lambda i: lockout() if i == ID else read(i))
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):
        response = client.get("/api/logs")
    assert [entry["experimentId"] for entry in response.json()["logs"]] == [SECOND_ID]
    assert ID in caplog.text



# 회차 전체가 기록된 줄 그대로 NDJSON 으로 오는지 검사
def test_a_log_comes_back_whole_as_ndjson(builder, clock, journal):
    client = builder()
    trial(client, clock, seconds=3)
    response = client.get(f"/api/logs/{ID}")
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.content == location(journal).read_bytes()
    records = [json.loads(line) for line in response.text.splitlines()]
    assert (records[0]["type"], records[-1]["kind"]) == ("meta", "stop")


# 쓰는 중인 끝줄은 스트림에서 빠지는지 검사
def test_a_line_still_being_written_is_left_out_of_the_stream(builder, clock, journal):
    client = builder()
    trial(client, clock)
    path = location(journal)
    whole = path.read_bytes()
    path.write_bytes(whole + '{"type":"obs","label":"보'.encode()[:-1])
    assert client.get(f"/api/logs/{ID}").content == whole


# 깨진 줄에서 스트림이 끝나는지 검사
def test_a_broken_line_ends_the_stream_there(builder, clock, journal, caplog):
    client = builder()
    trial(client, clock)
    path = location(journal)
    lines = path.read_bytes().splitlines(keepends=True)  # 줄 단위(줄바꿈 포함)로 읽음
    path.write_bytes(b"".join([*lines[:3], b"{\n", *lines[3:]]))
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):
        response = client.get(f"/api/logs/{ID}")
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.content == b"".join(lines[:3])
    assert "4번째 줄" in caplog.text


# 묶음보다 긴 기록도 통째로 오는지 검사
def test_a_log_longer_than_a_batch_comes_back_whole(
    builder, clock, journal, monkeypatch
):
    monkeypatch.setattr("app.api.logs.BATCH_LINES", 2)
    client = builder()
    trial(client, clock, seconds=4)
    assert client.get(f"/api/logs/{ID}").content == location(journal).read_bytes()


# 뒷 묶음의 깨진 줄에서도 스트림이 끝나는지 검사(묶음 2줄, 6번째 줄까지 보냄)
def test_a_broken_line_in_a_later_batch_ends_the_stream_there(
    builder, clock, journal, monkeypatch
):
    monkeypatch.setattr("app.api.logs.BATCH_LINES", 2)
    client = builder()
    trial(client, clock, seconds=4)
    path = location(journal)
    lines = path.read_bytes().splitlines(keepends=True)  # 줄 단위로 읽음
    path.write_bytes(b"".join([*lines[:6], b"{\n", *lines[6:]]))
    assert client.get(f"/api/logs/{ID}").content == b"".join(lines[:6])


# 읽다가 오류가 나면 정상 종료인 척하지 않고 스트림을 끊는지 검사
def test_a_read_error_partway_aborts_the_stream(builder, clock, journal, monkeypatch):
    client = builder()
    trial(client, clock)
    first = next(journal.records(ID))

    # 첫 줄만 주고 입출력 오류를 내는 가짜 읽기 함수
    def rupture(experiment_id):
        yield first
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(journal, "records", rupture)
    with pytest.raises(OSError, match="Input/output error"):
        client.get(f"/api/logs/{ID}")



# 이벤트만 따로 오는지 검사
def test_events_come_back_alone(builder, clock, journal, monkeypatch):
    client = builder()
    client.post("/api/experiment/start", json={})
    lapse(clock, client.app.state.service, 2)
    sabotage(client, clock, monkeypatch)
    events = [r for r in journal.records(ID) if r["type"] == "event"]
    assert [event["kind"] for event in events] == ["calc_error"]
    response = client.get(f"/api/logs/{ID}/events")
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.json() == {"events": events}


# 이벤트 없는 기록은 빈 목록을 주는지 검사
def test_a_log_without_events_gives_an_empty_list(builder, clock):
    client = builder()
    trial(client, clock)
    assert client.get(f"/api/logs/{ID}/events").json() == {"events": []}


# 이벤트 중 깨진 줄에서 끝나는지 검사
def test_a_broken_line_ends_the_events_there(
    builder, clock, journal, caplog, monkeypatch
):
    client = builder()
    client.post("/api/experiment/start", json={})
    lapse(clock, client.app.state.service, 2)
    sabotage(client, clock, monkeypatch)
    [event] = [r for r in journal.records(ID) if r["type"] == "event"]
    later = json.dumps({**event, "message": "나중 이벤트"}, ensure_ascii=False)
    with location(journal).open("a", encoding="utf-8") as f:
        f.write("{\n" + later + "\n")
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):
        response = client.get(f"/api/logs/{ID}/events")
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.json() == {"events": [event]}
    assert ID in caplog.text



# 전체·이벤트 경로 둘로 되풀이. 없는 기록은 404, 읽을 수 없는 저장소는 503
@pytest.mark.parametrize("route", ["/api/logs/{}", "/api/logs/{}/events"], ids=["log", "events"])
@pytest.mark.parametrize(
    "experiment_id",
    ["EXP-20261022-009", "EXP-1", "EXP-STANDBY", "exp-20261022-001"],
    ids=["missing", "short", "standby", "lowercase"],
)
# 이름이 가리키는 기록이 없으면 404 인지 검사
def test_an_id_that_names_no_log_is_404(builder, clock, route, experiment_id):
    client = builder()
    trial(client, clock)
    response = client.get(route.format(experiment_id))
    assert response.status_code == 404  # 찾을 수 없음(404)이어야 함
    assert response.json() == {"detail": f"그런 실험 기록이 없다: {experiment_id}"}


@pytest.mark.parametrize("route", [f"/api/logs/{ID}", f"/api/logs/{ID}/events"])
# 열 수 없는 기록은 503 인지 검사
def test_a_log_that_cannot_be_opened_is_503(builder, clock, journal, monkeypatch, route):
    client = builder()
    trial(client, clock)
    monkeypatch.setattr(journal, "records", lockout)
    response = client.get(route)
    assert response.status_code == 503  # 서비스 이용 불가(503)여야 함
    assert response.json() == {"detail": "실험 기록을 쓸 수 없다: Permission denied"}


# 목록을 읽을 수 없는 기록 폴더는 503 인지 검사
def test_a_log_folder_that_cannot_be_listed_is_503(builder, journal, monkeypatch):
    client = builder()

    # 권한 오류를 내는 가짜 목록 함수
    def barrier():
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(journal, "index", barrier)
    response = client.get("/api/logs")
    assert response.status_code == 503  # 서비스 이용 불가(503)여야 함
    assert response.json() == {"detail": "실험 기록을 쓸 수 없다: Permission denied"}
