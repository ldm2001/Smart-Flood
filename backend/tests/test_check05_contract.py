import copy
import math
import pytest
from app.adapters.clock import Fake
from app.adapters.jsonl_log import Jsonl
from app.main import factory
from app.schemas import Board
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tests.helpers import START

SPEC_EXAMPLE = {  # 지시서 4.1 의 응답 예시
    "experimentId": "EXP-20261022-001",
    "mode": "live",  # 모드(live 또는 replay)
    "timestamp": "2026-10-22T10:00:00+09:00",
    "elapsedSec": 42,
    "zones": {
        "A": {"levelMm": 31.2, "rateMmSec": 0.24, "source": "simulated", "thresholdMm": 40},
        "B": {"levelMm": 22.7, "rateMmSec": 0.16, "source": "simulated", "thresholdMm": 70},
        "C": {"levelMm": 15.4, "rateMmSec": 0.10, "source": "estimated", "thresholdMm": 110},
    },
    "predictions": {  # 구역별 10·20·30초 뒤 예측 수위(mm)
        "A": {"10": 33.6, "20": 36.0, "30": 38.4},
        "B": {"10": 24.3, "20": 25.9, "30": 27.5},
        "C": {"10": 16.4, "20": 17.4, "30": 18.4},
    },
    "drain": {"volumeL": 1.84, "flowLMin": 1.12},  # 배수량(L)과 유량(L/분)
    "rain": {"state": "ON", "intensity": "보통 강우", "mmPerHour": 60},
    "blockage": {"location": "INLET-02", "type": "partial", "label": "빗물받이 ② 부분 막힘"},
    "devices": {
        "esp32_1": "online",
        "esp32_2": "online",
        "floatSwitch": "normal",
        "emergencyStop": "normal",
    },
    "quality": "valid",
    "outputsLocked": True,  # 출력은 항상 잠김
    "dataSource": "sim",
    "alerts": [{"zone": "A", "stage": "caution", "etaSec": 20}],  # 경보 목록: A 구역 주의, 20초 뒤
}

SOURCES = ("measured", "simulated", "estimated", "replay")
HORIZONS = ("10", "20", "30")  # 예측 시점 키(초)


# 4.1 제약을 pydantic 없이 옮긴 검사기. 위반 항목 목록을 반환
def breaches(body: dict) -> list[str]:
    problems = []

    # 값이 범위 안의 유한한 숫자인지 보는 안쪽 함수
    def number(path, value, lo, hi):
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        if not (is_number and math.isfinite(value) and lo <= value <= hi):
            problems.append(f"{path}={value!r}")

    # 시각이 한국(+09:00) 오프셋인지 보는 안쪽 함수
    def stamp(path, value):
        try:
            if datetime.fromisoformat(value).utcoffset() == timedelta(hours=9):
                return
        except (TypeError, ValueError):
            pass
        problems.append(f"{path}={value!r}")

    # 값이 허용 목록에 있는지 보는 안쪽 함수
    def choice(path, value, allowed):
        if value not in allowed:
            problems.append(f"{path}={value!r}")

    if not isinstance(body.get("experimentId"), str):
        problems.append("experimentId")
    choice("mode", body.get("mode"), ("live", "replay"))
    stamp("timestamp", body.get("timestamp"))
    number("elapsedSec", body.get("elapsedSec"), 0, 864000)  # 경과 초는 0 ~ 10일
    zones, predictions = body.get("zones") or {}, body.get("predictions") or {}
    for z in ("A", "B", "C"):
        zone = zones.get(z) or {}
        number(f"zones.{z}.levelMm", zone.get("levelMm"), 0, 500)
        number(f"zones.{z}.rateMmSec", zone.get("rateMmSec"), -20, 20)
        choice(f"zones.{z}.source", zone.get("source"), SOURCES)
        horizons = predictions.get(z) or {}
        for h in HORIZONS:
            number(f"predictions.{z}.{h}", horizons.get(h), 0, 500)
    drain = body.get("drain") or {}
    number("drain.volumeL", drain.get("volumeL"), 0, 10000)
    number("drain.flowLMin", drain.get("flowLMin"), 0, 1000)
    choice("quality", body.get("quality"), ("valid", "degraded", "invalid"))
    if body.get("outputsLocked") is not True:
        problems.append("outputsLocked")
    choice("dataSource", body.get("dataSource"), ("sim", "replay", "live"))
    if not isinstance(body.get("alerts"), list):
        problems.append("alerts")
    if "predictionMeta" in body:
        stamp("predictionMeta.basisTime", (body["predictionMeta"] or {}).get("basisTime"))
    return problems


# 예시에 있는 키 중 실제에 없는 것(중첩 포함)을 찾음. 필드 삭제·이름 변경 검사용
def holes(example: dict, actual: dict, path: str = "") -> list[str]:
    missing = []
    for key, value in example.items():
        if key not in actual:
            missing.append(path + key)
        elif isinstance(value, dict):
            missing += holes(value, actual[key], f"{path}{key}.")
    return missing


# 경로 끝의 값을 바꾸는 변형 함수를 만듦
def twist(*path_and_value):
    *path, key, value = path_and_value

    # 본문을 직접 고치는 변형
    def mutant(body):
        target = body
        for part in path:
            target = target[part]
        target[key] = value

    return mutant


# 경로 끝의 키를 지우는 변형 함수를 만듦
def omission(*path_and_key):
    *path, key = path_and_key

    # 본문에서 키를 지우는 변형
    def variant(body):
        target = body
        for part in path:
            target = target[part]
        del target[key]

    return variant


VIOLATIONS = {  # 계약을 어긴 변형 모음(이름 → 변형)
    "levelMm-over-500": twist("zones", "A", "levelMm", 500.1),
    "levelMm-negative": twist("zones", "B", "levelMm", -0.1),
    "levelMm-nan": twist("zones", "C", "levelMm", math.nan),
    "rate-over-20": twist("zones", "A", "rateMmSec", 20.1),
    "rate-under-minus-20": twist("zones", "B", "rateMmSec", -20.1),
    "source-unknown": twist("zones", "A", "source", "sensor"),
    "zone-C-missing": omission("zones", "C"),
    "prediction-over-500": twist("predictions", "A", "30", 500.1),
    "prediction-negative": twist("predictions", "C", "10", -0.1),
    "prediction-key-missing": omission("predictions", "B", "30"),
    "predictions-C-missing": omission("predictions", "C"),
    "quality-unknown": twist("quality", "ok"),
    "mode-sim": twist("mode", "sim"),
    "dataSource-unknown": twist("dataSource", "mock"),
    "outputsLocked-false": twist("outputsLocked", False),
    "elapsedSec-over-10-days": twist("elapsedSec", 864001),
    "elapsedSec-negative": twist("elapsedSec", -1),
    "volumeL-over-10000": twist("drain", "volumeL", 10000.1),
    "flowLMin-over-1000": twist("drain", "flowLMin", 1000.1),
    "flowLMin-negative": twist("drain", "flowLMin", -0.1),
    "timestamp-utc": twist("timestamp", "2026-10-22T01:00:00Z"),  # 시각이 UTC(Z)
    "timestamp-naive": twist("timestamp", "2026-10-22T10:00:00"),
    "timestamp-not-a-time": twist("timestamp", "yesterday"),
}

BOUNDARIES = [
    twist("zones", "A", "levelMm", 0),
    twist("zones", "B", "levelMm", 500),
    twist("zones", "A", "rateMmSec", -20),
    twist("zones", "C", "rateMmSec", 20),
    twist("predictions", "A", "10", 0),
    twist("predictions", "C", "30", 500),
    twist("elapsedSec", 864000),  # 경과 초 10일
    twist("drain", "volumeL", 10000),
    twist("drain", "flowLMin", 1000),
    twist("timestamp", "2026-10-22T10:00:00.123+09:00"),
]



# (a) 응답 모델: 예시가 두 검사를 모두 통과
def test_spec_example_validates():
    Board.model_validate(SPEC_EXAMPLE)
    assert breaches(SPEC_EXAMPLE) == []


# 모르는 필드가 늘어도 받는지 검사
def test_extra_fields_are_allowed():
    body = copy.deepcopy(SPEC_EXAMPLE)
    body["futureField"] = {"x": 1}
    body["zones"]["A"]["note"] = "추가 필드"
    Board.model_validate(body)
    assert breaches(body) == []


# 경계값은 받아들이는지 검사
def test_boundary_values_are_accepted():
    body = copy.deepcopy(SPEC_EXAMPLE)
    for mutate in BOUNDARIES:
        mutate(body)
    Board.model_validate(body)
    assert breaches(body) == []


@pytest.mark.parametrize("mutate", VIOLATIONS.values(), ids=VIOLATIONS.keys())
# 계약 위반은 거절하는지 검사
def test_violations_are_rejected(mutate):
    body = copy.deepcopy(SPEC_EXAMPLE)
    mutate(body)
    with pytest.raises(ValidationError):
        Board.model_validate(body)
    assert breaches(body)


SCENARIO = (  # (b) 실제 API 출력. (주소, 본문) 요청이나 돌릴 초(정수)를 차례로 적음
    ("/api/rain", {"intensity": "heavy"}),
    ("/api/experiment/start", {"blockage": {"type": "full", "location": "INLET-02"}}),
    300,
    ("/api/rain", {"mmPerHour": 150}),
    ("/api/blockage", {"type": "partial", "location": "INLET-03"}),
    300,
    ("/api/blockage", {"type": "full", "location": "INLET-02"}),
    120,
    ("/api/rain", {"mmPerHour": 0}),
    60,
    ("/api/experiment/stop", {}),
    3,
    ("/api/experiment/reset", {}),
    ("/api/source", {"mode": "sim"}),
    # 방금 회차(빈 폴더의 첫 회차)를 재생. 780 초를 돌고 781 번째 틱에서 멈춤
    ("/api/source", {"mode": "replay", "logId": "EXP-20261022-001"}),
    785,
    ("/api/source", {"mode": "sim"}),
)


@pytest.fixture(scope="module")
# 시나리오의 모든 제어 응답과 매초 상태 응답을 모음
def dossier(config, tmp_path_factory):
    clock = Fake(START)
    log = Jsonl(tmp_path_factory.mktemp("logs"))
    app = factory(config, clock=clock, experiment_log=log, start_ticker=False, static_dir=None)
    bodies = []
    with TestClient(app) as client:
        service = app.state.service
        bodies.append(client.get("/api/state").json())  # 시작 상태를 먼저 담음
        for step in SCENARIO:
            if isinstance(step, int):
                for _ in range(step):
                    clock.jump(1.0)
                    service.catchup()
                    bodies.append(client.get("/api/state").json())
                continue
            path, body = step  # 아니면 (주소, 본문) 요청
            response = client.post(path, json=body)
            assert response.status_code == 200, response.text
            bodies.append(response.json())
    return bodies


# 시나리오가 실행 상태를 모두 거치는지 검사
def test_scenario_covers_every_run_state(dossier):
    seen = {(b["runState"], b["rain"]["state"]) for b in dossier}
    assert {("idle", "OFF"), ("running", "ON"), ("running", "OFF"), ("stopped", "OFF")} <= seen


# 시나리오가 재생도 거치는지 검사
def test_scenario_covers_the_replay_of_its_run(dossier):
    seen = {(b["mode"], b["dataSource"], b["runState"]) for b in dossier}
    assert {("replay", "replay", "running"), ("replay", "replay", "stopped")} <= seen
    sources = {zone["source"] for b in dossier for zone in b["zones"].values()}
    assert {"simulated", "replay", "estimated"} <= sources


# 모든 응답이 계약을 지키는지 검사
def test_api_output_meets_the_contract(dossier):
    for body in dossier:
        assert breaches(body) == [], body
        Board.model_validate(body)


# 예시의 모든 필드가 남아 있는지 검사
def test_api_output_keeps_every_example_field(dossier):
    for body in dossier:
        assert holes(SPEC_EXAMPLE, body) == []


# 더한 필드가 항상 있는지 검사
def test_api_output_always_carries_the_added_fields(dossier, config):
    for body in dossier:
        assert body["runState"] in ("idle", "running", "stopped")
        meta = body["predictionMeta"]
        assert meta["basisTime"] == body["timestamp"]
        assert meta["basisElapsedSec"] == body["elapsedSec"]
        for z in ("A", "B", "C"):
            assert body["zones"][z]["thresholdMm"] == config["zones"][z]["threshold_mm"]


# 범위 밖 값은 잘라 내지 않고 응답 검증에서 실패하는지 검사(500 으로 드러남)
def test_out_of_contract_snapshot_is_not_clipped(client, service):
    from dataclasses import replace

    flooded = replace(service.snapshot, levels_m={"A": 0.5001, "B": 0.0, "C": 0.0})
    with pytest.raises(ValidationError):
        Board.snapshot(flooded)  # 응답으로 바꾸려 하면
