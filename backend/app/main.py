from __future__ import annotations

import asyncio
from app.adapters.clock import Wall
from app.adapters.jsonl_log import Jsonl
from app.adapters.sim_source import Sim
from app.api import control, logs, state
from app.config import settings
from app.ports.clock import Clock
from app.ports.experiment_log import Journal
from app.ports.notifier import Notifier
from app.ports.source import Source
from app.schemas import encoding
from app.service import (
    Conflict,
    Experiment,
    Fault,
    Lack,
    Outage,
)
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

FRONTEND_OUT = Path(__file__).resolve().parents[2] / "frontend" / "out"  # 빌드된 프론트 폴더
MAX_TICKER_SLEEP_S = 0.25  # tick 사이 최대 잠(초). 가상 시계로 바꿔도 밀린 tick 을 알아챈다


# 앱 조립: 서비스, CORS, 오류 응답, 1 Hz tick, 빌드된 프론트
def factory(
    config: dict | None = None,  # 설정(없으면 파일에서 읽는다)
    *,  # 아래는 이름으로만 넘긴다
    clock: Clock | None = None,  # 시계(테스트에서 바꿔 끼운다)
    source: Source | None = None,  # 입력원
    experiment_log: Journal | None = None,  # 실험 기록
    notifier: Notifier | None = None,  # 알림기
    start_ticker: bool = True,  # tick 태스크를 돌릴지
    static_dir: str | Path | None = FRONTEND_OUT,  # 빌드된 프론트 폴더(없으면 붙이지 않는다)
) -> FastAPI:  # 만든 앱을 반환
    config = settings() if config is None else config  # 설정을 결정
    service = Experiment(  # 서비스를 만듦
        config,  # 설정
        clock=Wall() if clock is None else clock,  # 시계: 안 주면 진짜 시계
        source=Sim(config) if source is None else source,  # 입력원: 안 주면 가상 센서
        experiment_log=Jsonl() if experiment_log is None else experiment_log,  # 기록: 안 주면 JSONL
        notifier=notifier,  # 알림기
    )

    @asynccontextmanager  # 시작과 끝에 할 일을 결정
    # 앱이 도는 동안 열려 있는 구간
    async def lifespan(app: FastAPI):
        # 1 Hz tick 태스크를 시작
        ticker = asyncio.create_task(pulse(service)) if start_ticker else None
        yield  # 여기서 앱이 일
        if ticker is not None:  # 끝날 때 태스크가 있으면
            ticker.cancel()  # 취소
            with suppress(asyncio.CancelledError):  # 취소 오류는 무시
                await ticker  # 끝나기를 기다린다

    app = FastAPI(title="SMART FLOOD", lifespan=lifespan)  # FastAPI 앱을 만듦
    app.state.service = service  # 서비스를 앱에 달아 둔다
    app.add_middleware(  # CORS 를 끼운다
        CORSMiddleware,  # CORS 처리기
        allow_origins=config["server"]["cors_origins"],  # 설정에 적힌 출처만 허용
        allow_methods=["GET", "POST"],  # GET·POST 만 허용
        allow_headers=["Content-Type"],  # Content-Type 헤더만 허용
    )

    @app.exception_handler(RequestValidationError)  # 요청 검증 오류(422) 처리기
    # 검증 오류를 422 응답으로 변환
    async def validation(request: Request, error: RequestValidationError) -> JSONResponse:
        # 기본 처리기와 같은 모양. 입력값의 NaN·Infinity 는 글자로 변환
        detail = encoding(jsonable_encoder(error.errors()))
        return JSONResponse(status_code=422, content={"detail": detail})  # 422 로 응답

    @app.exception_handler(Fault)  # 입력 오류(Fault) 처리기
    # 입력 오류를 422 응답으로 변환
    async def fault(request: Request, error: Fault) -> JSONResponse:
        # body 안 위치와 메시지를 담는다
        detail = [{"loc": ["body", *error.loc], "msg": error.message, "type": "value_error"}]
        return JSONResponse(status_code=422, content={"detail": detail})  # 422 로 응답

    @app.exception_handler(Lack)  # 미지원(Lack) 처리기
    # 미지원 오류를 501 응답으로 변환
    async def lack(request: Request, error: Lack) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(error)})  # 501 로 응답

    @app.exception_handler(Conflict)  # 충돌(Conflict) 처리기
    # 충돌 오류를 409 응답으로 변환
    async def conflict(request: Request, error: Conflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})  # 409 로 응답

    @app.exception_handler(Outage)  # 입출력 장애(Outage) 처리기
    # 장애를 503 응답으로 변환
    async def outage(request: Request, error: Outage) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})  # 503 으로 응답

    app.include_router(state.router)  # 상태 API 를 붙임
    app.include_router(control.router)  # 제어 API 를 붙임
    app.include_router(logs.router)  # 기록 API 를 붙임
    if static_dir is not None and Path(static_dir).is_dir():  # 빌드된 프론트 폴더가 있으면
        # 맨 마지막에 붙인다(API 경로가 먼저 잡힌다)
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="front")
    return app  # 만든 앱을 반환


# 밀린 tick 을 하나씩 처리하고 다음 tick 까지 잔다
async def pulse(service: Experiment) -> None:
    while True:  # 끝날 때까지 반복
        service.catchup(limit=1)  # 밀린 tick 을 하나 처리
        delay = service.delay()  # 다음 tick 까지 남은 시간
        # 남은 시간만큼(최대 MAX 까지) 잔다
        await asyncio.sleep(MAX_TICKER_SLEEP_S if delay is None else min(delay, MAX_TICKER_SLEEP_S))


app = factory()  # uvicorn 이 읽는 앱 객체
