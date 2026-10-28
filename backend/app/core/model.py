from __future__ import annotations

import math
from dataclasses import dataclass, field

ZONES = ("A", "B", "C")  # 구역 이름: A, B, C
BLOCKAGE_TYPES = ("none", "partial", "full")  # 막힘 종류: 없음, 일부, 전부
G = 9.81  # 중력가속도(m/s²)


# 저장량이 음수이거나 유한하지 않을 때의 오류. 계산을 멈춤(3.5)
class Underflow(ArithmeticError):
    pass


# 조건이 거짓이면 ValueError 를 내는 검사
def guard(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


@dataclass(frozen=True)
# 구역 하나의 모양
class Basin:
    S_m2: float  # 건물 점유를 뺀 저장 면적(m²)
    z_m: float  # 구역 바닥 높이(m)
    share: float  # 강우 배분 비율


@dataclass(frozen=True)
# 두 구역 사이 월류 경계. 흐름 방향은 수면 높이가 결정
class Link:
    from_zone: str  # 연결의 한쪽 구역(설정 표기일 뿐)
    to_zone: str  # 연결의 다른쪽 구역
    sill_m: float  # 경계 절대 높이(m)
    k: float  # 월류 계수


@dataclass(frozen=True)
# 빗물받이 하나의 모양
class Inlet:
    zone: str  # 속한 구역
    area_m2: float  # 입구 면적(m²)
    Cd: float  # 배수 계수


@dataclass(frozen=True)
# 모델 계수 묶음(전부 config.yaml 에서 옴)
class Params:
    zones: dict[str, Basin]  # 구역별 모양
    links: tuple[Link, ...]  # 구역 사이 월류 경계들
    inlets: dict[str, Inlet]  # 빗물받이들
    open_ratio: dict[str, float]  # 막힘 종류 → 개방 비율
    model_area_m2: float  # 모형 면적(m²)
    dt_s: float  # 계산 간격(초)
    model_version: str  # 모델 버전

    @classmethod  # 클래스 메서드(인스턴스 없이 부름)
    # 설정 한 덩어리로 계수 묶음을 만듦
    def config(cls, cfg: dict) -> Params:
        zones_cfg = cfg["zones"]
        guard(set(zones_cfg) == set(ZONES), f"zones 는 {ZONES} 여야 한다: {sorted(zones_cfg)}")
        zones = {
            z: Basin(
                S_m2=float(zones_cfg[z]["S_m2"]),
                z_m=float(zones_cfg[z]["z_m"]),
                share=float(zones_cfg[z]["share"]),
            )
            for z in ZONES
        }
        for z, zone in zones.items():
            guard(zone.S_m2 > 0, f"{z}.S_m2 는 양수여야 한다")
            guard(zone.share >= 0, f"{z}.share 는 음수일 수 없다")
        total_share = sum(zone.share for zone in zones.values())
        guard(  # 합이 1 인지 확인
            math.isclose(total_share, 1.0, abs_tol=1e-9), f"share 합이 1 이 아니다: {total_share}"
        )

        links = tuple(
            Link(
                from_zone=str(c["from"]),
                to_zone=str(c["to"]),
                sill_m=float(c["sill_m"]),
                k=float(c["k"]),
            )
            for c in cfg.get("links", [])  # 설정에 있는 연결마다(없으면 빈 목록)
        )
        for link in links:
            ends = (link.from_zone, link.to_zone)
            guard(set(ends) <= set(ZONES) and ends[0] != ends[1], f"잘못된 연결: {ends}")
            guard(link.k >= 0, f"연결 {ends} 의 k 는 음수일 수 없다")

        inlets = {
            str(inlet_id): Inlet(
                zone=str(c["zone"]), area_m2=float(c["area_m2"]), Cd=float(c["Cd"])
            )
            for inlet_id, c in cfg["inlets"].items()
        }
        for inlet_id, inlet in inlets.items():
            guard(inlet.zone in ZONES, f"{inlet_id} 의 구역을 모른다: {inlet.zone}")
            guard(  # 면적과 계수가 음수가 아닌지 확인
                inlet.area_m2 >= 0 and inlet.Cd >= 0, f"{inlet_id} 의 면적·계수는 음수일 수 없다"
            )

        ratio_cfg = cfg["blockage_open_ratio"]
        guard(set(ratio_cfg) == set(BLOCKAGE_TYPES), f"막힘 종류는 {BLOCKAGE_TYPES} 여야 한다")
        open_ratio = {kind: float(ratio_cfg[kind]) for kind in BLOCKAGE_TYPES}
        guard(all(0 <= r <= 1 for r in open_ratio.values()), "개방 비율은 0~1 이어야 한다")

        dt_s, area = float(cfg["dt_s"]), float(cfg["model_area_m2"])
        guard(dt_s > 0 and area > 0, "dt_s 와 model_area_m2 는 양수여야 한다")
        return cls(zones, links, inlets, open_ratio, area, dt_s, str(cfg["model_version"]))


@dataclass(frozen=True)
# 강우와 막힘 조건. 예측은 이 조건 유지를 가정(3.6)
class Conditions:
    rain_mm_per_h: float = 0.0  # 강우 세기(mm/h)
    blockage: dict[str, str] = field(default_factory=dict)  # 빗물받이 ID → 막힘 종류(빠지면 none)

    # 만든 직후 값을 검사
    def __post_init__(self) -> None:
        rain = self.rain_mm_per_h
        guard(math.isfinite(rain) and rain >= 0, f"강우는 0 이상의 유한값이어야 한다: {rain}")
        for inlet_id, kind in self.blockage.items():
            guard(kind in BLOCKAGE_TYPES, f"{inlet_id} 의 막힘 종류를 모른다: {kind}")


@dataclass(frozen=True)
# 모델 상태
class State:
    V: dict[str, float]  # 구역 저장량(m³)
    rain_m3: float = 0.0  # 누적 강우 유입(m³)
    drained_m3: dict[str, float] = field(default_factory=dict)  # 빗물받이별 누적 배수(m³)
    correction_m3: float = 0.0  # 누적 관측 보정량(m³, 물수지 보정 항)

    # 만든 직후 값을 검사
    def __post_init__(self) -> None:
        guard(set(self.V) == set(ZONES), f"V 는 {ZONES} 구역을 모두 가져야 한다")


@dataclass(frozen=True)
# 연결 하나를 흐르는 유량
class Flow:
    src: str  # 물이 나가는 구역
    dst: str  # 물이 들어가는 구역
    q_m3s: float  # 유량(m³/s)


@dataclass(frozen=True)
# 한 순간의 모든 유량
class Flows:
    rain_m3s: dict[str, float]  # 구역별 강우 유입
    links: tuple[Flow, ...]  # 연결별 월류(높은 수면 → 낮은 수면)
    drains_m3s: dict[str, float]  # 빗물받이별 배수


# 마른 상태에서 시작
def baseline(params: Params) -> State:
    return State(V={z: 0.0 for z in ZONES}, drained_m3={i: 0.0 for i in params.inlets})


# 수위 h = V / S. 나중에 구간별 선형 곡선으로 바꿀 자리(3.1)
def depth(zone: str, V_m3: float, params: Params) -> float:
    return V_m3 / params.zones[zone].S_m2


# 저장량 V = h × S. 수위 → 저장량
def storage(zone: str, h_m: float, params: Params) -> float:
    return h_m * params.zones[zone].S_m2


# 수면 높이 H = 바닥 높이 + 수위
def surface(zone: str, V_m3: float, params: Params) -> float:
    return params.zones[zone].z_m + depth(zone, V_m3, params)


# 강우 유입 Q = I[mm/h] / 3.6e6 × 모형 면적 (3.2)
def inflow(rain_mm_per_h: float, params: Params) -> float:
    return rain_mm_per_h / 3.6e6 * params.model_area_m2


# 월류 유량 Q = k × 수두^1.5 × 잠김 보정 s (3.3)
def weir(H_hi: float, H_lo: float, link: Link) -> float:
    head = max(0.0, H_hi - link.sill_m)  # 높은 쪽 수면이 경계 위로 올라온 높이
    if head == 0.0:
        return 0.0
    lo_over = max(0.0, H_lo - link.sill_m)  # 낮은 쪽 수면이 경계 위로 올라온 높이
    return link.k * head**1.5 * (1.0 - (lo_over / head) ** 1.5) ** 0.385


# 저장량이 정상인지 검사
def audit(V: dict[str, float]) -> None:
    for zone, v in V.items():
        if not (math.isfinite(v) and v >= 0.0):
            raise Underflow(f"{zone} 저장량이 {v!r} m³ 다")


# 현재 상태에서 모든 유량을 계산(가용량에 따른 축소 전 값)
def flux(state: State, cond: Conditions, params: Params) -> Flows:
    audit(state.V)  # 저장량이 정상인지 먼저 확인
    unknown = set(cond.blockage) - set(params.inlets)  # 조건에는 있는데 설정에 없는 빗물받이
    guard(not unknown, f"모르는 빗물받이: {sorted(unknown)}")

    q_rain = inflow(cond.rain_mm_per_h, params)
    rain = {z: q_rain * params.zones[z].share for z in ZONES}  # 구역별 강우 유입(배분 비율대로)
    H = {z: surface(z, state.V[z], params) for z in ZONES}
    links = []
    for link in params.links:
        a, b = link.from_zone, link.to_zone
        src, dst = (a, b) if H[a] >= H[b] else (b, a)
        links.append(Flow(src, dst, weir(H[src], H[dst], link)))
    drains = {}
    for inlet_id, inlet in params.inlets.items():
        m = params.open_ratio[cond.blockage.get(inlet_id, "none")]
        h = depth(inlet.zone, state.V[inlet.zone], params)
        drains[inlet_id] = inlet.Cd * inlet.area_m2 * m * math.sqrt(2.0 * G * h)  # 오리피스 식
    return Flows(rain, tuple(links), drains)


# 현재 순간의 dh/dt = (강우 + 월류 유입 − 월류 유출 − 배수) / S
def gradient(
    state: State, cond: Conditions, params: Params  # 상태·조건·계수(축소 전 유량 기준)
) -> dict[str, float]:  # 구역별 수위 변화율(m/s)
    flows = flux(state, cond, params)
    net = dict(flows.rain_m3s)
    for lf in flows.links:
        net[lf.src] -= lf.q_m3s
        net[lf.dst] += lf.q_m3s
    for inlet_id, q in flows.drains_m3s.items():
        net[params.inlets[inlet_id].zone] -= q
    return {z: net[z] / params.zones[z].S_m2 for z in ZONES}


# 명시적 오일러 한 걸음. 유량을 먼저 모두 확정한 뒤 한꺼번에 갱신(3.5)
def step(
    state: State, cond: Conditions, params: Params, dt: float | None = None
) -> State:
    dt = params.dt_s if dt is None else dt
    guard(dt > 0, f"dt 는 양수여야 한다: {dt}")
    flows = flux(state, cond, params)
    H = {z: surface(z, state.V[z], params) for z in ZONES}

    received = {z: flows.rain_m3s[z] * dt for z in ZONES}  # 구역별 받는 양(강우 유입으로 시작)
    drained = {}
    V = {}
    for zone in sorted(ZONES, key=lambda z: H[z], reverse=True):  # 높은 순 처리로 유입 먼저 확정
        outs = [(lf.dst, lf.q_m3s * dt) for lf in flows.links if lf.src == zone]
        drains = [  # 이 구역에서 나가는 배수량 목록
            (inlet_id, flows.drains_m3s[inlet_id] * dt)  # (빗물받이 ID, 이번 간격 배수량)
            for inlet_id, inlet in params.inlets.items()
            if inlet.zone == zone
        ]
        available = state.V[zone] + received[zone]  # 쓸 수 있는 물 = 현재 저장량 + 받는 양
        demand = sum(v for _, v in outs) + sum(v for _, v in drains)
        if demand > available:
            scale, V[zone] = available / demand, 0.0  # 유출을 비례 축소하고 저장량은 0
        else:
            scale, V[zone] = 1.0, available - demand
        for dst, v in outs:
            received[dst] += v * scale  # 받는 구역에는 축소된 양만 합산
        for inlet_id, v in drains:
            drained[inlet_id] = v * scale

    V = {z: V[z] for z in ZONES}  # 구역 순서(A·B·C)로 되돌림
    audit(V)
    return State(
        V=V,
        rain_m3=state.rain_m3 + sum(flows.rain_m3s[z] * dt for z in ZONES),
        drained_m3={i: state.drained_m3.get(i, 0.0) + drained[i] for i in params.inlets},
        correction_m3=state.correction_m3,  # 관측 보정량은 그대로 둠
    )


# dt 간격으로 duration_s 동안 이어서 계산(dt 의 정수배여야 함)
def evolution(
    state: State, cond: Conditions, params: Params, duration_s: float
) -> State:
    n = round(duration_s / params.dt_s)
    on_grid = math.isclose(n * params.dt_s, duration_s, rel_tol=1e-9, abs_tol=1e-12)
    guard(duration_s >= 0 and on_grid, f"{duration_s} s 는 dt {params.dt_s} s 의 배수가 아니다")
    for _ in range(n):
        state = step(state, cond, params)
    return state
