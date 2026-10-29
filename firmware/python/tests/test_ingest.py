import ingest


# REV16 스케치와 같은 모양: 거리 = 설치 높이 - 수위, B 와 로드셀은 absent 인지 검사
def test_message_has_the_rev16_shape():
    body = ingest.message("a1b2c3d4", 7, 7000, 40.0)
    assert body == {
        "deviceId": "esp32_1",
        "bootId": "a1b2c3d4",
        "seq": 7,
        "tMs": 7000,
        "readings": {"distA_mm": 560.0, "distB_mm": None, "weight_g": None},
        "sensorStatus": {"A": "ok", "B": "absent", "load": "absent"},
    }


# 센서 이상(수위 None)이면 거리는 null, A 는 fault 인지 검사
def test_fault_sends_null_and_fault():
    body = ingest.message("a1b2c3d4", 0, 0, None)
    assert body["readings"]["distA_mm"] is None
    assert body["sensorStatus"]["A"] == "fault"


# 거리는 소수 첫째 자리까지인지 검사(스케치의 String(x, 1))
def test_distance_is_rounded_to_one_decimal():
    assert ingest.message("b", 0, 0, 40.04)["readings"]["distA_mm"] == 560.0
    assert ingest.message("b", 0, 0, 40.06)["readings"]["distA_mm"] == 559.9


# 부팅 ID 는 무작위 바이트의 16진 글자인지 검사
def test_boot_id_is_hex():
    assert ingest.boot_id(b"\x01\xab\xff\x00") == "01abff00"


# 장치 이름과 설치 높이를 바꿀 수 있는지 검사
def test_device_and_height_are_parameters():
    body = ingest.message("b", 0, 0, 40.0, device="esp32_2", height_mm=500.0)
    assert (body["deviceId"], body["readings"]["distA_mm"]) == ("esp32_2", 460.0)
