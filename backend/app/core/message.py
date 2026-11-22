from __future__ import annotations

from typing import Protocol

LIMIT = 90  # SMS 바이트 상한(cp949)
HEAD = "[SMARTFLOOD시연]"  # 발신. 실제 재난문자로 오인되지 않게 "시연" 표시
NAMES = {"A": "A구역", "B": "B구역", "C": "C구역(추정)"}  # C 는 모델 추정이라 "(추정)" 표시
HIGH = "C구역 고지대"  # A·B 위험 때 갈 곳
SHELTER = "지정 대피지점"  # C 위험 때 갈 곳
NUMERALS = "0123456789"  # 번호에서 남길 글자(ASCII 숫자만)


# 시·분만 쓰는 시각 모양. datetime 이 그대로 맞음(core 는 datetime 을 가져오지 않음)
class Moment(Protocol):
    @property
    def hour(self) -> int: ...

    @property
    def minute(self) -> int: ...


# 시각이 가진 시간대 기준 HH:MM 글
def stamp(at: Moment) -> str:
    return f"{at.hour:02d}:{at.minute:02d}"


# 단계·구역·도달 초·시각으로 위험 문안을 만듦. eta 는 warning 에서만 씀. 모르는 값은 ValueError
def text(stage: str, zone: str, eta: int, at: Moment) -> str:
    if zone not in NAMES:
        raise ValueError(f"모르는 구역: {zone!r}")
    name = NAMES[zone]
    dest = SHELTER if zone == "C" else HIGH  # C 가 위험하면 고지대가 없음
    if stage == "warning":
        return f"{HEAD} 침수주의 {name} 약{eta}초 뒤 침수예상. {dest} 쪽으로 이동 {stamp(at)}"
    if stage == "evacuate":
        return f"{HEAD} 침수경보 {name} 침수발생. 즉시 {dest} 쪽으로 대피 {stamp(at)}"
    raise ValueError(f"모르는 단계: {stage!r}")


# 시험 문자 문안
def trial(at: Moment) -> str:
    return f"{HEAD} 테스트 문자입니다 {stamp(at)}"


# cp949 바이트 수(한글 2·영문숫자 1). cp949 로 못 쓰는 글자는 UnicodeEncodeError
def size(body: str) -> int:
    return len(body.encode("cp949"))


# 숫자만 남김(하이픈·공백 등 제거)
def digits(number: str) -> str:
    return "".join(c for c in number if c in NUMERALS)


# 숫자만 남기고 뒤 4자리만 보이게 앞을 * 로 가림. 4자리 이하면 전부 *
def mask(number: str) -> str:
    shown = digits(number)
    if len(shown) <= 4:
        return "*" * len(shown)
    return "*" * (len(shown) - 4) + shown[-4:]
