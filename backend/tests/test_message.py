import pytest
from app.core.message import HEAD, LIMIT, digits, mask, size, text, trial
from datetime import UTC, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))  # 한국 시간대
TIMES = [  # 문안 시각 후보(자정·하루 끝 포함)
    datetime(2026, 11, 3, 0, 0, tzinfo=KST),
    datetime(2026, 11, 3, 9, 5, tzinfo=KST),
    datetime(2026, 11, 3, 12, 30, tzinfo=KST),
    datetime(2026, 11, 3, 23, 59, tzinfo=KST),
]
CASES = [  # (단계, 구역, 도달 초, 시각) 모든 조합
    (stage, zone, eta, at)
    for stage in ("warning", "evacuate")
    for zone in "ABC"
    for eta in range(0, 31)
    for at in TIMES
]
WORDS = {"warning": ("침수주의", "이동"), "evacuate": ("침수경보", "대피")}  # 위험·행동 낱말
NAMES = {"A": "A구역", "B": "B구역", "C": "C구역(추정)"}  # 위치 낱말


# 모든 조합이 SMS 90바이트(cp949) 안인지 검사
def test_every_case_fits():
    worst = max(size(text(stage, zone, eta, at)) for stage, zone, eta, at in CASES)
    assert LIMIT == 90
    assert worst <= LIMIT


# 모든 조합이 5요소(발신·위험·위치·행동·시간)를 담는지 검사
@pytest.mark.parametrize("stage", ["warning", "evacuate"])
@pytest.mark.parametrize("zone", ["A", "B", "C"])
def test_five_parts(stage, zone):
    for eta in range(0, 31):
        for at in TIMES:
            body = text(stage, zone, eta, at)
            danger, action = WORDS[stage]
            assert body.startswith(HEAD) and "시연" in HEAD
            assert danger in body and action in body
            assert NAMES[zone] in body
            assert body.endswith(f"{at.hour:02d}:{at.minute:02d}")
            if stage == "warning":
                assert f"약{eta}초" in body


# C 는 모델 추정이라 "(추정)" 표시, A·B 에는 없음
def test_c_estimated():
    at = TIMES[0]
    assert "C구역(추정)" in text("warning", "C", 10, at)
    assert "C구역(추정)" in text("evacuate", "C", 0, at)
    assert "(추정)" not in text("warning", "A", 10, at)
    assert "(추정)" not in text("evacuate", "B", 0, at)


# 갈 곳: A·B 위험이면 C구역 고지대, C 위험이면 지정 대피지점
@pytest.mark.parametrize("stage", ["warning", "evacuate"])
def test_destination(stage):
    at = TIMES[1]
    for zone in "AB":
        body = text(stage, zone, 5, at)
        assert "C구역 고지대 쪽으로" in body and "지정 대피지점" not in body
    body = text(stage, "C", 5, at)
    assert "지정 대피지점 쪽으로" in body and "고지대" not in body


# 문안 전체 모양
def test_exact_text():
    at = datetime(2026, 11, 3, 14, 7, tzinfo=KST)
    warning = "[SMARTFLOOD시연] 침수주의 A구역 약12초 뒤 침수예상. C구역 고지대 쪽으로 이동 14:07"
    evacuate = "[SMARTFLOOD시연] 침수경보 C구역(추정) 침수발생. "
    evacuate += "즉시 지정 대피지점 쪽으로 대피 14:07"
    assert text("warning", "A", 12, at) == warning
    assert text("evacuate", "C", 99, at) == evacuate  # 침수 문안은 eta 를 안 씀
    assert trial(at) == "[SMARTFLOOD시연] 테스트 문자입니다 14:07"
    assert size(trial(at)) <= LIMIT


# HH:MM 은 시각이 가진 시간대 기준
def test_zone_clock():
    instant = datetime(2026, 11, 3, 14, 5, tzinfo=UTC)
    assert text("warning", "B", 3, instant.astimezone(KST)).endswith(" 23:05")
    assert text("warning", "B", 3, instant).endswith(" 14:05")
    assert trial(datetime(2026, 11, 3, 23, 59, tzinfo=KST)).endswith(" 23:59")
    assert trial(datetime(2026, 11, 4, 0, 0, tzinfo=KST)).endswith(" 00:00")


# 모르는 단계·구역은 ValueError
@pytest.mark.parametrize(
    ("stage", "zone"),
    [("caution", "A"), ("safe", "B"), ("", "A"), ("warning", "D"), ("evacuate", "a")],
)
def test_unknown(stage, zone):
    with pytest.raises(ValueError):
        text(stage, zone, 5, TIMES[0])


# cp949 바이트 수: 한글 2·영문숫자 1
def test_size():
    assert size("") == 0
    assert size("AB12") == 4
    assert size("침수") == 4
    assert size("[시연]") == 6


# 숫자만 남김
def test_digits():
    number = "010-" + "1234" + "-5678"  # 스캔에 안 걸리게 조립
    assert digits(number) == "010" + "1234" + "5678"
    assert digits(" 0 1 0 ") == "010"
    assert digits("abc") == ""


# 뒤 4자리만 보이게 가림, 4자리 이하면 전부 *
def test_mask():
    number = "010-" + "1234" + "-5678"
    assert mask(number) == "*******5678"
    assert mask("0" + "2" + "9302266") == "*****2266"
    assert mask("5678") == "****"
    assert mask("12") == "**"
    assert mask("") == ""
