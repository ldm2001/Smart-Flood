import copy
import logging
import pytest
import threading
from app.adapters.dispatch import Courier, Dispatch
from app.core import message
from datetime import datetime
from tests.helpers import Mailbox, lapse
from types import SimpleNamespace

ALLOWED = "010" + "1234" + "5678"  # 가짜 허용 번호(조립해 스캔에 안 걸림)
STRANGER = "010" + "9999" + "8888"  # 허용 목록 밖 번호
KEYS = SimpleNamespace(allowed=(ALLOWED,))  # Keys 대신 allowed 만 흉내
ARM_URL = "/api/notifier/arm"
TEST_URL = "/api/notifier/test"
STATE_URL = "/api/state"
LOGGER = "app.adapters.dispatch"


# send(to, body) 를 흉내 내며 부른 횟수를 셈. fail 이면 예외를 냄
class Phone:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    def send(self, to: str, body: str) -> None:
        self.calls.append((to, body))
        if self.fail:
            raise TimeoutError("시험용 실패")


# 일을 바로 부르는 runner(시험에서는 동기)
def direct(job) -> None:
    job()


# config.yaml 의 notifier 에서 mode·상한만 바꾼 것
def settings(config, mode="sms", **changes) -> dict:
    return {**copy.deepcopy(config["notifier"]), "mode": mode, **changes}


# 단계 사건 줄(service 가 만드는 모양 + experimentId)
def shift(stage, previous, zone="B", experiment="EXP-1", eta=12) -> dict:
    return {
        "type": "event",
        "kind": "stage",
        "elapsedSec": 30.0,
        "time": "2026-10-22T10:00:30.000+09:00",
        "message": f"{zone} 구역",
        "zone": zone,
        "stage": stage,
        "previous": previous,
        "etaSec": eta,
        "experimentId": experiment,
    }


# 디스패치 로그 글 목록
def notes(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


# 무장한 sms 디스패치(가짜 전화, 동기 runner)
def armed(config, phone, **changes) -> Dispatch:
    dispatch = Dispatch(settings(config, **changes), KEYS, phone, runner=direct)
    dispatch.arm(True)
    return dispatch


@pytest.mark.parametrize(  # 검증 15: 세 조건 중 하나라도 빠지면 가짜 HTTP 호출 0회
    ("mode", "keys", "arm"),
    [("stub", KEYS, True), ("sms", KEYS, False), ("sms", None, True)],
    ids=["mode-stub", "unarmed", "no-env"],
)
# 조건이 빠지면 보내지 않고 SMS 예정과 본문만 남기는지 검사
def test_a_missing_condition_sends_nothing(config, caplog, mode, keys, arm):
    phone = Phone()
    dispatch = Dispatch(settings(config, mode), keys, phone if keys else None, runner=direct)
    dispatch.arm(arm)  # 조건이 안 맞으면 켜지지 않음
    with caplog.at_level(logging.WARNING):
        dispatch.notice(shift("warning", "caution"))
    assert phone.calls == []
    assert dispatch.armed is False
    body = message.text("warning", "B", 12, datetime.fromisoformat(shift("x", "y")["time"]))
    assert [n for n in notes(caplog) if n.startswith("SMS 예정")] == [
        f"SMS 예정({dispatch.reason}) EXP-1: {body}"
    ]


# 세 조건이 다 맞을 때만 허용 번호로 한 번 보내는지 검사
def test_all_three_conditions_send_once(config, caplog):
    phone = Phone()
    with caplog.at_level(logging.WARNING):
        armed(config, phone).notice(shift("warning", "caution"))
    assert [to for to, _ in phone.calls] == [ALLOWED]
    assert notes(caplog) == [f"SMS 보냄 EXP-1 {message.mask(ALLOWED)}: {phone.calls[0][1]}"]
    assert ALLOWED not in caplog.text  # 번호는 가려서만 남김


# 검증 8: 같은 구역·단계는 한 번, 단계가 오르면 새로, 내려가거나 다시 들어와도 없음
def test_each_zone_stage_sends_once_and_a_rise_sends_again(config):
    phone = Phone()
    dispatch = armed(config, phone)
    for stage, previous in [
        ("caution", "safe"),  # caution 은 문자 없음
        ("warning", "caution"),
        ("warning", "caution"),  # 같은 키
        ("evacuate", "warning"),  # 단계 상승
        ("warning", "evacuate"),  # 내려감
        ("evacuate", "warning"),  # 다시 들어옴
    ]:
        dispatch.notice(shift(stage, previous))
    dispatch.notice(shift("warning", "caution", zone="A"))  # 다른 구역
    dispatch.notice(shift("warning", "caution", experiment="EXP-2"))  # 다른 실험
    assert len(phone.calls) == 4
    assert [b for _, b in phone.calls[:2]] == [
        message.text(s, "B", 12, datetime.fromisoformat(shift(s, "x")["time"]))
        for s in ("warning", "evacuate")
    ]


# 검증 14: 허용 외 번호는 보내기 시도 0회와 SMS 차단
def test_a_number_outside_the_allowlist_is_blocked(config, caplog):
    phone = Phone()
    dispatch = Dispatch(settings(config), KEYS, phone, runner=direct, to=(STRANGER,))
    dispatch.arm(True)
    with caplog.at_level(logging.WARNING):
        dispatch.notice(shift("warning", "caution"))
    assert phone.calls == []
    assert notes(caplog) == [f"SMS 차단 EXP-1 {message.mask(STRANGER)}: 허용 번호가 아니다"]
    assert STRANGER not in caplog.text


# 검증 18: 실험당 상한을 넘기면 더 보내지 않고 SMS 상한
def test_the_experiment_cap_stops_further_sends(config, caplog):
    phone = Phone()
    dispatch = armed(config, phone, max_sms_per_experiment=2)
    with caplog.at_level(logging.WARNING):
        for zone in ("A", "B", "C"):
            dispatch.notice(shift("warning", "caution", zone=zone))
        dispatch.notice(shift("warning", "caution", zone="A", experiment="EXP-2"))  # 다른 실험
    assert len(phone.calls) == 3
    assert "SMS 상한 EXP-1: C 구역 warning, 실험당 2 건" in notes(caplog)


# 보내기 실패는 SMS 실패(예외 종류만)로 남고 예외가 밖으로 나가지 않는지 검사
def test_a_failed_send_is_logged_and_swallowed(config, caplog):
    phone = Phone(fail=True)
    with caplog.at_level(logging.WARNING):
        armed(config, phone).notice(shift("evacuate", "warning", eta=None))
    assert len(phone.calls) == 1
    assert notes(caplog) == [f"SMS 실패 EXP-1 {message.mask(ALLOWED)}: TimeoutError"]
    assert "시험용 실패" not in caplog.text


# 기본 runner 는 notice 를 바로 돌려주고 데몬 스레드에서 보내는지 검사
def test_the_courier_sends_off_the_calling_thread(config):
    gate, done = threading.Event(), threading.Event()
    threads: list[threading.Thread] = []

    class Slow:
        def send(self, to, body):
            gate.wait(5)
            threads.append(threading.current_thread())
            done.set()

    dispatch = Dispatch(settings(config), KEYS, Slow(), runner=Courier())
    dispatch.arm(True)
    dispatch.notice(shift("warning", "caution"))  # 보내기가 막혀 있어도 돌아옴
    assert not done.is_set()
    gate.set()
    assert done.wait(5)
    assert threads[0] is not threading.current_thread() and threads[0].daemon


# 알 수 없는 mode·단계는 기동에서 실패하는지 검사
def test_unknown_mode_or_stage_fails_at_startup(config):
    with pytest.raises(ValueError):
        Dispatch(settings(config, "email"))
    with pytest.raises(ValueError):
        Dispatch(settings(config, sms_stages=["warning", "flood"]))


# /api/state 의 notifier: 기본은 stub·해제, 무장을 모르는 가짜 알림도 stub·해제
def test_state_always_carries_the_notifier(builder):
    assert builder().get(STATE_URL).json()["notifier"] == {"mode": "stub", "armed": False}
    fake = builder(notifier=Mailbox()).get(STATE_URL).json()
    assert fake["notifier"] == {"mode": "stub", "armed": False}


# 무장 조건이 안 맞으면 409(어느 조건인지), 해제는 언제나 200
def test_arming_needs_sms_mode_and_the_environment(builder, config):
    client = builder()  # config 의 mode stub
    answer = client.post(ARM_URL, json={"armed": True})
    assert (answer.status_code, answer.json()) == (
        409,
        {"detail": "notifier.mode 가 sms 가 아니라 무장할 수 없다"},
    )
    assert client.post(ARM_URL, json={"armed": False}).json()["notifier"]["armed"] is False
    bare = builder(notifier=Dispatch(settings(config), None, None, runner=direct))
    answer = bare.post(ARM_URL, json={"armed": True})
    assert (answer.status_code, answer.json()) == (
        409,
        {"detail": "발송 환경 변수가 없어 무장할 수 없다"},
    )
    assert bare.post(ARM_URL, json={"armed": "yes"}).status_code == 422  # 엄격한 bool


# 무장하면 state 에 보이고, 시험 문자는 무장 중에만 서버 실행당 3번까지
def test_arm_and_the_test_message(builder, config, clock):
    phone = Phone()
    client = builder(notifier=Dispatch(settings(config), KEYS, phone, runner=direct))
    answer = client.post(TEST_URL)
    assert (answer.status_code, answer.json()) == (
        409,
        {"detail": "무장하지 않아 시험 문자를 보낼 수 없다"},
    )
    body = client.post(ARM_URL, json={"armed": True}).json()
    assert body["notifier"] == {"mode": "sms", "armed": True}
    assert client.get(STATE_URL).json()["notifier"]["armed"] is True
    for _ in range(config["notifier"]["test_limit"]):
        answer = client.post(TEST_URL)
        assert (answer.status_code, answer.json()) == (
            200,
            {"to": message.mask(ALLOWED), "body": message.trial(clock.now())},
        )
    answer = client.post(TEST_URL)
    assert (answer.status_code, answer.json()) == (
        409,
        {"detail": "시험 문자는 서버 실행당 3 번까지다"},
    )
    assert phone.calls == [(ALLOWED, message.trial(clock.now()))] * 3
    client.post(ARM_URL, json={"armed": False})
    assert client.post(TEST_URL).status_code == 409


# 시험 문자를 보내지 못하면 502(예외 종류만)
def test_a_failed_test_message_is_502(builder, config):
    client = builder(notifier=Dispatch(settings(config), KEYS, Phone(fail=True), runner=direct))
    client.post(ARM_URL, json={"armed": True})
    answer = client.post(TEST_URL)
    assert (answer.status_code, answer.json()) == (
        502,
        {"detail": "시험 문자를 보내지 못했다: TimeoutError"},
    )


# 재생 중에는 무장·시험 문자가 409, 해제는 200, 알림 호출은 없음(검증 7)
def test_replay_refuses_arming_and_the_test_message(builder, config, clock):
    phone = Phone()
    client = builder(notifier=Dispatch(settings(config), KEYS, phone, runner=direct))
    service = client.app.state.service
    client.post("/api/experiment/start", json={"rain": "heavy"})
    client.post("/api/blockage", json={"type": "full", "location": "INLET-01"})
    lapse(clock, service, 40)
    client.post("/api/experiment/stop")
    experiment = client.get(STATE_URL).json()["experimentId"]
    assert client.post("/api/source", json={"mode": "replay", "logId": experiment}).is_success
    answer = client.post(ARM_URL, json={"armed": True})
    assert (answer.status_code, answer.json()) == (
        409,
        {"detail": "재생 중에는 실제 발송을 무장할 수 없다"},
    )
    answer = client.post(TEST_URL)
    assert (answer.status_code, answer.json()) == (
        409,
        {"detail": "재생 중에는 시험 문자를 보낼 수 없다"},
    )
    assert client.post(ARM_URL, json={"armed": False}).status_code == 200
    lapse(clock, service, 40)
    assert phone.calls == []
