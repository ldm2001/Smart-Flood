import ast
import pytest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend 폴더 경로
CORE_DIR = BACKEND_DIR / "app" / "core"  # 검사할 core 폴더

BANNED_MODULES = {  # core 가 가져오면 안 되는 모듈들
    "fastapi", "starlette", "pydantic", "uvicorn", "httpx", "requests",  # 웹·검증 프레임워크
    "time", "datetime",  # 시간(시간은 인자로 받는다)
    # 파일·OS·네트워크 입출력
    "os", "io", "pathlib", "shutil", "tempfile", "glob", "fileinput", "socket", "urllib",
    # 통신·로그·DB·파일 형식
    "http", "logging", "sqlite3", "subprocess", "yaml", "json", "pickle", "csv",
    "importlib", "builtins", "sys",  # 위 규칙을 우회하는 통로
# 집합을 닫는다(줄 모양은 서식 도구가 건드리지 않는다)
}  # fmt: skip
BANNED_APP_MODULES = (  # core 는 바깥 계층(API·어댑터·포트·설정 로더)을 모른다
    "app.api",  # API 계층
    "app.adapters",  # 어댑터 계층
    "app.ports",  # 포트 계층
    "app.main",  # 앱 조립
    "app.schemas",  # 응답 스키마
    "app.config",  # 설정 로더
)
# 부르면 안 되는 내장 함수
BANNED_CALLS = {"open", "print", "input", "exec", "eval", "compile", "__import__"}
# 부르면 안 되는 시각 메서드
BANNED_METHOD_CALLS = {"now", "utcnow", "today", "time_ns", "perf_counter", "monotonic"}


# from 가져오기가 가리키는 모듈의 전체 이름을 구하는 함수
def target(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:  # 점 없는 절대 경로면
        return node.module or ""  # 그 이름 그대로 반환
    # 상대 경로의 점 수만큼 패키지를 거슬러 올라감
    parts = package.split(".")[: len(package.split(".")) - (node.level - 1)]
    # 올라간 패키지에 모듈 이름을 붙임
    return ".".join(parts + ([node.module] if node.module else []))


# 가져오면 안 되는 모듈인지 알려 주는 함수
def taboo(module: str) -> bool:
    if module.split(".")[0] in BANNED_MODULES:  # 첫 이름이 금지 목록에 있으면
        return True  # 금지다
    # 바깥 계층 이름과 같거나 그 아래면 금지다
    return any(module == m or module.startswith(m + ".") for m in BANNED_APP_MODULES)


# 소스에서 금지된 가져오기·호출을 찾는다. package 는 상대 경로 해석용 이름
def offenses(source: str, package: str) -> list[str]:
    found = []  # 찾은 위반을 모을 목록
    for node in ast.walk(ast.parse(source)):  # 구문 트리의 모든 노드를 확인
        if isinstance(node, ast.Import):  # import 문이면
            names = [alias.name for alias in node.names]  # 가져오는 모듈 이름들
        elif isinstance(node, ast.ImportFrom):  # from 가져오기면
            base = target(node, package)  # 가리키는 모듈의 전체 이름
            # 모듈과 그 안의 이름을 모두 확인
            names = [base] + [f"{base}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Call):  # 함수 호출이면
            func = node.func  # 부르는 대상
            if isinstance(func, ast.Name) and func.id in BANNED_CALLS:  # 금지된 내장 함수면
                found.append(f"line {node.lineno}: {func.id}()")  # 줄 번호와 함께 적는다
            # 금지된 시각 메서드면
            elif isinstance(func, ast.Attribute) and func.attr in BANNED_METHOD_CALLS:
                found.append(f"line {node.lineno}: .{func.attr}()")  # 줄 번호와 함께 적는다
            continue  # 다음 노드로 감
        else:  # 그 밖의 노드는
            continue  # 건너뛴다
        # 금지된 모듈이면 줄 번호와 함께 적는다
        found += [f"line {node.lineno}: import {name}" for name in names if taboo(name)]
    return found  # 찾은 위반을 반환


# core 폴더의 모든 파이썬 파일을 이름순으로 반환
def sources():
    return sorted(CORE_DIR.rglob("*.py"))  # 하위 폴더까지 찾아 정렬


# 파일이 속한 패키지의 점 이름을 구하는 함수
def namespace(path: Path) -> str:
    # backend 폴더 기준 경로를 점으로 연결
    return ".".join(path.parent.relative_to(BACKEND_DIR).parts)


# core 에 핵심 모듈이 있는지 검사
def test_core_modules_exist():
    # model·predictor·calibration 이 있어야 함
    assert {"model.py", "predictor.py", "calibration.py"} <= {p.name for p in sources()}


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)  # core 파일마다 반복
# core 파일이 순수한지 검사
def test_core_file_is_pure(path):
    assert offenses(path.read_text(encoding="utf-8"), namespace(path)) == []  # 위반이 없어야 함


@pytest.mark.parametrize(  # 금지해야 하는 조각마다 반복
    "snippet",  # 조각 이름
    [  # 금지 조각 목록
        "import fastapi",  # 웹 프레임워크
        "from fastapi import FastAPI",  # 웹 프레임워크
        "from pydantic import BaseModel",  # 검증 프레임워크
        "import time",  # 시간
        "from datetime import datetime",  # 시간
        "import datetime as dt",  # 이름을 바꿔도 잡는다
        "from os import path",  # 파일·OS
        "import pathlib",  # 파일 경로
        "import importlib",  # 우회 통로
        "from ..adapters import sim_source",  # 상대 경로로 어댑터를 가져옴
        "from .. import config",  # 상대 경로로 설정 로더를 가져옴
        "from app.api import state",  # API 계층
        "data = open('x.jsonl')",  # 파일 열기
        "stamp = clock.now()",  # 시각 읽기
        "os_mod = __import__('os')",  # 문자열로 가져오기
    ],
)
# 검사기가 금지 소스를 잡는지 확인
def test_checker_flags_banned_source(snippet):
    assert offenses(snippet, "app.core") != []  # 위반이 나와야 함


@pytest.mark.parametrize(  # 허용해야 하는 조각마다 반복
    "snippet",  # 조각 이름
    [  # 허용 조각 목록
        "import math",  # 수학 도구
        "from dataclasses import dataclass",  # 데이터 묶음 도구
        "from __future__ import annotations",  # 타입 힌트 지연
        "from .model import step",  # 같은 폴더의 모듈
        "from . import model",  # 같은 폴더의 모듈
    ],
)
# 검사기가 순수한 소스는 통과시키는지 확인
def test_checker_allows_pure_source(snippet):
    assert offenses(snippet, "app.core") == []  # 위반이 없어야 함
