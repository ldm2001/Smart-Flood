from __future__ import annotations

import math
import time
from app.ports.clock import KST
from datetime import datetime, timedelta


# 진짜 시계(실시간)
class Wall:
    # 단조 증가 초를 반환
    def monotonic(self) -> float:
        return time.monotonic()  # 운영체제의 단조 시계를 그대로 씀

    # 현재 한국 시각을 반환
    def now(self) -> datetime:
        return datetime.now(KST)  # 지금 시각에 한국 시간대를 붙임


# 가짜 시계: jump 로만 움직임. 재생·테스트용
class Fake:
    # 시작 시각과 시작 초를 받음
    def __init__(self, start: datetime, monotonic_s: float = 0.0) -> None:
        if start.utcoffset() is None:
            raise ValueError(f"시작 시각에 시간대가 없다: {start!r}")
        self._start = start.astimezone(KST)  # 시작 시각을 한국 시간으로 맞춰 둠
        self._mono0 = float(monotonic_s)
        self._elapsed = 0.0  # 지난 초는 0 에서 시작(이 값 하나로만 움직임)

    # 단조 증가 초를 반환
    def monotonic(self) -> float:
        return self._mono0 + self._elapsed

    # 현재 한국 시각을 반환
    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._elapsed)

    # 시계를 주어진 초만큼 앞으로 보냄
    def jump(self, seconds: float) -> None:
        if not (math.isfinite(seconds) and seconds >= 0):
            raise ValueError(f"시계는 0 이상 유한한 초만큼만 움직인다: {seconds!r}")
        self._elapsed += seconds
