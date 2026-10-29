# firmware

ESP32 DevKitC V4 펌웨어다. `board/` 가 설계서 REV16 의 본 펌웨어(수위 측정, 강우 흉내, 침수 예측 알림, 서버 전송)다. `parts/` 는 부품 한 개씩 켜 보는 시험 스케치, `node/` 는 REV15 구성(초음파·로드셀·버튼)을 모두 붙인 통합 시험이다. `python/` 은 같은 보드의 MicroPython 판으로, 아직 1단계(수위 측정과 서버 전송)만 있다.

어느 스케치도 아직 ESP32 로 컴파일하거나 보드에서 돌려 보지 않았다. `board/` 는 맥에서 Arduino API 대역을 붙여 로직만 돌려 보았다(아래 "확인한 것"). 컴파일 오류가 나면 오류 줄을 그대로 적어 두고 고친다.

## 준비

- Arduino IDE 2.x 를 설치한다. 환경설정 > 추가 보드 관리자 URL 에 `https://espressif.github.io/arduino-esp32/package_esp32_index.json` 을 넣고, 보드 매니저에서 "esp32 by Espressif Systems" 를 설치한다.
- 보드는 "ESP32 Dev Module", 업로드 속도 921600(안 되면 115200), 시리얼 모니터 115200.
- 포트: 터미널에서 `ls /dev/cu.*`. 보드를 꽂았을 때 `cu.usbserial-…` 또는 `cu.SLAB_USBtoUART` 가 새로 보이면 된다. 안 보이면 데이터용 마이크로 USB 케이블인지 확인하고, 보드 USB 칩(CP2102 또는 CH340)에 맞는 드라이버를 설치한다.
- 업로드 중 "Connecting....." 에서 멈추면 보드의 BOOT 버튼을 누른 채로 기다린다.
- 스케치 폴더 이름과 `.ino` 이름이 같아야 한다. 폴더째로 연다. `board/` 는 `board.ino`·`page.h`·`secrets.h` 가 같은 폴더에 있어야 한다.
- 접속 정보는 코드에 넣지 않는다. `board/` 는 `secrets.h`(저장소에 올리지 않음)에서 읽고, `parts/net` 은 시리얼 모니터에서 입력받는다. 입력한 값은 ESP32 안(NVS)에 저장될 수 있으니 보드를 남에게 넘길 때는 지운다.

견적에 없는 것: 마이크로 USB 데이터 케이블, 멀티미터, 자(mm 눈금).

## 핀맵(REV16)

| 부품 | ESP32 핀 | 전원 | 비고 |
|---|---|---|---|
| KIT0139 수위센서 변환보드 출력 | GPIO34 | 변환보드 VCC 3V3, 센서 12 V | 입력 전용 ADC1 핀. 출력이 3.3 V 를 넘지 않는지 멀티미터로 먼저 확인. 0 mm 에서 약 480 mV, 1 mV 가 약 2.6 mm |
| 릴레이 모듈 IN | GPIO26 | VCC 5V, GND | 12 V 는 COM·NO 접점에만. 기본은 IN=LOW 에서 켜지는 모듈(`RELAY_ACTIVE_LOW`) |
| 플로트 스위치 HWD-WLC002 | GPIO27 | - | 다른 쪽은 GND. 내부 풀업. 기본은 물이 모자랄 때 접점이 닫힘(`FLOAT_LOW_WHEN_CLOSED`) |
| 보드 LED | GPIO2 | - | `parts/led` 만 쓴다 |

REV15 부품(푸시 버튼 GPIO25, JSN-SR04T GPIO5·18, HX711 GPIO32·33)은 REV16 구성에 없다. `parts/button`·`parts/sonar`·`parts/scale`·`node` 는 참고용으로 남겨 둔다.

공통 규칙: 5 V 와 3V3 은 DevKitC 핀에서 끌어 쓰고 GND 는 모두 한 줄에 모은다. 12 V 어댑터 선은 릴레이 접점·펌프·수위센서에만 간다. ESP32 핀에 5 V 이상이 닿는 배선은 하지 않는다.

## board 스케치

100 ms 마다 수위를 읽고 펌프를 제어하며, 1초마다 최근 20초의 상승 속도로 A·B·C 구역의 침수 시각을 예측해 주의·경계·침수 알림을 낸다. 서버는 있어도 없어도 된다.

접속 정보는 `board/secrets.h.example` 을 `board/secrets.h` 로 복사해 채운다. 비워 둔 항목은 그 기능이 꺼진다.

| 항목 | 뜻 | 비우면 |
|---|---|---|
| `AP_PASS` | 보드가 여는 와이파이 `SMART_FLOOD` 의 암호. 8자 이상 | 관제 화면과 펌프 제어를 열지 않는다(암호 없는 AP 로 펌프를 제어하지 않기 위해) |
| `STA_SSID`·`STA_PASS` | 서버가 있는 와이파이 | 와이파이에 붙지 않는다 |
| `SERVER_URL` | `http://<노트북 IP>:8000`. 끝에 `/` 없이 | 서버로 보내지 않는다 |
| `NTFY_TOPIC` | 휴대폰 푸시용 ntfy 주제 | 푸시를 보내지 않는다 |

관제 화면은 휴대폰을 `SMART_FLOOD` 에 붙이고 시리얼에 찍힌 주소(보통 `http://192.168.4.1`)를 열면 나온다. 화면이 쓰는 경로는 다음과 같다.

| 경로 | 뜻 |
|---|---|
| `/api/cmd?c=start` | 강우 회차 시작(기록과 단계를 비움). `stop` 정지, `rain` 강우 재개, `manual` 수동 펌프, `flowtest` 30초 유량 측정 |
| `/api/cmd?c=flowset&v=<mL>` | 30초 동안 받은 물 양(mL)으로 유량 저장. `areaapply` 는 추정 수면 면적 적용 |
| `/api/cmd?c=cal1&v=<mm>`, `cal2&v=<mm>` | 자로 잰 수위 두 점으로 보정. `calreset` 은 이론값으로 되돌림 |
| `/api/set?z0=&z1=&z2=&maxLevel=&cautionEta=&warningEta=&rainOnS=&rainOffS=` | 설정 저장(플래시에 남음) |
| `/api/status`, `/api/hist`, `/log.csv` | 상태 JSON, 최근 수위, 회차 기록 |

기본 설정: 구역 침수 기준 A 40·B 70·C 110 mm(어항 바닥 0), 안전 최대 수위 100 mm(C 는 설계상 침수하지 않음), 주의 60초·경계 30초, 강우 흉내 ON 2초·OFF 8초, 연속 가동 최대 60초, 회차 최대 1800초.

펌프가 멈추는 조건: 플로트가 "물 모자람"이면 100 ms 안에, 수위센서 이상이면 강우 모드에서, 안전 최대 수위에 닿으면, 연속 가동이 60초를 넘으면, 회차가 1800초를 넘으면. 수동·유량 측정 모드는 센서 이상을 보지 않고 가동 제한으로만 멈춘다.

서버에는 1초마다 `POST /api/ingest` 로 `distA_mm = 600 - 수위` 를 보낸다. 600 은 `INSTALL_HEIGHT_MM` 이고 `backend/config.yaml` 의 `sensors.A.install_height_mm` 와 같아야 한다. B 구역과 무게는 `null`·`absent`, 센서 이상이면 `distA_mm` 가 `null` 이고 `A` 가 `fault` 다. 서버가 꺼져 있어도 연결·읽기 제한이 각 400 ms 라 펌프 제어 루프가 오래 막히지 않는다. ntfy 는 TLS 인증서를 확인하지 않고(`setInsecure`) 보낸다.

알려진 특성: 강우 흉내가 ON·OFF 펄스라 20초 회귀 기울기가 출렁이고, 그래서 ETA 가 흔들리며 첫 알림이 명목 60초보다 이르게 올 수 있다. 수위가 최대 수위 근처일 때 C 구역에도 "주의"가 잠깐 뜰 수 있다(C 는 침수하지 않는다). 설계서 10장의 화면 스크립트에서 PDF 에 잘린 줄과 `cfg.z2` 오류는 `page.h` 머리에 적은 대로 고쳤다.

### 확인한 것

맥에서 WiFi·HTTPClient·WebServer·Preferences·ADC 의 대역을 만들어 `board.ino` 를 C++ 로 컴파일하고, `setup()`·`loop()` 를 가짜 시계(100 ms)와 가짜 수위로 돌렸다. 통과한 것: 부팅 직후 릴레이 꺼짐(고임피던스), `secrets.h` 가 없으면 와이파이·관제 화면·전송 없음, 1초마다 전송과 `seq` 증가, 전송 본문 1101건이 서버의 `Message` 스키마와 live 모드 `/api/ingest` 를 통과, 강우 회차에서 A·B 순서 침수와 경보 선행 약 100초, 최대 수위 정지, 플로트 100 ms 정지, 센서 이상 정지와 `null` 전송, 수동 60초 정지, 설정 저장·재로드, 두 점 보정. 대역은 직접 만든 것이라 ESP32 코어 API 의 이름과 시그니처는 확인되지 않았다. 보드에서 처음 컴파일할 때 오류가 날 수 있다.

## python 노드(MicroPython)

`python/` 은 같은 ESP32 에서 돌아가는 MicroPython 판이다. 1단계 범위는 수위 읽기와 1초마다 `POST /api/ingest` 전송까지다. 펌프 제어·20초 기울기 예측·주의/경계 단계·관제 화면·ntfy 는 아직 `board/` 스케치에만 있다. 릴레이 핀(GPIO26)은 입력으로 두어 펌프가 켜지지 않는다.

파일은 두 층이다. 순수 모듈은 맥에서 pytest 로 돌고, 보드 층만 ESP32 API 를 쓴다. 공용 모듈은 MicroPython 에서도 돌아야 하므로 f-string·typing·dataclass 를 쓰지 않는다.

| 파일 | 뜻 | 어디서 도는가 |
|---|---|---|
| `level.py` | 전압(mV)→수위(mm) 직선, 센서 이상 범위(300~2800 mV), 100 ms 이동평균, `cal1`·`cal2`·`calreset` 과 같은 보정 | 맥·보드 |
| `ingest.py` | 서버 `/api/ingest` 메시지. `distA_mm = 600 - 수위`, 이상이면 `null`·`fault` | 맥·보드 |
| `client.py` | `socket` 만 쓰는 HTTP POST. 연결·응답 각 400 ms 제한, http 만 | 맥·보드 |
| `node.py` | 100 ms 표본·1 s 전송 루프. 시각·ADC·전송은 보드 객체가 준다 | 맥·보드 |
| `main.py` | ESP32 보드 층. ADC(GPIO34) 64회 평균, 와이파이 접속, 감시 타이머 8초, 부팅 시 자동 실행 | 보드 |
| `host.py` | 맥 실행기. 가짜 수위나 표준입력의 mV 로 같은 루프를 돌려 서버에 보낸다 | 맥 |
| `secret.py.example` | 접속 정보 견본. `secret.py` 로 복사해 채운다. `secret.py` 는 저장소에 올리지 않는다 | - |

부품 시험 1~6 은 그대로 `parts/` 스케치로 한다. 8(서버 연동)은 `python/` 으로도 할 수 있고, 7(펌프 제어)은 아직 `board/` 만 된다.

### 맥에서 시험

```bash
cd firmware/python
python3 -m pytest -q && ruff check .
```

보드 없이 서버 경로를 미리 확인하려면 서버를 띄우고 live 로 바꾼 뒤("서버에 닿게 하기") 실행기를 돌린다. `--mm` 은 가짜 수위(mm), `--ramp` 는 초당 변화(mm/s), `--seconds` 는 보낼 횟수다. `--server` 를 비우면 서버 없이 메시지를 한 줄씩 찍는다.

```bash
python3 host.py --server http://localhost:8000 --mm 40 --ramp 0.5 --seconds 30
python3 host.py --mm 40 --seconds 3
```

시리얼 등에서 mV 값이 한 줄씩 들어오면 `--stdin` 으로 그 값을 센서 값으로 쓴다(첫 토큰이 숫자인 줄만 읽는다).

### 보드에 올리기

도구와 MicroPython 펌웨어는 사람이 설치한다. 아래는 보드를 꽂은 뒤 한 번만 한다. `.bin` 은 micropython.org 의 ESP32_GENERIC 다운로드 페이지에서 받고, 파일명은 받은 판으로 바꾼다. esptool 새 판은 명령 이름이 `esptool` 이다.

```bash
python3 -m pip install esptool mpremote
ls /dev/cu.*                                   # cu.usbserial-… 또는 cu.SLAB_USBtoUART
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX erase_flash
esptool.py --chip esp32 --port /dev/cu.usbserial-XXXX --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-<판>.bin
```

그다음 코드를 올린다. `main.py` 는 부팅마다 자동으로 돈다.

```bash
cd firmware/python
cp secret.py.example secret.py                 # STA_SSID·STA_PASS·SERVER_URL 채움
mpremote connect /dev/cu.usbserial-XXXX cp level.py ingest.py client.py node.py main.py secret.py :
mpremote connect /dev/cu.usbserial-XXXX reset
mpremote connect /dev/cu.usbserial-XXXX repl    # 전송 실패가 있으면 여기 찍힌다. Ctrl-] 로 나감
```

`secret.py` 가 없거나 `SERVER_URL`·`STA_SSID` 가 비면 와이파이에 붙지 않고 메시지를 REPL 에만 찍는다. 보드를 남에게 넘길 때는 `mpremote rm :secret.py` 로 지운다.

### 확인한 것

맥에서 pytest 36건(변환·보정·메시지·HTTP 클라이언트·루프 타이밍·실행기)과 ruff 가 통과했다. `main.py` 는 `machine`·`network`·`time.ticks_*` 대역을 붙여 CPython 에서 3회 전송까지 돌렸다: 릴레이 핀이 입력으로 설정되고 핀 출력이 없으며, `seq` 0·1·2 가 `/api/ingest` 로 가고, 감시 타이머가 표본마다 먹여진다. `host.py` 로 로컬 서버(live)에 4초 보내 `/api/state` 의 `devices.esp32_1` 이 online, A 구역 `levelMm` 40.0·`source` measured 가 되는 것을 확인했다. MicroPython 실제 API(`ADC.read_uv`, `WDT`, `network.WLAN`)는 보드에서 아직 돌려 보지 않았다.

## 순서

앞 단계가 통과해야 다음으로 간다. 한 번에 하나만 꽂는다.

| 순서 | 부품 | 스케치 | 배선 | 통과 기준 |
|---|---|---|---|---|
| 1 | ESP32 단독 | `parts/led` | USB 만 | 업로드 성공. 시리얼에 칩 이름과 0.5초마다 tick 이 찍힌다. LED 가 깜빡인다 |
| 2 | ESP32 WiFi | `parts/net` | USB 만 | 시리얼 모니터에 SSID·암호·서버 URL 을 한 줄씩 입력(줄 끝 "New Line"). IP 가 찍히고 `GET … -> 200` 과 `/api/state` 앞부분이 보인다 |
| 3 | 플로트 스위치 | `parts/reed` | GPIO27-스위치-GND | 플로트를 위아래로 돌리면 닫힘·열림이 바뀐다. 어느 방향이 "물 모자람"인지 적는다 |
| 4 | 릴레이(무부하) | `parts/relay` | IN GPIO26, VCC 5V, GND | 3초마다 딸깍 소리와 LED. IN 이 LOW 일 때 켜지면 active-LOW 모듈이다. 어느 쪽인지 적는다 |
| 5 | 릴레이 + 펌프 | `parts/relay` | 어댑터 + 를 COM, NO 를 펌프 +, 펌프 - 를 어댑터 - | 펌프를 물에 넣은 뒤에만 어댑터를 꽂는다(수중펌프는 공회전 금지). 3초 켜짐·꺼짐이 반복된다. 1분간 받은 물 양으로 L/min 을 적는다 |
| 6 | KIT0139 | `parts/depth` | 변환보드 출력을 GPIO34 에 | 물이 없을 때 mV 와 1분 동안의 흔들림(mV)을 적는다. 1 mV 가 약 2.6 mm 라 ±3 mV 면 수위 ±8 mm 다. 깊이 두 점에서 mV 를 적는다 |
| 7 | board(서버 없이) | `board` | 전부. `secrets.h` 에 `AP_PASS` 만 | 관제 화면에 수위가 보인다. `cal1`·`cal2` 보정 뒤 자 눈금과 ±5 mm 안에 든다. `start` 로 강우 회차를 돌리면 물이 A 기준(40 mm)에 닿기 전에 주의·경계가 뜨고, 플로트를 들면 바로 멈춘다 |
| 8 | board + 서버 | `board` | 전부. `STA_SSID`·`STA_PASS`·`SERVER_URL` 채움 | 서버를 live 로 바꾸고 회차를 시작하면 `/api/state` 의 `devices.esp32_1` 이 online 이고 A 수위가 보드 값과 같다 |

시험 3·4 의 결과가 기본값과 다르면 `board.ino` 위쪽의 `FLOAT_LOW_WHEN_CLOSED`·`RELAY_ACTIVE_LOW` 를 바꾼 뒤 올린다.

## 서버에 닿게 하기

ESP32 가 노트북의 서버에 붙으려면 서버를 모든 주소에서 듣게 띄운다. 노트북 IP 는 `ipconfig getifaddr en0` 으로 본다.

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

서버는 기본이 시뮬레이션이다. 보드 값을 쓰려면 멈춘 상태에서 live 로 바꾸고 회차를 시작한다.

```bash
curl -X POST http://localhost:8000/api/source -H 'Content-Type: application/json' -d '{"mode":"live"}'
curl -X POST http://localhost:8000/api/experiment/start -H 'Content-Type: application/json' -d '{}'
```

macOS 방화벽이 켜져 있으면 python 의 수신 연결을 허용한다. ESP32 와 노트북이 같은 WiFi 에 있어야 한다.

## 적어 둘 값

| 값 | 어디서 | 들어갈 곳 |
|---|---|---|
| 센서 설치 높이(바닥에서 센서 기준면까지, mm) | 모형에 단 뒤 | `board.ino` 의 `INSTALL_HEIGHT_MM`, `backend/config.yaml` 의 `sensors.A.install_height_mm`·`max_range_mm` |
| 0 mm 에서의 mV 와 1분 흔들림(mV) | 시험 6 | `cal1`·`cal2` 보정, 잡음이 커서 평균 시간을 늘릴지 판단 |
| 펌프 유량(L/min 또는 30초 mL) | 시험 5, `flowtest` | `flowset`, 강우 세기 환산 |
| 릴레이 켜지는 레벨, 플로트 "물 모자람" 방향 | 시험 3·4 | `RELAY_ACTIVE_LOW`, `FLOAT_LOW_WHEN_CLOSED` |
| 수면 면적(cm²) | 자로 재서 | 설정 `areaCm2`(기본 1700) 또는 `areaapply` |
| 구역 기준 높이(mm) | 모형에서 자로 | `/api/set` 의 `z0`·`z1`·`z2`, `backend/config.yaml` 의 임계값 |
