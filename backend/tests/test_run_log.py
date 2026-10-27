import copy
import errno
import json
import logging
import math
import pytest
from app.config import checksum
from app.core.model import Underflow
from app.schemas import Message, encoding
from datetime import date, timedelta
from tests.helpers import SENSOR_OK, START, Script, breakage, lapse, readout

ID = "EXP-20261022-001"  # 첫 회차 ID
START_URL = "/api/experiment/start"  # 실험 시작 주소
STOP_URL = "/api/experiment/stop"  # 실험 정지 주소
RESET_URL = "/api/experiment/reset"  # 실험 초기화 주소
NO_BLOCKAGE = {"type": "none", "location": None}  # 막힘 없음 표시
DISK_FULL = (errno.ENOSPC, "No space left on device")  # 디스크가 가득 찬 오류 인자
# 기록을 못 쓸 때 기대하는 503 본문
UNAVAILABLE = {"detail": "실험 기록을 쓸 수 없다: No space left on device"}
# state 줄의 model 항목이 가져야 할 키들
MODEL_KEYS = {"volumesL", "correction", "correctionTotalL", "rainTotalL", "drainedL"}


# 가상 시계 시작 시각에서 seconds 초 뒤의 기록 시각 글자
def stamp(seconds: float) -> str:
    # 마이크로초까지 ISO 형식으로 만듦
    return (START + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


# 회차 기록의 모든 줄을 목록으로 읽는 도우미
def lines(experiment_log, experiment_id: str = ID) -> list[dict]:
    return list(experiment_log.records(experiment_id))  # 기록기가 내는 레코드를 목록으로 모음


# 레코드 중 종류가 kind 인 것만 거르는 도우미
def subset(records: list[dict], kind: str) -> list[dict]:
    return [r for r in records if r["type"] == kind]  # 종류가 같은 것만 남김


# POST 를 보내 성공(200)을 확인하고 본문을 돌려주는 도우미
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})  # 본문이 없으면 빈 객체로 전송
    assert response.status_code == 200, response.text  # 성공(200)이어야 함
    return response.json()  # 응답 본문을 반환


# 회차를 시작해 seconds 초 돌린 클라이언트와 서비스. kwargs 는 앱 만드는 함수로 감
def session(make_client, clock, *, body=None, seconds=0, **kwargs):
    client = make_client(**kwargs)  # 클라이언트를 만듦
    answer(client, START_URL, body)  # 회차를 시작
    service = client.app.state.service  # 앱 안의 서비스를 꺼냄
    lapse(clock, service, seconds)  # 정한 초만큼 전송
    return client, service  # 둘을 반환


# 기록기 Journal 의 대역. fail 에 OSError 인자를 넣으면 그때부터 쓰기가 그 오류로 실패
class Breaker:
    # 진짜 기록기를 감싸는 대역을 만듦
    def __init__(self, inner) -> None:
        self.inner, self.fail = inner, None  # 속 기록기와 실패 인자(없으면 정상)를 둔다

    # 한 줄을 쓴다. fail 이 있으면 실패
    def entry(self, experiment_id, record):
        if self.fail is not None:  # 실패 인자가 있으면
            raise OSError(*self.fail)  # 그 인자로 입출력 오류를 냄
        self.inner.entry(experiment_id, record)  # 아니면 진짜 기록기에 기록

    # 여러 줄을 쓴다. fail 이 있으면 실패
    def batch(self, experiment_id, records):
        if self.fail is not None:  # 실패 인자가 있으면
            raise OSError(*self.fail)  # 그 인자로 입출력 오류를 냄
        self.inner.batch(experiment_id, records)  # 아니면 진짜 기록기에 기록

    # 기록 목록은 진짜 기록기에서 읽음
    def index(self):
        return self.inner.index()  # 진짜 기록기의 목록을 반환

    # 회차 줄들은 진짜 기록기에서 읽음
    def records(self, experiment_id):
        return self.inner.records(experiment_id)  # 진짜 기록기의 줄들을 반환


# 기록 폴더를 읽을 수 없는 대역. 오류에 폴더 경로가 들어 있다
class Blocker(Breaker):
    # 기록 목록을 읽으려 하면
    def index(self):
        # 폴더 경로가 담긴 권한 오류를 냄
        raise OSError(errno.EACCES, "Permission denied", str(self.inner.directory))



# 기록할 값 다듬기: 무한·NaN 은 글자로 쓰는지 검사
def test_json_safe_writes_non_finite_numbers_as_text():
    # NaN·무한대·보통 값이 섞인 값
    value = {"a": math.nan, "b": [math.inf, -math.inf, 1.5], "c": {"d": None, "e": "x", "f": 2}}
    assert encoding(value) == {  # 다듬은 결과가
        "a": "nan",  # NaN 은 글자 nan
        "b": ["inf", "-inf", 1.5],  # 무한대는 글자로, 보통 숫자는 그대로
        "c": {"d": None, "e": "x", "f": 2},  # None·글자·정수는 그대로
    }


# 글자로 쓴 NaN·무한대 관측이 읽으면 같은 실수로 돌아오는지 검사
def test_non_finite_readings_written_as_text_read_back_as_the_same_floats():
    raw = {  # 비정상 값이 든 관측 메시지
        "deviceId": "esp32_1",  # 장치 ID
        "bootId": "b",  # 부팅 ID
        "seq": 1,  # 순번
        "tMs": 1000,  # 경과 시간(ms)
        # NaN, 무한대, 음의 무한대
        "readings": {"distA_mm": math.nan, "distB_mm": math.inf, "weight_g": -math.inf},
        "sensorStatus": {"A": "ok", "B": "ok", "load": "ok"},  # 센서 상태는 모두 정상
    }
    line = json.dumps(encoding(raw), allow_nan=False)  # 다듬어 JSON 한 줄로 쓴다(NaN 은 허용 안 함)
    # 그 줄을 메시지로 읽어 관측값을 꺼냄
    readings = Message.model_validate(json.loads(line)).readings
    assert math.isnan(readings.distA_mm)  # NaN 이 돌아와야 함
    # 무한대 둘도 돌아와야 함
    assert (readings.distB_mm, readings.weight_g) == (math.inf, -math.inf)


# 설정 해시는 키 순서가 아니라 값을 따르는지 검사
def test_config_hash_follows_the_values_not_the_key_order(config):
    digest = checksum(config)  # 설정의 해시를 구
    # 접두어 sha256: 와 16진수 64자여야 함
    assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64
    # 키 순서를 뒤집어도 같은 해시여야 함
    assert checksum(dict(reversed(list(config.items())))) == digest
    changed = copy.deepcopy(config)  # 설정을 깊은 복사
    changed["correction"]["gain"] = 0.31  # 보정 비율 하나를 변환
    assert checksum(changed) != digest  # 값이 바뀌면 해시도 달라야 함


# JSON 으로 쓸 수 없는 값마다 반복
@pytest.mark.parametrize("value", [math.nan, date(2026, 10, 22)], ids=["nan", "date"])
# JSON 에 담을 수 없는 설정은 해시를 못 구하는지 검사
def test_a_config_json_cannot_hold_has_no_hash(config, value):
    cfg = copy.deepcopy(config)  # 설정을 깊은 복사
    cfg["calibrated_on"] = value  # 교정일 자리에 못 쓰는 값을 넣음
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        checksum(cfg)  # 해시를 구하려



# 회차의 줄은 meta 와 start 로 시작하는지 검사(틱마다 obs 다음에 state)
def test_a_run_opens_with_meta_and_its_start_command(builder, clock, journal, config):
    # 강한 비와 2번 완전 막힘으로 시작할 본문
    body = {"rain": "heavy", "blockage": {"type": "full", "location": "INLET-02"}}
    # 관측 없는 입력원으로 회차를 시작
    client, _ = session(builder, clock, body=body, source=Script(None))
    assert client.get("/api/state").json()["experimentId"] == ID  # 회차 ID 가 첫 번호여야 함
    meta, start = lines(journal)  # 기록은 두 줄(meta, start)뿐이어야 함
    assert meta == {  # meta 줄의 내용
        "type": "meta",  # 줄 종류
        "logVersion": 1,  # 기록 형식 버전
        "experimentId": ID,  # 회차 ID
        "dataSource": "sim",  # 입력원
        "startTime": stamp(0),  # 시작 시각
        "modelVersion": config["model_version"],  # 모델 버전
        "configHash": checksum(config),  # 설정 해시
        "config": config,  # 설정 전체
    }
    assert start == {  # start 줄의 내용
        "type": "cmd",  # 줄 종류
        "kind": "start",  # 조작 종류
        "elapsedSec": 0.0,  # 적용 시점의 경과 초
        "receivedAt": stamp(0),  # 받은 시각
        "rainMmPerHour": 90.0,  # 강한 비 세기(mm/h)
        "blockage": {"type": "full", "location": "INLET-02"},  # 막힘 선택
    }


# 틱마다 obs 줄 다음에 state 줄을 쓰는지 검사
def test_each_tick_writes_its_observations_then_its_state(
    builder, clock, journal, config  # 준비물 이름들
):
    # A 20 mm, B 10 mm, 무게 150 g 을 매번 내는 입력원
    source = Script(readout(config, a_mm=20, b_mm=10, weight_g=150))
    client, service = session(builder, clock, source=source)  # 그 입력원으로 회차를 시작
    for second in (1, 2, 3):  # 1~3초마다
        lapse(clock, service, 1)  # 1초를 전송
        obs, state = lines(journal)[-2:]  # 마지막 두 줄이 obs 와 state
        # obs 줄의 종류·경과 초·받은 시각이어야 함
        assert (obs["type"], obs["elapsedSec"], obs["receivedAt"]) == ("obs", second, stamp(second))
        assert obs["raw"] == {  # 받은 원본 메시지가 그대로 있어야 함
            "deviceId": "esp32_1",  # 장치 ID
            "bootId": "test",  # 부팅 ID
            "seq": second,  # 순번은 초와 같다
            "tMs": second * 1000,  # 경과 시간(ms)
            "readings": source.readings,  # 관측값
            "sensorStatus": SENSOR_OK,  # 센서 상태
        }
        assert obs["levelsMm"] == pytest.approx({"A": 20, "B": 10})  # 변환한 수위(mm)여야 함
        assert obs["drainVolumeL"] == pytest.approx(0.15)  # 150 g 은 배수량 0.15 L
        # 세 센서 모두 유효여야 함
        assert obs["quality"] == {"A": "valid", "B": "valid", "load": "valid"}
        # 다음 줄은 같은 초의 state 여야 함
        assert (state["type"], state["elapsedSec"]) == ("state", second)
        assert state["state"] == client.get("/api/state").json()  # state 줄이 응답 본문과 같아야 함
        volumes = service.state.V  # 서비스의 구역별 부피(m³)
        # model 의 부피(L)가 m³ × 1000 이어야 함
        assert state["model"]["volumesL"] == {z: volumes[z] * 1000 for z in "ABC"}
    records = lines(journal)  # 전체 줄을 읽음
    # meta, cmd 다음에 obs·state 가 세 번 이어져야 함
    assert [r["type"] for r in records] == ["meta", "cmd"] + ["obs", "state"] * 3
    assert all(next(iter(r)) == "type" for r in records)  # 모든 줄의 첫 키가 type 이어야 함


# state 줄이 보정 내역과 물 수지를 담는지 검사
def test_state_lines_carry_the_correction_and_the_water_balance(
    builder, clock, journal, config, params  # 준비물 이름들
):
    source = Script(readout(config, a_mm=20, b_mm=10), until_s=2)  # 2초까지만 관측을 내는 입력원
    # 3초 돌린다(셋째 틱은 관측 없음)
    _, service = session(builder, clock, source=source, seconds=3)
    models = [r["model"] for r in subset(lines(journal), "state")]  # state 줄의 model 항목들
    assert len(models) == 3  # 틱 3개분이어야 함
    for model in models:  # 모든 model 이
        assert set(model) == MODEL_KEYS  # 정해진 키를 가져야 함
        assert set(model["drainedL"]) == set(params.inlets)  # 빗물받이마다 배수량이 있어야 함
    for model in models[:2]:  # 관측이 있던 처음 두 틱은
        assert set(model["correction"]) == {"A", "B"}  # A·B 보정 내역이 있어야 함
        for zone, change in model["correction"].items():  # 구역별 보정 내역마다
            assert change["afterL"] == model["volumesL"][zone]  # 보정 뒤 부피가 현재 부피여야 함
            # 변화량이 뒤 − 앞이어야 함
            assert change["deltaL"] == pytest.approx(change["afterL"] - change["beforeL"])
    assert models[2]["correction"] == {}  # 관측이 없던 셋째 틱은 보정이 비어야 함
    # 보정 변화량을 모두 모음
    deltas = [c["deltaL"] for m in models for c in m["correction"].values()]
    final, state = models[-1], service.state  # 마지막 model 과 서비스 상태
    # 누적 보정량이 변화량의 합이어야 함
    assert final["correctionTotalL"] == pytest.approx(sum(deltas))
    # 누적 강우량이 서비스 값과 같고 0 보다 커야 함
    assert final["rainTotalL"] == pytest.approx(state.rain_m3 * 1000) and final["rainTotalL"] > 0
    # 빗물받이별 누적 배수량이 서비스 값과 같아야 함
    assert final["drainedL"] == pytest.approx({i: v * 1000 for i, v in state.drained_m3.items()})



# 도는 동안의 조작이 적용 시각(처리한 마지막 틱의 경과 초)과 함께 기록되는지 검사
def test_controls_during_a_run_are_logged_with_their_apply_time(builder, clock, journal):
    # 관측 없는 입력원으로 시작해 2초 돌린다
    client, service = session(builder, clock, source=Script(None), seconds=2)
    answer(client, "/api/rain", {"intensity": "light"})  # 2초째에 비를 약하게 변환
    # 2초째에 3번을 부분 차단
    answer(client, "/api/blockage", {"type": "partial", "location": "INLET-03"})
    lapse(clock, service, 1)  # 1초를 전송
    answer(client, "/api/rain", {"mmPerHour": 42.5})  # 3초째에 비를 42.5 mm/h 로 변환
    answer(client, "/api/rain", {"mmPerHour": 42.5})  # 같은 값을 한 번 더 보내도 줄이 남음
    answer(client, START_URL, {"rain": "heavy"})  # 돌고 있을 때 다시 시작하면 start 줄이 또 남음
    answer(client, STOP_URL)  # 정지
    # 멈춘 뒤의 조작은 이 회차에 적지 않는다. 다음 start 줄이 가져감
    answer(client, "/api/rain", {"intensity": "light"})
    answer(client, RESET_URL)  # 초기화

    records = lines(journal)  # 전체 줄을 읽음
    cmds = subset(records, "cmd")  # cmd 줄만 모음
    assert [(c["kind"], c["elapsedSec"]) for c in cmds] == [  # 조작 종류와 적용 시각이 차례로
        ("start", 0.0),  # 시작 0초
        ("rain", 2.0),  # 비 2초
        ("blockage", 2.0),  # 막힘 2초
        ("rain", 3.0),  # 비 3초
        ("rain", 3.0),  # 같은 비 3초
        ("start", 3.0),  # 다시 시작 3초
        ("stop", 3.0),  # 정지 3초
    ]
    # 정지가 마지막 줄이고 기록은 한 회차뿐이어야 함
    assert records[-1] == cmds[-1] and journal.index() == [ID]
    rain, blockage, start, stop = cmds[1], cmds[2], cmds[5], cmds[6]  # 확인할 조작 줄들을 꺼냄
    # 약한 비 30 mm/h, 받은 시각 2초
    assert (rain["rainMmPerHour"], rain["receivedAt"]) == (30.0, stamp(2))
    # 막힘 선택이 기록돼야 함
    assert blockage["blockage"] == {"type": "partial", "location": "INLET-03"}
    # 같은 값 두 줄은 둘 다 42.5 여야 함
    assert cmds[3]["rainMmPerHour"] == cmds[4]["rainMmPerHour"] == 42.5
    assert start["rainMmPerHour"] == 90.0  # 다시 시작한 비는 강함 90 mm/h
    # 막힘은 앞서 고른 값이 이어져야 함
    assert start["blockage"] == {"type": "partial", "location": "INLET-03"}
    base = ["type", "kind", "elapsedSec", "receivedAt"]  # 모든 cmd 줄의 공통 키
    # 비·막힘 줄은 공통 키 뒤에 자기 키가 붙는다
    assert (list(rain), list(blockage)) == (base + ["rainMmPerHour"], base + ["blockage"])
    # 정지 줄은 공통 키뿐이고 받은 시각은 3초
    assert (list(stop), stop["receivedAt"]) == (base, stamp(3))


# 도는 중 초기화가 회차의 마지막 줄이 되는지 검사
def test_a_reset_during_a_run_is_its_last_line(builder, clock, journal):
    client, _ = session(  # 약한 비로 시작해 1초 돌린다
        builder, clock, body={"rain": "light"}, source=Script(None), seconds=1  # 준비물과 시작 본문
    )
    answer(client, RESET_URL)  # 초기화
    last = lines(journal)[-1]  # 마지막 줄을 읽음
    # 1초에 적용된 reset 조작이어야 함
    assert (last["type"], last["kind"], last["elapsedSec"]) == ("cmd", "reset", 1.0)
    # 초기화가 선택도 기본값으로 돌렸다. 다음 회차의 start 줄에 그 값이 감
    answer(client, START_URL)
    start = subset(lines(journal, "EXP-20261022-002"), "cmd")[0]  # 둘째 회차의 첫 cmd 줄
    # 기본 비 60 mm/h 와 막힘 없음이어야 함
    assert (start["rainMmPerHour"], start["blockage"]) == (60.0, NO_BLOCKAGE)


# 대기 중 고른 값이 start 줄로 기록에 들어가는지 검사
def test_selections_made_while_idle_reach_the_log_through_the_start_line(
    builder, journal  # 준비물 이름들
):
    client = builder(source=Script(None))  # 관측 없는 입력원으로 앱을 만듦
    answer(client, "/api/rain", {"intensity": "light"})  # 대기 중에 비를 약하게 선택
    # 대기 중에 1번을 부분 차단
    answer(client, "/api/blockage", {"type": "partial", "location": "INLET-01"})
    assert journal.index() == []  # 시작 전이라 기록이 없어야 함
    answer(client, START_URL)  # 시작
    start = subset(lines(journal), "cmd")[0]  # 첫 cmd 줄(start)을 꺼냄
    assert start["rainMmPerHour"] == 30.0  # 고른 약한 비가 담겨야 함
    assert start["blockage"] == {"type": "partial", "location": "INLET-01"}  # 고른 막힘이 담겨야 함


INVALID_READINGS = {  # 무효 관측 사례: (바꿀 관측값, 바꿀 상태, 무효가 될 센서)
    "distance-nan": ({"distA_mm": math.nan}, {}, "A"),  # A 거리가 NaN
    "distance-out-of-range": ({"distA_mm": 150.0}, {}, "A"),  # A 거리가 범위 밖
    "status-not-ok": ({}, {"B": "error"}, "B"),  # B 상태가 정상이 아님
    "weight-nan": ({"weight_g": math.nan}, {}, "load"),  # 무게가 NaN
    "weight-status-not-ok": ({}, {"load": "error"}, "load"),  # 무게 센서 상태가 정상이 아님
}


@pytest.mark.parametrize(  # 사례마다 반복
    # (관측, 상태, 무효 센서) 이름과 사례 이름
    ("readings", "status", "bad"), INVALID_READINGS.values(), ids=INVALID_READINGS.keys()
)
# 무효 관측도 받은 그대로 적고 그 센서 값은 보정에서 빼는지 검사
def test_an_invalid_reading_is_logged_as_received_and_left_out(
    builder, clock, journal, config, readings, status, bad  # 준비물과 사례 이름들
):
    good = readout(config, a_mm=20, b_mm=10, weight_g=150)  # 정상 관측값
    # 사례대로 망가뜨린 관측과 상태를 내는 입력원
    source = Script({**good, **readings}, {**SENSOR_OK, **status})
    client, _ = session(builder, clock, source=source, seconds=1)  # 1초 돌린다
    obs, state = lines(journal)[-2:]  # 마지막 두 줄이 obs 와 state
    # 받은 관측이 그대로(다듬어서) 적혀야 함
    assert obs["raw"]["readings"] == encoding(source.readings)
    assert obs["raw"]["sensorStatus"] == source.status  # 센서 상태도 그대로 적혀야 함
    # 무효 센서만 invalid, 나머지는 valid
    assert obs["quality"] == {s: "invalid" if s == bad else "valid" for s in ("A", "B", "load")}
    values = {**obs["levelsMm"], "load": obs["drainVolumeL"]}  # 센서별 변환 값을 모음
    # 값이 null 인 센서는 무효 센서뿐이어야 함
    assert [s for s, value in values.items() if value is None] == [bad]
    assert set(state["model"]["correction"]) == {"A", "B"} - {bad}  # 무효 센서는 보정에서 빠져야 함
    assert client.get("/api/state").json()["runState"] == "running"  # 회차는 계속 돌아야 함


# 계산 오류가 나면 event 줄로 기록을 끝내는지 검사
def test_a_calc_error_ends_the_log_with_an_event(
    builder, clock, journal, config, monkeypatch  # 준비물 이름들
):
    source = Script(readout(config, a_mm=20, b_mm=10))  # A 20 mm, B 10 mm 를 매번 내는 입력원
    client, service = session(builder, clock, source=source, seconds=1)  # 1초 돌린다

    # 항상 실패하는 가짜 계산 함수
    def wreck(*args, **kwargs):
        raise Underflow("A 저장량이 -1.0 m³ 다")  # 저장량 음수 오류를 냄

    monkeypatch.setattr("app.service.evolution", wreck)  # 서비스의 계산을 가짜로 변환
    clock.jump(1.0)  # 시계를 1초 전송
    assert service.catchup() == 0  # 처리된 틱은 0 이어야 함
    records = lines(journal)  # 전체 줄을 읽음
    # 실패한 2초 틱의 obs·state 는 없고 그 자리에 event 하나
    assert [r["type"] for r in records] == ["meta", "cmd", "obs", "state", "event"]
    assert records[-1] == {  # 마지막 줄은 event 여야 함
        "type": "event",  # 줄 종류
        "kind": "calc_error",  # 이벤트 종류
        "elapsedSec": 2.0,  # 실패한 틱의 경과 초
        "time": stamp(2),  # 기록 시각
        "message": "Underflow: A 저장량이 -1.0 m³ 다",  # 오류 이름과 설명
    }
    assert client.get("/api/state").json()["runState"] == "stopped"  # 회차가 정지돼야 함


# 계약 밖 상태가 나오면 GET 이 깨지지 않고 회차가 멈추는지 검사
def test_a_state_outside_the_contract_stops_the_run_instead_of_breaking_get(
    builder, clock, journal, config  # 준비물 이름들
):
    # 설정을 복사한다. 센서를 높이 달면 관측 수위가 계약 범위(0~500 mm)를 넘을 수 있다
    cfg = copy.deepcopy(config)
    # A 센서를 900 mm 높이에 달고 범위도 900 mm 로 늘린다
    cfg["sensors"]["A"] = {**cfg["sensors"]["A"], "install_height_mm": 900, "max_range_mm": 900}
    source = Script(readout(cfg, a_mm=20, b_mm=10))  # 처음엔 정상 범위의 관측을 냄
    # 그 설정으로 1초 돌린다
    client, service = session(builder, clock, source=source, seconds=1, cfg=cfg)
    # 다음 관측은 A 수위 600 mm 로 계약 범위를 넘는다
    source.readings = readout(cfg, a_mm=600, b_mm=10)
    clock.jump(1.0)  # 시계를 1초 전송
    assert service.catchup() == 0  # 처리된 틱은 0 이어야 함
    event = lines(journal)[-1]  # 마지막 줄을 읽음
    # 2초에 계산 오류 event 가 남아야 함
    assert (event["type"], event["kind"], event["elapsedSec"]) == ("event", "calc_error", 2.0)
    assert event["message"].startswith("ValidationError: ")  # 오류 이름이 ValidationError 여야 함
    response = client.get("/api/state")  # 멈춘 화면은 계약을 지킨 마지막 틱의 상태다
    assert response.status_code == 200  # 성공(200)이어야 함
    # 정지 상태, 마지막 정상 틱인 1초여야 함
    assert (response.json()["runState"], response.json()["elapsedSec"]) == ("stopped", 1)



# 실험 ID: 그 날짜 기록 중 가장 큰 번호 + 1 인지 검사
def test_the_next_id_follows_the_logs_of_that_date(builder, journal):
    # 오늘 001·007 번과 어제 012 번 기록
    for experiment_id in ("EXP-20261022-001", "EXP-20261022-007", "EXP-20261021-012"):
        journal.entry(experiment_id, {"type": "meta"})  # meta 줄만 있는 기록을 만듦
    client = builder(source=Script(None))  # 관측 없는 입력원으로 앱을 만듦
    # 오늘 최대 007 다음인 008 이어야 함
    assert answer(client, START_URL)["experimentId"] == "EXP-20261022-008"


# 서버를 다시 띄워도 ID 가 겹치지 않는지 검사
def test_ids_stay_unique_across_server_restarts(builder):
    first = builder(source=Script(None))  # 첫 서버를 띄운다
    assert answer(first, START_URL)["experimentId"] == "EXP-20261022-001"  # 첫 회차는 001 이어야 함
    second = builder(source=Script(None))  # 서버를 다시 띄운다
    # 다음 회차는 002 여야 함
    assert answer(second, START_URL)["experimentId"] == "EXP-20261022-002"



# 기록을 못 쓰면 시작·강우·막힘은 503 거절, 종료·초기화는 적용. 먼저 시작 거절 검사
def test_a_start_the_log_cannot_take_is_503_and_starts_nothing(builder, journal):
    log = Breaker(journal)  # 쓰기를 막을 수 있는 대역 기록기
    client = builder(source=Script(None), experiment_log=log)  # 그 기록기로 앱을 만듦
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다
    log.fail = DISK_FULL  # 이제부터 디스크 가득 오류로 실패하게
    response = client.post(START_URL, json={"rain": "heavy"})  # 시작을 요청
    # 503 과 기록 불가 사유여야 함
    assert (response.status_code, response.json()) == (503, UNAVAILABLE)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert journal.index() == []  # 기록 파일이 만들어지지 않아야 함
    log.fail = None  # 오류를 푼다
    assert answer(client, START_URL)["experimentId"] == ID  # 다시 시작하면 첫 회차 ID 를 받아야 함


# 첫 줄을 쓰다 끊기면 기록도 회차 번호도 남지 않는지 검사
def test_a_start_cut_short_leaves_no_log_and_keeps_the_number(builder, journal, monkeypatch):
    client = builder(source=Script(None))  # 진짜 기록기로 앱을 만듦
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다
    breakage(monkeypatch)  # 이제부터 이어쓰기가 절반에서 끊긴다
    response = client.post(START_URL, json={"rain": "heavy"})  # 시작을 요청
    # 503 과 기록 불가 사유여야 함
    assert (response.status_code, response.json()) == (503, UNAVAILABLE)
    monkeypatch.undo()  # 이어쓰기를 원래대로 돌린다
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert journal.index() == []  # 반쪽 기록 파일이 남지 않아야 함
    # 다시 시작하면 번호를 건너뛰지 않고 첫 회차여야 함
    assert answer(client, START_URL)["experimentId"] == ID


# 503 사유에 파일 경로가 안 들어가는지 검사
def test_the_503_reason_leaves_out_the_file_path(builder, journal):
    # 폴더를 못 읽는 대역 기록기로 앱을 만듦
    client = builder(source=Script(None), experiment_log=Blocker(journal))
    response = client.post(START_URL, json={})  # 시작을 요청
    assert (response.status_code, response.json()) == (  # 503 과 경로 없는 사유여야 함
        503,  # 상태 코드
        {"detail": "실험 기록을 쓸 수 없다: Permission denied"},  # 사유에 폴더 경로가 없다
    )
    assert client.get("/api/state").json()["runState"] == "idle"  # 상태는 대기 그대로여야 함


RUN_CONTROLS = {  # 돌고 있을 때 기록을 남기는 조작들
    "rain": ("/api/rain", {"mmPerHour": 42.5}),  # 비 바꾸기
    "blockage": ("/api/blockage", {"type": "full", "location": "INLET-01"}),  # 막힘 바꾸기
    "start": (  # 다시 시작
        START_URL,  # 시작 주소
        # 강한 비와 부분 막힘 본문
        {"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-03"}},
    ),
}


# 조작마다 반복
@pytest.mark.parametrize(("path", "body"), RUN_CONTROLS.values(), ids=RUN_CONTROLS.keys())
# 기록이 못 받는 조작은 503 이고 아무것도 안 바꾸는지 검사
def test_a_control_the_log_cannot_take_is_503_and_changes_nothing(
    builder, clock, journal, path, body  # 준비물과 사례 이름들
):
    log = Breaker(journal)  # 쓰기를 막을 수 있는 대역 기록기
    client, service = session(  # 그 기록기로 회차를 시작해 1초 돌린다
        # 준비물과 입력원, 기록기, 초
        builder, clock, source=Script(None), experiment_log=log, seconds=1
    )
    before, conditions, written = (  # 요청 전 상태·조건·기록을 잡아 둔다
        client.get("/api/state").json(),  # 응답 본문
        service.conditions,  # 서비스 조건
        lines(journal),  # 기록 줄들
    )
    log.fail = DISK_FULL  # 이제부터 디스크 가득 오류로 실패하게
    response = client.post(path, json=body)  # 조작을 전송
    # 503 과 기록 불가 사유여야 함
    assert (response.status_code, response.json()) == (503, UNAVAILABLE)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert service.conditions == conditions  # 서비스 조건도 그대로여야 함
    assert lines(journal) == written  # 기록 줄도 그대로여야 함


@pytest.mark.parametrize(  # 정지와 초기화 두 경우로 반복
    # (주소, 기대 실행 상태)와 사례 이름
    ("path", "run_state"), [(STOP_URL, "stopped"), (RESET_URL, "idle")], ids=["stop", "reset"]
)
# 기록을 못 써도 정지·초기화는 적용되는지 검사
def test_stop_and_reset_apply_even_when_the_log_cannot_take_them(
    builder, clock, journal, caplog, path, run_state  # 준비물과 사례 이름들
):
    log = Breaker(journal)  # 쓰기를 막을 수 있는 대역 기록기
    client, _ = session(  # 그 기록기로 회차를 시작해 1초 돌린다
        # 준비물과 입력원, 기록기, 초
        builder, clock, source=Script(None), experiment_log=log, seconds=1
    )
    written = lines(journal)  # 기록 줄을 잡아 둔다
    log.fail = DISK_FULL  # 이제부터 디스크 가득 오류로 실패하게
    with caplog.at_level(logging.WARNING, logger="app.service"):  # 경고 로그를 붙잡음
        # 성공(200)이고 실행 상태가 기대와 같아야 함
        assert answer(client, path)["runState"] == run_state
    assert lines(journal) == written  # 기록 줄은 늘지 않아야 함
    assert [r.levelno for r in caplog.records] == [logging.WARNING]  # 경고 로그가 하나 남아야 함


# 기록이 못 받는 틱은 회차를 멈추는지 검사
def test_a_tick_the_log_cannot_take_stops_the_run(builder, clock, journal, caplog):
    from app.service import Outage

    log = Breaker(journal)  # 쓰기를 막을 수 있는 대역 기록기
    client, service = session(  # 그 기록기로 회차를 시작해 1초 돌린다
        # 준비물과 입력원, 기록기, 초
        builder, clock, source=Script(None), experiment_log=log, seconds=1
    )
    written = lines(journal)  # 기록 줄을 잡아 둔다
    log.fail = DISK_FULL  # 이제부터 디스크 가득 오류로 실패하게
    clock.jump(1.0)  # 시계를 1초 전송
    with caplog.at_level(logging.WARNING, logger="app.service"):  # 경고 로그를 붙잡음
        assert service.catchup() == 0  # 처리된 틱은 0 이어야 함
    body = client.get("/api/state").json()  # 상태를 읽음
    # 정지 상태, 마지막 정상 틱인 1초여야 함
    assert (body["runState"], body["elapsedSec"]) == ("stopped", 1)
    assert lines(journal) == written  # 기록 줄은 늘지 않아야 함
    # 틱 실패(ERROR) 하나, 그 event 도 못 썼다는 경고(WARNING) 하나
    assert [r.levelno for r in caplog.records] == [logging.ERROR, logging.WARNING]
    error = caplog.records[0].exc_info[1]  # 첫 로그에 붙은 예외를 꺼냄
    # Outage 이고 원인이 입출력 오류여야 함
    assert isinstance(error, Outage) and isinstance(error.__cause__, OSError)
