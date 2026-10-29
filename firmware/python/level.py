# KIT0139 수위센서(4~20 mA, 0~5000 mm) 전압(mV)을 수위(mm)로 바꾸는 순수 계산
# REV16 스케치(firmware/board/board.ino)와 같은 식
SLOPE_THEORY = 5000.0 / 16.0 / 120.0  # mm/mV. 120 Ω 변환보드에서 16 mA 폭이 5000 mm
MV_AT_ZERO = 480.0  # 0 mm 에서 4 mA × 120 Ω
ZERO_LIFT_MM = 10.0  # 이론 영점에 더하는 설계서 값
FAULT_LOW_MV = 300.0  # 이 아래는 단선이나 전원 이상
FAULT_HIGH_MV = 2800.0  # 이 위는 단락이나 과전압
KEEP = 0.85  # 100 ms 이동평균에서 이전 값의 비중
GAP_MV = 5.0  # 2점 보정에 필요한 두 점의 최소 전압 차


# 전압→수위 직선. slope(mm/mV)·offset(mm) 과 1점 보정 기록(mv, mm). 보정은 새 직선을 돌려줌
class Line:
    def __init__(self, slope=SLOPE_THEORY, offset=None, point=None):
        self.slope = slope
        self.offset = -SLOPE_THEORY * MV_AT_ZERO + ZERO_LIFT_MM if offset is None else offset
        self.point = point

    # 1점 보정: 이론 기울기를 두고 지금 전압 mv 가 수위 mm 가 되게 영점 이동
    def point1(self, mv, mm):
        return Line(SLOPE_THEORY, mm - SLOPE_THEORY * mv, (mv, mm))

    # 2점 보정: 1점 기록과 지금 점으로 기울기까지 맞춤. 1점이 없거나 전압 차가 작으면 그대로
    def point2(self, mv, mm):
        if self.point is None or abs(mv - self.point[0]) <= GAP_MV:
            return self
        slope = (mm - self.point[1]) / (mv - self.point[0])
        return Line(slope, mm - slope * mv, self.point)

    # 보정 초기화: 이론 직선
    def reset(self):
        return Line()


# 전압이 센서 정상 범위 밖인지(단선·단락)
def fault(mv):
    return mv < FAULT_LOW_MV or mv > FAULT_HIGH_MV


# 전압→수위(mm). 음수는 0
def mm(mv, line):
    return max(0.0, line.slope * mv + line.offset)


# 여러 번 읽은 값의 평균
def mean(samples):
    return sum(samples) / len(samples)


# 이동평균 한 걸음. 이전 값이 None 이면 새 값으로 시작
def smooth(previous, mv):
    if previous is None:
        return mv
    return previous * KEEP + mv * (1.0 - KEEP)
