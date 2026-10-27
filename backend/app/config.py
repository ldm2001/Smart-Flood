import hashlib
import json
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"  # 설정 파일(config.yaml) 위치


# 설정 파일을 읽어 사전으로 반환
def settings(path: str | Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:  # 파일을 UTF-8 로 연다
        cfg = yaml.safe_load(f)  # YAML 을 안전하게 읽음
    if not isinstance(cfg, dict):  # 최상위가 사전이 아니면
        raise ValueError(f"{path}: 최상위가 매핑이 아니다")  # 오류를 냄
    return cfg  # 읽은 설정을 반환


# 설정의 지문(해시)을 만든다. 값이 같으면 키 순서와 상관없이 같다
def checksum(config: dict) -> str:
    try:  # JSON 글자로 바꿔 확인
        text = json.dumps(  # 키를 정렬해 글자로 변환
            # 공백 없이, 한글 그대로, NaN 은 거부
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as error:  # JSON 으로 쓸 수 없는 값(NaN·날짜 등)이면
        # 기록할 수 없다는 오류를 냄
        raise ValueError(f"config 를 JSON 으로 기록할 수 없다: {error}") from None
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()  # sha256 지문을 글자로 반환
