# SMART FLOOD sensor

`sensor` 는 센서와 보드 공간이다

ESP32 스케치를 만들고 부품을 하나씩 보드에 붙여 시험한다

`firmware/` 만 담고 서버와 웹은 `sim` 이 맡는다

보드가 서버로 보내는 메시지는 서버의 `/api/ingest` 계약을 따른다

여기서 만든 것은 `dev` 로 합친다

## 만든 것

### 본 스케치 `firmware/board/`

| 파일 | 내용 |
|---|---|
| `board.ino` | 수위 측정 · 펌프 제어 · 침수 예측 · 서버 전송 |
| `page.h` | 휴대폰으로 여는 관제 화면 |
| `secrets.h.example` | 접속 정보 견본 |

수위와 예측

- 100 ms 마다 수위를 읽는다
- 1초마다 최근 20초 상승 속도로 A·B·C 구역의 침수 시각을 예측해 주의 · 경계 · 침수 알림을 낸다
- 구역 기준 높이는 모형 바닥에서 A 40 mm · B 70 mm · C 110 mm 다
- 자로 잰 두 점으로 수위를 보정한다 (`cal1` · `cal2`)

관제 화면

- 보드가 연 와이파이에 휴대폰을 붙이고 시리얼에 찍힌 주소를 연다
- 센서 전압 · 수위 · 급수통 상태 · 구역 단계를 보여 준다
- 펌프 수동 ON · 정지 · 강우 회차 시작 · 30초 유량 측정 · 설정 저장을 한다
- 구역 · 단계 · 한계 수위 이름은 관제 웹과 같다
- 선행 시간 칸에 현재 수위 경보와 견준 설명을 단다

펌프 제어와 공회전 막기

- 강우 흉내로 펌프를 2초 켜고 8초 끄기를 되풀이한다
- 릴레이 끄기는 핀을 고임피던스(입력)로 두는 방식 하나로 맞췄다
- 펌프가 멈추는 조건
  - 플로트가 급수통 물 모자람을 알리면 100 ms 안
  - 강우 모드에서 수위센서 이상
  - 안전 최대 수위 100 mm 도달
  - 연속 가동 60초 초과
  - 회차 1800초 초과

서버 전송

- `STA_SSID` · `STA_PASS` · `SERVER_URL` 을 채우면 1초마다 `POST /api/ingest` 로 보낸다
- 보내는 값은 `distA_mm = 600 - 수위` 이고 600 은 `INSTALL_HEIGHT_MM` 이다
- 이 값은 `backend/config.yaml` 의 `sensors.A.install_height_mm` 와 같아야 한다
- 센서 이상이면 `distA_mm` 를 `null` 로 하고 `A` 를 `fault` 로 보낸다
- 급수통 플로트 상태도 `floatSwitch` 로 함께 보낸다 (물이 모자라면 `low` 이고 아니면 `normal`)
- 와이파이가 끊기면 10초마다 다시 붙고 그동안 측정 · 펌프 제어 · 알림 판단은 계속 돈다
- 연결과 읽기 제한이 각 400 ms 라 서버가 꺼져 있어도 펌프 제어 루프가 오래 막히지 않는다
- 휴대폰 푸시(ntfy)는 대기열과 별도 태스크로 보낸다
- 와이파이와 전송 상태는 바뀔 때만 시리얼에 한 줄 찍는다

### 부품 시험 `firmware/parts/`

| 시험 | 폴더 | 확인하는 것 |
|---|---|---|
| 1 | `parts/led` | ESP32 단독 업로드와 500 ms tick |
| 2 | `parts/net` | 와이파이 접속과 서버 `/api/state` 읽기 |
| 3 | `parts/reed` | 플로트 스위치 닫힘과 열림 |
| 4·5 | `parts/relay` | 릴레이 단독과 릴레이에 단 펌프 |
| 6 | `parts/depth` | 수위센서 전압(mV)과 흔들림 |
| 7 | `board` | 서버 없이 관제 화면 · 보정 · 강우 회차 · 플로트 정지 |
| 8 | `board` | 서버와 함께 `/api/ingest` 전송 |

### MicroPython 판 `firmware/python/`

같은 보드에서 도는 MicroPython 판으로 수위 측정과 `/api/ingest` 전송을 맡는다

| 파일 | 내용 |
|---|---|
| `level.py` | 전압을 수위로 바꾸는 직선 · 센서 이상 범위 · 이동평균 · 보정 직선 |
| `ingest.py` | 서버 `/api/ingest` 메시지 |
| `client.py` | `socket` 만 쓰는 HTTP POST |
| `node.py` | 100 ms 표본과 1초 전송 루프 |
| `main.py` | 보드 층 (ADC · 와이파이 · 감시 타이머) |
| `host.py` | 보드 없이 같은 루프를 컴퓨터에서 돌리는 실행기 |

- 순수 모듈은 컴퓨터에서 pytest 로 돈다
- 릴레이 핀은 입력으로 두고 펌프 제어는 본 스케치가 맡는다

### 핀맵 REV16

| 부품 | ESP32 핀 |
|---|---|
| 수위센서 KIT0139 변환보드 출력 | GPIO34 |
| 릴레이 모듈 IN | GPIO26 |
| 플로트 스위치 HWD-WLC002 | GPIO27 |
| 보드 LED | GPIO2 |

## 컴파일과 업로드

처음 한 번 Arduino IDE `2.x` 에 ESP32 보드를 들인다

- 환경설정의 추가 보드 관리자 URL 에 `https://espressif.github.io/arduino-esp32/package_esp32_index.json` 을 넣는다
- 보드 매니저에서 "esp32 by Espressif Systems" 를 설치한다

접속 정보 파일을 견본에서 복사한다

```bash
cp firmware/board/secrets.h.example firmware/board/secrets.h
```

그 뒤 스케치를 올린다

- `firmware/board/board.ino` 를 폴더째로 연다
- 도구 메뉴에서 보드 "ESP32 Dev Module" 과 포트를 고른다
- 업로드 속도는 921600 이고 안 되면 115200 으로 둔다
- 업로드 단추를 누르고 시리얼 모니터를 115200 으로 연다
- `board.ino` · `page.h` · `secrets.h` 는 같은 폴더에 둔다
- 부품 시험은 `firmware/parts/<이름>/<이름>.ino` 를 같은 방법으로 올린다
- 업로드가 `Connecting.....` 에서 멈추면 BOOT 단추를 누른 채로 기다린다
- 접속 정보는 `secrets.h` 와 `secret.py` 에만 두고 저장소에는 견본만 올린다

MicroPython 판은 펌웨어를 쓴 뒤 코드를 올린다

```bash
python -m esptool --chip esp32 --port <포트> erase_flash
python -m esptool --chip esp32 --port <포트> --baud 460800 write_flash -z 0x1000 <.bin 경로>
```

```bash
cd firmware/python
cp secret.py.example secret.py
```

```bash
mpremote connect <포트> cp level.py ingest.py client.py node.py main.py secret.py :
mpremote connect <포트> reset
mpremote connect <포트> repl
```

MicroPython 판의 공용 모듈은 컴퓨터에서 시험한다

```bash
cd firmware/python
python -m pytest -q
ruff check .
```

## 따라하기 안내

- 조립한 보드의 첫 실행은 `firmware/README.md` 의 "조립서대로 연결한 뒤" 절에 있다
- Windows 와 macOS 의 단계별 명령은 `firmware/README.md` 의 "보드 시험 따라하기 (Windows·macOS)" 절에 있다
- 배선과 통과 기준은 같은 파일의 "핀맵(REV16)" 절과 "순서" 절에 있다
- 서버와 함께 하는 시험 8 은 서버가 함께 있는 `dev` 에서 한다
