import pytest
from app.adapters.replay_source import Command, Replay
from app.core.model import Conditions
from app.ports.experiment_log import Flaw
from datetime import UTC, timedelta
from tests.helpers import SENSOR_OK, START

ID = "EXP-20261022-001"  # 예시 회차 ID
DRY = Conditions(0.0, {})  # 비 없는 마른 조건
NO_BLOCKAGE = {"type": "none", "location": None}  # 막힘 없음 값


# 기록 맨 앞 meta 줄을 만드는 도우미. 필요한 필드만 변환
def meta(**changes) -> dict:
    record = {  # 기본 meta 줄
        "type": "meta",  # 줄 종류
        "logVersion": 1,  # 기록 형식 버전
        "experimentId": ID,  # 회차 ID
        "dataSource": "sim",  # 입력원
        "startTime": START.isoformat(timespec="microseconds"),  # 시작 시각(마이크로초까지)
    }
    return {**record, **changes}  # 바꾸려는 필드를 덮어써 반환


# 조작(cmd) 줄을 만드는 도우미
def cmd(kind: str, elapsed, **values) -> dict:
    # 경과 초와 추가 값을 담은 조작 줄을 반환
    return {"type": "cmd", "kind": kind, "elapsedSec": elapsed, "receivedAt": "-", **values}


# 기록된 관측 원문을 만드는 도우미. NaN 은 글자 "nan" 으로 적혀 있다
def payload(seq: int) -> dict:
    return {  # 원문 메시지를 반환
        "deviceId": "esp32_1",  # 장치 ID
        "bootId": "b",  # 부팅 ID
        "seq": seq,  # 순번
        "tMs": seq * 1000,  # 장치 시각(ms)
        # A 는 580, B 는 NaN 글자, 무게는 0
        "readings": {"distA_mm": 580.0, "distB_mm": "nan", "weight_g": 0.0},
        "sensorStatus": SENSOR_OK,  # 센서 상태는 모두 정상
    }


# 관측(obs) 줄을 만드는 도우미
def obs(elapsed, seq: int) -> dict:
    # 경과 초와 원문을 담은 관측 줄을 반환
    return {"type": "obs", "elapsedSec": elapsed, "receivedAt": "-", "raw": payload(seq)}


# 상태(state) 줄을 만드는 도우미
def state(elapsed) -> dict:
    # 경과 초만 맞춘 상태 줄을 반환
    return {"type": "state", "elapsedSec": elapsed, "state": {}, "model": {}}


# 경과 0초에 시작하는 조작 줄
START_CMD = cmd("start", 0.0, rainMmPerHour=60.0, blockage=NO_BLOCKAGE)
HEAD = [meta(), START_CMD]  # 기록 머리: meta 와 시작 조작


# 관측이 때가 되면 한 번씩만 나오는지 검사
def test_observations_come_out_once_when_their_time_has_come():
    replay = Replay(  # 관측과 상태가 섞인 기록으로 재생 입력원을 만듦
        # 기록 줄 목록
        [*HEAD, obs(1.0, 1), state(1.0), obs(2.0, 2), obs(2.0, 3), state(2.0), obs(3.0, 4)]
    )
    assert replay.inbox(0.5, DRY) == []  # 0.5초에는 아직 아무것도 없다
    assert replay.inbox(1.0, DRY) == [payload(1)]  # 1초에는 첫 관측이 나옴
    assert replay.inbox(1.0, DRY) == []  # 같은 초에 다시 부르면 비어 있다
    assert replay.inbox(2.0, DRY) == [payload(2), payload(3)]  # 2초에는 관측 둘이 나옴
    assert replay.inbox(9.0, DRY) == [payload(4)]  # 9초에는 남은 관측이 나옴
    assert replay.inbox(9.0, DRY) == []  # 그 뒤에는 더 없다


# 조작이 요청한 초까지 한 번씩만 나오는지 검사
def test_commands_come_out_once_up_to_the_time_asked():
    rain = cmd("rain", 2.0, rainMmPerHour=90.0)  # 비 세기를 바꾸는 조작
    # 막힘을 바꾸는 조작
    blockage = cmd("blockage", 2.0, blockage={"type": "full", "location": "INLET-02"})
    # 조작이 든 기록으로 만듦
    replay = Replay([*HEAD, state(1.0), state(2.0), rain, blockage, cmd("stop", 3.0)])
    # 0초에는 시작 조작이 나옴
    assert replay.orders(0.0) == [Command(2, "start", 0.0, 60.0, ("none", None))]
    assert replay.orders(1.0) == []  # 1초에는 새 조작이 없다
    assert replay.orders(2.0) == [  # 2초에는 비와 막힘 조작이 나옴
        Command(5, "rain", 2.0, rain_mm_per_h=90.0),  # 비 조작
        Command(6, "blockage", 2.0, blockage=("full", "INLET-02")),  # 막힘 조작
    ]
    assert replay.orders(2.0) == []  # 같은 초에 다시 부르면 비어 있다
    assert replay.orders(9.0) == [Command(7, "stop", 3.0)]  # 9초에는 정지 조작이 나옴
    # 조작 종류 전체가 순서대로 있어야 함
    assert [c.kind for c in replay.commands] == ["start", "rain", "blockage", "stop"]


# 초기화하면 처음부터 다시 내보내는지 검사
def test_reset_gives_everything_again_from_the_start():
    replay = Replay([*HEAD, obs(1.0, 1), state(1.0)])  # 관측이 든 기록으로 만듦
    replay.inbox(9.0, DRY)  # 관측을 모두 받음
    replay.orders(9.0)  # 조작을 모두 받음
    replay.origin()  # 초기화
    assert replay.inbox(9.0, DRY) == [payload(1)]  # 관측이 처음부터 다시 나옴
    assert [c.kind for c in replay.orders(9.0)] == ["start"]  # 조작도 시작부터 다시 나옴


# meta 가 회차 ID 와 한국 시각 기준 시작 시각을 주는지 검사
def test_meta_gives_the_id_and_the_start_time_in_kst():
    utc = START.astimezone(UTC).isoformat()  # 시작 시각을 UTC 문자열로 변환
    # 그 시각으로 meta 를 만들어 재생 입력원을 만듦
    replay = Replay([meta(startTime=utc), START_CMD])
    assert replay.experiment_id == ID  # 회차 ID 가 같아야 함
    assert replay.start_time == START  # UTC 로 적어도 시작 시각은 원래와 같아야 함
    assert replay.start_time.utcoffset() == timedelta(hours=9)  # 오프셋은 한국(+9 시간)이어야 함


@pytest.mark.parametrize(  # 끝 사례마다 반복
    ("tail", "end_s"),  # (뒤에 붙는 줄, 기대 끝 초) 이름
    [  # 사례 목록
        ([state(1.0), state(2.0), cmd("stop", 2.0)], 2.0),  # 정지 조작에서 끝난다
        ([state(1.0), cmd("reset", 1.0)], 1.0),  # 초기화 조작에서 끝난다
        # 처음 정지에서 끝나고 뒤는 무시
        ([state(1.0), cmd("stop", 1.0), state(2.0), cmd("stop", 2.0)], 1.0),
        # 조작이 없으면 마지막 상태에서 끝난다
        ([obs(1.0, 1), state(1.0), state(2.0), obs(3.0, 2)], 2.0),
        ([], 0.0),  # 틱이 없으면 0초에서 끝난다
    ],
    ids=["stop", "reset", "first-stop", "last-state", "no-tick"],  # 사례 이름
)
# 재생이 첫 정지·초기화에서, 없으면 마지막 상태에서 끝나는지 검사
def test_the_replay_ends_at_the_first_stop_or_reset_else_at_the_last_state(tail, end_s):
    assert Replay([*HEAD, *tail]).end_s == end_s  # 끝 초가 기대와 같아야 함


# 모르는 종류의 줄은 건너뛰는지 검사
def test_other_kinds_of_lines_are_skipped():
    # 계산 오류 이벤트 줄
    event = {"type": "event", "kind": "calc_error", "elapsedSec": 3.0, "time": "-", "message": "x"}
    later = {"type": "note", "text": "나중 판에 생길 줄"}  # 나중 판에 생길 줄(모르는 종류)
    replay = Replay([*HEAD, later, obs(1.0, 1), state(1.0), event])  # 그 줄들이 섞인 기록으로 만듦
    assert replay.inbox(9.0, DRY) == [payload(1)]  # 관측은 그대로 나와야 함
    assert replay.end_s == 1.0  # 끝 초는 마지막 상태(1초)여야 함


BAD_LOGS = {  # 재생할 수 없는 기록 모음(이름 → 기록 줄들)
    "empty": [],  # 빈 기록
    "meta-not-first": [START_CMD, meta()],  # meta 가 첫 줄이 아니다
    "meta-twice": [*HEAD, meta()],  # meta 가 두 번 있다
    "other-log-version": [meta(logVersion=2), START_CMD],  # 다른 기록 버전
    "id-not-text": [meta(experimentId=1), START_CMD],  # 회차 ID 가 글자가 아니다
    "start-time-not-a-time": [meta(startTime="어제"), START_CMD],  # 시작 시각이 시각이 아니다
    # 시작 시각에 오프셋이 없다
    "start-time-without-offset": [meta(startTime="2026-10-22T10:00:00"), START_CMD],
    "no-start": [meta()],  # 시작 조작이 없다
    # 첫 조작이 시작이 아니다
    "first-command-not-start": [meta(), cmd("rain", 0.0, rainMmPerHour=90.0)],
    # 시작 조작이 0초가 아니다
    "start-after-zero": [meta(), cmd("start", 1.0, rainMmPerHour=60.0, blockage=NO_BLOCKAGE)],
    # 시작 조작에 막힘이 없다
    "start-without-blockage": [meta(), cmd("start", 0.0, rainMmPerHour=60.0)],
    "unknown-command": [*HEAD, cmd("pump", 1.0)],  # 모르는 조작 종류
    "rain-missing": [*HEAD, cmd("rain", 1.0)],  # 비 조작에 세기가 없다
    "rain-as-text": [*HEAD, cmd("rain", 1.0, rainMmPerHour="90")],  # 비 세기가 글자다
    "rain-nan-text": [*HEAD, cmd("rain", 1.0, rainMmPerHour="nan")],  # 비 세기가 NaN 글자다
    # 막힘이 객체가 아니다
    "blockage-not-an-object": [*HEAD, cmd("blockage", 1.0, blockage="full")],
    "blockage-location-not-text": [  # 막힘 위치가 글자가 아니다
        *HEAD,  # 기록 머리
        cmd("blockage", 1.0, blockage={"type": "full", "location": 2}),  # 위치가 숫자인 막힘 조작
    ],
    "elapsed-missing": [*HEAD, {"type": "state"}],  # 경과 초가 없다
    "elapsed-as-text": [*HEAD, obs("1", 1)],  # 경과 초가 글자다
    "elapsed-bool": [*HEAD, state(True)],  # 경과 초가 불리언이다
    "elapsed-negative": [*HEAD, obs(-1.0, 1)],  # 경과 초가 음수다
    "time-goes-back": [*HEAD, state(2.0), cmd("rain", 1.0, rainMmPerHour=90.0)],  # 시간이 거꾸로 감
    "raw-missing": [*HEAD, {"type": "obs", "elapsedSec": 1.0}],  # 관측 원문이 없다
    # 원문이 관측 모양이 아니다
    "raw-not-an-observation": [*HEAD, {**obs(1.0, 1), "raw": {"deviceId": "esp32_1"}}],
}


@pytest.mark.parametrize("records", BAD_LOGS.values(), ids=BAD_LOGS.keys())  # 깨진 기록마다 반복
# 재생할 수 없는 기록은 형식 오류인지 검사
def test_a_log_that_cannot_be_replayed_is_a_format_error(records):
    with pytest.raises(Flaw):  # 형식 오류가 나야 함
        Replay(records)  # 그 기록으로 재생 입력원을 만들면


# 형식 오류가 줄 번호를 알려 주는지 검사
def test_the_format_error_names_the_line():
    with pytest.raises(Flaw, match="^3번째 줄: "):  # 메시지가 "3번째 줄: " 로 시작 필요
        Replay([*HEAD, cmd("pump", 1.0)])  # 셋째 줄에 모르는 조작을 둔 기록으로 만듦
