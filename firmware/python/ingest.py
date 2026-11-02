import binascii

# 서버 /api/ingest 메시지(REV16 모양). 서버는 거리를 받으므로 거리 = 설치 높이 - 수위
DEVICE_ID = "esp32_1"  # backend/config.yaml devices.allowed 에 있는 이름
INSTALL_HEIGHT_MM = 600.0  # backend/config.yaml sensors.A.install_height_mm 와 같은 값
PATH = "/api/ingest"  # 서버 주소 뒤에 붙는 경로


# 부팅 ID: 무작위 바이트의 16진 글자
def boot_id(raw):
    return binascii.hexlify(raw).decode()


# 메시지 하나. level_mm 이 None(센서 이상)이면 거리는 null, A 는 fault
def message(boot, seq, t_ms, level_mm, device=DEVICE_ID, height_mm=INSTALL_HEIGHT_MM):
    ok = level_mm is not None
    return {
        "deviceId": device,
        "bootId": boot,
        "seq": seq,
        "tMs": t_ms,
        "readings": {
            "distA_mm": round(height_mm - level_mm, 1) if ok else None,
            "distB_mm": None,
            "weight_g": None,
        },
        "sensorStatus": {"A": "ok" if ok else "fault", "B": "absent", "load": "absent"},
    }
