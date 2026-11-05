import ipaddress
import pytest
import socket
from app.adapters.solapi import NAMES
from pathlib import Path
from tests.helpers import START

# 설정 파일 config.yaml 의 경로(backend 폴더 안)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


# 시험 중 바깥 네트워크 연결이 막혔을 때 나는 오류(OSError 라 기존 연결 오류 처리와 같음)
class Offline(OSError):
    pass


# 같은 컴퓨터 주소인지(127.x·::1·localhost·빈 주소)
def nearby(host) -> bool:
    if host is None:
        return True
    name = host.decode() if isinstance(host, bytes) else str(host)
    if name.lower() in ("", "localhost", "localhost."):
        return True
    try:
        address = ipaddress.ip_address(name.split("%")[0])  # IPv6 범위 표시 제거
    except ValueError:
        return False  # 그 밖의 이름은 바깥으로 봄
    return address.is_loopback or address.is_unspecified


@pytest.fixture(autouse=True)
# 바깥 네트워크 연결을 막는 준비물. 같은 컴퓨터 주소와 AF_UNIX 만 허용
def offline(monkeypatch):
    connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
    getaddrinfo, gethostbyname = socket.getaddrinfo, socket.gethostbyname

    # 연결 대상이 허용 범위인지 검사, 아니면 Offline
    def inspection(sock, address):
        if sock.family == getattr(socket, "AF_UNIX", None):
            return
        host = address[0] if isinstance(address, tuple) else address
        if not nearby(host):
            raise Offline(f"시험 중 바깥 연결 차단: {host}")

    # socket.connect 대역
    def connection(sock, address):
        inspection(sock, address)
        return connect(sock, address)

    # socket.connect_ex 대역
    def attempt(sock, address):
        inspection(sock, address)
        return connect_ex(sock, address)

    # socket.getaddrinfo 대역
    def lookup(host, *args, **kwargs):
        if not nearby(host):
            raise Offline(f"시험 중 이름 풀이 차단: {host}")
        return getaddrinfo(host, *args, **kwargs)

    # socket.gethostbyname 대역
    def resolution(host):
        if not nearby(host):
            raise Offline(f"시험 중 이름 풀이 차단: {host}")
        return gethostbyname(host)

    monkeypatch.setattr(socket.socket, "connect", connection)
    monkeypatch.setattr(socket.socket, "connect_ex", attempt)
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    monkeypatch.setattr(socket, "gethostbyname", resolution)


@pytest.fixture(autouse=True)
# 셸에 불러온 발송 환경 변수를 시험마다 지우는 준비물. 실제 키·번호가 시험에 섞이지 않게
def keyless(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


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
