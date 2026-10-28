from __future__ import annotations

import math
from app.core.model import ZONES
from datetime import datetime, timedelta
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from typing import TYPE_CHECKING, Annotated, Literal

if TYPE_CHECKING:  # 타입 검사할 때만 읽음(순환 참조 방지)
    from app.core.calibration import Delta
    from app.core.model import State
    from app.service import Snapshot

CONTRACT_HORIZONS_S = (10, 20, 30)  # predictions 의 키: 10·20·30 초
M_TO_MM = 1000.0  # m → mm 변환 계수(단위 변환은 여기서만)
M3_TO_L = 1000.0  # m³ → L 변환 계수
M3S_TO_L_PER_MIN = 60_000.0  # m³/s → L/min 변환 계수
KST_OFFSET = timedelta(hours=9)  # 한국 표준시 +09:00


# 시각 글자가 ISO 8601 이고 +09:00 인지 검사
def stamp(value: str) -> str:
    try:
        offset = datetime.fromisoformat(value).utcoffset()
    except ValueError as error:  # ISO 형식이 아니면
        raise ValueError(f"ISO 8601 시각이 아니다: {value!r}") from error
    if offset != KST_OFFSET:  # +09:00 이 아니면
        raise ValueError(f"시각은 +09:00 이어야 한다: {value!r}")
    return value  # 통과한 값을 그대로 반환


# JSON 숫자만 받는 실수 타입을 만듦(문자열·불리언 거부)
def number(**bounds: float):
    return Annotated[float, Field(strict=True, **bounds)]  # 엄격 모드에 범위(ge·le·gt)를 붙임


KstTime = Annotated[str, AfterValidator(stamp)]
Level = number(ge=0, le=500)  # 수위(mm) 0~500. 벗어나면 잘라 내지 않고 검증 실패
Elapsed = number(ge=0, le=864_000)  # 경과 시간(초) 0~864000
NonNegative = number(ge=0)
BlockageType = Literal["none", "partial", "full"]
RainPreset = Literal["light", "medium", "heavy"]



# /api/state 응답의 공통 바탕(4.1). 기존 필드는 바꾸지 않고 추가만
class Response(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


# 구역 하나의 측정값
class Zone(Response):
    levelMm: Level  # 수위(mm)
    rateMmSec: number(ge=-20, le=20)  # 수위 변화율(mm/s) -20~20
    source: Literal["measured", "simulated", "estimated", "replay"]  # 실측·가상 실측·모델 추정·재생


# A·B·C 세 구역
class Zones(Response):
    A: Zone  # A 구역
    B: Zone  # B 구역
    C: Zone  # C 구역


# 10·20·30 초 뒤 예측 수위
class Horizons(Response):
    model_config = ConfigDict(serialize_by_alias=True)  # 내보낼 때 별칭 키(10·20·30)를 씀

    s10: Level = Field(alias="10")  # 10 초 뒤 수위(mm)
    s20: Level = Field(alias="20")  # 20 초 뒤 수위(mm)
    s30: Level = Field(alias="30")  # 30 초 뒤 수위(mm)


# 구역별 예측
class Predictions(Response):
    A: Horizons  # A 구역 예측
    B: Horizons  # B 구역 예측
    C: Horizons  # C 구역 예측


# 배수 현황
class Drain(Response):
    volumeL: number(ge=0, le=10_000)  # 누적 배수량(L) 0~10000
    flowLMin: number(ge=0, le=1_000)  # 배수 유량(L/min) 0~1000


# 강우 현황
class Rain(Response):
    state: Literal["ON", "OFF"]  # 강우 켜짐·꺼짐
    intensity: str  # 강우 세기 이름
    mmPerHour: NonNegative  # 강우 세기(mm/h)


# 막힘 현황
class Blockage(Response):
    location: str | None  # 막힌 빗물받이(없으면 null)
    type: BlockageType  # 막힘 종류
    label: str  # 화면에 보일 막힘 이름


# 장치 연결 상태
class Devices(Response):
    esp32_1: str  # ESP32 1번 상태
    esp32_2: str  # ESP32 2번 상태
    floatSwitch: str  # 플로트 스위치 상태
    emergencyStop: str  # 비상 정지 상태


# 경보 하나
class Alert(Response):
    zone: Literal["A", "B", "C"]  # 경보 구역
    stage: Literal["caution", "warning", "evacuate"]  # 경보 단계: 주의·경고·대피
    etaSec: NonNegative | None = None  # 임계 도달까지 남은 시간(초), 모르면 null


# 예측이 가정한 조건
class Assumptions(Response):
    rule: str  # 예측 규칙 이름
    rainMmPerHour: NonNegative  # 가정한 강우 세기(mm/h)
    blockage: dict[str, BlockageType]  # 가정한 빗물받이별 막힘


# 예측 메타 정보
class Meta(Response):
    basisTime: KstTime  # 예측 기준 시각
    basisElapsedSec: Elapsed  # 예측 기준 경과 시간(초)
    validForSec: number(gt=0)  # 예측이 유효한 시간(초), 0 초과
    modelVersion: str  # 모델 버전
    assumptions: Assumptions  # 예측이 가정한 조건


# /api/state 전체 응답(4.1)
class Board(Response):
    experimentId: str  # 실험 회차 ID
    mode: Literal["live", "replay"]  # 화면 모드: live 또는 replay
    timestamp: KstTime  # 응답 시각
    elapsedSec: Elapsed  # 회차 시작 후 경과 시간(초)
    zones: Zones  # 구역별 측정값
    predictions: Predictions  # 구역별 예측
    drain: Drain  # 배수 현황
    rain: Rain  # 강우 현황
    blockage: Blockage  # 막힘 현황
    devices: Devices  # 장치 상태
    quality: Literal["valid", "degraded", "invalid"]  # 데이터 품질
    outputsLocked: Literal[True]  # 출력 잠금(항상 true)
    dataSource: Literal["sim", "replay", "live"]  # 입력원: 시뮬레이션·재생·실측
    alerts: list[Alert]  # 경보 목록
    runState: Literal["idle", "running", "stopped"] | None = None  # 추가 필드(회차 진행 상태)
    predictionMeta: Meta | None = None  # 추가 필드: 예측 메타 정보

    @classmethod  # 클래스 메서드(인스턴스 없이 부름)
    # 서비스 스냅샷을 API 응답으로 변환(단위는 mm·L·L/min)
    def snapshot(cls, s: Snapshot) -> Board:
        p = s.prediction
        timestamp = s.timestamp.isoformat(timespec="milliseconds")  # 응답 시각(밀리초 단위 ISO)
        return cls.model_validate(
            {
                "experimentId": s.experiment_id,
                "mode": "replay" if s.data_source == "replay" else "live",
                "timestamp": timestamp,
                "elapsedSec": s.elapsed_s,  # 경과 시간(초)
                "zones": {
                    z: {
                        "levelMm": s.levels_m[z] * M_TO_MM,  # 수위 m → mm
                        "rateMmSec": s.rates_m_per_s[z] * M_TO_MM,  # 변화율 m/s → mm/s
                        "source": s.zone_sources[z],
                    }
                    for z in ZONES
                },
                "predictions": {
                    z: {str(h): p.levels_m[z][h] * M_TO_MM for h in CONTRACT_HORIZONS_S}
                    for z in ZONES
                },
                "drain": {
                    "volumeL": s.drained_m3 * M3_TO_L,  # 누적 배수량 m³ → L
                    "flowLMin": s.drain_flow_m3s * M3S_TO_L_PER_MIN,  # 배수 유량 m³/s → L/min
                },
                "rain": {
                    "state": "ON" if s.rain_on else "OFF",
                    "intensity": s.rain_label,
                    "mmPerHour": s.rain_mm_per_h,  # 강우 세기(mm/h)
                },
                "blockage": {
                    "location": s.blockage_location,
                    "type": s.blockage_type,
                    "label": s.blockage_label,
                },
                "devices": dict(s.devices),
                "quality": s.quality,
                "outputsLocked": True,  # 출력은 항상 잠금
                "dataSource": s.data_source,
                "alerts": list(s.alerts),
                "runState": s.run_state,
                "predictionMeta": {
                    "basisTime": timestamp,
                    "basisElapsedSec": p.basis_elapsed_s,
                    "validForSec": p.valid_for_s,
                    "modelVersion": p.model_version,
                    "assumptions": {
                        "rule": p.assumptions["rule"],
                        "rainMmPerHour": p.assumptions["rain_mm_per_h"],
                        "blockage": p.assumptions["blockage"],
                    },
                },
            }
        )



# 제어 요청의 공통 바탕(4.2). 모양만 보고 값의 의미는 서비스가 확인
class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# 강우 조작 요청
class Shower(Request):
    intensity: RainPreset | None = None  # 프리셋 이름(light·medium·heavy)
    mmPerHour: NonNegative | None = None  # 직접 준 강우 세기(mm/h)


# 막힘 조작 요청
class Clog(Request):
    type: BlockageType  # 막힘 종류
    location: str | None = None  # 막을 빗물받이


# 회차 시작 요청
class Kickoff(Request):
    rain: RainPreset | None = None  # 처음 강우 프리셋
    blockage: Clog | None = None  # 처음 막힘 조건


# 입력원 바꾸기 요청
class Feed(Request):
    mode: Literal["sim", "replay", "live"]  # 입력원: 시뮬레이션·재생·실측
    logId: str | None = None  # 재생할 기록 ID


# 내용 없는 요청
class Blank(Request):
    pass



# 관측 메시지의 공통 바탕(4.3). 장치가 덧붙인 필드는 무시
class Intake(BaseModel):
    model_config = ConfigDict(extra="ignore")  # 모르는 필드는 무시


# 센서 읽은 값. 없거나 NaN 이면 그 구역만 무효
class Readings(Intake):
    distA_mm: float | None = None  # A 구역 수면까지 거리(mm)
    distB_mm: float | None = None  # B 구역 수면까지 거리(mm)
    weight_g: float | None = None  # 배수 무게(g)


# 센서 상태 글자
class Status(Intake):
    A: str  # A 센서 상태
    B: str  # B 센서 상태
    load: str  # 무게 센서 상태


# 관측 메시지 하나(4.3)
class Message(Intake):
    deviceId: str  # 장치 ID
    bootId: str  # 부팅 ID
    seq: Annotated[int, Field(ge=0)]  # 메시지 순번(0 이상)
    tMs: Annotated[int, Field(ge=0)]  # 장치 시각(ms, 0 이상)
    readings: Readings  # 읽은 값
    sensorStatus: Status  # 센서 상태


# 장치 메시지의 영수증(POST /api/ingest 응답)
class Receipt(Response):
    deviceId: str  # 받은 장치 ID
    seq: int  # 받은 메시지 순번
    dataSource: str  # 받은 시점의 입력원. live 가 아니면 메시지는 쓰이지 않음



# NaN·무한대를 'nan'·'inf' 글자로 변환(JSON 에 못 씀)
def encoding(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)  # 글자로 돌려줌(재생이 Message 의 float 로 다시 읽음)
    if isinstance(value, dict):
        return {key: encoding(item) for key, item in value.items()}
    if isinstance(value, list):
        return [encoding(item) for item in value]
    return value  # 그 밖의 값은 그대로 반환


LOG_VERSION = 1  # 기록 형식 버전. 줄 하나가 JSON 객체 하나이고 단위는 API 와 같음(7장)


# 시각을 마이크로초 단위 ISO 글자로 변환
def moment(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


# 회차 기록의 첫 줄. 재생과 비교에 필요한 구성을 담음
def header(
    *,
    experiment_id: str,
    data_source: str,
    start_time: datetime,
    model_version: str,
    config_hash: str,
    config: dict,
) -> dict:
    return {
        "type": "meta",  # 줄 종류: 첫 줄
        "logVersion": LOG_VERSION,
        "experimentId": experiment_id,
        "dataSource": data_source,
        "startTime": moment(start_time),
        "modelVersion": model_version,
        "configHash": config_hash,
        "config": config,
    }


# 조작 한 건. elapsedSec 는 적용 시각(다음 tick 부터 걸림)
def directive(
    kind: str,
    elapsed_s: float,  # 적용 경과 시간(초)
    received_at: datetime,
    *,
    rain_mm_per_h: float | None = None,  # 바꾼 강우 세기(없으면 생략)
    blockage: tuple[str, str | None] | None = None,  # 바꾼 막힘(종류, 위치)
) -> dict:
    record = {
        "type": "cmd",  # 줄 종류: 조작
        "kind": kind,
        "elapsedSec": elapsed_s,
        "receivedAt": moment(received_at),
    }
    if rain_mm_per_h is not None:
        record["rainMmPerHour"] = rain_mm_per_h
    if blockage is not None:
        blockage_type, location = blockage
        record["blockage"] = {"type": blockage_type, "location": location}
    return record


# 받은 관측 메시지 하나와 그 해석. 무효 센서의 값은 null
def observation(
    elapsed_s: float,  # 경과 시간(초)
    received_at: datetime,
    raw: dict,
    levels_m: dict[str, float | None],  # 구역별 수위(m), 무효면 None
    drained_m3: float | None,  # 누적 배수량(m³), 무효면 None
    quality: dict[str, str],
) -> dict:
    return {
        "type": "obs",  # 줄 종류: 관측
        "elapsedSec": elapsed_s,
        "receivedAt": moment(received_at),
        "raw": encoding(raw),  # 받은 원본(NaN 은 글자로)
        "levelsMm": {z: None if h is None else h * M_TO_MM for z, h in levels_m.items()},
        "drainVolumeL": None if drained_m3 is None else drained_m3 * M3_TO_L,
        "quality": dict(quality),
    }


# tick 하나의 결과: 그 시점 응답과 모델 내부 값
def frame(
    snapshot: Snapshot, model_state: State, corrections: tuple[Delta, ...]
) -> dict:
    return {
        "type": "state",  # 줄 종류: 상태
        "elapsedSec": snapshot.elapsed_s,
        "state": Board.snapshot(snapshot).model_dump(mode="json", by_alias=True),  # /api/state 응답
        "model": {
            "volumesL": {z: model_state.V[z] * M3_TO_L for z in ZONES},  # 구역 저장량 m³ → L
            "correction": {
                r.zone: {
                    "beforeL": r.before_m3 * M3_TO_L,  # 보정 전 저장량(L)
                    "afterL": r.after_m3 * M3_TO_L,  # 보정 후 저장량(L)
                    "deltaL": r.delta_m3 * M3_TO_L,  # 바뀐 양(L)
                }
                for r in corrections
            },
            "correctionTotalL": model_state.correction_m3 * M3_TO_L,  # 누적 보정량(L)
            "rainTotalL": model_state.rain_m3 * M3_TO_L,  # 누적 강우 유입(L)
            "drainedL": {i: v * M3_TO_L for i, v in model_state.drained_m3.items()},
        },
    }


# 사건 기록 한 줄을 만듦
def event(kind: str, elapsed_s: float, time: datetime, message: str) -> dict:
    return {
        "type": "event",  # 줄 종류: 사건
        "kind": kind,
        "elapsedSec": elapsed_s,
        "time": moment(time),
        "message": message,
    }
