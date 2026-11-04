from __future__ import annotations

import logging
import queue
import threading
from app.core import message
from app.core.danger import RANK
from app.ports.notifier import Spent
from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.adapters.solapi import Keys

log = logging.getLogger(__name__)

MODES = ("stub", "sms")  # 발송 방식


# 문자 한 건을 보내는 쪽(Solapi 또는 시험용 가짜)
class Sender(Protocol):
    def send(self, to: str, body: str) -> None:
        ...


# 발송 일을 데몬 스레드 하나의 큐에서 차례로 처리. 부른 쪽(tick)은 기다리지 않음
class Courier:
    def __init__(self) -> None:
        self._jobs: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None  # 첫 일이 올 때 띄움
        self._lock = threading.Lock()

    # 일을 큐에 넣고 바로 돌아옴
    def __call__(self, job: Callable[[], None]) -> None:
        with self._lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self.loop, name="sms", daemon=True)
                self._thread.start()
        self._jobs.put(job)

    # 큐의 일을 하나씩 처리. 한 일이 실패해도 다음 일은 이어 감
    def loop(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                job()
            except Exception as error:  # 예외 종류만(글에 키·번호가 섞일 수 있음)
                log.warning("SMS 실패: %s", type(error).__name__)


# 단계 사건을 문자로 바꿔 보냄. 단계·중복·상한·무장을 보고, 실제 보내기는 runner 에 맡김
class Dispatch:
    def __init__(
        self,
        config: dict,  # config.yaml 의 notifier
        keys: Keys | None = None,  # 환경 변수의 키(없으면 보내지 않음)
        sender: Sender | None = None,  # 문자 한 건을 보내는 쪽
        *,
        runner: Callable[[Callable[[], None]], None] | None = None,  # 시험에서는 바로 부름
        to: tuple[str, ...] | None = None,  # 받는 번호(없으면 허용 번호 전부)
    ) -> None:
        self.mode = str(config["mode"])
        if self.mode not in MODES:
            raise ValueError(f"notifier.mode 는 {' 또는 '.join(MODES)} 여야 한다: {self.mode}")
        self._stages = frozenset(str(s) for s in config["sms_stages"])
        if not self._stages <= set(RANK):
            raise ValueError(f"notifier.sms_stages 에 모르는 단계가 있다: {sorted(self._stages)}")
        self.armed = False  # 서버를 다시 켜면 늘 해제
        self._keys = keys
        self._sender = sender
        self._limit = int(config["max_sms_per_experiment"])  # 실험당 발송 상한(건)
        self._test_limit = int(config["test_limit"])  # 시험 문자 상한(서버 실행당)
        self._runner = Courier() if runner is None else runner
        self._to = (keys.allowed if keys else ()) if to is None else tuple(to)
        self._lock = threading.Lock()
        self._seen: set[tuple[str, str, str]] = set()  # 처리한 (실험, 구역, 단계)
        self._counts: dict[str, int] = {}  # 실험 → 발송 건수(사건 기준)
        self._tests = 0  # 이번 서버 실행에서 보낸 시험 문자 수

    @property
    # 발송 환경 변수(키)와 보내는 쪽이 다 있는지
    def ready(self) -> bool:
        return self._keys is not None and self._sender is not None

    @property
    # 실제 발송 조건 세 개(mode sms·환경 변수·무장)가 다 맞는지
    def live(self) -> bool:
        return self.mode == "sms" and self.ready and self.armed

    @property
    # 보내지 않는 까닭(로그용)
    def reason(self) -> str:
        if self.mode != "sms":
            return "mode stub"
        return "무장 해제" if self.ready else "환경 변수 없음"

    # 무장·해제. 조건이 안 맞으면 켜지 않음(409 는 서비스가 냄)
    def arm(self, on: bool) -> None:
        self.armed = bool(on) and self.mode == "sms" and self.ready

    # 단계 사건 하나. 오르는 전환의 문자 대상 단계만, (실험, 구역, 단계)마다 한 번
    def notice(self, event: dict) -> None:
        stage, zone = event.get("stage"), event.get("zone")
        if event.get("kind") != "stage" or stage not in self._stages:
            return  # caution·정상은 화면과 기록만
        if RANK[stage] <= RANK.get(event.get("previous"), 0):
            return  # 내려가는 전환은 문자 없음
        experiment = str(event.get("experimentId"))
        at = datetime.fromisoformat(event["time"])  # 사건 시각(+09:00)
        body = message.text(stage, zone, int(event.get("etaSec") or 0), at)
        if not self.live:  # 무장 전·설정 없음은 기록만(중복 키·건수 안 씀)
            log.warning("SMS 예정(%s) %s: %s", self.reason, experiment, body)
            return
        with self._lock:
            key = (experiment, zone, stage)
            if key in self._seen:
                return
            self._seen.add(key)
            used = self._counts.get(experiment, 0)
            if used >= self._limit:
                log.warning("SMS 상한 %s: %s 구역 %s, 실험당 %d 건", experiment, zone, stage, used)
                return
            self._counts[experiment] = used + 1
        for number in self._to:
            if message.digits(number) not in self._keys.allowed:  # 보내기 시도 자체를 안 함
                log.warning("SMS 차단 %s %s: 허용 번호가 아니다", experiment, message.mask(number))
                continue
            self._runner(partial(self.deliver, experiment, number, body))

    # 문자 한 건(발송 스레드에서 돎). 실패는 로그만, 재시도 없음
    def deliver(self, experiment: str, number: str, body: str) -> None:
        try:
            self._sender.send(number, body)
        except Exception as error:  # 예외 종류만(글에 키·번호가 섞일 수 있음)
            name = type(error).__name__
            log.warning("SMS 실패 %s %s: %s", experiment, message.mask(number), name)
            return
        log.warning("SMS 보냄 %s %s: %s", experiment, message.mask(number), body)

    # 시험 문자 한 건을 허용 번호 첫째로 바로 보냄. 무장 해제·횟수 초과는 Spent
    def trial(self, at: datetime) -> tuple[str, str]:
        with self._lock:
            if not self.live:
                raise Spent("무장하지 않아 시험 문자를 보낼 수 없다")
            if self._tests >= self._test_limit:
                raise Spent(f"시험 문자는 서버 실행당 {self._test_limit} 번까지다")
            self._tests += 1  # 실패해도 한 번으로 셈
            number = self._keys.allowed[0]
        body = message.trial(at)
        shown = message.mask(number)  # 가린 번호(뒤 4자리)
        try:
            self._sender.send(number, body)
        except Exception as error:
            log.warning("SMS 실패(시험) %s: %s", shown, type(error).__name__)
            raise
        log.warning("SMS 보냄(시험) %s: %s", shown, body)
        return shown, body
