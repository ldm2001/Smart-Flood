import host
import io
import json
import level
import pytest


# 수위→전압 변환이 level.mm 의 역함수이고, 10 mm 는 이론 영점 480 mV 인지 검사
def test_volts_inverts_the_line():
    line = level.Line()
    assert host.volts(level.mm(1000.0, line), line) == pytest.approx(1000.0)
    assert host.volts(10.0) == pytest.approx(480.0)


# 가짜 센서가 시작 수위에서 초당 ramp 만큼 오르는지 검사
def test_fake_sensor_ramps_with_the_clock():
    clock = iter([0.0, 0.0, 5.0])
    read = host.fake(40.0, 2.0, lambda: next(clock))
    assert read() == pytest.approx(host.volts(40.0))
    assert read() == pytest.approx(host.volts(50.0))


# 줄 흐름에서 첫 토큰이 숫자인 줄만 mV 로 읽고, 끝나면 마지막 값을 유지하는지 검사
def test_lines_skip_text_and_keep_the_last_value():
    read = host.lines(iter(["x", "", "1000", "abc 2", "1100.5\n"]))
    assert (read(), read(), read()) == (1000.0, 1100.5, 1100.5)


# 아무 숫자도 없이 끝나면 0 mV(센서 이상으로 보냄)인지 검사
def test_lines_without_numbers_give_zero():
    assert host.lines(iter(["x"]))() == 0.0


# depth 스케치 출력처럼 mV 앞에 다른 숫자(millis)가 있으면 mV 바로 앞 토큰을 읽는지 검사
def test_lines_read_the_token_before_mv():
    read = host.lines(iter(["1500 ms raw 615  482 mV", "1600 ms raw 620  484.5 mV"]))
    assert (read(), read()) == (482.0, 484.5)


# 명령행 선택지와 기본값 검사
def test_options_have_defaults():
    plain = host.options([])
    assert (plain.server, plain.mm, plain.ramp) == ("", 40.0, 0.0)
    assert (plain.stdin, plain.seconds) == (False, None)
    full = host.options(["--server", "http://h:1", "--mm", "60", "--ramp", "0.5", "--seconds", "3"])
    assert (full.server, full.mm, full.ramp, full.seconds) == ("http://h:1", 60.0, 0.5, 3)


# --server 는 끝 슬래시를 떼고, http:// 가 아니면 시작 전에 거절하는지 검사
def test_options_normalize_the_server():
    assert host.options(["--server", "http://h:1/"]).server == "http://h:1"
    with pytest.raises(SystemExit):
        host.options(["--server", "h:1"])


# 서버 주소가 없으면 메시지를 JSON 줄로 찍고, 시각은 시작 기준 ms 인지 검사
def test_mac_prints_when_there_is_no_server():
    out = io.StringIO()
    clock = iter([10.0, 10.5])
    mac = host.Mac("", lambda: 480.0, clock=lambda: next(clock), out=out)
    mac.post({"seq": 0})
    assert json.loads(out.getvalue()) == {"seq": 0}
    assert mac.now_ms() == 500


# 주소는 서버 + /api/ingest 이고, 전송 함수의 예외는 그대로 올려 loop 가 로그를 남기게 하는지 검사
def test_mac_posts_to_the_ingest_path():
    calls = []

    def poster(url, body, timeout_s):
        calls.append((url, body, timeout_s))
        raise OSError("서버 응답 422")

    mac = host.Mac("http://h:1", lambda: 480.0, poster=poster)
    with pytest.raises(OSError):
        mac.post({"seq": 0})
    assert calls == [("http://h:1/api/ingest", {"seq": 0}, 0.4)]
