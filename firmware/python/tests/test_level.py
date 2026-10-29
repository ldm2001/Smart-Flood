import level
import pytest


# 이론 기울기 2.604 mm/mV 와, 480 mV 에서 설계서 영점 10 mm 가 나오는지 검사
def test_theory_line_puts_zero_current_at_ten_mm():
    line = level.Line()
    assert line.slope == pytest.approx(2.6041667, abs=1e-6)
    assert level.mm(480.0, line) == pytest.approx(10.0)


# 1 V 오르면 2604 mm 가 더해지는지 검사(0~5000 mm 가 16 mA × 120 Ω = 1920 mV 폭)
def test_level_follows_the_slope():
    line = level.Line()
    assert level.mm(1480.0, line) - level.mm(480.0, line) == pytest.approx(2604.1667, abs=1e-3)


# 영점 아래 전압은 음수 대신 0 mm 인지 검사
def test_level_below_zero_is_clamped():
    assert level.mm(400.0, level.Line()) == 0.0


# 300~2800 mV 밖은 fault, 경계값은 정상인지 검사
@pytest.mark.parametrize(
    "mv, bad", [(299.9, True), (300.0, False), (2800.0, False), (2800.1, True)]
)
def test_fault_outside_the_sensor_range(mv, bad):
    assert level.fault(mv) is bad


# 1점 보정: 이론 기울기를 두고, 지금 전압이 준 수위가 되게 영점만 옮기는지 검사
def test_point1_moves_the_offset_only():
    line = level.Line().point1(500.0, 0.0)
    assert line.slope == level.SLOPE_THEORY
    assert level.mm(500.0, line) == 0.0
    assert line.point == (500.0, 0.0)


# 2점 보정: 두 점을 지나는 직선이 되는지 검사
def test_point2_fits_both_points():
    line = level.Line().point1(500.0, 0.0).point2(900.0, 100.0)
    assert level.mm(500.0, line) == pytest.approx(0.0)
    assert level.mm(900.0, line) == pytest.approx(100.0)


# 1점이 없거나 전압 차가 5 mV 이하면 2점 보정을 받지 않는지 검사
def test_point2_needs_point1_and_a_voltage_gap():
    plain = level.Line()
    assert plain.point2(900.0, 100.0) is plain
    close = plain.point1(500.0, 0.0)
    assert close.point2(504.0, 100.0) is close


# 보정 초기화는 이론 직선으로 돌아가는지 검사
def test_reset_returns_the_theory_line():
    line = level.Line().point1(500.0, 0.0).reset()
    theory = level.Line()
    assert (line.slope, line.offset, line.point) == (theory.slope, theory.offset, None)


# 평균과 이동평균(이전 0.85, 새 값 0.15)이 스케치와 같은지 검사
def test_mean_and_smooth_match_the_sketch():
    assert level.mean([1.0, 2.0, 3.0]) == 2.0
    assert level.smooth(None, 1000.0) == 1000.0
    assert level.smooth(1000.0, 1100.0) == pytest.approx(1015.0)
