import pytest
from pathlib import Path
from tests.helpers import START

# 설정 파일 config.yaml 의 경로(backend 폴더 안)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture(scope="session")  # 테스트 전체에서 한 번만 만드는 준비물
# 설정 딕셔너리를 내주는 준비물
def config():
    from app.config import settings

    return settings(CONFIG_PATH)  # 설정 파일을 읽어 반환


@pytest.fixture(scope="session")  # 테스트 전체에서 한 번만 만드는 준비물
# 모델 계수를 내주는 준비물
def params(config):
    from app.core.model import Params

    return Params.config(config)  # 설정으로 계수를 만들어 반환


@pytest.fixture(scope="session")  # 테스트 전체에서 한 번만 만드는 준비물
# 사례별 (계수, 1초 상태 목록) 준비물. 검사 1·2 가 같이 기록
def runs(config, params):
    from tests.scenarios import EXPERIMENT, EXPERIMENT_S, flood, stress, trace

    stressed = stress(config)  # 빗물받이를 좁혀 수위가 넘치게 만든 가혹한 계수
    return {  # 사례 이름 → (계수, 상태 목록) 을 반환
        # 기본 계수로 시나리오를 돌린다
        "default": (params, trace(params, EXPERIMENT, EXPERIMENT_S)),
        # 가혹한 계수로 시나리오를 돌린다
        "stressed": (stressed, trace(stressed, EXPERIMENT, EXPERIMENT_S)),
        # 처음부터 물이 찬 상태에서 시나리오를 돌린다
        "flooded": (params, trace(params, EXPERIMENT, EXPERIMENT_S, flood(params))),
    }


# 테스트 전체에서 한 번 만들고, 모든 테스트에 자동으로 붙는다
@pytest.fixture(scope="session", autouse=True)
# 테스트가 logs 폴더를 건드리지 않는지 지키는 준비물
def sentinel():
    from app.adapters.jsonl_log import LOG_DIR

    # 폴더 안 파일 목록(이름, 크기)을 만드는 안쪽 함수
    def entries():
        if not LOG_DIR.is_dir():  # 폴더가 없으면
            return []  # 빈 목록을 반환
        # 파일 이름과 크기를 이름순으로 반환
        return sorted((p.name, p.stat().st_size) for p in LOG_DIR.iterdir())

    before = entries()  # 테스트 전 목록을 적어 둔다
    yield  # 여기서 테스트들이 돈다
    # 끝난 뒤 목록이 같아야 한다. 다르면 실패
    assert entries() == before, f"테스트가 {LOG_DIR} 를 바꿨다"


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 임시 폴더를 받아 기록기를 내주는 준비물
def journal(tmp_path):
    from app.adapters.jsonl_log import Jsonl

    return Jsonl(tmp_path / "logs")  # 임시 폴더 안 logs 에 쓰는 기록기


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 가상 시계를 내주는 준비물
def clock():
    from app.adapters.clock import Fake

    return Fake(START)  # START 에서 출발하는 시계


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 앱을 가상 시계·임시 기록으로 띄우는 준비물. 틱·정적 서빙은 끈다
def builder(config, clock, journal):
    from app.main import factory
    from fastapi.testclient import TestClient

    clients = []  # 띄운 클라이언트를 모아 둘 목록

    # 설정과 추가 인자를 받아 클라이언트를 만드는 함수
    def product(cfg=None, **kwargs):
        kwargs = {  # 기본 인자 묶음을 만듦
            "clock": clock,  # 가상 시계를 기록
            "experiment_log": journal,  # 임시 기록기를 기록
            "start_ticker": False,  # 1초 틱 태스크는 띄우지 않음
            "static_dir": None,  # 정적 파일은 서빙하지 않음
            **kwargs,  # 호출자가 준 인자로 기본값을 덮는다
        }
        # 앱을 만들어 클라이언트로 감싼다
        client = TestClient(factory(config if cfg is None else cfg, **kwargs))
        clients.append(client.__enter__())  # 클라이언트를 열어 목록에 담는다
        return client  # 클라이언트를 반환

    yield product  # 만드는 함수를 테스트에 내반환
    for client in clients:  # 테스트가 끝나면 열었던 클라이언트를 하나씩 보고
        client.__exit__(None, None, None)  # 모두 닫는다


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 기본 설정으로 띄운 클라이언트를 내주는 준비물
def client(builder):
    return builder()  # 앱 클라이언트를 만들어 반환


@pytest.fixture  # 테스트마다 새로 만드는 준비물
# 앱 안의 실험 서비스를 내주는 준비물
def service(client):
    return client.app.state.service  # 앱 상태에 든 서비스를 반환
