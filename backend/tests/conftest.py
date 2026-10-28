import pytest
from pathlib import Path
from tests.helpers import START

# 설정 파일 config.yaml 의 경로(backend 폴더 안)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture(scope="session")
# 설정 딕셔너리를 내주는 준비물
def config():
    from app.config import settings

    return settings(CONFIG_PATH)


@pytest.fixture(scope="session")
# 모델 계수를 내주는 준비물
def params(config):
    from app.core.model import Params

    return Params.config(config)


@pytest.fixture(scope="session")
# 사례별 (계수, 1초 상태 목록) 준비물. 검사 1·2 가 같이 씀
def runs(config, params):
    from tests.scenarios import EXPERIMENT, EXPERIMENT_S, flood, stress, trace

    stressed = stress(config)
    return {  # 사례 이름 → (계수, 상태 목록) 을 반환
        "default": (params, trace(params, EXPERIMENT, EXPERIMENT_S)),
        "stressed": (stressed, trace(stressed, EXPERIMENT, EXPERIMENT_S)),
        "flooded": (params, trace(params, EXPERIMENT, EXPERIMENT_S, flood(params))),
    }


@pytest.fixture(scope="session", autouse=True)
# 테스트가 logs 폴더를 건드리지 않는지 지키는 준비물
def sentinel():
    from app.adapters.jsonl_log import LOG_DIR

    # 폴더 안 파일 목록(이름, 크기)을 만드는 안쪽 함수
    def entries():
        if not LOG_DIR.is_dir():
            return []
        return sorted((p.name, p.stat().st_size) for p in LOG_DIR.iterdir())

    before = entries()
    yield
    assert entries() == before, f"테스트가 {LOG_DIR} 를 바꿨다"


@pytest.fixture
# 임시 폴더를 받아 기록기를 내주는 준비물
def journal(tmp_path):
    from app.adapters.jsonl_log import Jsonl

    return Jsonl(tmp_path / "logs")


@pytest.fixture
# 가상 시계를 내주는 준비물
def clock():
    from app.adapters.clock import Fake

    return Fake(START)


@pytest.fixture
# 앱을 가상 시계·임시 기록으로 띄우는 준비물. 틱·정적 서빙은 끔
def builder(config, clock, journal):
    from app.main import factory
    from fastapi.testclient import TestClient

    clients = []

    # 설정과 추가 인자를 받아 클라이언트를 만드는 함수
    def product(cfg=None, **kwargs):
        kwargs = {
            "clock": clock,
            "experiment_log": journal,
            "start_ticker": False,  # 1초 틱 태스크는 띄우지 않음
            "static_dir": None,
            **kwargs,
        }
        client = TestClient(factory(config if cfg is None else cfg, **kwargs))
        clients.append(client.__enter__())
        return client

    yield product
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
# 기본 설정으로 띄운 클라이언트를 내주는 준비물
def client(builder):
    return builder()


@pytest.fixture
# 앱 안의 실험 서비스를 내주는 준비물
def service(client):
    return client.app.state.service
