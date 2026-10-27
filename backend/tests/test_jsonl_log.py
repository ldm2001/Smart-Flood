import json
import pytest
from app.adapters.jsonl_log import LOG_DIR, Jsonl
from app.ports.experiment_log import Absence, Flaw
from tests.helpers import breakage

ID = "EXP-20261022-001"


# 기록이 한 줄에 하나씩 순서대로 돌아오는지 검사
def test_records_come_back_in_order_one_line_each(tmp_path):
    log = Jsonl(tmp_path)
    records = [{"type": "meta", "label": "보통 강우"}, {"type": "obs", "x": 1.5}, {"type": "state"}]
    for record in records:
        log.entry(ID, record)
    assert list(log.records(ID)) == records
    text = (tmp_path / f"{ID}.jsonl").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert [json.loads(line) for line in text.splitlines()] == records
    assert "보통 강우" in text  # 한글이 이스케이프 없이 그대로 적혀야 함


# 덧붙이기가 끝에만 더하는지 검사
def test_append_only_adds_to_the_end(tmp_path):
    log = Jsonl(tmp_path)
    log.entry(ID, {"type": "meta"})
    before = (tmp_path / f"{ID}.jsonl").read_bytes()
    log.entry(ID, {"type": "cmd", "kind": "start"})
    after = (tmp_path / f"{ID}.jsonl").read_bytes()
    assert after.startswith(before) and len(after) > len(before)  # 앞부분은 그대로고 더 길어져야 함


# 목록이 날짜, 번호 순이고 다른 파일은 무시하는지 검사
def test_list_orders_by_date_then_number_and_ignores_other_files(tmp_path):
    log = Jsonl(tmp_path)
    for experiment_id in ("EXP-20261023-002", "EXP-20261022-010", "EXP-20261022-002"):
        log.entry(experiment_id, {"type": "meta"})
    (tmp_path / ".gitkeep").write_text("")
    (tmp_path / "notes.jsonl").write_text("{}\n")
    (tmp_path / "EXP-20261022-003.txt").write_text("{}\n")
    assert log.index() == ["EXP-20261022-002", "EXP-20261022-010", "EXP-20261023-002"]


# 첫 기록 전에는 폴더도 없는지 검사
def test_nothing_exists_until_the_first_append(tmp_path):
    log = Jsonl(tmp_path / "logs")
    assert log.index() == []
    assert not (tmp_path / "logs").exists()
    log.entry(ID, {"type": "meta"})
    assert log.index() == [ID]


# 없는 기록은 읽을 때 바로 실패하는지 검사
def test_reading_a_missing_log_fails_at_once(tmp_path):
    with pytest.raises(Absence):
        Jsonl(tmp_path).records(ID)


# 쓰는 중인 끝줄은 빼고 읽는지 검사
def test_a_last_line_still_being_written_is_left_out(tmp_path):
    (tmp_path / f"{ID}.jsonl").write_text('{"type":"meta"}\n{"type":"obs","x":', encoding="utf-8")
    assert list(Jsonl(tmp_path).records(ID)) == [{"type": "meta"}]


# 글자 중간에서 끊긴 끝줄도 빼고 읽는지 검사
def test_a_last_line_cut_inside_a_character_is_left_out(tmp_path):
    line = '{"type":"state","label":"보통 강우"}'.encode()
    cut = line[: line.index("우".encode()) + 1]  # "우" 의 첫 바이트에서 자름(쓰다 만 줄)
    (tmp_path / f"{ID}.jsonl").write_bytes(b'{"type":"meta"}\n' + cut)
    assert list(Jsonl(tmp_path).records(ID)) == [{"type": "meta"}]


# UTF-8 이 아닌 줄은 형식 오류인지 검사
def test_a_line_that_is_not_utf8_is_a_format_error(tmp_path):
    (tmp_path / f"{ID}.jsonl").write_bytes(b'{"type":"meta"}\n{"x":"\xff"}\n{"type":"state"}\n')
    records = Jsonl(tmp_path).records(ID)
    assert next(records) == {"type": "meta"}
    with pytest.raises(Flaw, match="2번째 줄"):
        next(records)


@pytest.mark.parametrize(
    "line",
    ['{"type":"obs",', '{"type":"obs","x":NaN}', '{"x":Infinity}', "[1, 2]", '"meta"', ""],
    ids=["cut", "nan", "infinity", "array", "string", "blank"],
)
# 중간의 깨진 줄은 형식 오류인지 검사
def test_a_broken_line_in_the_middle_is_a_format_error(tmp_path, line):
    text = '{"type":"meta"}\n' + line + '\n{"type":"state"}\n'
    (tmp_path / f"{ID}.jsonl").write_text(text, encoding="utf-8")
    records = Jsonl(tmp_path).records(ID)
    assert next(records) == {"type": "meta"}
    with pytest.raises(Flaw):
        next(records)


@pytest.mark.parametrize("value", [float("nan"), float("inf")], ids=["nan", "inf"])
# JSON 이 못 담는 값은 거절하고 아무것도 쓰지 않는지 검사
def test_a_value_json_cannot_hold_is_refused_and_nothing_is_written(tmp_path, value):
    log = Jsonl(tmp_path)
    with pytest.raises(ValueError):
        log.entry(ID, {"type": "obs", "x": value})
    assert not (tmp_path / f"{ID}.jsonl").exists()


# 쓰다 끊긴 뒤에 쓴 줄까지 읽히는지 검사
def test_a_write_cut_short_does_not_corrupt_the_next_line(tmp_path, monkeypatch):
    log = Jsonl(tmp_path)
    meta = {"type": "meta", "experimentId": ID}
    log.entry(ID, meta)
    breakage(monkeypatch)
    with pytest.raises(OSError):
        log.entry(ID, {"type": "obs", "elapsedSec": 1.0, "readings": {"distA_mm": 598.375}})
    monkeypatch.undo()
    state = {"type": "state", "elapsedSec": 2.0}
    log.entry(ID, state)
    assert list(log.records(ID)) == [meta, state]  # 반쪽 줄이 남지 않았으므로 두 줄 다 읽혀야 함


# 묶음 쓰기가 쓴 순서대로 들어가는지 검사
def test_a_batch_writes_every_line_in_order(tmp_path):
    log = Jsonl(tmp_path)
    records = [{"type": "meta"}, {"type": "cmd", "kind": "start"}, {"type": "obs", "x": 1.5}]
    log.batch(ID, records)
    assert list(log.records(ID)) == records


# 묶음 쓰기가 끊기면 회차 파일이 남지 않는지 검사
def test_a_batch_cut_short_leaves_no_file(tmp_path, monkeypatch):
    log = Jsonl(tmp_path)
    breakage(monkeypatch)
    with pytest.raises(OSError):
        log.batch(ID, [{"type": "meta", "experimentId": ID}, {"type": "cmd", "kind": "start"}])
    monkeypatch.undo()
    assert log.index() == []


@pytest.mark.parametrize(
    "experiment_id",
    ["../EXP-20261022-001", "EXP-STANDBY", "EXP-2026102-001", "EXP-20261022-01", "", "x/y"]
    + ["EXP-٢٠٢٦١٠٢٢-٠٠١"],
)
# 회차 ID 모양만 파일 이름이 되는지 검사
def test_only_experiment_ids_name_files(tmp_path, experiment_id):
    log = Jsonl(tmp_path / "logs")
    with pytest.raises(ValueError):
        log.entry(experiment_id, {"type": "meta"})
    with pytest.raises(ValueError):
        log.records(experiment_id)
    assert not (tmp_path / "logs").exists()


# 기본 폴더가 backend/logs 인지 검사
def test_the_default_directory_is_backend_logs():
    assert LOG_DIR.name == "logs" and LOG_DIR.parent.name == "backend"
    assert Jsonl().directory == LOG_DIR
