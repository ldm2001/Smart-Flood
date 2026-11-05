from __future__ import annotations

import math
from app.core.model import ZONES, guard
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

STAGES = ("safe", "caution", "warning", "evacuate")  # 정상·주의·경계·침수. 뒤가 높음
RANK = {stage: i for i, stage in enumerate(STAGES)}


@dataclass(frozen=True)
# 경보 규칙: 구역별 한계 수위(m), 주의·경계 도달 상한(초), 침수 해제 비율, 내림 유지 시간(초)
# 실측 판정 입력원은 보드처럼 판정: 기울기 창·최소 표본 수·최소 오름, 회차 동안 단계 안 내림
class Rule:
    thresholds_m: dict[str, float]
    caution_eta_s: float
    warning_eta_s: float
    release_ratio: float
    release_hold_s: float
    slope_window_s: float = 20.0  # 실측 기울기 창(초)
    measured_sources: frozenset[str] = frozenset()  # 실측 수위로 판정할 입력원
    slope_min_samples: int = 2  # 실측 기울기를 쓰는 최소 표본 수
    slope_min_m_per_s: float = 0.0  # 이 이하의 실측 기울기는 안 오름으로 봄(m/s)

    @classmethod
    # config 의 zones.*.threshold_mm 와 alerts 로 규칙을 만듦. 쓸 수 없는 값은 ValueError
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
        window = alerts.get("slope_window_s", 20.0)
        sources = alerts.get("measured_sources", [])
        ok = isinstance(window, (int, float)) and math.isfinite(window) and window > 0
        guard(ok, "기울기 창은 0 초과 유한해야 한다")
        ok = isinstance(sources, list) and all(isinstance(s, str) for s in sources)
        guard(ok, "실측 판정 입력원은 문자열 목록이어야 한다")
        samples = alerts.get("slope_min_samples", 2)
        floor = alerts.get("slope_min_mm_s", 0.0)
        ok = isinstance(samples, int) and not isinstance(samples, bool) and samples >= 2
        guard(ok, "최소 표본 수는 2 이상 정수여야 한다")
        ok = isinstance(floor, (int, float)) and math.isfinite(floor) and floor >= 0
        guard(ok, "최소 오름은 0 이상 유한해야 한다")
        return cls(
            thresholds,
            float(caution),
            float(warning),
            float(ratio),
            float(hold),
            float(window),
            frozenset(sources),
            samples,
            floor / 1000.0,
        )


# (경과 초, 수위 m) 표본 중 마지막에서 window_s 안의 것으로 최소제곱 기울기(m/s)를 냄. 모자라면 None
def slope(samples: Sequence[tuple[float, float]], window_s: float) -> float | None:
    if not samples:
        return None
    latest = max(t for t, _ in samples)
    kept = [(t, h) for t, h in samples if latest - t <= window_s]  # 창 안 표본
    mean_t = sum(t for t, _ in kept) / len(kept)
    mean_h = sum(h for _, h in kept) / len(kept)
    spread = sum((t - mean_t) ** 2 for t, _ in kept)  # 시간 분산(0 이면 기울기 없음)
    if len(kept) < 2 or spread == 0:
        return None
    return sum((t - mean_t) * (h - mean_h) for t, h in kept) / spread


# 판정용 실측 기울기(m/s). 최소 오름 이하(내림 포함)는 0
def rising(rate_m_per_s: float, rule: Rule) -> float:
    return rate_m_per_s if rate_m_per_s > rule.slope_min_m_per_s else 0.0


# 실측 판정의 구역별 (수위 m, 기울기 m/s). 신선한 실측 구역은 자기 값(수위는 0 이상)
# A 가 신선하면 실측 없는 구역은 A 수면 높이 − 그 구역 바닥 높이(음수 그대로)와 A 기울기
# 표본이 최소 표본 수 미만이면 기울기 0. 내림 기울기는 그대로 둠(예측용)
def gauge(
    fresh: Mapping[str, float],  # 신선한 실측 수위(m)
    trails: Mapping[str, Sequence[tuple[float, float]]],  # 구역별 창 안 (경과 초, 수위 m)
    floors: Mapping[str, float],  # 구역 바닥 높이(m)
    rule: Rule,
) -> dict[str, tuple[float, float]]:
    view = {}
    for z, h in fresh.items():
        samples = trails.get(z, ())
        enough = len(samples) >= rule.slope_min_samples
        rate = slope(samples, rule.slope_window_s) if enough else None
        view[z] = (max(0.0, h), rate or 0.0)
    if "A" in view:
        level, rate = view["A"]
        surface = level + floors["A"]  # A 수면 높이(m)
        for z in ZONES:
            view.setdefault(z, (surface - floors[z], rate))
    return view


@dataclass(frozen=True)
# 구역 하나의 감시 상태: 단계, 도달 예상 초(안 오르면 None), 내림 유지가 시작된 경과 초
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
# latch 면 내리지 않고 단계만 둠(도달 초는 지금 판정)
def verdict(
    watch: Watch,
    level_m: float,
    rate_m_per_s: float,
    threshold_m: float,
    rule: Rule,
    elapsed_s: float,
    *,
    latch: bool = False,
) -> Watch:
    stage, eta = outlook(level_m, rate_m_per_s, threshold_m, rule, watch.stage)
    if RANK[stage] >= RANK[watch.stage]:
        return Watch(stage, eta, None)
    if latch:
        return Watch(watch.stage, eta, None)
    since = elapsed_s if watch.calm_since_s is None else watch.calm_since_s  # 내림이 시작된 초
    if elapsed_s - since >= rule.release_hold_s:
        return Watch(stage, eta, None)
    return Watch(watch.stage, watch.eta_s, since)


# 모든 구역의 감시 상태를 한 tick 앞으로. 없는 구역은 정상에서 시작. latch 면 단계를 안 내림
def patrol(
    watches: dict[str, Watch],
    levels_m: dict[str, float],
    rates_m_per_s: dict[str, float],
    elapsed_s: float,
    rule: Rule,
    *,
    latch: bool = False,
) -> dict[str, Watch]:
    return {
        z: verdict(
            watches.get(z, Watch()),
            levels_m[z],
            rates_m_per_s[z],
            rule.thresholds_m[z],
            rule,
            elapsed_s,
            latch=latch,
        )
        for z in ZONES
    }


# 도달 예상 초를 올림한 정수 초로. 1 초 안도 1 이라 0(한계 도달)과 섞이지 않음. 없거나 무한이면 None
def countdown(eta_s: float | None) -> int | None:
    if eta_s is None or not math.isfinite(eta_s):
        return None
    return math.ceil(eta_s)


# 정상이 아닌 구역의 경보를 A·B·C 순서로 {"zone", "stage", "etaSec"} 모양으로 냄. 도달 초는 올림
def bulletin(watches: dict[str, Watch]) -> tuple[dict, ...]:
    return tuple(
        {"zone": z, "stage": watch.stage, "etaSec": countdown(watch.eta_s)}
        for z in ZONES
        if (watch := watches.get(z, Watch())).stage != "safe"
    )


# 단계가 바뀐 구역을 (구역, 이전 단계, 지금 단계, 올림한 도달 초)로 A·B·C 순서로 냄
def shifts(
    before: dict[str, Watch], after: dict[str, Watch]
) -> list[tuple[str, str, str, int | None]]:
    return [
        (z, before.get(z, Watch()).stage, after[z].stage, countdown(after[z].eta_s))
        for z in ZONES
        if before.get(z, Watch()).stage != after[z].stage
    ]
