from __future__ import annotations

import json
from app.ports.experiment_log import EXPERIMENT_ID, Absence, Flaw
from collections.abc import Iterator
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"  # 기록 폴더(backend/logs)


# JSONL 기록: 회차마다 파일 하나, 한 줄에 JSON 하나
class Jsonl:
    # 기록 폴더를 받음
    def __init__(self, directory: str | Path = LOG_DIR) -> None:
        self.directory = Path(directory)  # 폴더 경로를 보관

    # 회차 파일 끝에 한 건을 붙임
    def entry(self, experiment_id: str, record: dict) -> None:
        self.batch(experiment_id, [record])  # 한 건짜리 묶음으로 넘긴다

    # 회차 파일 끝에 여러 건을 붙인다. 다 쓰이거나 하나도 안 쓰임
    def batch(self, experiment_id: str, records: list[dict]) -> None:
        path = self.path(experiment_id)  # 회차 파일 경로를 구
        # 먼저 글자로 바꾼다(실패하면 파일을 만들지 않는다)
        body = "".join(dump(record) for record in records).encode("utf-8")
        self.directory.mkdir(parents=True, exist_ok=True)  # 폴더가 없으면 만듦
        fresh = not path.is_file()  # 이 쓰기가 파일을 새로 만드는지 확인
        with path.open("ab") as f:  # 파일을 바이트 이어쓰기로 연다(쓸 때마다 열고 닫는다)
            mark = f.tell()  # 쓰기 전 끝 위치를 기억
            try:  # 쓰다 끊기면 쓴 만큼을 되돌린다
                f.write(body)  # 묶음을 한 번에 기록
                f.flush()  # 버퍼를 비워 실패를 지금 받음
            except OSError:  # 끝까지 쓰지 못했으면
                if fresh:  # 이번에 만든 파일이면 통째로 지운다(회차 번호를 먹지 않게)
                    path.unlink(missing_ok=True)  # 파일을 제거
                else:  # 있던 파일이면 쓰다 남은 조각만 잘라냄
                    f.truncate(mark)  # 쓰기 전 끝으로 되돌린다
                raise  # 오류를 그대로 올림

    # 기록이 있는 회차 ID 를 날짜·번호 순으로 반환
    def index(self) -> list[str]:
        if not self.directory.is_dir():  # 폴더가 없으면
            return []  # 빈 목록을 반환
        ids = [  # ID 목록을 만듦
            p.stem  # 파일 이름(확장자 뺀 것)을
            for p in self.directory.glob("*.jsonl")  # jsonl 파일마다 보고
            if p.is_file() and EXPERIMENT_ID.fullmatch(p.stem)  # 진짜 파일이고 ID 모양일 때만 넣음
        ]
        return sorted(ids, key=rank)  # 날짜·번호 순으로 정렬해 반환

    # 회차 기록을 앞에서부터 반환
    def records(self, experiment_id: str) -> Iterator[dict]:
        path = self.path(experiment_id)  # 회차 파일 경로를 구
        if not path.is_file():  # 파일이 없으면
            raise Absence(experiment_id)  # 없다는 오류를 냄
        return stream(path)  # 줄을 하나씩 읽어 주는 반복자를 반환

    # 회차 ID 로 파일 경로를 만듦
    def path(self, experiment_id: str) -> Path:
        if not EXPERIMENT_ID.fullmatch(experiment_id):  # ID 모양이 아니면
            # 형식이 아니라는 오류를 냄
            raise ValueError(f"실험 ID 형식이 아니다: {experiment_id!r}")
        return self.directory / f"{experiment_id}.jsonl"  # 폴더 아래 ID.jsonl 경로를 반환


# 기록 한 건을 JSON 한 줄로 변환
def dump(record: dict) -> str:
    # 줄바꿈까지 붙여 반환
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


# ID 를 (날짜, 번호) 정렬 기준으로 변환
def rank(experiment_id: str) -> tuple[str, int]:
    date, number = EXPERIMENT_ID.fullmatch(experiment_id).groups()  # ID 에서 날짜와 번호를 추출
    return date, int(number)  # 번호는 숫자로 바꿔 반환


# 파일의 줄을 하나씩 푼다
def stream(path: Path) -> Iterator[dict]:
    with path.open("rb") as f:  # 바이트로 연다(끊긴 마지막 줄이 글자 중간일 수 있다)
        for number, line in enumerate(f, start=1):  # 줄 번호와 함께 읽음
            if not line.endswith(b"\n"):  # 줄바꿈으로 안 끝났으면
                return  # 쓰는 중이거나 끊긴 마지막 줄이니 멈춘다
            try:  # 줄을 JSON 으로 풀어 확인
                # 글자로 바꿔 풀고, NaN 같은 값은 거부
                record = json.loads(line.decode("utf-8"), parse_constant=veto)
            except ValueError as error:  # 풀 수 없으면
                # 몇 번째 줄인지 담아 Flaw 를 냄
                raise Flaw(f"{path.name} {number}번째 줄: {error}") from None
            if not isinstance(record, dict):  # JSON 객체(사전)가 아니면
                # 객체가 아니라는 Flaw 를 냄
                raise Flaw(f"{path.name} {number}번째 줄이 JSON 객체가 아니다")
            yield record  # 읽은 기록을 하나씩 내전송


# NaN·Infinity 같은 JSON 아닌 값을 차단
def veto(name: str) -> float:
    raise ValueError(f"JSON 이 아닌 값 {name}")  # 그 값을 알리는 오류를 냄
