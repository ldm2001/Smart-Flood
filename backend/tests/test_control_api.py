import copy
import pytest
from app.core.model import Conditions
from app.core.predictor import ASSUMPTION_RULE
from tests.helpers import lapse

START = "/api/experiment/start"
STOP = "/api/experiment/stop"
RESET = "/api/experiment/reset"
DRY = {"A": 0, "B": 0, "C": 0}
DEFAULT_RAIN_OFF = {"state": "OFF", "intensity": "보통 강우", "mmPerHour": 60}
NO_BLOCKAGE = {"location": None, "type": "none", "label": "정상 배수"}


# 응답에서 구역별 수위를 뽑는 도우미
def levels(body: dict) -> dict:
    return {z: body["zones"][z]["levelMm"] for z in "ABC"}  # A·B·C 구역의 수위(mm)를 모음


# 응답에서 (회차 ID, 실행 상태, 경과 초)를 뽑는 도우미
def status(body: dict) -> tuple:
    return body["experimentId"], body["runState"], body["elapsedSec"]


@pytest.fixture(params=[False, True], ids=["idle", "running"])
# 대기 중이거나 2초째 돌고 있는 회차를 만드는 준비물
def scene(request, client, clock, service):
    if request.param:
        assert client.post(START, json={}).status_code == 200
        lapse(clock, service, 2)
    return client


INVALID_REQUESTS = {  # 422 가 나야 하는 잘못된 요청들. 이유를 돌려주고 아무것도 바꾸지 않음
    "rain-unknown-preset": ("/api/rain", {"intensity": "storm"}),
    "rain-both-fields": ("/api/rain", {"intensity": "light", "mmPerHour": 30}),
    "rain-no-field": ("/api/rain", {}),
    "rain-negative": ("/api/rain", {"mmPerHour": -1}),
    "rain-over-max": ("/api/rain", {"mmPerHour": 150.1}),
    "blockage-unknown-type": ("/api/blockage", {"type": "half", "location": "INLET-02"}),
    "blockage-partial-without-location": ("/api/blockage", {"type": "partial"}),
    "blockage-unknown-inlet": ("/api/blockage", {"type": "full", "location": "INLET-09"}),
    "blockage-none-unknown-inlet": ("/api/blockage", {"type": "none", "location": "INLET-09"}),
    "blockage-unknown-field": ("/api/blockage", {"type": "none", "inlet": "INLET-02"}),
    "source-replay-without-logId": ("/api/source", {"mode": "replay"}),
    "source-replay-unknown-log": ("/api/source", {"mode": "replay", "logId": "EXP-20261022-009"}),
    "source-replay-bad-id": ("/api/source", {"mode": "replay", "logId": "EXP-1"}),
    "source-unknown-mode": ("/api/source", {"mode": "file"}),
    "start-unknown-rain": (START, {"rain": "storm"}),
    "start-partial-without-location": (START, {"blockage": {"type": "partial"}}),
    "start-unknown-inlet": (START, {"blockage": {"type": "full", "location": "INLET-09"}}),
    "stop-unknown-field": (STOP, {"force": True}),
    "reset-unknown-field": (RESET, {"x": 1}),
}


@pytest.mark.parametrize(("path", "body"), INVALID_REQUESTS.values(), ids=INVALID_REQUESTS.keys())
# 잘못된 요청은 422 를 주고 아무것도 바꾸지 않는지 검사
def test_invalid_request_is_422_and_changes_nothing(scene, service, path, body):
    before, conditions = scene.get("/api/state").json(), service.conditions
    response = scene.post(path, json=body)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
    assert scene.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert service.conditions == conditions  # 조건도 그대로여야 함


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
# 유한하지 않은 비 세기는 422 인지 검사
def test_non_finite_rain_is_422(client, raw):
    response = client.post(  # JSON 규격 밖 숫자를 날것으로 전송
        "/api/rain",
        content=f'{{"mmPerHour": {raw}}}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


# 서비스 오류가 FastAPI 오류 모양을 쓰는지 검사
def test_service_errors_use_the_fastapi_error_shape(client):
    response = client.post("/api/blockage", json={"type": "full", "location": "INLET-09"})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "location"]  # 위치가 body → location 이어야 함
    assert error["type"] == "value_error"
    assert "INLET-09" in error["msg"]


# 비 최댓값이 설정에서 오는지 검사
def test_rain_limit_comes_from_config(builder, config):
    cfg = copy.deepcopy(config)
    cfg["rain_max_mm_per_h"] = 100
    client = builder(cfg)
    assert client.post("/api/rain", json={"mmPerHour": 100}).status_code == 200
    response = client.post("/api/rain", json={"mmPerHour": 100.5})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "mmPerHour"]



# 아직 없는 입력원(live)은 501 이고 상태를 안 바꾸는지 검사
def test_the_live_source_is_501_and_changes_nothing(client):
    before = client.get("/api/state").json()
    response = client.post("/api/source", json={"mode": "live"})
    assert response.status_code == 501
    assert isinstance(response.json()["detail"], str)
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함


# sim 입력원 요청은 그대로 유지하는지 검사
def test_sim_source_is_kept(client):
    before = client.get("/api/state").json()
    response = client.post("/api/source", json={"mode": "sim"})
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.json() == before


IDEMPOTENT_REQUESTS = {  # 같은 요청 두 번이 같은 상태를 주어야 하는 요청들 (멱등)
    "start-spec-example": (START, {"rain": "medium", "blockage": {"type": "none"}}),
    "start-with-blockage": (
        START,
        {"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}},
    ),
    "stop": (STOP, {}),
    "reset": (RESET, {}),
    "rain-preset": ("/api/rain", {"intensity": "light"}),
    "rain-value": ("/api/rain", {"mmPerHour": 75}),
    "blockage-full": ("/api/blockage", {"type": "full", "location": "INLET-03"}),
    "blockage-none": ("/api/blockage", {"type": "none"}),
    "source-sim": ("/api/source", {"mode": "sim"}),
}


@pytest.mark.parametrize(
    ("path", "body"), IDEMPOTENT_REQUESTS.values(), ids=IDEMPOTENT_REQUESTS.keys()
)
# 같은 요청을 두 번 보내면 같은 상태인지 검사
def test_same_request_twice_gives_the_same_state(scene, path, body):
    first = scene.post(path, json=body)
    second = scene.post(path, json=body)
    assert first.status_code == second.status_code == 200  # 둘 다 성공(200)이어야 함
    assert second.json() == first.json()
    assert scene.get("/api/state").json() == first.json()



# 시작 전 대기 상태 검사 (회차 수명)
def test_idle_state_before_any_start(client):
    body = client.get("/api/state").json()
    assert status(body) == ("EXP-STANDBY", "idle", 0)
    assert body["timestamp"] == "2026-10-22T10:00:00.000+09:00"
    assert body["rain"] == DEFAULT_RAIN_OFF
    assert body["blockage"] == NO_BLOCKAGE
    assert levels(body) == DRY  # 수위는 모두 0 이어야 함
    assert (body["mode"], body["dataSource"], body["outputsLocked"]) == ("live", "sim", True)


# 시작하면 ID 를 내주고 돌기 시작하는지 검사
def test_start_issues_an_id_and_runs(client):
    body = client.post(START, json={}).json()
    assert status(body) == ("EXP-20261022-001", "running", 0)
    assert body["rain"] == {"state": "ON", "intensity": "보통 강우", "mmPerHour": 60}


# 돌고 있을 때 다시 시작하면 회차는 유지하고 본문만 적용하는지 검사
def test_start_while_running_keeps_the_run_and_applies_the_body(client, clock, service):
    client.post(START, json={})
    lapse(clock, service, 5)
    body = client.post(START, json={"rain": "heavy"}).json()
    assert (body["experimentId"], body["elapsedSec"]) == ("EXP-20261022-001", 5)
    assert body["rain"]["mmPerHour"] == 90
    assert service.conditions == Conditions(90.0, {})


# 정지하면 회차가 멈춰 굳는지 검사
def test_stop_freezes_the_run(client, clock, service):
    client.post(START, json={})
    lapse(clock, service, 5)
    stopped = client.post(STOP, json={}).json()
    assert status(stopped) == ("EXP-20261022-001", "stopped", 5)
    assert stopped["rain"]["state"] == "OFF"
    frozen = service.state
    lapse(clock, service, 5)
    assert client.get("/api/state").json() == stopped
    assert service.state == frozen


# 시작·정지·초기화가 본문 없이도 되는지 검사
def test_start_stop_and_reset_need_no_body(client):
    assert client.post(START).json()["runState"] == "running"  # 본문 없이 시작하면 실행 중이어야 함
    assert client.post(STOP).status_code == 200
    assert client.post(RESET).status_code == 200
    assert client.get("/api/state").json()["runState"] == "idle"


# 정지 뒤 시작하면 마른 새 회차를 시작하는지 검사
def test_start_after_stop_begins_a_new_dry_run(client, clock, service):
    client.post("/api/rain", json={"intensity": "heavy"})
    client.post(START, json={})
    lapse(clock, service, 25)
    client.post(STOP, json={})
    lapse(clock, service, 5)
    body = client.post(START, json={}).json()
    assert status(body) == ("EXP-20261022-002", "running", 0)
    assert body["timestamp"] == "2026-10-22T10:00:30.000+09:00"
    assert levels(body) == DRY  # 수위는 모두 0 이어야 함
    assert body["drain"] == {"volumeL": 0, "flowLMin": 0}
    assert body["rain"]["mmPerHour"] == 90


# 초기화하면 기본 선택으로 대기 상태에 돌아가는지 검사
def test_reset_returns_to_standby_with_the_default_selection(client, clock, service):
    client.post(START, json={"rain": "heavy", "blockage": {"type": "full", "location": "INLET-02"}})
    lapse(clock, service, 10)
    body = client.post(RESET, json={}).json()
    assert status(body) == ("EXP-STANDBY", "idle", 0)
    assert body["timestamp"] == "2026-10-22T10:00:10.000+09:00"
    assert body["rain"] == DEFAULT_RAIN_OFF
    assert body["blockage"] == NO_BLOCKAGE
    assert levels(body) == DRY  # 수위는 모두 0 이어야 함
    assert service.conditions == Conditions()
    assert client.post(START, json={}).json()["experimentId"] == "EXP-20261022-002"


# 대기 중 초기화는 선택값만 되돌리는지 검사
def test_reset_while_idle_only_restores_the_selection(client, clock):
    before = client.get("/api/state").json()
    client.post("/api/rain", json={"intensity": "heavy"})
    client.post("/api/blockage", json={"type": "full", "location": "INLET-03"})
    clock.jump(5.0)
    assert client.post(RESET, json={}).json() == before  # 초기화하면 처음 상태와 같아야 함



# 대기 중에 고른 비·막힘이 시작할 때 적용되는지 검사
def test_selection_made_while_idle_applies_at_start(client, service):
    body = client.post("/api/rain", json={"intensity": "heavy"}).json()
    assert body["runState"] == "idle"
    assert body["rain"] == {"state": "OFF", "intensity": "강한 강우", "mmPerHour": 90}
    client.post("/api/blockage", json={"type": "full", "location": "INLET-03"})
    assert service.conditions == Conditions(0.0, {"INLET-03": "full"})
    assert client.post(START, json={}).json()["rain"]["state"] == "ON"  # 시작하면 비가 켜짐
    assert service.conditions == Conditions(90.0, {"INLET-03": "full"})


# 정지 중에 고른 값이 다음 시작 때 적용되는지 검사
def test_selection_made_while_stopped_applies_at_the_next_start(client, clock, service):
    client.post(START, json={})
    lapse(clock, service, 3)
    client.post(STOP, json={})
    body = client.post("/api/rain", json={"intensity": "light"}).json()
    assert body["runState"] == "stopped"
    assert body["rain"] == {"state": "OFF", "intensity": "약한 강우", "mmPerHour": 30}
    body = client.post(START, json={}).json()
    assert body["rain"] == {"state": "ON", "intensity": "약한 강우", "mmPerHour": 30}


RAIN_LABELS = [  # 비 세기 표시 문구 사례들 (요청 본문, 문구, mm/h)
    ({"intensity": "light"}, "약한 강우", 30),
    ({"intensity": "medium"}, "보통 강우", 60),
    ({"intensity": "heavy"}, "강한 강우", 90),
    ({"mmPerHour": 60}, "보통 강우", 60),
    ({"mmPerHour": 75}, "직접 입력 75 mm/h", 75),
    ({"mmPerHour": 12.5}, "직접 입력 12.5 mm/h", 12.5),
    ({"mmPerHour": 150}, "직접 입력 150 mm/h", 150),
]


@pytest.mark.parametrize(("body", "label", "mm"), RAIN_LABELS)
# 비 세기 표시 문구 검사
def test_rain_labels(client, body, label, mm):
    client.post(START, json={})
    rain = client.post("/api/rain", json=body).json()["rain"]
    assert rain == {"state": "ON", "intensity": label, "mmPerHour": mm}


# 돌고 있을 때 비 0 은 꺼짐인지 검사
def test_zero_rain_while_running_is_off(client):
    client.post(START, json={})
    rain = client.post("/api/rain", json={"mmPerHour": 0}).json()["rain"]
    assert rain == {"state": "OFF", "intensity": "강우 없음", "mmPerHour": 0}


BLOCKAGE_LABELS = [  # 막힘 표시 문구 사례들 (요청 본문, 위치, 문구)
    ({"type": "partial", "location": "INLET-02"}, "INLET-02", "빗물받이 ② 부분 막힘"),
    ({"type": "full", "location": "INLET-03"}, "INLET-03", "빗물받이 ③ 완전 막힘"),
    ({"type": "none"}, None, "정상 배수"),
    ({"type": "none", "location": "INLET-02"}, None, "정상 배수"),  # 막힘 없음이면 위치는 무시
]


@pytest.mark.parametrize(("body", "location", "label"), BLOCKAGE_LABELS)
# 막힘 표시 문구 검사
def test_blockage_labels(client, body, location, label):
    blockage = client.post("/api/blockage", json=body).json()["blockage"]
    assert blockage == {"location": location, "type": body["type"], "label": label}


# 새 막힘이 이전 막힘을 대체하는지 검사
def test_a_new_blockage_replaces_the_previous_one(client, service):
    client.post("/api/blockage", json={"type": "partial", "location": "INLET-02"})
    body = client.post("/api/blockage", json={"type": "full", "location": "INLET-03"}).json()
    assert service.conditions.blockage == {"INLET-03": "full"}
    assert body["predictionMeta"]["assumptions"]["blockage"] == {"INLET-03": "full"}
    client.post("/api/blockage", json={"type": "none"})
    assert service.conditions.blockage == {}


# 예측 메타가 기준과 가정을 밝히는지 검사
def test_prediction_meta_states_basis_and_assumptions(client):
    body = client.post(  # 강한 비와 2번 부분 막힘으로 시작
        START, json={"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}}
    ).json()
    assert body["predictionMeta"] == {
        "basisTime": "2026-10-22T10:00:00.000+09:00",
        "basisElapsedSec": 0,
        "validForSec": 5,  # 유효 시간(초)
        "modelVersion": "0.1-assumed",
        "assumptions": {
            "rule": ASSUMPTION_RULE,
            "rainMmPerHour": 90,
            "blockage": {"INLET-02": "partial"},
        },
    }
    stopped = client.post(STOP, json={}).json()
    assert stopped["predictionMeta"]["assumptions"]["rainMmPerHour"] == 0
