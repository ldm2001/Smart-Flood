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
    "experimentId": "EXP-20261022-001",  # 회차 ID
    "mode": "live",  # 모드(live 또는 replay)
    "timestamp": "2026-10-22T10:00:00+09:00",  # 한국 시각 문자열
    "elapsedSec": 42,  # 경과 초
    "zones": {  # 구역별 수위·속도·출처
        "A": {"levelMm": 31.2, "rateMmSec": 0.24, "source": "simulated"},  # A 구역: 가상 실측
        "B": {"levelMm": 22.7, "rateMmSec": 0.16, "source": "simulated"},  # B 구역: 가상 실측
        "C": {"levelMm": 15.4, "rateMmSec": 0.10, "source": "estimated"},  # C 구역: 모델 추정
    },
    "predictions": {  # 구역별 10·20·30초 뒤 예측 수위(mm)
        "A": {"10": 33.6, "20": 36.0, "30": 38.4},  # A 구역 예측
        "B": {"10": 24.3, "20": 25.9, "30": 27.5},  # B 구역 예측
        "C": {"10": 16.4, "20": 17.4, "30": 18.4},  # C 구역 예측
    },
    "drain": {"volumeL": 1.84, "flowLMin": 1.12},  # 배수량(L)과 유량(L/분)
    # 비 상태·세기 이름·강우량(mm/h)
    "rain": {"state": "ON", "intensity": "보통 강우", "mmPerHour": 60},
    # 막힘 위치·종류·표시 문구
    "blockage": {"location": "INLET-02", "type": "partial", "label": "빗물받이 ② 부분 막힘"},
    "devices": {  # 장치 상태
        "esp32_1": "online",  # 장치 1 접속
        "esp32_2": "online",  # 장치 2 접속
        "floatSwitch": "normal",  # 플로트 스위치 정상
        "emergencyStop": "normal",  # 비상정지 정상
    },
    "quality": "valid",  # 데이터 품질
    "outputsLocked": True,  # 출력은 항상 잠김
    "dataSource": "sim",  # 입력원
    "alerts": [{"zone": "A", "stage": "caution", "etaSec": 20}],  # 경보 목록: A 구역 주의, 20초 뒤
}

SOURCES = ("measured", "simulated", "estimated", "replay")  # 허용하는 구역 출처 표시
HORIZONS = ("10", "20", "30")  # 예측 시점 키(초)


# 4.1 제약을 pydantic 없이 옮긴 검사기. 위반 항목 목록을 반환
def breaches(body: dict) -> list[str]:
    problems = []  # 위반 항목을 모을 목록

    # 값이 범위 안의 유한한 숫자인지 보는 안쪽 함수
    def number(path, value, lo, hi):
        # 불리언을 뺀 정수·실수인지 확인
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        # 숫자가 아니거나 범위 밖이면
        if not (is_number and math.isfinite(value) and lo <= value <= hi):
            problems.append(f"{path}={value!r}")  # 위반으로 적는다

    # 시각이 한국(+09:00) 오프셋인지 보는 안쪽 함수
    def stamp(path, value):
        try:  # 시각 문자열을 읽어 확인
            # 오프셋이 +09:00 이면
            if datetime.fromisoformat(value).utcoffset() == timedelta(hours=9):
                return  # 통과
        except (TypeError, ValueError):  # 문자열이 아니거나 시각이 아니면
            pass  # 아래에서 위반으로 적는다
        problems.append(f"{path}={value!r}")  # 위반으로 적는다

    # 값이 허용 목록에 있는지 보는 안쪽 함수
    def choice(path, value, allowed):
        if value not in allowed:  # 목록에 없으면
            problems.append(f"{path}={value!r}")  # 위반으로 적는다

    if not isinstance(body.get("experimentId"), str):  # 회차 ID 가 글자가 아니면
        problems.append("experimentId")  # 위반으로 적는다
    choice("mode", body.get("mode"), ("live", "replay"))  # 모드는 live 나 replay
    stamp("timestamp", body.get("timestamp"))  # 시각은 한국 오프셋
    number("elapsedSec", body.get("elapsedSec"), 0, 864000)  # 경과 초는 0 ~ 10일
    # 구역·예측 묶음을 꺼낸다(없으면 빈 묶음)
    zones, predictions = body.get("zones") or {}, body.get("predictions") or {}
    for z in ("A", "B", "C"):  # 구역마다 확인
        zone = zones.get(z) or {}  # 구역 값을 꺼냄
        number(f"zones.{z}.levelMm", zone.get("levelMm"), 0, 500)  # 수위는 0 ~ 500 mm
        number(f"zones.{z}.rateMmSec", zone.get("rateMmSec"), -20, 20)  # 속도는 ±20 mm/s
        choice(f"zones.{z}.source", zone.get("source"), SOURCES)  # 출처는 허용 목록에서만
        horizons = predictions.get(z) or {}  # 그 구역의 예측 값을 꺼냄
        for h in HORIZONS:  # 예측 시점마다 확인
            number(f"predictions.{z}.{h}", horizons.get(h), 0, 500)  # 예측 수위는 0 ~ 500 mm
    drain = body.get("drain") or {}  # 배수 묶음을 꺼냄
    number("drain.volumeL", drain.get("volumeL"), 0, 10000)  # 배수량은 0 ~ 10000 L
    number("drain.flowLMin", drain.get("flowLMin"), 0, 1000)  # 유량은 0 ~ 1000 L/분
    # 품질은 valid·degraded·invalid 중 하나
    choice("quality", body.get("quality"), ("valid", "degraded", "invalid"))
    if body.get("outputsLocked") is not True:  # 출력 잠김이 true 가 아니면
        problems.append("outputsLocked")  # 위반으로 적는다
    # 입력원은 sim·replay·live 중 하나
    choice("dataSource", body.get("dataSource"), ("sim", "replay", "live"))
    if not isinstance(body.get("alerts"), list):  # 경보가 목록이 아니면
        problems.append("alerts")  # 위반으로 적는다
    if "predictionMeta" in body:  # 예측 메타가 있으면
        # 기준 시각도 한국 오프셋이어야 함
        stamp("predictionMeta.basisTime", (body["predictionMeta"] or {}).get("basisTime"))
    return problems  # 위반 목록을 반환


# 예시에 있는 키 중 실제에 없는 것(중첩 포함)을 찾는다. 필드 삭제·이름 변경 검사용
def holes(example: dict, actual: dict, path: str = "") -> list[str]:
    missing = []  # 빠진 키를 모을 목록
    for key, value in example.items():  # 예시의 키마다 확인
        if key not in actual:  # 실제에 없으면
            missing.append(path + key)  # 빠진 키 경로를 적는다
        elif isinstance(value, dict):  # 안쪽 묶음이면
            missing += holes(value, actual[key], f"{path}{key}.")  # 안쪽까지 같은 검사를 반복
    return missing  # 빠진 키 목록을 반환


# 경로 끝의 값을 바꾸는 변형 함수를 만듦
def twist(*path_and_value):
    *path, key, value = path_and_value  # 경로, 마지막 키, 새 값으로 나눈다

    # 본문을 직접 고치는 변형
    def mutant(body):
        target = body  # 본문에서 출발
        for part in path:  # 경로를 따라
            target = target[part]  # 안쪽으로 내려감
        target[key] = value  # 마지막 키의 값을 변환

    return mutant  # 변형 함수를 반환


# 경로 끝의 키를 지우는 변형 함수를 만듦
def omission(*path_and_key):
    *path, key = path_and_key  # 경로와 마지막 키로 나눈다

    # 본문에서 키를 지우는 변형
    def variant(body):
        target = body  # 본문에서 출발
        for part in path:  # 경로를 따라
            target = target[part]  # 안쪽으로 내려감
        del target[key]  # 마지막 키를 삭제

    return variant  # 변형 함수를 반환


VIOLATIONS = {  # 계약을 어긴 변형 모음(이름 → 변형)
    "levelMm-over-500": twist("zones", "A", "levelMm", 500.1),  # 수위 500 초과
    "levelMm-negative": twist("zones", "B", "levelMm", -0.1),  # 수위 음수
    "levelMm-nan": twist("zones", "C", "levelMm", math.nan),  # 수위 NaN
    "rate-over-20": twist("zones", "A", "rateMmSec", 20.1),  # 속도 20 초과
    "rate-under-minus-20": twist("zones", "B", "rateMmSec", -20.1),  # 속도 -20 미만
    "source-unknown": twist("zones", "A", "source", "sensor"),  # 모르는 출처
    "zone-C-missing": omission("zones", "C"),  # C 구역 없음
    "prediction-over-500": twist("predictions", "A", "30", 500.1),  # 예측 500 초과
    "prediction-negative": twist("predictions", "C", "10", -0.1),  # 예측 음수
    "prediction-key-missing": omission("predictions", "B", "30"),  # 예측 키 없음
    "predictions-C-missing": omission("predictions", "C"),  # C 구역 예측 없음
    "quality-unknown": twist("quality", "ok"),  # 모르는 품질
    "mode-sim": twist("mode", "sim"),  # 모드 sim 은 불가
    "dataSource-unknown": twist("dataSource", "mock"),  # 모르는 입력원
    "outputsLocked-false": twist("outputsLocked", False),  # 출력 잠김이 false
    "elapsedSec-over-10-days": twist("elapsedSec", 864001),  # 경과 초 10일 초과
    "elapsedSec-negative": twist("elapsedSec", -1),  # 경과 초 음수
    "volumeL-over-10000": twist("drain", "volumeL", 10000.1),  # 배수량 10000 초과
    "flowLMin-over-1000": twist("drain", "flowLMin", 1000.1),  # 유량 1000 초과
    "flowLMin-negative": twist("drain", "flowLMin", -0.1),  # 유량 음수
    "timestamp-utc": twist("timestamp", "2026-10-22T01:00:00Z"),  # 시각이 UTC(Z)
    "timestamp-naive": twist("timestamp", "2026-10-22T10:00:00"),  # 시각에 오프셋 없음
    "timestamp-not-a-time": twist("timestamp", "yesterday"),  # 시각이 아닌 글자
}

BOUNDARIES = [  # 경계값이라 받아야 하는 변형 모음
    twist("zones", "A", "levelMm", 0),  # 수위 0
    twist("zones", "B", "levelMm", 500),  # 수위 500
    twist("zones", "A", "rateMmSec", -20),  # 속도 -20
    twist("zones", "C", "rateMmSec", 20),  # 속도 20
    twist("predictions", "A", "10", 0),  # 예측 0
    twist("predictions", "C", "30", 500),  # 예측 500
    twist("elapsedSec", 864000),  # 경과 초 10일
    twist("drain", "volumeL", 10000),  # 배수량 10000
    twist("drain", "flowLMin", 1000),  # 유량 1000
    twist("timestamp", "2026-10-22T10:00:00.123+09:00"),  # 밀리초가 붙은 한국 시각
]



# (a) 응답 모델: 예시가 두 검사를 모두 통과
def test_spec_example_validates():
    Board.model_validate(SPEC_EXAMPLE)  # 응답 모델이 받아야 함
    assert breaches(SPEC_EXAMPLE) == []  # 별도 검사기도 위반이 없어야 함


# 모르는 필드가 늘어도 받는지 검사
def test_extra_fields_are_allowed():
    body = copy.deepcopy(SPEC_EXAMPLE)  # 예시를 복사
    body["futureField"] = {"x": 1}  # 새 최상위 필드를 합산
    body["zones"]["A"]["note"] = "추가 필드"  # 구역 안에도 새 필드를 합산
    Board.model_validate(body)  # 응답 모델이 받아야 함
    assert breaches(body) == []  # 검사기도 통과 필요


# 경계값은 받아들이는지 검사
def test_boundary_values_are_accepted():
    body = copy.deepcopy(SPEC_EXAMPLE)  # 예시를 복사
    for mutate in BOUNDARIES:  # 경계 변형마다
        mutate(body)  # 본문에 적용
    Board.model_validate(body)  # 응답 모델이 받아야 함
    assert breaches(body) == []  # 검사기도 통과 필요


@pytest.mark.parametrize("mutate", VIOLATIONS.values(), ids=VIOLATIONS.keys())  # 위반 변형마다 반복
# 계약 위반은 거절하는지 검사
def test_violations_are_rejected(mutate):
    body = copy.deepcopy(SPEC_EXAMPLE)  # 예시를 복사
    mutate(body)  # 위반으로 고친다
    with pytest.raises(ValidationError):  # 응답 모델이 거절 필요
        Board.model_validate(body)  # 검증을 시도
    assert breaches(body)  # 별도 검사기도 위반을 찾아야 함


SCENARIO = (  # (b) 실제 API 출력. (주소, 본문) 요청이나 돌릴 초(정수)를 차례로 적는다
    ("/api/rain", {"intensity": "heavy"}),  # 비를 강하게
    # 실험 시작, 2번 빗물받이 완전 막힘으로
    ("/api/experiment/start", {"blockage": {"type": "full", "location": "INLET-02"}}),
    300,  # 300 초 돌린다
    ("/api/rain", {"mmPerHour": 150}),  # 비를 150 mm/h 로
    ("/api/blockage", {"type": "partial", "location": "INLET-03"}),  # 3번 빗물받이 일부 막힘
    300,  # 300 초 돌린다
    ("/api/blockage", {"type": "full", "location": "INLET-02"}),  # 2번 빗물받이 완전 막힘
    120,  # 120 초 돌린다
    ("/api/rain", {"mmPerHour": 0}),  # 비 끄기
    60,  # 60 초 돌린다
    ("/api/experiment/stop", {}),  # 실험 종료
    3,  # 3 초 돌린다
    ("/api/experiment/reset", {}),  # 실험 초기화
    ("/api/source", {"mode": "sim"}),  # 입력원을 sim 으로
    # 방금 회차(빈 폴더의 첫 회차)를 재생. 780 초를 돌고 781 번째 틱에서 멈춘다
    ("/api/source", {"mode": "replay", "logId": "EXP-20261022-001"}),
    785,  # 785 초 돌린다
    ("/api/source", {"mode": "sim"}),  # 입력원을 sim 으로
)


@pytest.fixture(scope="module")  # 이 파일에서 한 번만 만드는 준비물
# 시나리오의 모든 제어 응답과 매초 상태 응답을 모음
def dossier(config, tmp_path_factory):
    clock = Fake(START)  # 가상 시계
    log = Jsonl(tmp_path_factory.mktemp("logs"))  # 임시 폴더 기록기
    # 가상 시계·임시 기록으로 앱을 만듦
    app = factory(config, clock=clock, experiment_log=log, start_ticker=False, static_dir=None)
    bodies = []  # 응답을 모을 목록
    with TestClient(app) as client:  # 앱을 띄운다
        service = app.state.service  # 앱 안의 서비스를 꺼냄
        bodies.append(client.get("/api/state").json())  # 시작 상태를 먼저 담는다
        for step in SCENARIO:  # 시나리오 항목마다 확인
            if isinstance(step, int):  # 정수면 그만큼 시간을 전송
                for _ in range(step):  # 초마다 반복
                    clock.jump(1.0)  # 시계를 1초 전송
                    service.catchup()  # 밀린 틱을 처리
                    bodies.append(client.get("/api/state").json())  # 그 초의 상태를 담는다
                continue  # 다음 항목으로 감
            path, body = step  # 아니면 (주소, 본문) 요청이다
            response = client.post(path, json=body)  # 요청을 전송
            assert response.status_code == 200, response.text  # 요청이 성공 필요
            bodies.append(response.json())  # 제어 응답을 담는다
    return bodies  # 모은 응답을 반환


# 시나리오가 실행 상태를 모두 거치는지 검사
def test_scenario_covers_every_run_state(dossier):
    # (실행 상태, 비 상태) 조합을 모음
    seen = {(b["runState"], b["rain"]["state"]) for b in dossier}
    # 대기·실행·정지가 모두 나와야 함
    assert {("idle", "OFF"), ("running", "ON"), ("running", "OFF"), ("stopped", "OFF")} <= seen


# 시나리오가 재생도 거치는지 검사
def test_scenario_covers_the_replay_of_its_run(dossier):
    # (모드, 입력원, 실행 상태) 조합을 모음
    seen = {(b["mode"], b["dataSource"], b["runState"]) for b in dossier}
    # 재생 중과 재생 정지가 나와야 함
    assert {("replay", "replay", "running"), ("replay", "replay", "stopped")} <= seen
    # 구역 출처 표시를 모음
    sources = {zone["source"] for b in dossier for zone in b["zones"].values()}
    assert {"simulated", "replay", "estimated"} <= sources  # 가상 실측·재생·추정이 모두 나와야 함


# 모든 응답이 계약을 지키는지 검사
def test_api_output_meets_the_contract(dossier):
    for body in dossier:  # 응답마다 확인
        assert breaches(body) == [], body  # 검사기에 위반이 없어야 함
        Board.model_validate(body)  # 응답 모델도 받아야 함


# 예시의 모든 필드가 남아 있는지 검사
def test_api_output_keeps_every_example_field(dossier):
    for body in dossier:  # 응답마다 확인
        assert holes(SPEC_EXAMPLE, body) == []  # 빠진 필드가 없어야 함


# 더한 필드가 항상 있는지 검사
def test_api_output_always_carries_the_added_fields(dossier):
    for body in dossier:  # 응답마다 확인
        # 실행 상태는 대기·실행·정지 중 하나
        assert body["runState"] in ("idle", "running", "stopped")
        meta = body["predictionMeta"]  # 예측 메타를 꺼냄
        assert meta["basisTime"] == body["timestamp"]  # 기준 시각이 응답 시각과 같다
        assert meta["basisElapsedSec"] == body["elapsedSec"]  # 기준 경과 초도 같다


# 범위 밖 값은 잘라 내지 않고 응답 검증에서 실패하는지 검사(500 으로 드러난다)
def test_out_of_contract_snapshot_is_not_clipped(client, service):
    from dataclasses import replace

    # A 수위가 범위 밖(500.1 mm)인 스냅샷을 만듦
    flooded = replace(service.snapshot, levels_m={"A": 0.5001, "B": 0.0, "C": 0.0})
    with pytest.raises(ValidationError):  # 검증 오류가 나야 함
        Board.snapshot(flooded)  # 응답으로 바꾸려 하면
