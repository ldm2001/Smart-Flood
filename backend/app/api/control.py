from app.api.deps import ServiceDep
from app.schemas import (
    Blank,
    Board,
    Clog,
    Feed,
    Kickoff,
    Shower,
)
from fastapi import APIRouter

router = APIRouter(prefix="/api")  # /api 아래 라우터. 같은 요청을 또 보내도 결과가 같다


@router.post("/experiment/start", response_model=Board)  # 실험 시작 경로
# 실험을 시작한다(본문은 없어도 됨)
async def launch(service: ServiceDep, body: Kickoff | None = None) -> Board:
    body = body or Kickoff()  # 본문이 없으면 기본값을 기록
    blockage = body.blockage  # 처음부터 걸 막힘(없을 수 있다)
    service.launch(  # 서비스에 시작을 맡긴다
        rain=body.rain,  # 강우 단계
        blockage=blockage.type if blockage else None,  # 막힘 종류(없으면 없음)
        location=blockage.location if blockage else None,  # 막힘 위치(없으면 없음)
    )
    return Board.snapshot(service.snapshot)  # 바뀐 뒤의 상태를 응답


@router.post("/experiment/stop", response_model=Board)  # 실험 종료 경로
# 실험을 끝냄
async def end(service: ServiceDep, body: Blank | None = None) -> Board:
    service.end()  # 서비스에 종료를 맡긴다
    return Board.snapshot(service.snapshot)  # 바뀐 뒤의 상태를 응답


@router.post("/experiment/reset", response_model=Board)  # 실험 초기화 경로
# 대기 상태로 돌린다
async def standby(service: ServiceDep, body: Blank | None = None) -> Board:
    service.standby()  # 서비스에 초기화를 맡긴다
    return Board.snapshot(service.snapshot)  # 바뀐 뒤의 상태를 응답


@router.post("/rain", response_model=Board)  # 강우 경로
# 강우를 변환
async def rain(service: ServiceDep, body: Shower) -> Board:
    service.rain(intensity=body.intensity, mm_per_h=body.mmPerHour)  # 단계 또는 mm/h 값을 넘긴다
    return Board.snapshot(service.snapshot)  # 바뀐 뒤의 상태를 응답


@router.post("/blockage", response_model=Board)  # 막힘 경로
# 막힘을 변환
async def clog(service: ServiceDep, body: Clog) -> Board:
    service.blockage(body.type, body.location)  # 종류와 위치를 넘긴다
    return Board.snapshot(service.snapshot)  # 바뀐 뒤의 상태를 응답


@router.post("/source", response_model=Board)  # 입력원 경로
# 입력원(sim·replay)을 변환
async def channel(service: ServiceDep, body: Feed) -> Board:
    service.channel(body.mode, body.logId)  # 모드와 기록 ID 를 넘긴다
    return Board.snapshot(service.snapshot)  # 바뀐 뒤의 상태를 응답
