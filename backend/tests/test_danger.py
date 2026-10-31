import copy
import math
import pytest
from app.core.danger import (
    RANK,
    STAGES,
    Rule,
    Watch,
    bulletin,
    countdown,
    outlook,
    patrol,
    shifts,
    verdict,
)
from app.core.model import ZONES

BAD_RULE_CONFIGS = {  # 이름 → 설정을 망가뜨리는 함수. 전부 시작 때 ValueError 여야 함
    "threshold-zero": lambda c: c["zones"]["A"].update(threshold_mm=0),
    "threshold-negative": lambda c: c["zones"]["B"].update(threshold_mm=-1),
    "threshold-nan": lambda c: c["zones"]["C"].update(threshold_mm=math.nan),
    "threshold-inf": lambda c: c["zones"]["C"].update(threshold_mm=math.inf),
    "warning-over-caution": lambda c: c["alerts"].update(warning_eta_s=61),
    "warning-zero": lambda c: c["alerts"].update(warning_eta_s=0),
    "caution-inf": lambda c: c["alerts"].update(caution_eta_s=math.inf),
    "ratio-zero": lambda c: c["alerts"].update(release_ratio=0),
    "ratio-over-one": lambda c: c["alerts"].update(release_ratio=1.1),
    "hold-negative": lambda c: c["alerts"].update(release_hold_s=-1),
    "hold-inf": lambda c: c["alerts"].update(release_hold_s=math.inf),
}

OUTLOOKS = {  # 이름 → (수위 m, 변화율 m/s, 유지 중 단계, 기대 단계, 기대 도달 초). A 한계 0.040
    "dry-still": (0.0, 0.0, "safe", "safe", None),
    "falling": (0.010, -0.001, "safe", "safe", None),
    "rising-far": (0.010, 0.0001, "safe", "safe", 300.0),
    "just-outside-caution": (0.0339, 0.0001, "safe", "safe", 61.0),
    "just-inside-caution": (0.0341, 0.0001, "safe", "caution", 59.0),
    "caution": (0.035, 0.0001, "safe", "caution", 50.0),
    "just-outside-warning": (0.0369, 0.0001, "safe", "caution", 31.0),
    "just-inside-warning": (0.0371, 0.0001, "safe", "warning", 29.0),
    "warning": (0.039, 0.0001, "safe", "warning", 10.0),
    "at-threshold": (0.040, 0.0001, "safe", "evacuate", 0.0),
    "over-threshold-falling": (0.045, -0.001, "safe", "evacuate", 0.0),
    "over-threshold-still": (0.045, 0.0, "safe", "evacuate", 0.0),
    "held-evacuate-in-band": (0.037, -0.001, "evacuate", "evacuate", 0.0),
    "held-evacuate-below-band": (0.0359, -0.001, "evacuate", "safe", None),
    "held-caution-no-band": (0.037, -0.001, "caution", "safe", None),
    "rising-slowly": (0.0, 1e-9, "safe", "safe", 4e7),
}

COUNTDOWNS = {  # 이름 → (도달 초, 기대 정수 초). 올림이라 1 초 안도 1, 0 은 한계 도달뿐
    "under-one": (0.3, 1),
    "half": (2.5, 3),
    "whole": (30.0, 30),
    "just-over": (30.000001, 31),
    "long-fraction": (59.70588235294117, 60),
    "reached": (0.0, 0),
    "still": (None, None),
    "endless": (math.inf, None),
}


# 설정 사본에 손을 댄 규칙 설정을 만드는 보조 함수
def spoiled(config, damage):
    cfg = copy.deepcopy(config)
    damage(cfg)
    return cfg


# 단계가 정상·주의·경계·침수 순으로 높아지는지 검사
def test_stages_rank_from_safe_to_evacuate():
    assert STAGES == ("safe", "caution", "warning", "evacuate")
    assert [RANK[s] for s in STAGES] == [0, 1, 2, 3]


# 설정의 구역 한계(mm → m)와 경보 시간을 읽는지 검사
def test_rule_reads_thresholds_in_metres_and_alert_timings(config):
    rule = Rule.config(config)
    assert rule.thresholds_m == pytest.approx({"A": 0.040, "B": 0.070, "C": 0.110})
    assert (rule.caution_eta_s, rule.warning_eta_s) == (60, 30)
    assert (rule.release_ratio, rule.release_hold_s) == (0.9, 10)


@pytest.mark.parametrize("damage", BAD_RULE_CONFIGS.values(), ids=BAD_RULE_CONFIGS.keys())
# 쓸 수 없는 경보 설정이 ValueError 인지 검사
def test_unusable_rule_config_fails(config, damage):
    with pytest.raises(ValueError):
        Rule.config(spoiled(config, damage))


@pytest.mark.parametrize("case", OUTLOOKS.values(), ids=OUTLOOKS.keys())
# 수위·변화율로 단계와 도달 초를 판정하는지 검사(한계 이상이면 침수, 안 오르면 정상)
def test_outlook_grades_level_and_eta(config, case):
    level, rate, held, stage, eta = case
    rule = Rule.config(config)
    got_stage, got_eta = outlook(level, rate, rule.thresholds_m["A"], rule, held)
    assert got_stage == stage
    assert got_eta == (pytest.approx(eta) if eta is not None else None)


@pytest.mark.parametrize("level, rate", [(math.nan, 0.0), (0.01, math.inf), (-math.inf, 0.0)])
# 수위나 변화율이 유한하지 않으면 ValueError 인지 검사
def test_outlook_refuses_non_finite_inputs(config, level, rate):
    rule = Rule.config(config)
    with pytest.raises(ValueError):
        outlook(level, rate, rule.thresholds_m["A"], rule)


@pytest.mark.parametrize("eta, sec", COUNTDOWNS.values(), ids=COUNTDOWNS.keys())
# 도달 초를 올림한 정수 초로 내고, 없거나 무한이면 None 인지 검사
def test_countdown_ceils_the_eta_to_whole_seconds(eta, sec):
    got = countdown(eta)
    assert got == sec and type(got) is type(sec)


# 오르는 쪽 전환은 바로 되는지 검사
def test_verdict_raises_the_stage_immediately(config):
    rule = Rule.config(config)
    thr = rule.thresholds_m["A"]
    first = verdict(Watch(), 0.035, 0.0001, thr, rule, 5.0)
    assert first == Watch("caution", pytest.approx(50.0), None)
    second = verdict(first, 0.039, 0.0001, thr, rule, 6.0)
    assert second == Watch("warning", pytest.approx(10.0), None)
    third = verdict(second, 0.040, 0.0001, thr, rule, 7.0)
    assert third == Watch("evacuate", 0.0, None)


# 내리는 쪽 전환은 유지 시간(10 초) 뒤에만 되고, 그동안 단계와 도달 초는 그대로인지 검사
def test_verdict_lowers_the_stage_only_after_the_hold(config):
    rule = Rule.config(config)
    thr = rule.thresholds_m["A"]
    watch = Watch("warning", 10.0, None)
    for t in (20.0, 25.0, 29.0):
        watch = verdict(watch, 0.010, -0.001, thr, rule, t)
        assert watch == Watch("warning", 10.0, 20.0)
    assert verdict(watch, 0.010, -0.001, thr, rule, 30.0) == Watch("safe", None, None)


# 유지 중에 다시 오르면 유지가 취소되는지 검사
def test_a_rise_during_the_hold_cancels_it(config):
    rule = Rule.config(config)
    thr = rule.thresholds_m["A"]
    watch = Watch("warning", 10.0, 20.0)
    after = verdict(watch, 0.038, 0.0001, thr, rule, 25.0)
    assert after == Watch("warning", pytest.approx(20.0), None)


# 침수에서 한 단계만 내려가도 유지되고, 유지가 끝나면 그때의 단계로 가는지 검사
def test_the_hold_releases_to_the_current_stage(config):
    rule = Rule.config(config)
    thr = rule.thresholds_m["A"]
    watch = Watch("evacuate", 0.0, None)
    watch = verdict(watch, 0.035, 0.0001, thr, rule, 0.0)  # 해제 띠(0.036) 아래, 50 초 뒤 도달
    assert watch == Watch("evacuate", 0.0, 0.0)
    released = verdict(watch, 0.035, 0.0001, thr, rule, 10.0)
    assert released == Watch("caution", pytest.approx(50.0), None)


# 유지 시간이 0 이면 바로 내려가는지 검사
def test_zero_hold_lowers_the_stage_at_once(config):
    rule = Rule.config(spoiled(config, lambda c: c["alerts"].update(release_hold_s=0)))
    thr = rule.thresholds_m["A"]
    watch = verdict(Watch("warning", 10.0, None), 0.0, 0.0, thr, rule, 3.0)
    assert watch == Watch("safe", None, None)


# 구역마다 제 한계로 판정하고, 없는 구역은 정상에서 시작하는지 검사
def test_patrol_grades_every_zone_with_its_own_threshold(config):
    rule = Rule.config(config)
    levels = {"A": 0.0, "B": 0.069, "C": 0.110}
    rates = {"A": 0.0, "B": 0.001, "C": -0.001}
    watches = patrol({}, levels, rates, 7.0, rule)
    assert set(watches) == set(ZONES)
    assert watches["A"] == Watch("safe", None, None)
    assert watches["B"] == Watch("warning", pytest.approx(1.0), None)
    assert watches["C"] == Watch("evacuate", 0.0, None)


# 경보 목록은 정상이 아닌 구역만 A·B·C 순서로, 도달 초는 올림한 정수로 담는지 검사
def test_bulletin_lists_only_zones_above_safe_in_zone_order():
    watches = {
        "C": Watch("warning", 12.5, None),
        "B": Watch("safe", 200.0, None),
        "A": Watch("evacuate", 0.0, 3.0),
    }
    assert bulletin(watches) == (
        {"zone": "A", "stage": "evacuate", "etaSec": 0.0},
        {"zone": "C", "stage": "warning", "etaSec": 13},
    )
    assert bulletin({z: Watch() for z in ZONES}) == ()


# 단계가 바뀐 구역만 (구역, 이전, 지금, 올림한 도달 초)로 A·B·C 순서로 내는지 검사
def test_shifts_lists_zones_whose_stage_changed():
    before = {"A": Watch(), "B": Watch("caution", 40.0, None), "C": Watch("warning", 20.0, None)}
    after = {
        "A": Watch("caution", 54.2, None),
        "B": Watch("caution", 35.0, None),
        "C": Watch("safe", None, None),
    }
    assert shifts(before, after) == [("A", "safe", "caution", 55), ("C", "warning", "safe", None)]
    assert shifts(after, after) == []
    assert shifts({}, {"A": Watch(), "B": Watch(), "C": Watch("caution", 0.4, None)}) == [
        ("C", "safe", "caution", 1)
    ]
