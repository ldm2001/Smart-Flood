import json
import os
import pytest
import subprocess
import sys
from app.core.model import ZONES
from app.schemas import M3_TO_L
from pathlib import Path
from tests.helpers import digests, echo, footage, lapse, revision

ID = "EXP-20261022-001"  # 시험용 회차 ID
BACKEND = Path(__file__).resolve().parents[1]  # backend 폴더 경로(새 프로세스의 작업 위치)

SCENARIO = (  # (조작 주소, 요청 본문, 뒤에 돌릴 초) 목록. 강우·막힘을 거쳐 60 틱
    ("/api/experiment/start", {"rain": "medium"}, 10),  # 실험 시작, 보통 비, 10초
    ("/api/rain", {"intensity": "heavy"}, 10),  # 비를 강하게, 10초
    # 1번 빗물받이 일부 막힘, 10초
    ("/api/blockage", {"type": "partial", "location": "INLET-01"}, 10),
    ("/api/rain", {"mmPerHour": 120}, 5),  # 비를 120 mm/h 로, 5초
    ("/api/blockage", {"type": "full", "location": "INLET-02"}, 10),  # 2번 빗물받이 완전 막힘, 10초
    ("/api/rain", {"mmPerHour": 0}, 15),  # 비 끄기, 15초
    ("/api/experiment/stop", {}, 0),  # 실험 종료
)
TICKS = 60  # 기록되는 틱 수
# 모델 줄에서 비교할 누적 값 이름들
MODEL_KEYS = ("volumesL", "correctionTotalL", "rainTotalL", "drainedL")


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 시나리오를 돌려 기록 ID 를 남기고 멈춘 클라이언트를 내반환
def session(builder, clock):
    client = builder()  # 앱을 띄운 클라이언트
    for path, body, seconds in SCENARIO:  # 시나리오 항목을 차례로 실행
        response = client.post(path, json=body)  # 조작 요청을 전송
        assert response.status_code == 200, response.text  # 요청이 성공 필요
        lapse(clock, client.app.state.service, seconds)  # 조작 뒤에 정해진 초만큼 틱을 돌린다
    return client  # 클라이언트를 반환



# 같은 앱·새 앱에서 두 번 재생해도 틱마다 같은 바이트인지 검사
def test_two_replays_give_the_same_bytes_tick_by_tick(session, builder, clock):
    first = digests(footage(session, clock, ID))  # 한 번 재생해 틱별 해시를 구
    assert len(first) == TICKS + 2  # 0 초, 틱마다 하나, 기록 끝에서 멈춘 상태까지 틱 수 + 2 개
    assert digests(footage(session, clock, ID)) == first  # 같은 앱에서 다시 재생해도 같아야 함
    assert digests(footage(builder(), clock, ID)) == first  # 새 앱에서 재생해도 같아야 함


# 새 프로세스에서 실행할 재생 스크립트(문자열)
REPLAY_IN_A_NEW_PROCESS = """
import json, sys
from fastapi.testclient import TestClient
from app.adapters.clock import Fake
from app.adapters.jsonl_log import Jsonl
from app.main import factory
from tests.helpers import START, digests, footage

clock = Fake(START)
log = Jsonl(sys.argv[1])
app = factory(clock=clock, experiment_log=log, start_ticker=False, static_dir=None)
with TestClient(app) as client:
    print(json.dumps(digests(footage(client, clock, sys.argv[2]))))
"""


# 새 프로세스에서 재생한 틱별 해시를 구하는 함수. 시계는 기록과 다른 시각에서 시작
def isolation(log_dir: Path, hash_seed: str, tz: str) -> list[str]:
    result = subprocess.run(  # 파이썬을 새 프로세스로 실행
        # 명령: 위 스크립트에 기록 폴더와 ID 를 넘긴다
        [sys.executable, "-c", REPLAY_IN_A_NEW_PROCESS, str(log_dir), ID],
        cwd=BACKEND,  # backend 폴더에서 실행
        # 집합 순서(해시 시드)와 시간대를 바꾼 환경 변수
        env={**os.environ, "PYTHONHASHSEED": hash_seed, "TZ": tz},
        capture_output=True,  # 출력을 붙잡음
        text=True,  # 글자로 받음
        timeout=60,  # 60 초 안에 끝나야 함
    )
    assert result.returncode == 0, result.stderr  # 정상 종료여야 한다. 아니면 오류 출력을 보인다
    return json.loads(result.stdout.splitlines()[-1])  # 마지막 출력 줄(JSON 해시 목록)을 읽어 반환


# 해시 시드·시간대가 달라도 새 프로세스 재생이 같은지 검사
def test_replays_in_new_processes_give_the_same_bytes(session, clock, journal):
    here = digests(footage(session, clock, ID))  # 현재 프로세스의 재생 해시
    # 시드 1·2 는 집합을 도는 순서가 다르고 시간대도 다르다
    for hash_seed, tz in (("1", "UTC"), ("2", "America/Los_Angeles")):
        # 순서나 시간대에 기대면 갈라진다. 같아야 함
        assert isolation(journal.directory, hash_seed, tz) == here



# state 줄의 model 누적 값을 만드는 함수. 틱별 보정 내역은 제외
def totals(state) -> dict:
    return {  # 누적 값 묶음을 반환
        "volumesL": {z: state.V[z] * M3_TO_L for z in ZONES},  # 구역별 저장량(L)
        "correctionTotalL": state.correction_m3 * M3_TO_L,  # 보정 합계(L)
        "rainTotalL": state.rain_m3 * M3_TO_L,  # 강우 합계(L)
        # 배수 합계(L), 빗물받이별
        "drainedL": {i: v * M3_TO_L for i, v in state.drained_m3.items()},
    }


# 재생이 원래 회차를 다시 내는지 검사. 응답은 입력원 표시만 다르다
def test_the_replay_gives_back_the_recorded_run(session, clock, journal):
    service = session.app.state.service  # 앱 안의 서비스를 꺼냄
    records = [r for r in journal.records(ID) if r["type"] == "state"]  # 기록의 state 레코드만 모음
    assert len(records) == TICKS  # 틱 수만큼 있어야 함
    # 입력원을 이 기록의 재생으로 변환
    response = session.post("/api/source", json={"mode": "replay", "logId": ID})
    assert response.status_code == 200, response.text  # 요청이 성공 필요
    for record in records:  # 레코드마다 한 틱씩 반복
        lapse(clock, service, 1)  # 시계를 1초 전송
        # 응답이 원래 상태에서 입력원 표시만 바꾼 것과 같아야 함
        assert session.get("/api/state").json() == echo(record["state"])
        # 모델 누적 값이 기록의 model 줄과 같아야 함
        assert totals(service.state) == {k: record["model"][k] for k in MODEL_KEYS}



# state 줄마다 다른 틱의 state·model 을 거꾸로 싣는 편집. 종류·경과 초는 그대로
def jumble(records: list[dict]) -> list[dict]:
    # state 레코드를 거꾸로 뽑아 줄 기증자 목록
    donors = iter([r for r in records if r["type"] == "state"][::-1])

    # 레코드 하나를 바꾸는 안쪽 함수
    def trade(record: dict) -> dict:
        donor = next(donors)  # 다음 기증자를 꺼냄
        # state 와 model 만 기증자 것으로 변환
        return {**record, "state": donor["state"], "model": donor["model"]}

    # state 줄만 바꾸고 나머지는 그대로 둔다
    return [trade(r) if r["type"] == "state" else r for r in records]


# 저장된 state 줄은 재생에 쓰이지 않음을 검사
def test_stored_states_play_no_part_in_the_replay(session, clock, journal):
    before = digests(footage(session, clock, ID))  # 원본 재생 해시
    revision(journal, jumble, ID)  # 기록의 state 줄을 뒤섞는다
    assert digests(footage(session, clock, ID)) == before  # 재생 해시가 그대로여야 함



# 경과 초에 기록된 kind 줄의 자리를 구하는 함수
def slot(records: list[dict], kind: str, elapsed_s: int) -> int:
    [index] = [  # 조건에 맞는 줄이 정확히 하나 있어야 함
        # 종류와 경과 초가 맞는 줄의 자리를 모음
        i for i, r in enumerate(records) if r["type"] == kind and r["elapsedSec"] == elapsed_s
    ]
    return index  # 그 자리를 반환


# 경과 초의 kind 줄을 change 로 바꾸는 편집을 만드는 함수
def patch(kind: str, elapsed_s: int, change):
    # 기록 목록을 받아 바꿔 돌려주는 편집
    def alteration(records: list[dict]) -> list[dict]:
        index = slot(records, kind, elapsed_s)  # 바꿀 줄의 자리를 찾음
        # 그 줄만 change 로 바꾼 새 목록
        return [*records[:index], change(records[index]), *records[index + 1 :]]

    return alteration  # 편집 함수를 반환


# A 거리를 30 mm 줄인 관측. A 수위가 30 mm 오르거나 범위를 드나든다
def approach(obs: dict) -> dict:
    raw = obs["raw"]  # 관측의 원본 값
    # A 거리만 30 mm 줄인다
    readings = {**raw["readings"], "distA_mm": raw["readings"]["distA_mm"] - 30}
    return {**obs, "raw": {**raw, "readings": readings}}  # 바뀐 원본 값으로 관측을 다시 만듦


CHANGED_INPUTS = {  # 바꿀 입력 → (편집, 영향 받는 틱) 목록
    "obs": (patch("obs", 30, approach), 30),  # 30 초 틱이 읽은 관측을 변환
    # 10 초에 바꾼 강우를 30 mm/h 로(조작은 다음 틱부터 걸린다)
    "cmd": (patch("cmd", 10, lambda cmd: {**cmd, "rainMmPerHour": 30.0}), 11),
}


# 편집 종류마다 반복
@pytest.mark.parametrize(("edit", "tick"), CHANGED_INPUTS.values(), ids=CHANGED_INPUTS.keys())
# 바뀐 입력은 그 틱에서 재생을 바꾸고 앞 틱은 그대로인지 검사
def test_a_changed_input_changes_the_replay_at_its_tick_and_not_before(
    session, clock, journal, edit, tick  # 준비물과 편집, 달라질 틱
):
    before = digests(footage(session, clock, ID))  # 원본 재생 해시
    revision(journal, edit, ID)  # 기록을 편집
    after = digests(footage(session, clock, ID))  # 편집한 기록의 재생 해시
    assert after[:tick] == before[:tick]  # 그 틱 앞까지는 같아야 한다(미래 정보 없음)
    assert after[tick] != before[tick]  # 그 틱부터는 달라야 함



# 끊긴 기록도 마지막 state 줄까지 같게 재생되는지 검사
def test_a_log_cut_off_partway_replays_the_same_up_to_its_last_state(
    session, clock, journal  # 준비물
):
    whole = digests(footage(session, clock, ID))  # 온전한 기록의 재생 해시
    # 25 초 state 줄 뒤를 잘라 냄
    revision(journal, lambda records: records[: slot(records, "state", 25) + 1], ID)
    cut = footage(session, clock, ID)  # 끊긴 기록을 재생
    assert len(cut) == 27  # 0 초부터 25 초까지 26 개 + 끝 상태 1 개 = 27 개
    assert digests(cut[:26]) == whole[:26]  # 남은 줄까지는 같은 바이트여야 함
    ended = json.loads(cut[26])  # 마지막 바이트(끝 상태)를 JSON 으로 읽음
    # 정지 상태이고 경과 25 초에서 멈춰야 함
    assert (ended["runState"], ended["elapsedSec"]) == ("stopped", 25)
