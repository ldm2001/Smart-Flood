import copy
from app.core.model import (
    ZONES,
    Conditions,
    Params,
    State,
    baseline,
    evolution,
    storage,
)

ALL_BLOCKED = {"INLET-01": "full", "INLET-02": "full", "INLET-03": "full"}

EXPERIMENT = (  # (시작 초, 강우 mm/h, 막힘)을 차례로 적은 시나리오. 다음 항목이 시작될 때까지 유지
    (0, 60.0, {}),  # 0초: 약한 비, 막힘 없음
    (120, 90.0, {}),  # 120초: 강한 비
    (240, 90.0, {"INLET-02": "partial"}),  # 240초: 2번 빗물받이 일부 막힘
    (420, 90.0, {"INLET-02": "full"}),  # 420초: 2번 빗물받이 완전 막힘
    (600, 150.0, ALL_BLOCKED),  # 600초: 폭우에 전부 막힘
    (900, 0.0, ALL_BLOCKED),  # 900초: 비 그침, 전부 막힘 유지
    (1100, 0.0, {}),  # 1100초: 막힘 해소
)
EXPERIMENT_S = 1500  # 시나리오 전체 길이(초)


# 시나리오에서 t 초의 비·막힘 조건을 구하는 함수
def climate(schedule, t_s: float) -> Conditions:
    rain, blockage = 0.0, {}
    for start_s, mm_per_h, blocked in schedule:
        if t_s >= start_s:
            rain, blockage = mm_per_h, blocked
    return Conditions(rain_mm_per_h=rain, blockage=dict(blockage))


# 1초 틱마다 상태를 모으는 함수. 목록의 0번은 시작 상태
def trace(params: Params, schedule, duration_s: int, state: State | None = None):
    state = baseline(params) if state is None else state
    states = [state]
    for t in range(duration_s):
        state = evolution(state, climate(schedule, t), params, 1.0)
        states.append(state)
    return states


# 3.2 의 식을 테스트에서 따로 계산한 누적 강우량(m³)
def downpour(schedule, duration_s: int, model_area_m2: float) -> float:
    total = 0.0
    for t in range(duration_s):
        total += climate(schedule, t).rain_mm_per_h / 3.6e6 * model_area_m2
    return total


# 빗물받이 개구를 1/20 로 줄여 수위가 월류 경계를 넘게 만든 시험용 계수
def stress(config) -> Params:
    cfg = copy.deepcopy(config)
    for inlet in cfg["inlets"].values():
        inlet["area_m2"] *= 0.05  # 개구 면적을 5 % 로 줄임
    return Params.config(cfg)


# A 40 mm, B 50 mm, C 70 mm: 두 경계 양쪽이 잠긴 시작 상태
def flood(params: Params) -> State:
    levels_m = {"A": 0.040, "B": 0.050, "C": 0.070}  # 구역별 시작 수위(m)
    base = baseline(params)
    return State(
        V={z: storage(z, levels_m[z], params) for z in ZONES},
        drained_m3=dict(base.drained_m3),
    )
