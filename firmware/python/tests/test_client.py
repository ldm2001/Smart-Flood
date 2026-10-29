import client
import http.server
import json
import pytest
import socket
import socketserver
import threading
import time


# 받은 요청을 기록하고 정해진 상태 코드로 답하는 서버
class Handler(http.server.BaseHTTPRequestHandler):
    status = 200
    seen = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        Handler.seen.append((self.path, self.headers.get("Content-Type"), json.loads(raw)))
        self.send_response(Handler.status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


# getfqdn 역조회를 건너뛰는 서버. DNS 응답이 없는 맥에서는 그 조회 하나에 수십 초가 걸림
class Server(http.server.HTTPServer):
    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


@pytest.fixture
def server():
    Handler.seen = []
    Handler.status = 200
    httpd = Server(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05})
    worker.daemon = True
    worker.start()
    yield "http://127.0.0.1:{}".format(httpd.server_address[1])
    httpd.shutdown()
    httpd.server_close()


# 주소를 호스트·포트·경로로 나누고, 포트 생략은 80, 경로 생략은 / 인지 검사
def test_parse_splits_the_url():
    parsed = client.parse("http://192.168.0.10:8000/api/ingest")
    assert parsed == ("192.168.0.10", 8000, "/api/ingest")
    assert client.parse("http://flood.local") == ("flood.local", 80, "/")


# https 는 받지 않는지 검사(보드는 TLS 없이 보냄)
def test_parse_rejects_https():
    with pytest.raises(ValueError):
        client.parse("https://192.168.0.10/api/ingest")


# JSON 본문이 그대로 닿고 상태 코드가 돌아오는지 검사
def test_post_delivers_json(server):
    body = {"deviceId": "esp32_1", "seq": 3}
    assert client.post(server + "/api/ingest", body, 0.4) == 200
    assert Handler.seen == [("/api/ingest", "application/json", body)]


# 서버가 거절(422)하면 그 코드를 돌려주는지 검사
def test_post_returns_the_server_status(server):
    Handler.status = 422
    assert client.post(server + "/api/ingest", {}, 0.4) == 422


# 닫힌 포트는 OSError 인지 검사
def test_post_to_a_closed_port_raises():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(OSError):
        client.post("http://127.0.0.1:{}/api/ingest".format(port), {}, 0.4)


# 응답이 없으면 제한 시간 안에 OSError 로 끝나는지 검사
def test_post_gives_up_after_the_timeout():
    quiet = socket.socket()
    quiet.bind(("127.0.0.1", 0))
    quiet.listen(1)
    start = time.monotonic()
    with pytest.raises(OSError):
        client.post("http://127.0.0.1:{}/api/ingest".format(quiet.getsockname()[1]), {}, 0.3)
    assert time.monotonic() - start < 1.5
    quiet.close()


# send 는 2xx 면 조용히 끝나고, 거절되면 상태 코드를 담은 OSError 인지 검사
def test_send_raises_when_the_server_rejects(server):
    assert client.send(server + "/api/ingest", {}, 0.4) is None
    Handler.status = 422
    with pytest.raises(OSError, match="422"):
        client.send(server + "/api/ingest", {}, 0.4)


# localhost 처럼 IPv6 주소(::1)가 먼저 풀리는 이름으로도 닿는지 검사. IPv4 항목을 골라 연결해야 함
def test_post_reaches_the_server_through_localhost(server):
    url = server.replace("127.0.0.1", "localhost")
    assert client.post(url + "/api/ingest", {"seq": 0}, 0.4) == 200


# 서버 주소 정리: 양끝 공백과 끝 슬래시 제거, 빈 값은 그대로, http:// 가 아니면 ValueError 인지 검사
def test_base_normalizes_the_server_url():
    assert client.base("http://192.168.0.10:8000/") == "http://192.168.0.10:8000"
    assert client.base(" http://h:1 ") == "http://h:1"
    assert client.base("") == ""
    with pytest.raises(ValueError):
        client.base("192.168.0.10:8000")
