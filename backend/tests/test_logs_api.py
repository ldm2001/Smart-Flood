import json
import logging
import pytest
from app.core.model import Underflow
from tests.helpers import lapse, revision

ID = "EXP-20261022-001"  # 첫 회차 ID
SECOND_ID = "EXP-20261022-002"  # 둘째 회차 ID
# 목록에 나와야 하는 meta 필드들
META_FIELDS = ("experimentId", "startTime", "dataSource", "modelVersion", "configHash")


# 회차 하나를 seconds 초 돌리고 멈추는 도우미
def trial(client, clock, seconds: int = 2, **start) -> None:
    assert client.post("/api/experiment/start", json=start).status_code == 200  # 시작이 성공 필요
    lapse(clock, client.app.state.service, seconds)  # 가상 시계를 보내 틱을 돌린다
    assert client.post("/api/experiment/stop", json={}).status_code == 200  # 정지가 성공 필요


# 회차 기록 파일 경로를 주는 도우미
def location(experiment_log, experiment_id: str = ID):
    # 기록 폴더 아래 회차 ID 의 JSONL 파일
    return experiment_log.directory / f"{experiment_id}.jsonl"


# 다음 틱의 계산을 일부러 실패시키는 도우미. 회차가 멈추고 calc_error 이벤트가 남음
def sabotage(client, clock, monkeypatch) -> None:
    # 계산 대신 오류를 내는 가짜 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")  # 저장량이 음수라는 계산 오류를 냄

    monkeypatch.setattr("app.service.evolution", wreck)  # 서비스의 진행 함수를 가짜로 변환
    lapse(clock, client.app.state.service, 1)  # 틱 한 번을 돌려 실패시킨다
    monkeypatch.undo()  # 가짜를 원래대로 되돌린다


# 열 수 없는 기록을 흉내 내는 가짜 읽기 함수
def lockout(*args):
    raise PermissionError(13, "Permission denied")  # 권한 오류를 냄
    yield  # 생성기로 만든다: 첫 줄을 읽을 때 실패



# 사전에서 한 필드만 빼는 도우미
def omission(record: dict, field: str) -> dict:
    # 그 필드가 없는 사전을 반환
    return {key: value for key, value in record.items() if key != field}


# 첫 줄이 깨진 기록을 내려받으면 빈 200 이 아니라 503 인지 검사
def test_a_log_whose_first_line_is_broken_is_503(builder, clock, journal):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    revision(journal, lambda records: ["{", *records[1:]], ID)  # 첫 줄을 JSON 이 아닌 글자로 변환
    response = client.get(f"/api/logs/{ID}")  # 회차 전체를 요청
    assert response.status_code == 503, response.text  # 503 이어야 함
    # 사유에 기록 폴더 경로가 없어야 함
    assert str(journal.directory) not in response.json()["detail"]


@pytest.mark.parametrize("field", META_FIELDS)  # meta 필드마다 반복
# meta 에 필드가 빠진 기록이 목록에서 빠지는지 검사
def test_a_log_whose_meta_misses_a_field_is_left_out(builder, clock, journal, field):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    # meta 에서 그 필드를 제외
    revision(journal, lambda records: [omission(records[0], field), *records[1:]], ID)
    assert client.get("/api/logs").json() == {"logs": []}  # 목록이 비어야 함


# 목록이 날짜, 번호 순으로 meta 의 필드만 주는지 검사
def test_the_list_gives_each_log_its_meta_fields_in_order(builder, clock, journal):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    trial(client, clock, rain="heavy")  # 강한 비로 하나 더 돌린다
    response = client.get("/api/logs")  # 목록을 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    logs = response.json()["logs"]  # 목록을 꺼냄
    # ID 가 첫째, 둘째 순서여야 함
    assert [entry["experimentId"] for entry in logs] == [ID, SECOND_ID]
    metas = [next(journal.records(i)) for i in (ID, SECOND_ID)]  # 각 기록의 첫 줄(meta)을 직접 읽음
    # 목록은 meta 의 지정 필드만 담아야 함
    assert logs == [{key: meta[key] for key in META_FIELDS} for meta in metas]


# 첫 회차 전에는 목록이 비었는지 검사
def test_the_list_is_empty_before_the_first_run(builder):
    assert builder().get("/api/logs").json() == {"logs": []}  # 빈 목록이어야 함


# 진행 중인 회차도 목록에 나오는지 검사
def test_the_list_includes_the_run_in_progress(builder, clock):
    client = builder()  # 앱을 만듦
    client.post("/api/experiment/start", json={})  # 실험을 시작
    lapse(clock, client.app.state.service, 1)  # 1초를 전송
    # 목록에 그 회차가 있어야 함
    assert [entry["experimentId"] for entry in client.get("/api/logs").json()["logs"]] == [ID]


# 다른 회차 ID 를 지닌 기록으로 바꾸는 도우미
def stranger(lines: list[str]) -> str:
    # 첫 줄 meta 의 ID 를 둘째 ID 로 변환
    meta = {**json.loads(lines[0]), "experimentId": SECOND_ID}
    # 바뀐 첫 줄과 나머지를 줄바꿈으로 이어 반환
    return "".join(line + "\n" for line in [json.dumps(meta), *lines[1:]])


NO_READABLE_META = {  # 읽을 수 있는 meta 가 없게 망가뜨리는 방법들
    "broken": lambda lines: "".join(line + "\n" for line in ["{", *lines[1:]]),  # 첫 줄이 깨졌다
    "not-meta": lambda lines: "".join(line + "\n" for line in lines[1:]),  # 첫 줄(meta)이 없다
    "other-id": stranger,  # 파일 이름과 다른 ID
    "empty": lambda lines: "",  # 빈 파일
    "being-written": lambda lines: lines[0][:20],  # 쓰는 중이라 첫 줄이 끊겼다
}


# 망가뜨리는 방법마다 반복
@pytest.mark.parametrize("edit", NO_READABLE_META.values(), ids=NO_READABLE_META.keys())
# 읽을 수 있는 meta 가 없는 기록은 목록에서 빠지는지 검사
def test_a_log_without_a_readable_meta_is_left_out_of_the_list(
    builder, clock, journal, caplog, edit  # 준비물과 망가뜨리는 방법
):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    trial(client, clock)  # 하나 더 돌린다
    path = location(journal)  # 첫 회차 파일 경로
    # 파일 내용을 망가뜨려 다시 기록
    path.write_text(edit(path.read_text(encoding="utf-8").splitlines()), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):  # 경고 로그를 붙잡음
        response = client.get("/api/logs")  # 목록을 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    # 망가진 회차는 빠지고 둘째만 남아야 함
    assert [entry["experimentId"] for entry in response.json()["logs"]] == [SECOND_ID]
    assert ID in caplog.text  # 경고 로그에 그 회차 ID 가 있어야 함


# 열 수 없는 기록은 목록에서 빠지는지 검사
def test_a_log_that_cannot_be_opened_is_left_out_of_the_list(
    builder, clock, journal, caplog, monkeypatch  # 준비물 이름들
):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    trial(client, clock)  # 하나 더 돌린다
    read = journal.records  # 원래 읽기 함수를 보관
    # 첫 회차만 열기에 실패하게 변환
    monkeypatch.setattr(journal, "records", lambda i: lockout() if i == ID else read(i))
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):  # 경고 로그를 붙잡음
        response = client.get("/api/logs")  # 목록을 요청
    # 둘째만 남아야 함
    assert [entry["experimentId"] for entry in response.json()["logs"]] == [SECOND_ID]
    assert ID in caplog.text  # 경고 로그에 첫 회차 ID 가 있어야 함



# 회차 전체가 기록된 줄 그대로 NDJSON 으로 오는지 검사
def test_a_log_comes_back_whole_as_ndjson(builder, clock, journal):
    client = builder()  # 앱을 만듦
    trial(client, clock, seconds=3)  # 3초짜리 회차를 돌린다
    response = client.get(f"/api/logs/{ID}")  # 회차 전체를 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    # 내용 종류는 NDJSON 이어야 함
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.content == location(journal).read_bytes()  # 본문이 파일 바이트와 같아야 함
    records = [json.loads(line) for line in response.text.splitlines()]  # 줄마다 JSON 으로 읽음
    # 첫 줄은 meta, 마지막 줄은 정지 조작이어야 함
    assert (records[0]["type"], records[-1]["kind"]) == ("meta", "stop")


# 쓰는 중인 끝줄은 스트림에서 빠지는지 검사
def test_a_line_still_being_written_is_left_out_of_the_stream(builder, clock, journal):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    path = location(journal)  # 파일 경로
    whole = path.read_bytes()  # 온전한 내용을 보관
    # 글자 중간에서 끊긴 끝줄을 붙임
    path.write_bytes(whole + '{"type":"obs","label":"보'.encode()[:-1])
    assert client.get(f"/api/logs/{ID}").content == whole  # 본문은 온전한 내용과 같아야 함


# 깨진 줄에서 스트림이 끝나는지 검사
def test_a_broken_line_ends_the_stream_there(builder, clock, journal, caplog):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    path = location(journal)  # 파일 경로
    lines = path.read_bytes().splitlines(keepends=True)  # 줄 단위(줄바꿈 포함)로 읽음
    # 셋째 줄 뒤에 깨진 줄을 끼워 다시 기록
    path.write_bytes(b"".join([*lines[:3], b"{\n", *lines[3:]]))
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):  # 경고 로그를 붙잡음
        response = client.get(f"/api/logs/{ID}")  # 회차 전체를 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.content == b"".join(lines[:3])  # 깨진 줄 앞 세 줄만 와야 함
    assert "4번째 줄" in caplog.text  # 경고 로그에 4번째 줄이 적혀야 함


# 묶음보다 긴 기록도 통째로 오는지 검사
def test_a_log_longer_than_a_batch_comes_back_whole(
    builder, clock, journal, monkeypatch  # 준비물 이름들
):
    monkeypatch.setattr("app.api.logs.BATCH_LINES", 2)  # 묶음 크기를 2줄로 줄인다
    client = builder()  # 앱을 만듦
    trial(client, clock, seconds=4)  # 4초짜리 회차를 돌린다
    # 본문이 파일 바이트와 같아야 함
    assert client.get(f"/api/logs/{ID}").content == location(journal).read_bytes()


# 뒷 묶음의 깨진 줄에서도 스트림이 끝나는지 검사(묶음 2줄, 6번째 줄까지 보낸다)
def test_a_broken_line_in_a_later_batch_ends_the_stream_there(
    builder, clock, journal, monkeypatch  # 준비물 이름들
):
    monkeypatch.setattr("app.api.logs.BATCH_LINES", 2)  # 묶음 크기를 2줄로 줄인다
    client = builder()  # 앱을 만듦
    trial(client, clock, seconds=4)  # 4초짜리 회차를 돌린다
    path = location(journal)  # 파일 경로
    lines = path.read_bytes().splitlines(keepends=True)  # 줄 단위로 읽음
    # 여섯째 줄 뒤에 깨진 줄을 끼워 다시 기록
    path.write_bytes(b"".join([*lines[:6], b"{\n", *lines[6:]]))
    # 깨진 줄 앞 여섯 줄까지만 와야 함
    assert client.get(f"/api/logs/{ID}").content == b"".join(lines[:6])


# 읽다가 오류가 나면 정상 종료인 척하지 않고 스트림을 끊는지 검사
def test_a_read_error_partway_aborts_the_stream(builder, clock, journal, monkeypatch):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    first = next(journal.records(ID))  # 첫 줄을 미리 읽어 둔다

    # 첫 줄만 주고 입출력 오류를 내는 가짜 읽기 함수
    def rupture(experiment_id):
        yield first  # 첫 줄을 반환
        raise OSError(5, "Input/output error")  # 그다음에 입출력 오류를 냄

    monkeypatch.setattr(journal, "records", rupture)  # 읽기 함수를 가짜로 변환
    with pytest.raises(OSError, match="Input/output error"):  # 요청이 그 오류로 끊겨야 함
        client.get(f"/api/logs/{ID}")  # 회차 전체를 요청



# 이벤트만 따로 오는지 검사
def test_events_come_back_alone(builder, clock, journal, monkeypatch):
    client = builder()  # 앱을 만듦
    client.post("/api/experiment/start", json={})  # 실험을 시작
    lapse(clock, client.app.state.service, 2)  # 2초를 전송
    sabotage(client, clock, monkeypatch)  # 다음 틱의 계산을 실패시킨다
    events = [r for r in journal.records(ID) if r["type"] == "event"]  # 기록에서 이벤트 줄만 모음
    assert [event["kind"] for event in events] == ["calc_error"]  # 계산 오류 이벤트 하나여야 함
    response = client.get(f"/api/logs/{ID}/events")  # 이벤트 주소를 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.json() == {"events": events}  # 기록의 이벤트와 같아야 함


# 이벤트 없는 기록은 빈 목록을 주는지 검사
def test_a_log_without_events_gives_an_empty_list(builder, clock):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    assert client.get(f"/api/logs/{ID}/events").json() == {"events": []}  # 빈 이벤트 목록이어야 함


# 이벤트 중 깨진 줄에서 끝나는지 검사
def test_a_broken_line_ends_the_events_there(
    builder, clock, journal, caplog, monkeypatch  # 준비물 이름들
):
    client = builder()  # 앱을 만듦
    client.post("/api/experiment/start", json={})  # 실험을 시작
    lapse(clock, client.app.state.service, 2)  # 2초를 전송
    sabotage(client, clock, monkeypatch)  # 다음 틱의 계산을 실패시킨다
    # 기록에서 이벤트 하나를 꺼냄
    [event] = [r for r in journal.records(ID) if r["type"] == "event"]
    # 뒤에 올 이벤트를 만듦
    later = json.dumps({**event, "message": "나중 이벤트"}, ensure_ascii=False)
    with location(journal).open("a", encoding="utf-8") as f:  # 파일 끝에 덧붙여 연다
        f.write("{\n" + later + "\n")  # 깨진 줄을 쓰고 그 뒤에 이벤트를 기록
    with caplog.at_level(logging.WARNING, logger="app.api.logs"):  # 경고 로그를 붙잡음
        response = client.get(f"/api/logs/{ID}/events")  # 이벤트 주소를 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.json() == {"events": [event]}  # 깨진 줄 앞 이벤트만 와야 함
    assert ID in caplog.text  # 경고 로그에 회차 ID 가 있어야 함



# 전체·이벤트 경로 둘로 되풀이한다. 없는 기록은 404, 읽을 수 없는 저장소는 503
@pytest.mark.parametrize("route", ["/api/logs/{}", "/api/logs/{}/events"], ids=["log", "events"])
@pytest.mark.parametrize(  # ID 사례마다 반복
    "experiment_id",  # ID 이름
    # 없는 ID·짧은 ID·대기 ID·소문자 ID
    ["EXP-20261022-009", "EXP-1", "EXP-STANDBY", "exp-20261022-001"],
    ids=["missing", "short", "standby", "lowercase"],  # 사례 이름
)
# 이름이 가리키는 기록이 없으면 404 인지 검사
def test_an_id_that_names_no_log_is_404(builder, clock, route, experiment_id):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    response = client.get(route.format(experiment_id))  # 경로에 ID 를 끼워 요청
    assert response.status_code == 404  # 찾을 수 없음(404)이어야 함
    # 없다는 안내 문구가 와야 함
    assert response.json() == {"detail": f"그런 실험 기록이 없다: {experiment_id}"}


# 전체·이벤트 경로로 반복
@pytest.mark.parametrize("route", [f"/api/logs/{ID}", f"/api/logs/{ID}/events"])
# 열 수 없는 기록은 503 인지 검사
def test_a_log_that_cannot_be_opened_is_503(builder, clock, journal, monkeypatch, route):
    client = builder()  # 앱을 만듦
    trial(client, clock)  # 회차를 하나 돌린다
    monkeypatch.setattr(journal, "records", lockout)  # 읽기가 권한 오류로 실패하게 변환
    response = client.get(route)  # 요청
    assert response.status_code == 503  # 서비스 이용 불가(503)여야 함
    # 쓸 수 없다는 안내 문구와 사유가 와야 함
    assert response.json() == {"detail": "실험 기록을 쓸 수 없다: Permission denied"}


# 목록을 읽을 수 없는 기록 폴더는 503 인지 검사
def test_a_log_folder_that_cannot_be_listed_is_503(builder, journal, monkeypatch):
    client = builder()  # 앱을 만듦

    # 권한 오류를 내는 가짜 목록 함수
    def barrier():
        raise PermissionError(13, "Permission denied")  # 권한 오류를 냄

    monkeypatch.setattr(journal, "index", barrier)  # 목록 함수를 가짜로 변환
    response = client.get("/api/logs")  # 목록을 요청
    assert response.status_code == 503  # 서비스 이용 불가(503)여야 함
    # 쓸 수 없다는 안내 문구와 사유가 와야 함
    assert response.json() == {"detail": "실험 기록을 쓸 수 없다: Permission denied"}
