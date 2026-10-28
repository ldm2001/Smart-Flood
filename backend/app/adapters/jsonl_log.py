from __future__ import annotations

import json
import os
from app.ports.experiment_log import EXPERIMENT_ID, Absence, Flaw
from collections.abc import Iterator
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"  # 기록 폴더(backend/logs)


# JSONL 기록: 회차마다 파일 하나, 한 줄에 JSON 하나
class Jsonl:
    # 기록 폴더를 받음
    def __init__(self, directory: str | Path = LOG_DIR) -> None:
        self.directory = Path(directory)

    # 회차 파일 끝에 한 건을 붙임
    def entry(self, experiment_id: str, record: dict) -> None:
        self.batch(experiment_id, [record])

    # 회차 파일 끝에 여러 건을 붙임. 다 쓰이거나 하나도 안 쓰임
    def batch(self, experiment_id: str, records: list[dict]) -> None:
        path = self.path(experiment_id)
        if not records:  # 쓸 것이 없으면 파일도 만들지 않음(빈 파일이 회차 번호를 먹지 않게)
            return
        body = "".join(dump(record) for record in records).encode("utf-8")  # 먼저 글자로 변환
        self.directory.mkdir(parents=True, exist_ok=True)
        mark = None  # 쓰기 전 파일 끝(열지 못했으면 None)
        try:
            with path.open("ab") as f:  # 파일을 바이트 이어쓰기로 엶(쓸 때마다 열고 닫음)
                mark = f.tell()
                f.write(body)
                f.flush()
        except OSError:
            if mark is not None:
                rollback(path, mark)  # 닫힌 뒤에 되돌림(버퍼 재전송이 또 실패해도 되돌릴 수 있게)
            raise  # 오류를 그대로 올림

    # 기록이 있는 회차 ID 를 날짜·번호 순으로 반환
    def index(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        ids = [
            p.stem  # 파일 이름(확장자 뺀 것)을
            for p in self.directory.glob("*.jsonl")
            if p.is_file() and EXPERIMENT_ID.fullmatch(p.stem)  # 진짜 파일이고 ID 모양일 때만 넣음
        ]
        return sorted(ids, key=rank)

    # 회차 기록을 앞에서부터 반환
    def records(self, experiment_id: str) -> Iterator[dict]:
        path = self.path(experiment_id)
        if not path.is_file():
            raise Absence(experiment_id)
        return stream(path)  # 줄을 하나씩 읽어 주는 반복자를 반환

    # 회차 ID 로 파일 경로를 만듦
    def path(self, experiment_id: str) -> Path:
        if not EXPERIMENT_ID.fullmatch(experiment_id):
            raise ValueError(f"실험 ID 형식이 아니다: {experiment_id!r}")
        return self.directory / f"{experiment_id}.jsonl"  # 폴더 아래 ID.jsonl 경로를 반환


# 기록 한 건을 JSON 한 줄로 변환
def dump(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


# 실패한 쓰기를 되돌림. 쓰기 전 끝으로 자르고, 그러면 빈 파일이면 지움(회차 번호를 먹지 않게)
def rollback(path: Path, mark: int) -> None:
    if mark == 0:
        path.unlink(missing_ok=True)
    else:
        os.truncate(path, mark)


# ID 를 (날짜, 번호) 정렬 기준으로 변환
def rank(experiment_id: str) -> tuple[str, int]:
    date, number = EXPERIMENT_ID.fullmatch(experiment_id).groups()
    return date, int(number)


# 파일의 줄을 하나씩 풂
def stream(path: Path) -> Iterator[dict]:
    with path.open("rb") as f:  # 바이트로 엶(끊긴 마지막 줄이 글자 중간일 수 있음)
        for number, line in enumerate(f, start=1):
            if not line.endswith(b"\n"):
                return
            try:
                record = json.loads(line.decode("utf-8"), parse_constant=veto)  # NaN·Infinity 거부
            except ValueError as error:
                raise Flaw(f"{path.name} {number}번째 줄: {error}") from None
            if not isinstance(record, dict):  # JSON 객체(사전)가 아니면
                raise Flaw(f"{path.name} {number}번째 줄이 JSON 객체가 아니다")
            yield record


# NaN·Infinity 같은 JSON 아닌 값을 차단
def veto(name: str) -> float:
    raise ValueError(f"JSON 이 아닌 값 {name}")
