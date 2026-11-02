from app.api.deps import ServiceDep
from app.schemas import (
    Blank,
    Board,
    Clog,
    Feed,
    Kickoff,
    Message,
    Receipt,
    Shower,
)
from fastapi import APIRouter

router = APIRouter(prefix="/api")  # /api 아래 라우터. 같은 요청을 또 보내도 결과가 같음


@router.post("/experiment/start", response_model=Board)
# 실험을 시작(본문은 없어도 됨)
async def launch(service: ServiceDep, body: Kickoff | None = None) -> Board:
    body = body or Kickoff()
    blockage = body.blockage  # 처음부터 걸 막힘(없을 수 있음)
    service.launch(
        rain=body.rain,
        blockage=blockage.type if blockage else None,  # 막힘 종류(없으면 없음)
        location=blockage.location if blockage else None,  # 막힘 위치(없으면 없음)
    )
    return Board.snapshot(service.snapshot)


@router.post("/experiment/stop", response_model=Board)
# 실험을 끝냄
async def end(service: ServiceDep, body: Blank | None = None) -> Board:
    service.end()
    return Board.snapshot(service.snapshot)


@router.post("/experiment/reset", response_model=Board)
# 대기 상태로 돌림
async def standby(service: ServiceDep, body: Blank | None = None) -> Board:
    service.standby()
    return Board.snapshot(service.snapshot)


@router.post("/rain", response_model=Board)
# 강우를 변환
async def rain(service: ServiceDep, body: Shower) -> Board:
    service.rain(intensity=body.intensity, mm_per_h=body.mmPerHour)
    return Board.snapshot(service.snapshot)


@router.post("/blockage", response_model=Board)
# 막힘을 변환
async def clog(service: ServiceDep, body: Clog) -> Board:
    service.blockage(body.type, body.location)
    return Board.snapshot(service.snapshot)


@router.post("/source", response_model=Board)
# 입력원(sim·replay·live)을 변환
async def channel(service: ServiceDep, body: Feed) -> Board:
    service.channel(body.mode, body.logId)
    return Board.snapshot(service.snapshot)


@router.post("/ingest", response_model=Receipt)
# 장치 메시지를 받음(입력원이 live 일 때 다음 tick 에 쓰임)
async def intake(service: ServiceDep, body: Message) -> Receipt:
    service.intake(body.model_dump())
    return Receipt(deviceId=body.deviceId, seq=body.seq, dataSource=service.snapshot.data_source)
