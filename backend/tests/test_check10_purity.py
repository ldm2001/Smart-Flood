import ast
import pytest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
CORE_DIR = BACKEND_DIR / "app" / "core"

BANNED_MODULES = {  # core 가 가져오면 안 되는 모듈들
    "fastapi", "starlette", "pydantic", "uvicorn", "httpx", "requests",
    "time", "datetime",  # 시간(시간은 인자로 받음)
    "os", "io", "pathlib", "shutil", "tempfile", "glob", "fileinput", "socket", "urllib",
    "http", "logging", "sqlite3", "subprocess", "yaml", "json", "pickle", "csv",
    "importlib", "builtins", "sys",
# 집합을 닫음(줄 모양은 서식 도구가 건드리지 않음)
}  # fmt: skip
BANNED_APP_MODULES = (  # core 는 바깥 계층(API·어댑터·포트·설정 로더)을 모름
    "app.api",
    "app.adapters",
    "app.ports",
    "app.main",
    "app.schemas",
    "app.config",
)
BANNED_CALLS = {"open", "print", "input", "exec", "eval", "compile", "__import__"}
BANNED_METHOD_CALLS = {"now", "utcnow", "today", "time_ns", "perf_counter", "monotonic"}


# from 가져오기가 가리키는 모듈의 전체 이름을 구하는 함수
def target(node: ast.ImportFrom, package: str) -> str:
    if node.level == 0:  # 점 없는 절대 경로면
        return node.module or ""  # 그 이름 그대로 반환
    parts = package.split(".")[: len(package.split(".")) - (node.level - 1)]
    return ".".join(parts + ([node.module] if node.module else []))


# 가져오면 안 되는 모듈인지 알려 주는 함수
def taboo(module: str) -> bool:
    if module.split(".")[0] in BANNED_MODULES:
        return True
    return any(module == m or module.startswith(m + ".") for m in BANNED_APP_MODULES)


# 소스에서 금지된 가져오기·호출을 찾음. package 는 상대 경로 해석용 이름
def offenses(source: str, package: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = target(node, package)
            names = [base] + [f"{base}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BANNED_CALLS:
                found.append(f"line {node.lineno}: {func.id}()")
            elif isinstance(func, ast.Attribute) and func.attr in BANNED_METHOD_CALLS:
                found.append(f"line {node.lineno}: .{func.attr}()")
            continue
        else:
            continue
        found += [f"line {node.lineno}: import {name}" for name in names if taboo(name)]
    return found


# core 폴더의 모든 파이썬 파일을 이름순으로 반환
def sources():
    return sorted(CORE_DIR.rglob("*.py"))


# 파일이 속한 패키지의 점 이름을 구하는 함수
def namespace(path: Path) -> str:
    return ".".join(path.parent.relative_to(BACKEND_DIR).parts)


# core 에 핵심 모듈이 있는지 검사
def test_core_modules_exist():
    assert {"model.py", "predictor.py", "calibration.py"} <= {p.name for p in sources()}


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)  # core 파일마다 반복
# core 파일이 순수한지 검사
def test_core_file_is_pure(path):
    assert offenses(path.read_text(encoding="utf-8"), namespace(path)) == []


@pytest.mark.parametrize(
    "snippet",
    [
        "import fastapi",
        "from fastapi import FastAPI",
        "from pydantic import BaseModel",
        "import time",
        "from datetime import datetime",
        "import datetime as dt",
        "from os import path",
        "import pathlib",
        "import importlib",
        "from ..adapters import sim_source",
        "from .. import config",
        "from app.api import state",
        "data = open('x.jsonl')",
        "stamp = clock.now()",
        "os_mod = __import__('os')",
    ],
)
# 검사기가 금지 소스를 잡는지 확인
def test_checker_flags_banned_source(snippet):
    assert offenses(snippet, "app.core") != []


@pytest.mark.parametrize(
    "snippet",
    [
        "import math",
        "from dataclasses import dataclass",
        "from __future__ import annotations",
        "from .model import step",
        "from . import model",
    ],
)
# 검사기가 순수한 소스는 통과시키는지 확인
def test_checker_allows_pure_source(snippet):
    assert offenses(snippet, "app.core") == []
