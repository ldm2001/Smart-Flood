import hashlib
import json
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"  # 설정 파일(config.yaml) 위치


# 설정 파일을 읽어 사전으로 반환
def settings(path: str | Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"{path}: 최상위가 매핑이 아니다")
    return cfg


# 설정의 지문(해시)을 만듦. 값이 같으면 키 순서와 상관없이 같음
def checksum(config: dict) -> str:
    try:
        text = json.dumps(
            config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as error:  # JSON 으로 쓸 수 없는 값(NaN·날짜 등)이면
        raise ValueError(f"config 를 JSON 으로 기록할 수 없다: {error}") from None
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
