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

FRONTEND_OUT = Path(__file__).resolve().parents[2] / "frontend" / "out"
MAX_TICKER_SLEEP_S = 0.25  # tick 사이 최대 잠(초). 가상 시계로 바꿔도 밀린 tick 을 알아챔


# 앱 조립: 서비스, CORS, 오류 응답, 1 Hz tick, 빌드된 프론트
def factory(
    config: dict | None = None,  # 설정(없으면 파일에서 읽음)
    *,
    clock: Clock | None = None,  # 시계(테스트에서 바꿔 끼움)
    source: Source | None = None,
    experiment_log: Journal | None = None,
    notifier: Notifier | None = None,
    start_ticker: bool = True,
    static_dir: str | Path | None = FRONTEND_OUT,  # 빌드된 프론트 폴더(없으면 붙이지 않음)
) -> FastAPI:
    config = settings() if config is None else config
    service = Experiment(
        config,
        clock=Wall() if clock is None else clock,  # 시계: 안 주면 진짜 시계
        source=Sim(config) if source is None else source,  # 입력원: 안 주면 가상 센서
        experiment_log=Jsonl() if experiment_log is None else experiment_log,  # 기록: 안 주면 JSONL
        notifier=notifier,
    )

    @asynccontextmanager
    # 앱이 도는 동안 열려 있는 구간
    async def lifespan(app: FastAPI):
        ticker = asyncio.create_task(pulse(service)) if start_ticker else None
        yield
        if ticker is not None:
            ticker.cancel()
            with suppress(asyncio.CancelledError):  # 취소 오류는 무시
                await ticker

    app = FastAPI(title="SMART FLOOD", lifespan=lifespan)
    app.state.service = service
    app.add_middleware(  # CORS 를 끼움
        CORSMiddleware,
        allow_origins=config["server"]["cors_origins"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)  # 요청 검증 오류(422) 처리기
    # 검증 오류를 422 응답으로 변환
    async def validation(request: Request, error: RequestValidationError) -> JSONResponse:
        detail = encoding(jsonable_encoder(error.errors()))  # 기본 처리기와 같은 모양
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(Fault)  # 입력 오류(Fault) 처리기
    # 입력 오류를 422 응답으로 변환
    async def fault(request: Request, error: Fault) -> JSONResponse:
        detail = [{"loc": ["body", *error.loc], "msg": error.message, "type": "value_error"}]
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(Conflict)  # 충돌(Conflict) 처리기
    # 충돌 오류를 409 응답으로 변환
    async def conflict(request: Request, error: Conflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(Outage)  # 입출력 장애(Outage) 처리기
    # 장애를 503 응답으로 변환
    async def outage(request: Request, error: Outage) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    app.include_router(state.router)  # 상태 API 를 붙임
    app.include_router(control.router)  # 제어 API 를 붙임
    app.include_router(logs.router)  # 기록 API 를 붙임
    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="front")  # API 경로 뒤에
    return app


# 밀린 tick 을 하나씩 처리하고 다음 tick 까지 잠
async def pulse(service: Experiment) -> None:
    while True:
        service.catchup(limit=1)  # 밀린 tick 을 하나 처리
        delay = service.delay()  # 다음 tick 까지 남은 시간
        await asyncio.sleep(MAX_TICKER_SLEEP_S if delay is None else min(delay, MAX_TICKER_SLEEP_S))


app = factory()  # uvicorn 이 읽는 앱 객체
