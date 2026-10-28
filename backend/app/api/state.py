from app.api.deps import ServiceDep
from app.schemas import Board
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/state", response_model=Board)  # GET /api/state 로 현재 상태를 냄
# 상태를 돌려주는 함수
async def report(service: ServiceDep) -> Board:
    return Board.snapshot(service.snapshot)  # 서비스의 최신 스냅샷을 응답 모양으로 변환


@router.get("/api/config")
# 설정을 돌려주는 함수
async def profile(service: ServiceDep) -> dict:
    return service.config  # 서비스가 쥔 설정을 그대로 냄


@router.get("/health")  # GET /health 로 살아 있는지 알림
# 서버 상태를 돌려주는 함수
async def health() -> dict:
    return {"status": "ok"}
