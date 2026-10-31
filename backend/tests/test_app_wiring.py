import copy
import pytest
import time
from app.adapters.clock import Wall
from app.adapters.jsonl_log import LOG_DIR, Jsonl
from app.adapters.sim_source import Sim
from app.adapters.stub import Stub
from app.main import factory
from datetime import date

FRONT_ORIGINS = ["http://localhost:3000"]


# 건강 확인 주소가 정상 응답을 주는지 검사
def test_health(client):
    response = client.get("/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


# /api/config 가 불러온 설정을 그대로 돌려주는지 검사
def test_config_endpoint_returns_the_loaded_config(client, config):
    assert client.get("/api/config").json() == config


@pytest.mark.parametrize("origin", FRONT_ORIGINS)
@pytest.mark.parametrize("method", ["GET", "POST"])
# CORS 사전 요청이 두 프론트를 허용하는지 검사
def test_cors_preflight_allows_the_fronts(client, origin, method):
    response = client.options(  # 사전 요청(OPTIONS)을 전송
        "/api/experiment/start",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200  # 성공(200)이어야 함
    assert response.headers["access-control-allow-origin"] == origin


# CORS 가 다른 출처를 거절하는지 검사
def test_cors_rejects_other_origins(client):
    response = client.options(
        "/api/state",
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400  # 거절(400)이어야 함
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", FRONT_ORIGINS)
# 일반 요청에도 CORS 헤더가 붙는지 검사
def test_cors_header_on_plain_requests(client, origin):
    response = client.get("/api/state", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


# 허용 출처가 설정에서 오는지 검사
def test_cors_origins_come_from_config(builder, config):
    cfg = copy.deepcopy(config)
    cfg["server"]["cors_origins"] = ["http://example.test"]
    client = builder(cfg)
    allowed = client.get("/api/state", headers={"Origin": "http://example.test"})
    assert allowed.headers["access-control-allow-origin"] == "http://example.test"
    other = client.get("/api/state", headers={"Origin": "http://localhost:5500"})
    assert "access-control-allow-origin" not in other.headers


# 빌드한 프론트를 API 뒤에서 서빙하는지 검사
def test_built_front_is_served_behind_the_api(builder, tmp_path):
    (tmp_path / "index.html").write_text("<p>home</p>", encoding="utf-8")
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "index.html").write_text("<p>ops</p>", encoding="utf-8")
    client = builder(static_dir=tmp_path)
    assert client.get("/").text == "<p>home</p>"
    assert client.get("/ops/").text == "<p>ops</p>"
    assert client.get("/api/state").headers["content-type"] == "application/json"
    assert client.get("/health").json() == {"status": "ok"}  # /health 도 그대로여야 함


@pytest.mark.parametrize("static_dir", [None, "missing"])
# 빌드한 프론트가 없으면 루트가 404 인지 검사
def test_without_a_built_front_root_is_404(builder, tmp_path, static_dir):
    # 정적 폴더가 없거나 존재하지 않게 앱을 만듦
    client = builder(static_dir=static_dir and tmp_path / static_dir)
    assert client.get("/").status_code == 404


# 배경 티커가 기한 지난 틱을 돌리는지 검사
def test_background_ticker_runs_due_ticks(builder, clock):
    client = builder(start_ticker=True)
    client.post("/api/experiment/start", json={})
    clock.jump(3.0)
    deadline = time.monotonic() + 2.0
    while client.get("/api/state").json()["elapsedSec"] < 3 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert client.get("/api/state").json()["elapsedSec"] == 3
    time.sleep(0.3)
    assert client.get("/api/state").json()["elapsedSec"] == 3


# 기본 구성이 가상 입력원·실제 시계·backend 기록 폴더·기록만 하는 알림인지 검사
def test_default_wiring_uses_the_sim_the_system_clock_and_the_backend_logs():
    service = factory(start_ticker=False).state.service
    assert isinstance(service.source, Sim)
    assert isinstance(service.clock, Wall)
    assert isinstance(service.experiment_log, Jsonl)
    assert service.experiment_log.directory == LOG_DIR
    assert isinstance(service.notifier, Stub)


UNSERVABLE_CONFIGS = {  # 기동은 되지만 계약대로 응답 못 하는 구성들
    "tick-off-the-dt-grid": ("tick_hz", 3),
    # 비 세기 프리셋에 heavy 가 없음
    "preset-missing": ("rain_presets_mm_per_h", {"light": 30, "medium": 60}),
    "preset-over-the-rain-max": (
        "rain_presets_mm_per_h",
        {"light": 30, "medium": 60, "heavy": 200},
    ),
    # 예측 시점이 계약의 키와 다름
    "horizons-not-the-contract-keys": ("prediction", {"horizons_s": [10, 20], "valid_for_s": 5}),
    "gain-over-one": ("correction", {"gain": 1.5, "max_age_s": 3.0, "invalid_after_s": 10.0}),
    # 경계 도달 상한이 주의 도달 상한보다 큼
    "warning-eta-over-caution": (
        "alerts",
        {"caution_eta_s": 30, "warning_eta_s": 60, "release_ratio": 0.9, "release_hold_s": 10},
    ),
    # 구성에 날짜가 있음. 기록 첫 줄에 구성을 적는데 JSON 이 못 담는 값
    "date-in-config": ("calibrated_on", date(2026, 10, 22)),
}


@pytest.mark.parametrize(
    ("key", "value"), UNSERVABLE_CONFIGS.values(), ids=UNSERVABLE_CONFIGS.keys()
)
# 서비스가 감당 못 하는 구성은 기동에서 실패하는지 검사
def test_config_the_service_cannot_serve_fails_at_startup(config, key, value):
    cfg = copy.deepcopy(config)
    cfg[key] = value
    with pytest.raises(ValueError):
        factory(cfg, start_ticker=False, static_dir=None)
