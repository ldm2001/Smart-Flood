import copy
import pytest
import time
from app.adapters.clock import Wall
from app.adapters.jsonl_log import LOG_DIR, Jsonl
from app.adapters.sim_source import Sim
from app.main import factory
from datetime import date

FRONT_ORIGINS = ["http://localhost:3000"]  # 허용하는 프론트 주소


# 건강 확인 주소가 정상 응답을 주는지 검사
def test_health(client):
    response = client.get("/health")  # 건강 확인을 요청
    # 200 과 {"status": "ok"} 여야 함
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


# /api/config 가 불러온 설정을 그대로 돌려주는지 검사
def test_config_endpoint_returns_the_loaded_config(client, config):
    assert client.get("/api/config").json() == config  # 응답이 설정과 같아야 함


@pytest.mark.parametrize("origin", FRONT_ORIGINS)  # 프론트 주소마다 반복
@pytest.mark.parametrize("method", ["GET", "POST"])  # GET·POST 로 반복
# CORS 사전 요청이 두 프론트를 허용하는지 검사
def test_cors_preflight_allows_the_fronts(client, origin, method):
    response = client.options(  # 사전 요청(OPTIONS)을 전송
        "/api/experiment/start",  # 실험 시작 주소로
        headers={  # 헤더에
            "Origin": origin,  # 요청 출처
            "Access-Control-Request-Method": method,  # 쓰려는 메서드
            "Access-Control-Request-Headers": "content-type",  # 쓰려는 헤더
        },
    )
    assert response.status_code == 200  # 성공(200)이어야 함
    # 허용 출처가 요청 출처와 같아야 함
    assert response.headers["access-control-allow-origin"] == origin


# CORS 가 다른 출처를 거절하는지 검사
def test_cors_rejects_other_origins(client):
    response = client.options(  # 사전 요청을 전송
        "/api/state",  # 상태 주소로
        # 허용 목록에 없는 출처를 달아서
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400  # 거절(400)이어야 함
    assert "access-control-allow-origin" not in response.headers  # 허용 헤더가 없어야 함


@pytest.mark.parametrize("origin", FRONT_ORIGINS)  # 프론트 주소마다 반복
# 일반 요청에도 CORS 헤더가 붙는지 검사
def test_cors_header_on_plain_requests(client, origin):
    response = client.get("/api/state", headers={"Origin": origin})  # 출처를 달아 상태를 요청
    # 허용 출처가 요청 출처와 같아야 함
    assert response.headers["access-control-allow-origin"] == origin


# 허용 출처가 설정에서 오는지 검사
def test_cors_origins_come_from_config(builder, config):
    cfg = copy.deepcopy(config)  # 설정을 복사
    cfg["server"]["cors_origins"] = ["http://example.test"]  # 허용 출처를 변환
    client = builder(cfg)  # 그 설정으로 앱을 만듦
    allowed = client.get("/api/state", headers={"Origin": "http://example.test"})  # 새 출처로 요청
    # 새 출처는 허용돼야 함
    assert allowed.headers["access-control-allow-origin"] == "http://example.test"
    other = client.get("/api/state", headers={"Origin": "http://localhost:5500"})  # 미허용 출처
    assert "access-control-allow-origin" not in other.headers  # 미허용 출처는 거절돼야 함


# 빌드한 프론트를 API 뒤에서 서빙하는지 검사
def test_built_front_is_served_behind_the_api(builder, tmp_path):
    (tmp_path / "index.html").write_text("<p>home</p>", encoding="utf-8")  # 첫 화면 파일을 만듦
    (tmp_path / "ops").mkdir()  # ops 폴더를 만듦
    # ops 화면 파일을 만듦
    (tmp_path / "ops" / "index.html").write_text("<p>ops</p>", encoding="utf-8")
    client = builder(static_dir=tmp_path)  # 그 폴더를 정적 폴더로 앱을 만듦
    assert client.get("/").text == "<p>home</p>"  # 루트는 첫 화면이어야 함
    assert client.get("/ops/").text == "<p>ops</p>"  # /ops/ 는 ops 화면이어야 함
    # API 는 그대로 JSON 이어야 함
    assert client.get("/api/state").headers["content-type"] == "application/json"
    assert client.get("/health").json() == {"status": "ok"}  # /health 도 그대로여야 함


# 폴더를 안 주는 경우와 없는 폴더인 경우로 반복
@pytest.mark.parametrize("static_dir", [None, "missing"])
# 빌드한 프론트가 없으면 루트가 404 인지 검사
def test_without_a_built_front_root_is_404(builder, tmp_path, static_dir):
    # 정적 폴더가 없거나 존재하지 않게 앱을 만듦
    client = builder(static_dir=static_dir and tmp_path / static_dir)
    assert client.get("/").status_code == 404  # 루트는 404 여야 함


# 배경 티커가 기한 지난 틱을 돌리는지 검사
def test_background_ticker_runs_due_ticks(builder, clock):
    client = builder(start_ticker=True)  # 티커를 켜고 앱을 만듦
    client.post("/api/experiment/start", json={})  # 실험을 시작
    clock.jump(3.0)  # 가상 시계를 3초 전송
    deadline = time.monotonic() + 2.0  # 최대 2초까지 기다릴 기한을 잡는다
    # 경과가 3초가 되거나 기한이 지날 때까지
    while client.get("/api/state").json()["elapsedSec"] < 3 and time.monotonic() < deadline:
        time.sleep(0.02)  # 잠깐씩 쉬며 기다린다
    assert client.get("/api/state").json()["elapsedSec"] == 3  # 경과 초가 3 이어야 함
    time.sleep(0.3)  # 조금 더 기다린다
    assert client.get("/api/state").json()["elapsedSec"] == 3  # 더 돌지 않고 여전히 3 이어야 함


# 기본 구성이 가상 입력원·실제 시계·backend 기록 폴더인지 검사
def test_default_wiring_uses_the_sim_the_system_clock_and_the_backend_logs():
    service = factory(start_ticker=False).state.service  # 티커 없이 기본 구성으로 서비스를 꺼냄
    assert isinstance(service.source, Sim)  # 입력원이 Sim 이어야 함
    assert isinstance(service.clock, Wall)  # 시계가 Wall 이어야 함
    assert isinstance(service.experiment_log, Jsonl)  # 기록기가 Jsonl 이어야 함
    assert service.experiment_log.directory == LOG_DIR  # 기록 폴더가 기본 위치여야 함


# 기동은 되지만 계약대로 응답 못 하는 구성들. 첫 요청이 아니라 기동에서 실패 필요
UNSERVABLE_CONFIGS = {
    "tick-off-the-dt-grid": ("tick_hz", 3),  # 틱 주기가 시간 격자에 안 맞는다
    # 비 세기 프리셋에 heavy 가 없다
    "preset-missing": ("rain_presets_mm_per_h", {"light": 30, "medium": 60}),
    "preset-over-the-rain-max": (  # 프리셋이 비 최댓값을 넘는다
        "rain_presets_mm_per_h",  # 바꿀 키
        {"light": 30, "medium": 60, "heavy": 200},  # 바꿀 값
    ),
    # 예측 시점이 계약의 키와 다르다
    "horizons-not-the-contract-keys": ("prediction", {"horizons_s": [10, 20], "valid_for_s": 5}),
    # 보정 이득이 1 을 넘는다
    "gain-over-one": ("correction", {"gain": 1.5, "max_age_s": 3.0, "invalid_after_s": 10.0}),
    # 구성에 날짜가 있다. 기록 첫 줄에 구성을 적는데 JSON 이 못 담는 값이다
    "date-in-config": ("calibrated_on", date(2026, 10, 22)),
}


@pytest.mark.parametrize(  # 구성 사례마다 반복
    # (키, 값) 짝과 사례 이름
    ("key", "value"), UNSERVABLE_CONFIGS.values(), ids=UNSERVABLE_CONFIGS.keys()
)
# 서비스가 감당 못 하는 구성은 기동에서 실패하는지 검사
def test_config_the_service_cannot_serve_fails_at_startup(config, key, value):
    cfg = copy.deepcopy(config)  # 설정을 복사
    cfg[key] = value  # 문제 있는 키를 변환
    with pytest.raises(ValueError):  # 값 오류가 나야 함
        factory(cfg, start_ticker=False, static_dir=None)  # 그 구성으로 앱을 만들면
