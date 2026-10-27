import json
import pytest
from app.adapters.jsonl_log import LOG_DIR, Jsonl
from app.ports.experiment_log import Absence, Flaw
from tests.helpers import breakage

ID = "EXP-20261022-001"  # 예시 회차 ID


# 기록이 한 줄에 하나씩 순서대로 돌아오는지 검사
def test_records_come_back_in_order_one_line_each(tmp_path):
    log = Jsonl(tmp_path)  # 임시 폴더에 기록기를 만듦
    # 기록 세 개를 준비
    records = [{"type": "meta", "label": "보통 강우"}, {"type": "obs", "x": 1.5}, {"type": "state"}]
    for record in records:  # 하나씩
        log.entry(ID, record)  # 기록에 덧붙임
    assert list(log.records(ID)) == records  # 다시 읽으면 같은 순서여야 함
    text = (tmp_path / f"{ID}.jsonl").read_text(encoding="utf-8")  # 파일 내용을 글자로 읽음
    assert text.endswith("\n")  # 줄바꿈으로 끝나야 함
    # 줄마다 JSON 하나로 읽혀야 함
    assert [json.loads(line) for line in text.splitlines()] == records
    assert "보통 강우" in text  # 한글이 이스케이프 없이 그대로 적혀야 함


# 덧붙이기가 끝에만 더하는지 검사
def test_append_only_adds_to_the_end(tmp_path):
    log = Jsonl(tmp_path)  # 기록기를 만듦
    log.entry(ID, {"type": "meta"})  # 첫 줄을 기록
    before = (tmp_path / f"{ID}.jsonl").read_bytes()  # 그때의 파일 바이트를 잡아 둔다
    log.entry(ID, {"type": "cmd", "kind": "start"})  # 한 줄 더 기록
    after = (tmp_path / f"{ID}.jsonl").read_bytes()  # 다시 파일 바이트를 읽음
    assert after.startswith(before) and len(after) > len(before)  # 앞부분은 그대로고 더 길어져야 함


# 목록이 날짜, 번호 순이고 다른 파일은 무시하는지 검사
def test_list_orders_by_date_then_number_and_ignores_other_files(tmp_path):
    log = Jsonl(tmp_path)  # 기록기를 만듦
    # 섞인 순서의 회차 ID 셋으로
    for experiment_id in ("EXP-20261023-002", "EXP-20261022-010", "EXP-20261022-002"):
        log.entry(experiment_id, {"type": "meta"})  # 기록을 하나씩 만듦
    (tmp_path / ".gitkeep").write_text("")  # 빈 .gitkeep 을 둔다
    (tmp_path / "notes.jsonl").write_text("{}\n")  # 이름이 맞지 않는 파일을 둔다
    (tmp_path / "EXP-20261022-003.txt").write_text("{}\n")  # 확장자가 다른 파일을 둔다
    # 날짜, 번호 순 ID 만 나와야 함
    assert log.index() == ["EXP-20261022-002", "EXP-20261022-010", "EXP-20261023-002"]


# 첫 기록 전에는 폴더도 없는지 검사
def test_nothing_exists_until_the_first_append(tmp_path):
    log = Jsonl(tmp_path / "logs")  # 아직 없는 폴더로 기록기를 만듦
    assert log.index() == []  # 목록은 비어 있어야 함
    assert not (tmp_path / "logs").exists()  # 폴더는 만들어지지 않아야 함
    log.entry(ID, {"type": "meta"})  # 첫 기록을 기록
    assert log.index() == [ID]  # 이제 목록에 그 회차가 있어야 함


# 없는 기록은 읽을 때 바로 실패하는지 검사
def test_reading_a_missing_log_fails_at_once(tmp_path):
    with pytest.raises(Absence):  # 기록 없음 오류가 나야 함
        Jsonl(tmp_path).records(ID)  # 없는 회차를 읽으면


# 쓰는 중인 끝줄은 빼고 읽는지 검사
def test_a_last_line_still_being_written_is_left_out(tmp_path):
    # 끝줄이 중간에 끊긴 파일을 만듦
    (tmp_path / f"{ID}.jsonl").write_text('{"type":"meta"}\n{"type":"obs","x":', encoding="utf-8")
    assert list(Jsonl(tmp_path).records(ID)) == [{"type": "meta"}]  # 온전한 첫 줄만 나와야 함


# 글자 중간에서 끊긴 끝줄도 빼고 읽는지 검사
def test_a_last_line_cut_inside_a_character_is_left_out(tmp_path):
    line = '{"type":"state","label":"보통 강우"}'.encode()  # 한글이 든 줄을 바이트로 만듦
    cut = line[: line.index("우".encode()) + 1]  # "우" 의 첫 바이트에서 자른다(쓰다 만 줄)
    # 온전한 첫 줄 뒤에 잘린 줄을 붙여 기록
    (tmp_path / f"{ID}.jsonl").write_bytes(b'{"type":"meta"}\n' + cut)
    assert list(Jsonl(tmp_path).records(ID)) == [{"type": "meta"}]  # 온전한 첫 줄만 나와야 함


# UTF-8 이 아닌 줄은 형식 오류인지 검사
def test_a_line_that_is_not_utf8_is_a_format_error(tmp_path):
    # 둘째 줄에 잘못된 바이트가 든 파일을 만듦
    (tmp_path / f"{ID}.jsonl").write_bytes(b'{"type":"meta"}\n{"x":"\xff"}\n{"type":"state"}\n')
    records = Jsonl(tmp_path).records(ID)  # 기록을 읽는 순회자를 얻음
    assert next(records) == {"type": "meta"}  # 첫 줄은 정상으로 나옴
    # 둘째 줄에서 형식 오류가 나야 하고 줄 번호를 알려야 함
    with pytest.raises(Flaw, match="2번째 줄"):
        next(records)  # 다음 줄을 읽으면


@pytest.mark.parametrize(  # 깨진 줄 종류마다 반복
    "line",  # 줄 값 이름
    # 끊긴 줄, NaN, Infinity, 배열, 글자, 빈 줄
    ['{"type":"obs",', '{"type":"obs","x":NaN}', '{"x":Infinity}', "[1, 2]", '"meta"', ""],
    ids=["cut", "nan", "infinity", "array", "string", "blank"],  # 사례 이름
)
# 중간의 깨진 줄은 형식 오류인지 검사
def test_a_broken_line_in_the_middle_is_a_format_error(tmp_path, line):
    text = '{"type":"meta"}\n' + line + '\n{"type":"state"}\n'  # 깨진 줄을 정상 줄 사이에 끼운다
    (tmp_path / f"{ID}.jsonl").write_text(text, encoding="utf-8")  # 파일에 기록
    records = Jsonl(tmp_path).records(ID)  # 기록을 읽는 순회자를 얻음
    assert next(records) == {"type": "meta"}  # 첫 줄은 정상으로 나옴
    with pytest.raises(Flaw):  # 깨진 줄에서 형식 오류가 나야 함
        next(records)  # 다음 줄을 읽으면


# NaN, 무한대로 반복
@pytest.mark.parametrize("value", [float("nan"), float("inf")], ids=["nan", "inf"])
# JSON 이 못 담는 값은 거절하고 아무것도 쓰지 않는지 검사
def test_a_value_json_cannot_hold_is_refused_and_nothing_is_written(tmp_path, value):
    log = Jsonl(tmp_path)  # 기록기를 만듦
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        log.entry(ID, {"type": "obs", "x": value})  # 그 값을 담아 덧붙이면
    assert not (tmp_path / f"{ID}.jsonl").exists()  # 파일이 만들어지지 않아야 함


# 쓰다 끊긴 뒤에 쓴 줄까지 읽히는지 검사
def test_a_write_cut_short_does_not_corrupt_the_next_line(tmp_path, monkeypatch):
    log = Jsonl(tmp_path)  # 기록기를 만듦
    meta = {"type": "meta", "experimentId": ID}  # 성한 첫 줄
    log.entry(ID, meta)  # 첫 줄을 기록
    breakage(monkeypatch)  # 이제부터 이어쓰기가 절반에서 끊긴다
    with pytest.raises(OSError):  # 둘째 줄 쓰기는 입출력 오류여야 함
        # 긴 줄을 쓰면
        log.entry(ID, {"type": "obs", "elapsedSec": 1.0, "readings": {"distA_mm": 598.375}})
    monkeypatch.undo()  # 이어쓰기를 원래대로 돌린다
    state = {"type": "state", "elapsedSec": 2.0}  # 성한 뒷줄
    log.entry(ID, state)  # 끊긴 다음 줄을 정상으로 기록
    assert list(log.records(ID)) == [meta, state]  # 반쪽 줄이 남지 않았으므로 두 줄 다 읽혀야 함


# 묶음 쓰기가 쓴 순서대로 들어가는지 검사
def test_a_batch_writes_every_line_in_order(tmp_path):
    log = Jsonl(tmp_path)  # 기록기를 만듦
    # 세 건을 준비
    records = [{"type": "meta"}, {"type": "cmd", "kind": "start"}, {"type": "obs", "x": 1.5}]
    log.batch(ID, records)  # 한 번에 기록
    assert list(log.records(ID)) == records  # 읽은 순서가 쓴 순서와 같아야 함


# 묶음 쓰기가 끊기면 회차 파일이 남지 않는지 검사
def test_a_batch_cut_short_leaves_no_file(tmp_path, monkeypatch):
    log = Jsonl(tmp_path)  # 기록기를 만듦
    breakage(monkeypatch)  # 이제부터 이어쓰기가 절반에서 끊긴다
    with pytest.raises(OSError):  # 두 건을 한 번에 쓰는 것은 실패 필요
        # meta·start 두 줄을 묶어 쓰면
        log.batch(ID, [{"type": "meta", "experimentId": ID}, {"type": "cmd", "kind": "start"}])
    monkeypatch.undo()  # 이어쓰기를 원래대로 돌린다
    assert log.index() == []  # 새로 만들던 파일은 남지 않아야 함


@pytest.mark.parametrize(  # 잘못된 ID 마다 반복
    "experiment_id",  # ID 이름
    # 경로 탈출·모양 틀림·빈 문자열 같은 잘못된 ID 들
    ["../EXP-20261022-001", "EXP-STANDBY", "EXP-2026102-001", "EXP-20261022-01", "", "x/y"]
    + ["EXP-٢٠٢٦١٠٢٢-٠٠١"],  # 아라비아-인도 숫자로 쓴 ID 도 잘못된 ID 다
)
# 회차 ID 모양만 파일 이름이 되는지 검사
def test_only_experiment_ids_name_files(tmp_path, experiment_id):
    log = Jsonl(tmp_path / "logs")  # 아직 없는 폴더로 기록기를 만듦
    with pytest.raises(ValueError):  # 쓰기는 값 오류가 나야 함
        log.entry(experiment_id, {"type": "meta"})  # 잘못된 ID 로 덧붙이면
    with pytest.raises(ValueError):  # 읽기도 값 오류가 나야 함
        log.records(experiment_id)  # 잘못된 ID 로 읽으면
    assert not (tmp_path / "logs").exists()  # 폴더가 만들어지지 않아야 함


# 기본 폴더가 backend/logs 인지 검사
def test_the_default_directory_is_backend_logs():
    # 폴더 이름이 logs, 부모가 backend 여야 함
    assert LOG_DIR.name == "logs" and LOG_DIR.parent.name == "backend"
    assert Jsonl().directory == LOG_DIR  # 인자 없는 기록기의 폴더가 기본 폴더여야 함
