import copy
import pytest
from app.core.model import Conditions
from app.core.predictor import ASSUMPTION_RULE
from tests.helpers import lapse

START = "/api/experiment/start"  # 실험 시작 주소
STOP = "/api/experiment/stop"  # 실험 정지 주소
RESET = "/api/experiment/reset"  # 실험 초기화 주소
DRY = {"A": 0, "B": 0, "C": 0}  # 세 구역 수위가 모두 0
# 비가 꺼진 기본 표시
DEFAULT_RAIN_OFF = {"state": "OFF", "intensity": "보통 강우", "mmPerHour": 60}
NO_BLOCKAGE = {"location": None, "type": "none", "label": "정상 배수"}  # 막힘 없는 기본 표시


# 응답에서 구역별 수위를 뽑는 도우미
def levels(body: dict) -> dict:
    return {z: body["zones"][z]["levelMm"] for z in "ABC"}  # A·B·C 구역의 수위(mm)를 모음


# 응답에서 (회차 ID, 실행 상태, 경과 초)를 뽑는 도우미
def status(body: dict) -> tuple:
    return body["experimentId"], body["runState"], body["elapsedSec"]  # 세 값을 묶어 반환


# 대기 중 또는 실행 중인 두 경우로 되풀이하는 준비물
@pytest.fixture(params=[False, True], ids=["idle", "running"])
# 대기 중이거나 2초째 돌고 있는 회차를 만드는 준비물
def scene(request, client, clock, service):
    if request.param:  # 실행 중 경우면
        assert client.post(START, json={}).status_code == 200  # 실험을 시작
        lapse(clock, service, 2)  # 2초를 전송
    return client  # 클라이언트를 반환


INVALID_REQUESTS = {  # 422 가 나야 하는 잘못된 요청들. 이유를 돌려주고 아무것도 바꾸지 않음
    "rain-unknown-preset": ("/api/rain", {"intensity": "storm"}),  # 모르는 비 세기 이름
    # 이름과 값을 같이 줬다
    "rain-both-fields": ("/api/rain", {"intensity": "light", "mmPerHour": 30}),
    "rain-no-field": ("/api/rain", {}),  # 아무 필드도 없다
    "rain-negative": ("/api/rain", {"mmPerHour": -1}),  # 음수 비 세기
    "rain-over-max": ("/api/rain", {"mmPerHour": 150.1}),  # 비 최댓값 초과
    # 모르는 막힘 종류
    "blockage-unknown-type": ("/api/blockage", {"type": "half", "location": "INLET-02"}),
    # 부분 막힘인데 위치가 없다
    "blockage-partial-without-location": ("/api/blockage", {"type": "partial"}),
    # 모르는 빗물받이
    "blockage-unknown-inlet": ("/api/blockage", {"type": "full", "location": "INLET-09"}),
    # 막힘 없음인데 모르는 빗물받이
    "blockage-none-unknown-inlet": ("/api/blockage", {"type": "none", "location": "INLET-09"}),
    # 모르는 필드
    "blockage-unknown-field": ("/api/blockage", {"type": "none", "inlet": "INLET-02"}),
    "source-replay-without-logId": ("/api/source", {"mode": "replay"}),  # 재생인데 기록 ID 가 없다
    # 재생인데 없는 기록
    "source-replay-unknown-log": ("/api/source", {"mode": "replay", "logId": "EXP-20261022-009"}),
    # 재생인데 ID 모양이 틀리다
    "source-replay-bad-id": ("/api/source", {"mode": "replay", "logId": "EXP-1"}),
    "source-unknown-mode": ("/api/source", {"mode": "file"}),  # 모르는 입력원 모드
    "start-unknown-rain": (START, {"rain": "storm"}),  # 시작 요청에 모르는 비 세기
    # 시작 요청에 위치 없는 부분 막힘
    "start-partial-without-location": (START, {"blockage": {"type": "partial"}}),
    # 시작 요청에 모르는 빗물받이
    "start-unknown-inlet": (START, {"blockage": {"type": "full", "location": "INLET-09"}}),
    "stop-unknown-field": (STOP, {"force": True}),  # 정지 요청에 모르는 필드
    "reset-unknown-field": (RESET, {"x": 1}),  # 초기화 요청에 모르는 필드
}


# 요청마다 반복
@pytest.mark.parametrize(("path", "body"), INVALID_REQUESTS.values(), ids=INVALID_REQUESTS.keys())
# 잘못된 요청은 422 를 주고 아무것도 바꾸지 않는지 검사
def test_invalid_request_is_422_and_changes_nothing(scene, service, path, body):
    # 요청 전 상태와 조건을 잡아 둔다
    before, conditions = scene.get("/api/state").json(), service.conditions
    response = scene.post(path, json=body)  # 잘못된 요청을 전송
    assert response.status_code == 422, response.text  # 422 여야 함
    assert response.json()["detail"]  # 이유가 담겨야 함
    assert scene.get("/api/state").json() == before  # 상태가 그대로여야 함
    assert service.conditions == conditions  # 조건도 그대로여야 함


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])  # NaN·무한대 글자로 반복
# 유한하지 않은 비 세기는 422 인지 검사
def test_non_finite_rain_is_422(client, raw):
    response = client.post(  # JSON 규격 밖 숫자를 날것으로 전송
        "/api/rain",  # 비 주소로
        content=f'{{"mmPerHour": {raw}}}',  # 본문은 직접 쓴 글자
        headers={"Content-Type": "application/json"},  # JSON 내용 종류를 붙임
    )
    assert response.status_code == 422  # 422 여야 함


# 서비스 오류가 FastAPI 오류 모양을 쓰는지 검사
def test_service_errors_use_the_fastapi_error_shape(client):
    # 없는 빗물받이로 막힘을 요청
    response = client.post("/api/blockage", json={"type": "full", "location": "INLET-09"})
    assert response.status_code == 422  # 422 여야 함
    [error] = response.json()["detail"]  # 오류 하나를 꺼냄
    assert error["loc"] == ["body", "location"]  # 위치가 body → location 이어야 함
    assert error["type"] == "value_error"  # 종류는 value_error 여야 함
    assert "INLET-09" in error["msg"]  # 메시지에 문제의 빗물받이 이름이 있어야 함


# 비 최댓값이 설정에서 오는지 검사
def test_rain_limit_comes_from_config(builder, config):
    cfg = copy.deepcopy(config)  # 설정을 복사
    cfg["rain_max_mm_per_h"] = 100  # 최댓값을 100 으로 변환
    client = builder(cfg)  # 그 설정으로 앱을 만듦
    assert client.post("/api/rain", json={"mmPerHour": 100}).status_code == 200  # 100 은 받아야 함
    response = client.post("/api/rain", json={"mmPerHour": 100.5})  # 100.5 를 전송
    assert response.status_code == 422  # 422 여야 함
    # 위치가 body → mmPerHour 여야 함
    assert response.json()["detail"][0]["loc"] == ["body", "mmPerHour"]



# 아직 없는 입력원(live)은 501 이고 상태를 안 바꾸는지 검사
def test_the_live_source_is_501_and_changes_nothing(client):
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다
    response = client.post("/api/source", json={"mode": "live"})  # live 모드를 요청
    assert response.status_code == 501  # 501 이어야 함
    assert isinstance(response.json()["detail"], str)  # 사유가 글자여야 함
    assert client.get("/api/state").json() == before  # 상태가 그대로여야 함


# sim 입력원 요청은 그대로 유지하는지 검사
def test_sim_source_is_kept(client):
    before = client.get("/api/state").json()  # 요청 전 상태를 잡아 둔다
    response = client.post("/api/source", json={"mode": "sim"})  # sim 모드를 요청
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.json() == before  # 응답이 요청 전 상태와 같아야 함


IDEMPOTENT_REQUESTS = {  # 같은 요청 두 번이 같은 상태를 주어야 하는 요청들 (멱등)
    # 지시서 예시 시작
    "start-spec-example": (START, {"rain": "medium", "blockage": {"type": "none"}}),
    "start-with-blockage": (  # 막힘이 있는 시작
        START,  # 시작 주소
        # 강한 비와 부분 막힘 본문
        {"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}},
    ),
    "stop": (STOP, {}),  # 정지
    "reset": (RESET, {}),  # 초기화
    "rain-preset": ("/api/rain", {"intensity": "light"}),  # 비 세기 이름
    "rain-value": ("/api/rain", {"mmPerHour": 75}),  # 비 세기 값
    "blockage-full": ("/api/blockage", {"type": "full", "location": "INLET-03"}),  # 완전 막힘
    "blockage-none": ("/api/blockage", {"type": "none"}),  # 막힘 없음
    "source-sim": ("/api/source", {"mode": "sim"}),  # 입력원 sim
}


@pytest.mark.parametrize(  # 요청마다 반복
    # (주소, 본문) 이름
    ("path", "body"), IDEMPOTENT_REQUESTS.values(), ids=IDEMPOTENT_REQUESTS.keys()
)
# 같은 요청을 두 번 보내면 같은 상태인지 검사
def test_same_request_twice_gives_the_same_state(scene, path, body):
    first = scene.post(path, json=body)  # 첫 요청을 전송
    second = scene.post(path, json=body)  # 같은 요청을 한 번 더 전송
    assert first.status_code == second.status_code == 200  # 둘 다 성공(200)이어야 함
    assert second.json() == first.json()  # 두 응답이 같아야 함
    assert scene.get("/api/state").json() == first.json()  # 지금 상태도 그 응답과 같아야 함



# 시작 전 대기 상태 검사 (회차 수명)
def test_idle_state_before_any_start(client):
    body = client.get("/api/state").json()  # 상태를 읽음
    assert status(body) == ("EXP-STANDBY", "idle", 0)  # ID 는 대기용, 실행 상태는 idle, 경과는 0
    assert body["timestamp"] == "2026-10-22T10:00:00.000+09:00"  # 시각은 기준 시각이어야 함
    assert body["rain"] == DEFAULT_RAIN_OFF  # 비는 꺼진 기본 표시여야 함
    assert body["blockage"] == NO_BLOCKAGE  # 막힘은 없음이어야 함
    assert levels(body) == DRY  # 수위는 모두 0 이어야 함
    # 모드 live, 입력원 sim, 출력 잠김 true 여야 함
    assert (body["mode"], body["dataSource"], body["outputsLocked"]) == ("live", "sim", True)


# 시작하면 ID 를 내주고 돌기 시작하는지 검사
def test_start_issues_an_id_and_runs(client):
    body = client.post(START, json={}).json()  # 시작 응답을 받음
    # 첫 회차 ID, 실행 중, 경과 0 이어야 함
    assert status(body) == ("EXP-20261022-001", "running", 0)
    # 기본 비는 켜진 보통 강우여야 함
    assert body["rain"] == {"state": "ON", "intensity": "보통 강우", "mmPerHour": 60}


# 돌고 있을 때 다시 시작하면 회차는 유지하고 본문만 적용하는지 검사
def test_start_while_running_keeps_the_run_and_applies_the_body(client, clock, service):
    client.post(START, json={})  # 시작
    lapse(clock, service, 5)  # 5초를 전송
    body = client.post(START, json={"rain": "heavy"}).json()  # 강한 비로 다시 시작
    # 회차 ID 와 경과 5초는 그대로여야 함
    assert (body["experimentId"], body["elapsedSec"]) == ("EXP-20261022-001", 5)
    assert body["rain"]["mmPerHour"] == 90  # 비 세기는 90 이어야 함
    assert service.conditions == Conditions(90.0, {})  # 서비스 조건에도 반영돼야 함


# 정지하면 회차가 멈춰 굳는지 검사
def test_stop_freezes_the_run(client, clock, service):
    client.post(START, json={})  # 시작
    lapse(clock, service, 5)  # 5초를 전송
    stopped = client.post(STOP, json={}).json()  # 정지
    # 같은 회차, 정지됨, 경과 5초여야 함
    assert status(stopped) == ("EXP-20261022-001", "stopped", 5)
    assert stopped["rain"]["state"] == "OFF"  # 비는 꺼져야 함
    frozen = service.state  # 지금 상태를 잡아 둔다
    lapse(clock, service, 5)  # 5초를 더 전송
    assert client.get("/api/state").json() == stopped  # 응답이 정지 때와 같아야 함
    assert service.state == frozen  # 서비스 상태도 변하지 않아야 함


# 시작·정지·초기화가 본문 없이도 되는지 검사
def test_start_stop_and_reset_need_no_body(client):
    assert client.post(START).json()["runState"] == "running"  # 본문 없이 시작하면 실행 중이어야 함
    assert client.post(STOP).status_code == 200  # 본문 없이 정지해도 성공 필요
    assert client.post(RESET).status_code == 200  # 본문 없이 초기화해도 성공 필요
    assert client.get("/api/state").json()["runState"] == "idle"  # 그 뒤 상태는 대기여야 함


# 정지 뒤 시작하면 마른 새 회차를 시작하는지 검사
def test_start_after_stop_begins_a_new_dry_run(client, clock, service):
    client.post("/api/rain", json={"intensity": "heavy"})  # 강한 비를 선택
    client.post(START, json={})  # 시작
    lapse(clock, service, 25)  # 25초를 전송
    client.post(STOP, json={})  # 정지
    lapse(clock, service, 5)  # 5초를 전송
    body = client.post(START, json={}).json()  # 다시 시작
    # 새 회차 ID, 실행 중, 경과 0 이어야 함
    assert status(body) == ("EXP-20261022-002", "running", 0)
    # 시각은 가상 시계를 따라 30초 뒤여야 함
    assert body["timestamp"] == "2026-10-22T10:00:30.000+09:00"
    assert levels(body) == DRY  # 수위는 모두 0 이어야 함
    assert body["drain"] == {"volumeL": 0, "flowLMin": 0}  # 배수는 0 이어야 함
    assert body["rain"]["mmPerHour"] == 90  # 고른 강한 비가 이어져야 함


# 초기화하면 기본 선택으로 대기 상태에 돌아가는지 검사
def test_reset_returns_to_standby_with_the_default_selection(client, clock, service):
    # 강한 비와 완전 막힘으로 시작
    client.post(START, json={"rain": "heavy", "blockage": {"type": "full", "location": "INLET-02"}})
    lapse(clock, service, 10)  # 10초를 전송
    body = client.post(RESET, json={}).json()  # 초기화
    assert status(body) == ("EXP-STANDBY", "idle", 0)  # 대기 ID, idle, 경과 0 이어야 함
    assert body["timestamp"] == "2026-10-22T10:00:10.000+09:00"  # 시각은 10초 뒤여야 함
    assert body["rain"] == DEFAULT_RAIN_OFF  # 비는 꺼진 기본 표시여야 함
    assert body["blockage"] == NO_BLOCKAGE  # 막힘은 없음이어야 함
    assert levels(body) == DRY  # 수위는 모두 0 이어야 함
    assert service.conditions == Conditions()  # 서비스 조건이 빈 조건이어야 함
    # 다음 시작은 둘째 회차 ID 를 받아야 함
    assert client.post(START, json={}).json()["experimentId"] == "EXP-20261022-002"


# 대기 중 초기화는 선택값만 되돌리는지 검사
def test_reset_while_idle_only_restores_the_selection(client, clock):
    before = client.get("/api/state").json()  # 처음 상태를 잡아 둔다
    client.post("/api/rain", json={"intensity": "heavy"})  # 강한 비를 선택
    client.post("/api/blockage", json={"type": "full", "location": "INLET-03"})  # 완전 막힘을 선택
    clock.jump(5.0)  # 가상 시계를 5초 전송
    assert client.post(RESET, json={}).json() == before  # 초기화하면 처음 상태와 같아야 함



# 대기 중에 고른 비·막힘이 시작할 때 적용되는지 검사
def test_selection_made_while_idle_applies_at_start(client, service):
    body = client.post("/api/rain", json={"intensity": "heavy"}).json()  # 강한 비를 선택
    assert body["runState"] == "idle"  # 아직 대기 상태여야 함
    # 비는 꺼진 채 고른 표시만 바뀐다
    assert body["rain"] == {"state": "OFF", "intensity": "강한 강우", "mmPerHour": 90}
    client.post("/api/blockage", json={"type": "full", "location": "INLET-03"})  # 완전 막힘을 선택
    # 서비스 조건에 비는 아직 0, 막힘은 반영됨
    assert service.conditions == Conditions(0.0, {"INLET-03": "full"})
    assert client.post(START, json={}).json()["rain"]["state"] == "ON"  # 시작하면 비가 켜진다
    # 조건에 강한 비와 막힘이 모두 들어감
    assert service.conditions == Conditions(90.0, {"INLET-03": "full"})


# 정지 중에 고른 값이 다음 시작 때 적용되는지 검사
def test_selection_made_while_stopped_applies_at_the_next_start(client, clock, service):
    client.post(START, json={})  # 시작
    lapse(clock, service, 3)  # 3초를 전송
    client.post(STOP, json={})  # 정지
    body = client.post("/api/rain", json={"intensity": "light"}).json()  # 약한 비를 선택
    assert body["runState"] == "stopped"  # 여전히 정지 상태여야 함
    # 비는 꺼진 채 고른 표시만 바뀐다
    assert body["rain"] == {"state": "OFF", "intensity": "약한 강우", "mmPerHour": 30}
    body = client.post(START, json={}).json()  # 다시 시작
    # 약한 비가 켜져야 함
    assert body["rain"] == {"state": "ON", "intensity": "약한 강우", "mmPerHour": 30}


RAIN_LABELS = [  # 비 세기 표시 문구 사례들 (요청 본문, 문구, mm/h)
    ({"intensity": "light"}, "약한 강우", 30),  # 약한 비 이름
    ({"intensity": "medium"}, "보통 강우", 60),  # 보통 비 이름
    ({"intensity": "heavy"}, "강한 강우", 90),  # 강한 비 이름
    ({"mmPerHour": 60}, "보통 강우", 60),  # 값이 보통과 같으면 보통 문구
    ({"mmPerHour": 75}, "직접 입력 75 mm/h", 75),  # 프리셋에 없는 값은 직접 입력 문구
    ({"mmPerHour": 12.5}, "직접 입력 12.5 mm/h", 12.5),  # 소수 값
    ({"mmPerHour": 150}, "직접 입력 150 mm/h", 150),  # 최댓값
]


@pytest.mark.parametrize(("body", "label", "mm"), RAIN_LABELS)  # 사례마다 반복
# 비 세기 표시 문구 검사
def test_rain_labels(client, body, label, mm):
    client.post(START, json={})  # 시작
    rain = client.post("/api/rain", json=body).json()["rain"]  # 비를 바꾼 응답의 비 항목을 꺼냄
    # 켜짐, 기대 문구, 기대 세기여야 함
    assert rain == {"state": "ON", "intensity": label, "mmPerHour": mm}


# 돌고 있을 때 비 0 은 꺼짐인지 검사
def test_zero_rain_while_running_is_off(client):
    client.post(START, json={})  # 시작
    rain = client.post("/api/rain", json={"mmPerHour": 0}).json()["rain"]  # 비 세기를 0 으로 변환
    # 꺼짐, 강우 없음, 0 이어야 함
    assert rain == {"state": "OFF", "intensity": "강우 없음", "mmPerHour": 0}


BLOCKAGE_LABELS = [  # 막힘 표시 문구 사례들 (요청 본문, 위치, 문구)
    # 2번 부분 막힘
    ({"type": "partial", "location": "INLET-02"}, "INLET-02", "빗물받이 ② 부분 막힘"),
    ({"type": "full", "location": "INLET-03"}, "INLET-03", "빗물받이 ③ 완전 막힘"),  # 3번 완전 막힘
    ({"type": "none"}, None, "정상 배수"),  # 막힘 없음
    ({"type": "none", "location": "INLET-02"}, None, "정상 배수"),  # 막힘 없음이면 위치는 무시
]


@pytest.mark.parametrize(("body", "location", "label"), BLOCKAGE_LABELS)  # 사례마다 반복
# 막힘 표시 문구 검사
def test_blockage_labels(client, body, location, label):
    # 막힘을 바꾼 응답의 막힘 항목을 꺼냄
    blockage = client.post("/api/blockage", json=body).json()["blockage"]
    # 위치·종류·문구가 기대와 같아야 함
    assert blockage == {"location": location, "type": body["type"], "label": label}


# 새 막힘이 이전 막힘을 대체하는지 검사
def test_a_new_blockage_replaces_the_previous_one(client, service):
    # 2번 부분 막힘을 건다
    client.post("/api/blockage", json={"type": "partial", "location": "INLET-02"})
    # 3번 완전 막힘으로 변환
    body = client.post("/api/blockage", json={"type": "full", "location": "INLET-03"}).json()
    assert service.conditions.blockage == {"INLET-03": "full"}  # 서비스 조건에 3번만 남아야 함
    # 예측 가정에도 3번만 남아야 함
    assert body["predictionMeta"]["assumptions"]["blockage"] == {"INLET-03": "full"}
    client.post("/api/blockage", json={"type": "none"})  # 막힘을 제거
    assert service.conditions.blockage == {}  # 서비스 조건이 비어야 함


# 예측 메타가 기준과 가정을 밝히는지 검사
def test_prediction_meta_states_basis_and_assumptions(client):
    body = client.post(  # 강한 비와 2번 부분 막힘으로 시작
        # 시작 본문
        START, json={"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}}
    ).json()  # 응답을 읽음
    assert body["predictionMeta"] == {  # 예측 메타가 아래와 같아야 함
        "basisTime": "2026-10-22T10:00:00.000+09:00",  # 기준 시각
        "basisElapsedSec": 0,  # 기준 경과 초
        "validForSec": 5,  # 유효 시간(초)
        "modelVersion": "0.1-assumed",  # 모델 버전
        "assumptions": {  # 가정
            "rule": ASSUMPTION_RULE,  # 가정 규칙 문구
            "rainMmPerHour": 90,  # 가정한 비 세기
            "blockage": {"INLET-02": "partial"},  # 가정한 막힘
        },
    }
    stopped = client.post(STOP, json={}).json()  # 정지
    # 정지하면 가정한 비 세기가 0 이어야 함
    assert stopped["predictionMeta"]["assumptions"]["rainMmPerHour"] == 0
