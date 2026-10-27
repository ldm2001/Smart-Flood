from app.service import Experiment
from fastapi import Depends, Request
from typing import Annotated


# 요청에서 앱에 달린 서비스를 꺼내는 함수
def provider(request: Request) -> Experiment:
    return request.app.state.service  # 조립할 때 한 번 만든 서비스를 반환


ServiceDep = Annotated[Experiment, Depends(provider)]  # 라우터가 서비스를 받는 표시(의존성 주입)
