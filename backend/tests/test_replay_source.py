import pytest
from app.adapters.replay_source import Command, Replay
from app.core.model import Conditions
from app.ports.experiment_log import Flaw
from datetime import UTC, timedelta
from tests.helpers import SENSOR_OK, START

ID = "EXP-20261022-001"
DRY = Conditions(0.0, {})
NO_BLOCKAGE = {"type": "none", "location": None}


# 기록 맨 앞 meta 줄을 만드는 도우미. 필요한 필드만 변환
def meta(**changes) -> dict:
    record = {  # 기본 meta 줄
        "type": "meta",
        "logVersion": 1,
        "experimentId": ID,
        "dataSource": "sim",
        "startTime": START.isoformat(timespec="microseconds"),  # 시작 시각(마이크로초까지)
    }
    return {**record, **changes}


# 조작(cmd) 줄을 만드는 도우미
def cmd(kind: str, elapsed, **values) -> dict:
    return {"type": "cmd", "kind": kind, "elapsedSec": elapsed, "receivedAt": "-", **values}


# 기록된 관측 원문을 만드는 도우미. NaN 은 글자 "nan" 으로 적혀 있음
def payload(seq: int) -> dict:
    return {
        "deviceId": "esp32_1",
        "bootId": "b",
        "seq": seq,
        "tMs": seq * 1000,  # 장치 시각(ms)
        "readings": {"distA_mm": 580.0, "distB_mm": "nan", "weight_g": 0.0},
        "sensorStatus": SENSOR_OK,
    }


# 관측(obs) 줄을 만드는 도우미
def obs(elapsed, seq: int) -> dict:
    return {"type": "obs", "elapsedSec": elapsed, "receivedAt": "-", "raw": payload(seq)}


# 상태(state) 줄을 만드는 도우미
def state(elapsed) -> dict:
    return {"type": "state", "elapsedSec": elapsed, "state": {}, "model": {}}


START_CMD = cmd("start", 0.0, rainMmPerHour=60.0, blockage=NO_BLOCKAGE)
HEAD = [meta(), START_CMD]  # 기록 머리: meta 와 시작 조작


# 관측이 때가 되면 한 번씩만 나오는지 검사
def test_observations_come_out_once_when_their_time_has_come():
    replay = Replay(
        [*HEAD, obs(1.0, 1), state(1.0), obs(2.0, 2), obs(2.0, 3), state(2.0), obs(3.0, 4)]
    )
    assert replay.inbox(0.5, DRY) == []
    assert replay.inbox(1.0, DRY) == [payload(1)]
    assert replay.inbox(1.0, DRY) == []
    assert replay.inbox(2.0, DRY) == [payload(2), payload(3)]
    assert replay.inbox(9.0, DRY) == [payload(4)]
    assert replay.inbox(9.0, DRY) == []


# 조작이 요청한 초까지 한 번씩만 나오는지 검사
def test_commands_come_out_once_up_to_the_time_asked():
    rain = cmd("rain", 2.0, rainMmPerHour=90.0)
    blockage = cmd("blockage", 2.0, blockage={"type": "full", "location": "INLET-02"})
    replay = Replay([*HEAD, state(1.0), state(2.0), rain, blockage, cmd("stop", 3.0)])
    assert replay.orders(0.0) == [Command(2, "start", 0.0, 60.0, ("none", None))]
    assert replay.orders(1.0) == []
    assert replay.orders(2.0) == [
        Command(5, "rain", 2.0, rain_mm_per_h=90.0),
        Command(6, "blockage", 2.0, blockage=("full", "INLET-02")),
    ]
    assert replay.orders(2.0) == []
    assert replay.orders(9.0) == [Command(7, "stop", 3.0)]
    assert [c.kind for c in replay.commands] == ["start", "rain", "blockage", "stop"]


# 초기화하면 처음부터 다시 내보내는지 검사
def test_reset_gives_everything_again_from_the_start():
    replay = Replay([*HEAD, obs(1.0, 1), state(1.0)])
    replay.inbox(9.0, DRY)
    replay.orders(9.0)
    replay.origin()
    assert replay.inbox(9.0, DRY) == [payload(1)]
    assert [c.kind for c in replay.orders(9.0)] == ["start"]


# meta 가 회차 ID 와 한국 시각 기준 시작 시각을 주는지 검사
def test_meta_gives_the_id_and_the_start_time_in_kst():
    utc = START.astimezone(UTC).isoformat()
    replay = Replay([meta(startTime=utc), START_CMD])
    assert replay.experiment_id == ID
    assert replay.start_time == START  # UTC 로 적어도 시작 시각은 원래와 같아야 함
    assert replay.start_time.utcoffset() == timedelta(hours=9)  # 오프셋은 한국(+9 시간)이어야 함


@pytest.mark.parametrize(
    ("tail", "end_s"),  # (뒤에 붙는 줄, 기대 끝 초) 이름
    [
        ([state(1.0), state(2.0), cmd("stop", 2.0)], 2.0),
        ([state(1.0), cmd("reset", 1.0)], 1.0),
        # 처음 정지에서 끝나고 뒤는 무시
        ([state(1.0), cmd("stop", 1.0), state(2.0), cmd("stop", 2.0)], 1.0),
        ([obs(1.0, 1), state(1.0), state(2.0), obs(3.0, 2)], 2.0),
        ([], 0.0),
    ],
    ids=["stop", "reset", "first-stop", "last-state", "no-tick"],
)
# 재생이 첫 정지·초기화에서, 없으면 마지막 상태에서 끝나는지 검사
def test_the_replay_ends_at_the_first_stop_or_reset_else_at_the_last_state(tail, end_s):
    assert Replay([*HEAD, *tail]).end_s == end_s


# 모르는 종류의 줄은 건너뛰는지 검사
def test_other_kinds_of_lines_are_skipped():
    event = {"type": "event", "kind": "calc_error", "elapsedSec": 3.0, "time": "-", "message": "x"}
    later = {"type": "note", "text": "나중 판에 생길 줄"}  # 나중 판에 생길 줄(모르는 종류)
    replay = Replay([*HEAD, later, obs(1.0, 1), state(1.0), event])
    assert replay.inbox(9.0, DRY) == [payload(1)]  # 관측은 그대로 나와야 함
    assert replay.end_s == 1.0  # 끝 초는 마지막 상태(1초)여야 함


BAD_LOGS = {  # 재생할 수 없는 기록 모음(이름 → 기록 줄들)
    "empty": [],
    "meta-not-first": [START_CMD, meta()],
    "meta-twice": [*HEAD, meta()],
    "other-log-version": [meta(logVersion=2), START_CMD],
    "id-not-text": [meta(experimentId=1), START_CMD],
    "start-time-not-a-time": [meta(startTime="어제"), START_CMD],
    "start-time-without-offset": [meta(startTime="2026-10-22T10:00:00"), START_CMD],
    "no-start": [meta()],
    "first-command-not-start": [meta(), cmd("rain", 0.0, rainMmPerHour=90.0)],
    "start-after-zero": [meta(), cmd("start", 1.0, rainMmPerHour=60.0, blockage=NO_BLOCKAGE)],
    "start-without-blockage": [meta(), cmd("start", 0.0, rainMmPerHour=60.0)],
    "unknown-command": [*HEAD, cmd("pump", 1.0)],
    "rain-missing": [*HEAD, cmd("rain", 1.0)],
    "rain-as-text": [*HEAD, cmd("rain", 1.0, rainMmPerHour="90")],
    "rain-nan-text": [*HEAD, cmd("rain", 1.0, rainMmPerHour="nan")],
    "blockage-not-an-object": [*HEAD, cmd("blockage", 1.0, blockage="full")],
    "blockage-location-not-text": [
        *HEAD,
        cmd("blockage", 1.0, blockage={"type": "full", "location": 2}),
    ],
    "elapsed-missing": [*HEAD, {"type": "state"}],
    "elapsed-as-text": [*HEAD, obs("1", 1)],
    "elapsed-bool": [*HEAD, state(True)],
    "elapsed-negative": [*HEAD, obs(-1.0, 1)],
    "time-goes-back": [*HEAD, state(2.0), cmd("rain", 1.0, rainMmPerHour=90.0)],
    "raw-missing": [*HEAD, {"type": "obs", "elapsedSec": 1.0}],
    "raw-not-an-observation": [*HEAD, {**obs(1.0, 1), "raw": {"deviceId": "esp32_1"}}],
}


@pytest.mark.parametrize("records", BAD_LOGS.values(), ids=BAD_LOGS.keys())
# 재생할 수 없는 기록은 형식 오류인지 검사
def test_a_log_that_cannot_be_replayed_is_a_format_error(records):
    with pytest.raises(Flaw):
        Replay(records)


# 형식 오류가 줄 번호를 알려 주는지 검사
def test_the_format_error_names_the_line():
    with pytest.raises(Flaw, match="^3번째 줄: "):  # 메시지가 "3번째 줄: " 로 시작해야 함
        Replay([*HEAD, cmd("pump", 1.0)])
