from __future__ import annotations

import json
import logging
from app.api.deps import ServiceDep
from app.ports.experiment_log import (
    EXPERIMENT_ID,
    Absence,
    Flaw,
    Journal,
)
from app.service import Outage, shield
from collections.abc import Iterator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from itertools import chain, islice

META_FIELDS = ("experimentId", "startTime", "dataSource", "modelVersion", "configHash")
NDJSON = "application/x-ndjson"  # 줄 단위 JSON(NDJSON) 응답 형식
BATCH_LINES = 256  # 한 번에 보낼 줄 수. 한 줄씩이면 느려서(1시간 기록에 0.6 s) 묶음

router = APIRouter(prefix="/api/logs")  # /api/logs 아래 라우터. 파일을 읽으니 처리기는 동기 함수
log = logging.getLogger(__name__)


@router.get("")
# 회차 목록: 날짜·번호 순, meta 필드만 반환
def catalog(service: ServiceDep) -> dict:
    with shield():  # 입출력 오류는 503 으로
        experiment_ids = service.experiment_log.index()
    metas = (summary(service.experiment_log, experiment_id) for experiment_id in experiment_ids)
    return {"logs": [meta for meta in metas if meta is not None]}


@router.get("/{experiment_id}")
# 회차 기록 전체를 NDJSON 으로 그대로 전송
def transcript(experiment_id: str, service: ServiceDep) -> StreamingResponse:
    records = access(service.experiment_log, experiment_id)  # 기록 줄을 엶(없는 ID 는 404)
    with shield():  # 입출력 오류는 503 으로
        try:
            first = list(islice(records, 1))  # 응답 전에 첫 줄을 읽음(못 읽으면 빈 200 대신 503)
        except Flaw as error:
            raise Outage(f"실험 기록을 쓸 수 없다: {error}") from None  # 읽기 실패와 같은 503
    return StreamingResponse(  # 첫 줄에 나머지를 묶음으로 이어 흘려 전송
        chain(ndjson(experiment_id, iter(first)), batches(ndjson(experiment_id, records))),
        media_type=NDJSON,  # 줄 단위 JSON 형식
    )


@router.get("/{experiment_id}/events")
# 회차의 이벤트 줄만, 기록된 순서대로 반환
def timeline(experiment_id: str, service: ServiceDep) -> dict:
    records = access(service.experiment_log, experiment_id)  # 기록 줄을 엶(없는 ID 는 404)
    events = []
    with shield():  # 입출력 오류는 503 으로
        try:
            events.extend(record for record in records if record.get("type") == "event")
        except Flaw as error:
            log.warning("%s 이벤트를 끝까지 읽지 못했다: %s", experiment_id, error)
    return {"events": events}


# 기록 줄을 엶. 형식이 틀리거나 없는 ID 는 404
def access(experiment_log: Journal, experiment_id: str) -> Iterator[dict]:
    if not EXPERIMENT_ID.fullmatch(experiment_id):
        raise miss(experiment_id)  # 404 로 처리
    try:
        with shield():  # 입출력 오류는 503 으로
            return experiment_log.records(experiment_id)  # 기록 줄을 하나씩 내는 값을 반환
    except Absence:
        raise miss(experiment_id) from None  # 404 로 처리


# 404 오류를 만듦
def miss(experiment_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"그런 실험 기록이 없다: {experiment_id}")


# 목록에 실을 meta 필드. 첫 줄이 이 회차 meta 가 아니면 None
def summary(experiment_log: Journal, experiment_id: str) -> dict | None:
    try:
        first = next(iter(experiment_log.records(experiment_id)), None)  # 첫 줄(없으면 None)
    except (Absence, Flaw, OSError) as error:
        log.warning("%s 기록의 meta 를 읽을 수 없어 목록에서 뺀다: %s", experiment_id, error)
        return None
    if not (first and first.get("type") == "meta" and first.get("experimentId") == experiment_id):
        log.warning("%s 기록의 첫 줄이 이 회차의 meta 가 아니라 목록에서 뺀다", experiment_id)
        return None
    fields = {key: first.get(key) for key in META_FIELDS}
    if any(value is None for value in fields.values()):
        log.warning("%s 기록의 meta 에 빠진 필드가 있어 목록에서 뺀다", experiment_id)
        return None
    return fields


# 기록 한 건을 JSON 한 줄로. 파일의 줄과 같은 바이트
def ndjson(experiment_id: str, records: Iterator[dict]) -> Iterator[str]:
    try:
        for record in records:
            yield json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    except Flaw as error:
        log.warning("%s 기록을 끝까지 보내지 못했다: %s", experiment_id, error)


# BATCH_LINES 줄씩 묶음. 도중 입출력 오류는 응답을 끊음
def batches(lines: Iterator[str]) -> Iterator[str]:
    while batch := "".join(islice(lines, BATCH_LINES)):
        yield batch
