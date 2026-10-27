import json
import os
import pytest
import subprocess
import sys
from app.core.model import ZONES
from app.schemas import M3_TO_L
from pathlib import Path
from tests.helpers import digests, echo, footage, lapse, revision

ID = "EXP-20261022-001"
BACKEND = Path(__file__).resolve().parents[1]  # backend 폴더 경로(새 프로세스의 작업 위치)

SCENARIO = (  # (조작 주소, 요청 본문, 뒤에 돌릴 초) 목록. 강우·막힘을 거쳐 60 틱
    ("/api/experiment/start", {"rain": "medium"}, 10),
    ("/api/rain", {"intensity": "heavy"}, 10),
    ("/api/blockage", {"type": "partial", "location": "INLET-01"}, 10),
    ("/api/rain", {"mmPerHour": 120}, 5),
    ("/api/blockage", {"type": "full", "location": "INLET-02"}, 10),
    ("/api/rain", {"mmPerHour": 0}, 15),
    ("/api/experiment/stop", {}, 0),
)
TICKS = 60
MODEL_KEYS = ("volumesL", "correctionTotalL", "rainTotalL", "drainedL")


@pytest.fixture
# 시나리오를 돌려 기록 ID 를 남기고 멈춘 클라이언트를 내줌
def session(builder, clock):
    client = builder()
    for path, body, seconds in SCENARIO:
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        lapse(clock, client.app.state.service, seconds)
    return client



# 같은 앱·새 앱에서 두 번 재생해도 틱마다 같은 바이트인지 검사
def test_two_replays_give_the_same_bytes_tick_by_tick(session, builder, clock):
    first = digests(footage(session, clock, ID))
    assert len(first) == TICKS + 2  # 0 초, 틱마다 하나, 기록 끝에서 멈춘 상태까지 틱 수 + 2 개
    assert digests(footage(session, clock, ID)) == first
    assert digests(footage(builder(), clock, ID)) == first


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
    result = subprocess.run(
        [sys.executable, "-c", REPLAY_IN_A_NEW_PROCESS, str(log_dir), ID],
        cwd=BACKEND,
        env={**os.environ, "PYTHONHASHSEED": hash_seed, "TZ": tz},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])  # 마지막 출력 줄(JSON 해시 목록)을 읽어 반환


# 해시 시드·시간대가 달라도 새 프로세스 재생이 같은지 검사
def test_replays_in_new_processes_give_the_same_bytes(session, clock, journal):
    here = digests(footage(session, clock, ID))
    for hash_seed, tz in (("1", "UTC"), ("2", "America/Los_Angeles")):
        assert isolation(journal.directory, hash_seed, tz) == here



# state 줄의 model 누적 값을 만드는 함수. 틱별 보정 내역은 제외
def totals(state) -> dict:
    return {
        "volumesL": {z: state.V[z] * M3_TO_L for z in ZONES},  # 구역별 저장량(L)
        "correctionTotalL": state.correction_m3 * M3_TO_L,  # 보정 합계(L)
        "rainTotalL": state.rain_m3 * M3_TO_L,  # 강우 합계(L)
        "drainedL": {i: v * M3_TO_L for i, v in state.drained_m3.items()},
    }


# 재생이 원래 회차를 다시 내는지 검사. 응답은 입력원 표시만 다름
def test_the_replay_gives_back_the_recorded_run(session, clock, journal):
    service = session.app.state.service
    records = [r for r in journal.records(ID) if r["type"] == "state"]
    assert len(records) == TICKS
    response = session.post("/api/source", json={"mode": "replay", "logId": ID})
    assert response.status_code == 200, response.text
    for record in records:
        lapse(clock, service, 1)
        assert session.get("/api/state").json() == echo(record["state"])
        assert totals(service.state) == {k: record["model"][k] for k in MODEL_KEYS}



# state 줄마다 다른 틱의 state·model 을 거꾸로 싣는 편집. 종류·경과 초는 그대로
def jumble(records: list[dict]) -> list[dict]:
    donors = iter([r for r in records if r["type"] == "state"][::-1])

    # 레코드 하나를 바꾸는 안쪽 함수
    def trade(record: dict) -> dict:
        donor = next(donors)
        return {**record, "state": donor["state"], "model": donor["model"]}

    return [trade(r) if r["type"] == "state" else r for r in records]


# 저장된 state 줄은 재생에 쓰이지 않음을 검사
def test_stored_states_play_no_part_in_the_replay(session, clock, journal):
    before = digests(footage(session, clock, ID))
    revision(journal, jumble, ID)  # 기록의 state 줄을 뒤섞음
    assert digests(footage(session, clock, ID)) == before  # 재생 해시가 그대로여야 함



# 경과 초에 기록된 kind 줄의 자리를 구하는 함수
def slot(records: list[dict], kind: str, elapsed_s: int) -> int:
    [index] = [
        i for i, r in enumerate(records) if r["type"] == kind and r["elapsedSec"] == elapsed_s
    ]
    return index


# 경과 초의 kind 줄을 change 로 바꾸는 편집을 만드는 함수
def patch(kind: str, elapsed_s: int, change):
    # 기록 목록을 받아 바꿔 돌려주는 편집
    def alteration(records: list[dict]) -> list[dict]:
        index = slot(records, kind, elapsed_s)
        return [*records[:index], change(records[index]), *records[index + 1 :]]

    return alteration


# A 거리를 30 mm 줄인 관측. A 수위가 30 mm 오르거나 범위를 드나듦
def approach(obs: dict) -> dict:
    raw = obs["raw"]
    readings = {**raw["readings"], "distA_mm": raw["readings"]["distA_mm"] - 30}
    return {**obs, "raw": {**raw, "readings": readings}}


CHANGED_INPUTS = {  # 바꿀 입력 → (편집, 영향 받는 틱) 목록
    "obs": (patch("obs", 30, approach), 30),
    "cmd": (patch("cmd", 10, lambda cmd: {**cmd, "rainMmPerHour": 30.0}), 11),
}


@pytest.mark.parametrize(("edit", "tick"), CHANGED_INPUTS.values(), ids=CHANGED_INPUTS.keys())
# 바뀐 입력은 그 틱에서 재생을 바꾸고 앞 틱은 그대로인지 검사
def test_a_changed_input_changes_the_replay_at_its_tick_and_not_before(
    session, clock, journal, edit, tick
):
    before = digests(footage(session, clock, ID))
    revision(journal, edit, ID)
    after = digests(footage(session, clock, ID))
    assert after[:tick] == before[:tick]  # 그 틱 앞까지는 같아야 함(미래 정보 없음)
    assert after[tick] != before[tick]



# 끊긴 기록도 마지막 state 줄까지 같게 재생되는지 검사
def test_a_log_cut_off_partway_replays_the_same_up_to_its_last_state(
    session, clock, journal
):
    whole = digests(footage(session, clock, ID))
    revision(journal, lambda records: records[: slot(records, "state", 25) + 1], ID)
    cut = footage(session, clock, ID)
    assert len(cut) == 27  # 0 초부터 25 초까지 26 개 + 끝 상태 1 개 = 27 개
    assert digests(cut[:26]) == whole[:26]
    ended = json.loads(cut[26])  # 마지막 바이트(끝 상태)를 JSON 으로 읽음
    assert (ended["runState"], ended["elapsedSec"]) == ("stopped", 25)
