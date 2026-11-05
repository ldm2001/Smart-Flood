import pytest
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 저장소 뿌리(Smart-Flood)
PHONE = re.compile(r"(?<![\d.])01[016789]-?\d{3,4}-?\d{4}(?!\d)")  # 한국 휴대전화 전체 번호
KEY = re.compile(r"(?<![0-9A-Z])NCS[0-9A-Z]{13}(?![0-9A-Z])")  # SOLAPI 키 모양(문서 예: NCS+13자)
# SOLAPI 시크릿 모양: 대문자·숫자가 섞인 32자
SECRET = re.compile(r"(?<![0-9A-Za-z])(?=[0-9A-Z]*\d)(?=[0-9A-Z]*[A-Z])[0-9A-Z]{32}(?![0-9A-Za-z])")
LARGE = 5_000_000  # 이보다 큰 파일은 훑지 않음(바이트)


# git 이 아는 파일 목록(추적 중 + 무시되지 않은 새 파일). git 이 없으면 건너뜀
def files() -> list[Path]:
    try:
        listing = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        out = subprocess.run(
            ["git", "-C", str(ROOT), *listing], capture_output=True, check=True, timeout=30
        ).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git 저장소가 아님")
    names = sorted({name for name in out.decode("utf-8").split("\0") if name})
    return [ROOT / name for name in names if (ROOT / name).is_file()]


# 텍스트 파일 내용(바이너리·큰 파일은 None)
def content(path: Path) -> str | None:
    if path.stat().st_size > LARGE:
        return None
    raw = path.read_bytes()
    if b"\0" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


# 저장소 파일에 키·시크릿 모양과 휴대전화 전체 번호가 없는지 검사
def test_no_secrets():
    found = []
    for path in files():
        body = content(path)
        if body is None:
            continue
        for kind, pattern in (("번호", PHONE), ("키", KEY), ("시크릿", SECRET)):
            for match in pattern.finditer(body):
                line = body.count("\n", 0, match.start()) + 1
                found.append(f"{path.relative_to(ROOT)}:{line}: {kind}")  # 값은 안 찍음
    assert found == []


# 스캔 규칙이 실제 모양을 잡는지(값은 조립해 이 파일 자체가 걸리지 않게)
def test_patterns():
    number = "010" + "-" + "1234" + "-" + "5678"
    assert PHONE.search(number) and PHONE.search(number.replace("-", ""))
    assert PHONE.search("011" + "123" + "4567")
    assert not PHONE.search("0." + "010" + "12345678")  # 소수
    assert not PHONE.search("02" + "9302266")  # 지역 번호
    assert KEY.search("NC" + "SAYU7YDBXYORXC")
    assert SECRET.search("A1" * 16)
    assert not SECRET.search("A" * 32)


# .env 는 git 에 없고 무시 대상, .env.example 만 저장소에 둠
def test_env_untracked():
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True, timeout=30
    ).stdout.decode("utf-8")
    envs = [n for n in out.split("\0") if Path(n).name.startswith(".env")]
    assert all(Path(n).name == ".env.example" for n in envs)
    for name in ("backend/.env", ".env", "backend/.env.local"):
        ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name], timeout=30)
        assert ignored.returncode == 0, f"{name} 가 무시 대상이 아님"
    shown = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "-q", "backend/.env.example"], timeout=30
    )
    assert shown.returncode == 1  # 예시 파일은 저장소에 둘 수 있음
