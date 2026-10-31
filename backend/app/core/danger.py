from __future__ import annotations

import math
from app.core.model import ZONES, guard
from dataclasses import dataclass

STAGES = ("safe", "caution", "warning", "evacuate")  # 정상·주의·경계·침수. 뒤가 높음
RANK = {stage: i for i, stage in enumerate(STAGES)}


# 경보 규칙: 구역별 한계 수위(m), 주의·경계 도달 상한(초), 침수 해제 비율, 내림 유지 시간(초)
@dataclass(frozen=True)
class Rule:
    thresholds_m: dict[str, float]
    caution_eta_s: float
    warning_eta_s: float
    release_ratio: float
    release_hold_s: float

    # config 의 zones.*.threshold_mm 와 alerts 로 규칙을 만듦. 쓸 수 없는 값은 ValueError
    @classmethod
    def config(cls, cfg: dict) -> Rule:
        thresholds = {z: cfg["zones"][z]["threshold_mm"] / 1000.0 for z in ZONES}
        for z, threshold in thresholds.items():
            ok = math.isfinite(threshold) and threshold > 0
            guard(ok, f"{z} 구역 한계 수위는 유한한 양수여야 한다")
        alerts = cfg["alerts"]
        caution, warning = alerts["caution_eta_s"], alerts["warning_eta_s"]
        ratio, hold = alerts["release_ratio"], alerts["release_hold_s"]
        ok = math.isfinite(caution) and 0 < warning <= caution
        guard(ok, "경계 도달 상한은 0 초과, 주의 도달 상한 이하여야 한다")
        guard(0 < ratio <= 1, "해제 비율은 0 초과 1 이하여야 한다")
        guard(math.isfinite(hold) and hold >= 0, "유지 시간은 0 이상 유한해야 한다")
        return cls(thresholds, float(caution), float(warning), float(ratio), float(hold))


# 구역 하나의 감시 상태: 단계, 도달 예상 초(안 오르면 None), 내림 유지가 시작된 경과 초
@dataclass(frozen=True)
class Watch:
    stage: str = "safe"
    eta_s: float | None = None
    calm_since_s: float | None = None


# 수위·변화율로 (단계, 도달 초)를 판정. 한계 이상이면 침수, 안 오르면 정상. 침수 유지 중엔 해제 띠
def outlook(
    level_m: float, rate_m_per_s: float, threshold_m: float, rule: Rule, held: str = "safe"
) -> tuple[str, float | None]:
    guard(math.isfinite(level_m) and math.isfinite(rate_m_per_s), "수위와 변화율은 유한해야 한다")
    bar = threshold_m * (rule.release_ratio if held == "evacuate" else 1.0)  # 침수를 푸는 수위
    if level_m >= bar:
        return "evacuate", 0.0
    if rate_m_per_s <= 0:
        return "safe", None
    eta = (threshold_m - level_m) / rate_m_per_s  # 지금 변화율로 한계까지 걸리는 초
    if eta <= rule.warning_eta_s:
        return "warning", eta
    if eta <= rule.caution_eta_s:
        return "caution", eta
    return "safe", eta


# 감시 상태를 한 tick 앞으로. 오르면 바로, 내리면 유지 시간 뒤에 바뀜. 유지 중엔 단계·도달 초 그대로
def verdict(
    watch: Watch,
    level_m: float,
    rate_m_per_s: float,
    threshold_m: float,
    rule: Rule,
    elapsed_s: float,
) -> Watch:
    stage, eta = outlook(level_m, rate_m_per_s, threshold_m, rule, watch.stage)
    if RANK[stage] >= RANK[watch.stage]:
        return Watch(stage, eta, None)
    since = elapsed_s if watch.calm_since_s is None else watch.calm_since_s  # 내림이 시작된 초
    if elapsed_s - since >= rule.release_hold_s:
        return Watch(stage, eta, None)
    return Watch(watch.stage, watch.eta_s, since)


# 모든 구역의 감시 상태를 한 tick 앞으로. 없는 구역은 정상에서 시작
def patrol(
    watches: dict[str, Watch],
    levels_m: dict[str, float],
    rates_m_per_s: dict[str, float],
    elapsed_s: float,
    rule: Rule,
) -> dict[str, Watch]:
    return {
        z: verdict(
            watches.get(z, Watch()),
            levels_m[z],
            rates_m_per_s[z],
            rule.thresholds_m[z],
            rule,
            elapsed_s,
        )
        for z in ZONES
    }


# 정상이 아닌 구역의 경보를 A·B·C 순서로 {"zone", "stage", "etaSec"} 모양으로 냄
def bulletin(watches: dict[str, Watch]) -> tuple[dict, ...]:
    return tuple(
        {"zone": z, "stage": watch.stage, "etaSec": watch.eta_s}
        for z in ZONES
        if (watch := watches.get(z, Watch())).stage != "safe"
    )


# 단계가 바뀐 구역을 (구역, 이전 단계, 지금 단계, 도달 초)로 A·B·C 순서로 냄
def shifts(
    before: dict[str, Watch], after: dict[str, Watch]
) -> list[tuple[str, str, str, float | None]]:
    return [
        (z, before.get(z, Watch()).stage, after[z].stage, after[z].eta_s)
        for z in ZONES
        if before.get(z, Watch()).stage != after[z].stage
    ]
