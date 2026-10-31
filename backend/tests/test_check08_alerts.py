import copy
import json
import math
import pytest
from datetime import timedelta
from tests.helpers import START, Mailbox, Script, chronicle, footage, lapse, readout

ID = "EXP-20261022-001"
START_URL = "/api/experiment/start"
STOP_URL = "/api/experiment/stop"
RESET_URL = "/api/experiment/reset"
RAIN_URL = "/api/rain"
BLOCKAGE_URL = "/api/blockage"
EVENTS_URL = f"/api/logs/{ID}/events"
RAIN_MM_PER_H = 150.0  # 상한의 비
THRESHOLD_MM = 6.0  # 시험용 B 한계 수위(mm). 기본 70 mm 는 ASSUMED 개구로는 닿지 않음
B_BLOCKED = {"blockage": {"type": "full", "location": "INLET-03"}}  # B 의 빗물받이를 완전히 막음
EVACUATE = [{"zone": "B", "stage": "evacuate", "etaSec": 0}]  # 침수 경보 하나
A_ONLY = {"A": "ok", "B": "absent", "load": "absent"}  # REV16 처럼 A 센서만 있음
KICKS = {"dry-45": (0.0, 45.0), "dry-60": (0.0, 60.0), "storm-80": (150.0, 80.0)}  # (강우, A mm)


# 가상 시계 시작 시각에서 seconds 초 뒤의 기록 시각 글자
def stamp(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


# POST 를 보내 성공(200)을 확인하고 본문을 돌려주는 도우미
def answer(client, path: str, body: dict | None = None) -> dict:
    response = client.post(path, json=body or {})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
# B 가 한계에 닿는 시험 설정. 완전 막힘은 닫히고 월류 경계는 닿지 않게 높임. 선형 상승이라 dt 0.5
def cfg(config):
    cfg = copy.deepcopy(config)
    cfg["dt_s"] = 0.5
    cfg["zones"]["B"]["threshold_mm"] = THRESHOLD_MM
    cfg["blockage_open_ratio"]["full"] = 0.0
    for link in cfg["links"]:
        link["sill_m"] = 1.0
    cfg["alerts"] = {
        "caution_eta_s": 60, "warning_eta_s": 30, "release_ratio": 0.9, "release_hold_s": 10
    }
    return cfg


@pytest.fixture
# 시나리오의 예상 틱. B 는 틱마다 rise 만큼 선형으로 오름(월류·배수 없음). 한계까지 84.7 틱
def timing(cfg):
    zone = cfg["zones"]["B"]
    rise = zone["share"] * RAIN_MM_PER_H / 3.6e6 * cfg["model_area_m2"] / zone["S_m2"]  # m/s
    steps = THRESHOLD_MM / 1000 / rise
    alerts = cfg["alerts"]
    evacuate = math.ceil(steps)  # 85
    return {
        "steps": steps,
        "caution": math.ceil(steps - alerts["caution_eta_s"]),  # 25
        "warning": math.ceil(steps - alerts["warning_eta_s"]),  # 55
        "evacuate": evacuate,
        "release": evacuate + 1 + alerts["release_hold_s"],  # 내림 시작 틱 + 유지 시간 = 96
    }


# 틱 n 에 기대하는 B 의 단계
def phase(n: int, timing: dict) -> str:
    if n >= timing["release"]:
        return "safe"
    for stage in ("evacuate", "warning", "caution"):
        if n >= timing[stage]:
            return stage
    return "safe"


@pytest.fixture
# 알림기 가짜를 내주는 준비물
def mailbox():
    return Mailbox()


@pytest.fixture
# 시나리오를 돌리고 멈춘 클라이언트. 상한의 비·완전 막힘으로 B 가 한계를 넘고, 비를 그쳐 해제
def voyage(builder, clock, cfg, mailbox, timing):
    client = builder(cfg, source=Script(None), notifier=mailbox)
    answer(client, START_URL, B_BLOCKED)
    answer(client, RAIN_URL, {"mmPerHour": RAIN_MM_PER_H})
    service = client.app.state.service
    lapse(clock, service, timing["evacuate"])
    answer(client, RAIN_URL, {"mmPerHour": 0})
    answer(client, BLOCKAGE_URL, {"type": "none"})
    lapse(clock, service, timing["release"] - timing["evacuate"] + 2)
    answer(client, STOP_URL)
    return client


# 대기 중 /api/state 가 구역마다 설정의 한계 수위(mm)를 싣고 경보는 비어 있는지 검사
def test_idle_state_carries_the_zone_thresholds(client, config):
    body = client.get("/api/state").json()
    for z in ("A", "B", "C"):
        assert body["zones"][z]["thresholdMm"] == config["zones"][z]["threshold_mm"]
    assert body["alerts"] == []


# 틱마다 B 의 단계가 정상→주의→경계→침수로 오르고 유지 시간 뒤 정상으로 내리는지 검사
def test_stages_follow_the_eta_on_the_model_depth(voyage, journal, timing):
    states = chronicle(journal, ID)
    assert [s["elapsedSec"] for s in states] == list(range(1, timing["release"] + 3))
    stages = [[(a["zone"], a["stage"]) for a in s["alerts"]] for s in states]
    expected = [
        [] if phase(n, timing) == "safe" else [("B", phase(n, timing))]
        for n in range(1, len(states) + 1)
    ]
    assert stages == expected


# 주의·경계의 etaSec 가 지금 변화율로 한계까지 남은 초이고 침수는 0 인지 검사
def test_eta_is_the_seconds_left_to_the_threshold(voyage, journal, timing):
    states = chronicle(journal, ID)
    for n in range(timing["caution"], timing["evacuate"]):
        (alert,) = states[n - 1]["alerts"]
        assert alert["etaSec"] == pytest.approx(timing["steps"] - n, abs=1e-6)
    assert states[timing["evacuate"] - 1]["alerts"] == EVACUATE


# 침수 뒤 수위가 해제 띠 아래로 내려도 유지 시간 동안 침수(도달 0)가 남는지 검사
def test_the_evacuate_stage_holds_while_the_level_falls(voyage, journal, cfg, timing):
    states = chronicle(journal, ID)
    held = states[timing["evacuate"] : timing["release"] - 1]  # 내림 첫 틱부터 해제 직전까지
    assert len(held) == cfg["alerts"]["release_hold_s"]
    assert all(s["alerts"] == EVACUATE for s in held)
    band = THRESHOLD_MM * cfg["alerts"]["release_ratio"]  # 해제 띠(mm)
    assert all(s["zones"]["B"]["levelMm"] < band for s in held)


# 단계 전환마다 stage 이벤트가 그 틱의 state 줄 바로 뒤에 남는지 검사
def test_each_stage_change_leaves_a_stage_event(voyage, journal, timing):
    records = list(journal.records(ID))
    events = [r for r in records if r["type"] == "event"]
    assert [(e["kind"], e["zone"], e["previous"], e["stage"], e["elapsedSec"]) for e in events] == [
        ("stage", "B", "safe", "caution", timing["caution"]),
        ("stage", "B", "caution", "warning", timing["warning"]),
        ("stage", "B", "warning", "evacuate", timing["evacuate"]),
        ("stage", "B", "evacuate", "safe", timing["release"]),
    ]
    for e in events:
        assert e["time"] == stamp(e["elapsedSec"])
        before = records[records.index(e) - 1]
        assert (before["type"], before["elapsedSec"]) == ("state", e["elapsedSec"])
    assert events[0]["etaSec"] == pytest.approx(timing["steps"] - timing["caution"])
    assert [e["etaSec"] for e in events[2:]] == [0, None]
    assert events[0]["message"] == "B 구역 주의 (이전 정상, 한계까지 60 초)"
    assert events[1]["message"] == "B 구역 경계 (이전 주의, 한계까지 30 초)"
    assert events[2]["message"] == "B 구역 침수 (이전 경계, 한계 도달)"
    assert events[3]["message"] == "B 구역 정상 (이전 침수)"


# 전환 이벤트가 알림기에 한 번씩, 기록과 같은 모양으로 가는지 검사
def test_the_notifier_gets_every_stage_change_once(voyage, journal, mailbox):
    events = [r for r in journal.records(ID) if r["type"] == "event"]
    assert len(events) == 4
    assert mailbox.events == events


# 이벤트 조회 API 가 stage 이벤트를 기록 순서대로 주는지 검사
def test_the_events_endpoint_lists_the_stage_events(voyage, journal):
    events = [r for r in journal.records(ID) if r["type"] == "event"]
    assert len(events) == 4
    assert voyage.get(EVENTS_URL).json() == {"events": events}


# 재생은 같은 경보를 보이되 event 줄을 더 쓰지 않고 알림도 보내지 않는지 검사
def test_replay_shows_the_alerts_without_events_or_notices(voyage, clock, journal, mailbox):
    recorded = [s["alerts"] for s in chronicle(journal, ID)]
    sent = list(mailbox.events)
    assert len(sent) == 4
    replayed = [json.loads(body)["alerts"] for body in footage(voyage, clock, ID)]
    assert replayed == [[], *recorded, recorded[-1]]  # 0 초, 틱마다, 기록 끝에서 멈춘 상태
    assert sum(r["type"] == "event" for r in journal.records(ID)) == len(sent)
    assert mailbox.events == sent


# 멈춰도 경보는 남고, 초기화하면 비고, 새 회차는 정상에서 시작하는지 검사
def test_reset_and_a_new_start_clear_the_alerts(builder, clock, cfg, timing):
    client = builder(cfg, source=Script(None))
    answer(client, START_URL, B_BLOCKED)
    answer(client, RAIN_URL, {"mmPerHour": RAIN_MM_PER_H})
    service = client.app.state.service
    lapse(clock, service, timing["evacuate"])
    assert client.get("/api/state").json()["alerts"] == EVACUATE
    answer(client, STOP_URL)
    assert client.get("/api/state").json()["alerts"] == EVACUATE
    answer(client, RESET_URL)
    assert client.get("/api/state").json()["alerts"] == []
    answer(client, START_URL, B_BLOCKED)
    lapse(clock, service, 1)
    assert client.get("/api/state").json()["alerts"] == []


@pytest.mark.parametrize("rain, a_mm", KICKS.values(), ids=KICKS.keys())
# A 센서만 있을 때 보정이 끌어올린 A 의 순간 흐름으로 B 에 거짓 경보가 나지 않는지 검사
def test_a_correction_raises_no_false_alert_in_b(builder, clock, config, journal, rain, a_mm):
    readings = {**readout(config, a_mm=a_mm, b_mm=0.0), "distB_mm": None, "weight_g": None}
    client = builder(source=Script(readings, A_ONLY))
    answer(client, START_URL)
    answer(client, RAIN_URL, {"mmPerHour": rain})
    lapse(clock, client.app.state.service, 30)
    states = chronicle(journal, ID)
    assert len(states) == 30
    assert [s["elapsedSec"] for s in states if any(a["zone"] == "B" for a in s["alerts"])] == []
