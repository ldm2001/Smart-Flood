import json
import socket

# 서버에 JSON 을 POST 하는 작은 HTTP 클라이언트. CPython 과 MicroPython 의 socket 공통 부분만 씀
# 보드는 TLS 를 쓰지 않으므로 http 만 받음


# http://host[:port][/path] → (host, port, path)
def parse(url):
    if not url.startswith("http://"):
        raise ValueError("http:// 주소만 받음: " + url)
    rest = url[7:]
    slash = rest.find("/")
    netloc, path = (rest, "/") if slash < 0 else (rest[:slash], rest[slash:])
    host, _, port = netloc.partition(":")
    return host, int(port) if port else 80, path


# 설정의 서버 주소 정리: 양끝 공백과 끝 / 를 떼고, 비면 "" 그대로. http:// 가 아니면 ValueError
def base(url):
    url = url.strip().rstrip("/")
    if url and not url.startswith("http://"):
        raise ValueError("http:// 주소만 받음: " + url)
    return url


# 이름을 풀어 IPv4 주소를 고름. localhost 처럼 IPv6(::1)가 먼저 나오는 이름도 닿게 함
def address(host, port):
    for entry in socket.getaddrinfo(host, port):
        if entry[0] == socket.AF_INET:
            return entry[-1]
    raise OSError("IPv4 주소 없음: " + host)


# JSON 본문을 POST 하고 응답 상태 코드를 돌려줌. 연결과 응답 읽기가 각각 timeout_s 안에 끝나야 함
def post(url, body, timeout_s=0.4):
    host, port, path = parse(url)
    data = json.dumps(body).encode()
    head = (
        "POST {} HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\n"
        "Content-Length: {}\r\nConnection: close\r\n\r\n"
    ).format(path, host, len(data))
    sock = socket.socket()
    sock.settimeout(timeout_s)
    try:
        sock.connect(address(host, port))
        sock.sendall(head.encode() + data)
        line = b""
        while b"\n" not in line:
            chunk = sock.recv(128)
            if not chunk:
                break
            line += chunk
    finally:
        sock.close()
    return status(line)


# post 하고 2xx 가 아니면 OSError. 보드 층의 post 가 그대로 씀
def send(url, body, timeout_s=0.4):
    code = post(url, body, timeout_s)
    if not 200 <= code < 300:
        raise OSError("서버 응답 {}".format(code))


# 상태 줄 "HTTP/1.1 200 OK" 의 코드. 비었거나 HTTP 모양이 아니면 OSError
def status(line):
    parts = line.split(b" ")
    if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
        raise OSError("응답이 HTTP 가 아님: " + repr(line[:40]))
    return int(parts[1])
