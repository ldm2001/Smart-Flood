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

# 빗물받이 세 개가 모두 막힌 상태
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
    rain, blockage = 0.0, {}  # 비와 막힘을 비 없음·막힘 없음으로 시작
    for start_s, mm_per_h, blocked in schedule:  # 시나리오 항목을 차례로 확인
        if t_s >= start_s:  # 시작 초가 지났으면
            rain, blockage = mm_per_h, blocked  # 그 항목의 비와 막힘으로 변환
    return Conditions(rain_mm_per_h=rain, blockage=dict(blockage))  # 조건 묶음으로 반환


# 1초 틱마다 상태를 모으는 함수. 목록의 0번은 시작 상태다
def trace(params: Params, schedule, duration_s: int, state: State | None = None):
    state = baseline(params) if state is None else state  # 시작 상태가 없으면 기준 상태에서 출발
    states = [state]  # 상태 목록을 시작 상태로 시작
    for t in range(duration_s):  # 초 수만큼 반복
        state = evolution(state, climate(schedule, t), params, 1.0)  # 한 걸음 계산해 새 상태를 만듦
        states.append(state)  # 새 상태를 목록에 담는다
    return states  # 상태 목록을 반환


# 3.2 의 식을 테스트에서 따로 계산한 누적 강우량(m³)
def downpour(schedule, duration_s: int, model_area_m2: float) -> float:
    total = 0.0  # 누적 합을 0 에서 시작
    for t in range(duration_s):  # 초 수만큼 반복
        # 강우 mm/h 를 m/s 로 바꾸고 면적을 곱해 합산
        total += climate(schedule, t).rain_mm_per_h / 3.6e6 * model_area_m2
    return total  # 누적 합을 반환


# 빗물받이 개구를 1/20 로 줄여 수위가 월류 경계를 넘게 만든 시험용 계수
def stress(config) -> Params:
    cfg = copy.deepcopy(config)  # 설정을 깊은 복사로 떠서 원본을 지킨다
    for inlet in cfg["inlets"].values():  # 빗물받이마다 확인
        inlet["area_m2"] *= 0.05  # 개구 면적을 5 % 로 줄인다
    return Params.config(cfg)  # 줄인 설정으로 계수를 만들어 반환


# A 40 mm, B 50 mm, C 70 mm: 두 경계 양쪽이 잠긴 시작 상태
def flood(params: Params) -> State:
    levels_m = {"A": 0.040, "B": 0.050, "C": 0.070}  # 구역별 시작 수위(m)
    base = baseline(params)  # 기준 상태를 만듦
    return State(  # 상태 묶음을 만들어 반환
        V={z: storage(z, levels_m[z], params) for z in ZONES},  # 구역마다 수위에 맞는 저장량을 넣음
        drained_m3=dict(base.drained_m3),  # 배수량은 기준 상태 값을 복사
    )
