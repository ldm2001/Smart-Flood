# firmware

ESP32 DevKitC V4 펌웨어다. `board/` 가 설계서 REV16 의 본 펌웨어(수위 측정, 강우 흉내, 침수 예측 알림, 서버 전송)다. `parts/` 는 부품 한 개씩 켜 보는 시험 스케치다. `python/` 은 같은 보드의 MicroPython 판으로, 아직 1단계(수위 측정과 서버 전송)만 있다.

어느 스케치도 아직 ESP32 로 컴파일하거나 보드에서 돌려 보지 않았다. `board/` 는 맥에서 Arduino API 대역을 붙여 로직만 돌려 보았다(아래 "확인한 것"). 컴파일 오류가 나면 오류 줄을 그대로 적어 두고 고친다.

## 조립서대로 연결한 뒤

`SMART-FLOOD 조립서` 의 선 1~19 대로 꽂은 보드에 처음 올리는 순서다. 조립서의 `SMART_FLOOD_ESP32_v2.ino` 자리에 `firmware/board/board.ino` 를 쓴다. 핀(GPIO34 수위, GPIO26 릴레이, GPIO27 플로트)과 `RELAY_ACTIVE_LOW = true`, `FLOAT_LOW_WHEN_CLOSED = true` 는 조립서와 같다.

1. 접속 정보 파일을 견본에서 복사한다. 견본의 `AP_PASS` 는 조립서의 `flood1234` 이고, 8자 이상이면 바꿔도 된다. `secrets.h` 가 없으면 보드가 `SMART_FLOOD` 와이파이를 열지 않는다.

   ```bash
   cp firmware/board/secrets.h.example firmware/board/secrets.h
   ```

   개발 서버로도 보낼 때만 `STA_SSID`·`STA_PASS` 에 노트북이 붙은 2.4 GHz 와이파이를, `SERVER_URL` 에 `http://<노트북 IP>:8000` 을 적는다("서버에 닿게 하기"). 비워 두면 관제 화면만 쓴다.
2. Arduino IDE 로 `firmware/board/board.ino` 를 열고 보드 "ESP32 Dev Module" 과 포트를 고른 뒤 올린다. 설치와 포트 찾기는 9단계에 있다.
3. 전원은 12 V 어댑터를 먼저 꽂고 10초쯤 연기·탄내·뜨거운 곳이 없는지 본 뒤 ESP32 USB 를 꽂는다. 시리얼 모니터(115200)에 `관제 화면: http://192.168.4.1` 이 찍힌다.
4. 휴대폰을 와이파이 `SMART_FLOOD`(암호 `AP_PASS`)에 붙이고 `http://192.168.4.1` 을 연다. 화면에 센서 전압(mV), 수위, "펌프 수동 ON"·"정지" 단추, 급수통 상태가 보인다.
5. 프로브가 공기 중이면 센서 전압이 약 480 mV(400~560)이고, 물 10 cm 에 담그면 약 38 mV 오른다(1 mV 가 약 2.6 mm). 300 mV 아래나 2800 mV 위면 "수위센서 이상" 이 뜬다. 센서를 꽂기 전(조립서 4단계)에는 이것이 정상이다.
   공기 중 전압이 480 mV 와 다르면 펌프 시험 전에 `cal1` 을 0 mm 로 눌러 영점을 잡는다. 보정 전 수위는 2.604×mV − 1240 mm 라 약 514.6 mV 부터 100 mm 이상으로 읽히고, 수동 ON 이 "안전 최대 수위 도달"로 바로 멈춘다(`maxLevel` 100). 센서를 꽂기 전(조립서 5단계 릴레이·펌프 시험)에도 떠 있는 GPIO34 가 높게 읽히면 같은 정지가 난다. 수동 ON 은 60초 이어서 돈 뒤 스스로 멈춘다(`pumpMaxOnS` 60).
6. 펌프를 물이 있는 급수통 바닥에 넣고 "펌프 수동 ON" 으로 물이 나오는지 본 뒤 "정지" 를 누른다. 수동 ON 도 60초가 지나면 저절로 멈춘다. 플로트를 내리면 "급수통: 물 부족" 이 뜨고 펌프가 멈춘다.

| 화면·시리얼에 보이는 것 | 먼저 볼 곳(조립서 선 번호) |
|---|---|
| 와이파이 목록에 `SMART_FLOOD` 가 없고, 시리얼 모니터를 연 채 EN 단추를 누르면 `AP_PASS 가 없거나…` 가 찍힌다 | 1번대로 `secrets.h` 를 만들고 다시 올린다 |
| 센서 전압 0 근처, "수위센서 이상" | 선 14·15·16(센서 고리), 선 9(12 V), 어댑터가 꽂혔는지 |
| 센서 전압 3000 근처, "수위센서 이상" | 선 6·8 이 바뀌었는지, 합선 |
| 센서 전압이 마구 흔들린다 | 선 17(두 보드 GND) |
| 수동 ON 에 딸깍은 하는데 펌프가 안 돈다 | 선 11·12·13, COM/NO 위치, 펌프 플러그 |
| 수동 ON 에 릴레이가 아무 반응이 없다 | 화면의 "정지 사유" 를 먼저 본다. 없으면 선 3·4·5, USB 전원 |
| 센서를 꽂기 전 수동 ON 이 "안전 최대 수위 도달" 로 바로 멈춘다 | GPIO34 가 떠 있어 아무 값이나 읽혔다. 변환보드(선 6~9)를 꽂은 뒤 다시 본다 |
| 정지에서 켜지고 ON 에서 꺼진다 | `board.ino` 의 `RELAY_ACTIVE_LOW` 를 `false` 로 바꿔 다시 올린다 |
| 플로트를 내려도 "물 부족" 이 안 뜨고, 올리면 뜬다 | `board.ino` 의 `FLOAT_LOW_WHEN_CLOSED` 를 `false` 로 바꿔 다시 올린다 |
| 시리얼에 부팅 글이 되풀이된다(재부팅) | 바로 전원을 뺀다. 12 V 가 보드 1 에 닿았는지, USB 케이블·충전기 |

## 보드 시험 따라하기 (Windows·macOS)

노트북 한 대와 ESP32 한 대로 부품 시험부터 서버 연동까지 가는 순서다. Windows 는 PowerShell(시작 메뉴에서 "PowerShell"), macOS 는 터미널에서 친다. 두 OS 에서 똑같은 명령은 한 번만 적었다(PowerShell 도 경로의 `/` 와 `cp` 를 받는다). 창은 넷까지 쓴다. 창 1 은 서버, 창 2 는 제어(`state`·`post`), 창 3 은 `host.py`·`mpremote`, 창 4 는 관제 웹(선택)이다. 통과 기준은 아래 "순서" 표, 잰 값을 적을 곳은 "적어 둘 값" 표다.

확인한 범위: 2026-11-02 에 macOS(Python 3.11.9, zsh·bash)에서 가상 환경 만들기, `state`·`post` 함수, live 전환, 회차 시작, `host.py` 로 가짜 수위 40 mm 보내기를 이 순서대로 돌려 보았고, 보내는 동안 `live running online A=40.0 measured valid` 를 받았다. 그때 서버는 4단계 명령 대신, 같은 앱을 `127.0.0.1` 에서만 듣고 기록을 임시 폴더에 쓰게 띄웠다. `pip install`, `--host 0.0.0.0` 과 방화벽, 다른 기기에서 붙기, `npm` 단계는 이 꼴로 돌려 보지 않았다. Windows 명령은 Windows 에서 한 번도 돌려 보지 않았다. 보드에서 돌린 것은 아직 없다.

### 1. 준비물

| 항목 | Windows | macOS |
|---|---|---|
| Git | git-scm.com 의 설치 파일 | 터미널에서 `git --version`. 없으면 개발자 도구 설치 창이 뜬다 |
| Python 3.11 | python.org 의 3.11 설치 파일. 함께 깔리는 `py` 로 `py -3.11 --version` 이 3.11 을 보이면 된다 | python.org 의 3.11 설치 파일 또는 `brew install python@3.11`. `python3.11 --version` 으로 확인한다 |
| Arduino IDE 2.x | arduino.cc 의 Windows 판 | arduino.cc 의 macOS 판 |
| USB 드라이버 | 포트가 안 보일 때만(9단계). 보드의 USB 칩 글자가 CP2102 면 Silicon Labs 의 CP210x 드라이버, CH340 이면 WCH 의 CH340 드라이버 | 같다 |
| Node 24 | 관제 웹을 볼 때만(13단계). nodejs.org 의 24 판 | 관제 웹을 볼 때만. `brew install node@24` |
| MicroPython `.bin` | MicroPython 판을 쓸 때만(12단계). micropython.org 의 ESP32_GENERIC | 같다 |

부품은 "핀맵" 표의 것에 마이크로 USB 데이터 케이블, 멀티미터, 자(mm 눈금)를 더한다. Python 은 3.11.9 에서만 시험했다.

### 2. 코드 받기

창을 열자마자 받으면 홈 폴더에 `Smart-Flood` 가 생긴다. 서버와 펌웨어가 함께 있는 통합 브랜치 `dev` 로 바꾼다.

```bash
git clone https://github.com/ldm2001/Smart-Flood.git
cd Smart-Flood
git switch dev
```

이미 받아 두었으면 `Smart-Flood` 에서 `git switch dev` 와 `git pull --ff-only` 만 한다. Windows 는 OneDrive 가 동기화하는 바탕 화면·문서 폴더를 피한다. 아래 명령은 따로 적지 않으면 모두 `Smart-Flood` 폴더에서 친다. 새 창에서는 `cd ~/Smart-Flood` 로 들어간다(두 OS 같다).

### 3. 가상 환경 (처음 한 번)

서버와 펌웨어 도구를 저장소 맨 위의 `.venv` 하나에 깐다. `.venv` 는 저장소에 올라가지 않는다.

Windows(PowerShell):

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt esptool mpremote
```

macOS(터미널):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt esptool mpremote
```

`Set-ExecutionPolicy -Scope Process` 는 그 창에서만 스크립트를 허용하고, 창을 닫으면 사라진다. 실행 규칙을 바꿀지 물으면 `Y` 를 친다. 새 창을 열 때마다 `Smart-Flood` 에서 활성화를 다시 한다. Windows 는 `Set-ExecutionPolicy` 와 `Activate.ps1` 두 줄, macOS 는 `source` 한 줄이다. 프롬프트 앞에 `(.venv)` 가 붙으면 된다. 그 뒤로는 두 OS 모두 `python` 으로 친다. macOS 는 가상 환경 밖에 `python` 이 없다.

### 4. 서버 띄우기 (창 1)

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`Uvicorn running on http://0.0.0.0:8000` 이 보이면 된다. 이 창은 시험 내내 열어 둔다. `--host 0.0.0.0` 은 같은 와이파이의 보드가 붙을 수 있게 모든 주소에서 듣게 한다. 코드를 고치지 않으니 `--reload` 는 붙이지 않는다. 서버를 다시 띄우면 입력원이 sim 으로 돌아가므로 7단계부터 다시 한다. 회차 기록은 `backend/logs/` 에 쌓인다. 끌 때는 이 창에서 Ctrl+C 를 누른다. Windows 는 처음 띄울 때 방화벽 창이 뜬다(5단계).

### 5. 노트북 IP 와 방화벽

창 2 를 새로 열고 저장소로 들어가 활성화한다. 보드는 노트북 IP 로 서버에 붙는다.

- Windows: `ipconfig` 를 치고 "무선 LAN 어댑터 Wi-Fi" 아래의 "IPv4 주소"(예 `192.168.0.10`)를 적는다. 영문 Windows 는 "Wireless LAN adapter Wi-Fi" 의 "IPv4 Address" 다.
- macOS: `ipconfig getifaddr en0` 을 친다. 빈 줄이면 `ipconfig getifaddr en1` 을 치거나 시스템 설정 > Wi-Fi 에서 연결된 망의 "세부사항" 을 본다.

방화벽은 OS 마다 다르다.

- Windows: 4단계에서 서버를 처음 띄울 때 "Windows 보안 경고" 창이 뜨면 "개인 네트워크" 에 표시하고 "액세스 허용" 을 누른다. 그 창을 취소했거나 닫았으면 python 차단 규칙이 남는다. 그때는 제어판 > Windows Defender 방화벽 > "Windows Defender 방화벽을 통해 앱 또는 기능 허용" > "설정 변경" 에서 `python` 줄의 "개인" 에 표시한다. 지금 와이파이가 "공용" 이면 개인 허용이 듣지 않는다. 설정 > 네트워크 및 인터넷 > Wi-Fi 에서 연결된 망을 열고 네트워크 프로필 유형을 "개인" 으로 바꾼다. 관리자 PowerShell 에서 8000 포트만 여는 규칙을 더해도 된다. 다만 python 차단 규칙이 남아 있으면 차단이 이기므로 그것을 먼저 푼다.

  ```powershell
  New-NetFirewallRule -DisplayName "SMART FLOOD 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
  ```

- macOS: 시스템 설정 > 네트워크 > 방화벽이 켜져 있으면, 서버를 처음 띄울 때 들어오는 연결을 허용할지 묻는 창에서 "허용" 을 누른다. 놓쳤으면 방화벽 > 옵션에서 Python 을 "들어오는 연결 허용" 으로 둔다.

### 6. 바깥에서 닿는지 보기

창 2 에서 노트북 IP 로 상태를 읽는다.

Windows(PowerShell):

```powershell
curl.exe -s http://<노트북 IP>:8000/api/state
```

macOS(터미널):

```bash
curl -s http://<노트북 IP>:8000/api/state
```

`<노트북 IP>` 는 5단계에서 적은 값으로 바꾼다(예 `http://192.168.0.10:8000/api/state`). JSON 이 나오면 서버가 바깥 주소에서도 듣고 있다. Windows PowerShell 의 `curl` 은 다른 명령(`Invoke-WebRequest`)이라 `curl.exe` 로 친다. 노트북 안에서 친 요청은 방화벽을 거치지 않을 수 있다. 방화벽까지 보려면 같은 와이파이에 붙은 휴대폰 브라우저로 `http://<노트북 IP>:8000/api/state` 를 연다. 휴대폰에서 JSON 이 보이면 보드도 붙을 수 있다. 안 열리면 방화벽이거나, 와이파이가 기기끼리의 연결을 막는 것이다("서버에 닿게 하기").

### 7. live 로 바꾸기 (창 2)

서버 상태를 한 줄로 보는 `state` 와 제어 요청을 보내는 `post` 를 창마다 한 번 붙여 넣는다.

Windows(PowerShell):

```powershell
function state { $s = Invoke-RestMethod http://127.0.0.1:8000/api/state; "$($s.dataSource) $($s.runState) $($s.devices.esp32_1) A=$($s.zones.A.levelMm) $($s.zones.A.source) $($s.quality)" }
function post($path, $body) { $s = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000$path" -ContentType 'application/json' -Body $body; "$($s.dataSource) $($s.runState) $($s.experimentId)" }
```

macOS(터미널):

```bash
state() { curl -s http://127.0.0.1:8000/api/state | python3 -c "import json,sys; s=json.load(sys.stdin); print(s['dataSource'], s['runState'], s['devices']['esp32_1'], 'A=%s' % s['zones']['A']['levelMm'], s['zones']['A']['source'], s['quality'])"; }
post() { curl -s -X POST "http://127.0.0.1:8000$1" -H 'Content-Type: application/json' -d "$2" | python3 -c "import json,sys; s=json.load(sys.stdin); print(s.get('detail') or '%s %s %s' % (s['dataSource'], s['runState'], s['experimentId']))"; }
```

그다음 입력원을 live 로 바꾸고 상태를 본다. 여기서부터는 두 OS 가 같다.

```bash
post /api/source '{"mode":"live"}'
state
```

`post` 는 `live idle EXP-STANDBY` 를, `state` 는 `live idle offline A=0.0 estimated invalid` 를 찍는다. `state` 는 앞에서부터 입력원, 회차 상태, ESP32 #1 연결, A 구역 수위(mm), A 수위의 출처, 입력 품질이다. 아직 아무 장치도 보내지 않았으니 `offline` 이다. PowerShell 판에 따라 `A=0` 처럼 숫자 꼴이 조금 다를 수 있다. 브라우저로 `http://localhost:8000/api/state` 를 열어 같은 필드(`dataSource`, `runState`, `devices.esp32_1`, `zones.A`, `quality`)를 봐도 된다.

`post` 가 409 와 "회차가 도는 중에는 입력원을 바꿀 수 없다" 를 내면 `post /api/experiment/stop '{}'` 로 멈춘 뒤 다시 한다. PowerShell 은 이것을 빨간 오류 글로 보여 주고, Windows PowerShell 5.1 에서는 한국어 문장이 깨져 보일 수 있다. PowerShell 에서 POST 를 `curl.exe` 가 아니라 `Invoke-RestMethod` 로 보내는 것은, Windows PowerShell 5.1 이 바깥 프로그램에 넘기는 인수에서 큰따옴표를 지워 JSON 이 깨지기 때문이다. 두 함수가 `localhost` 대신 `127.0.0.1` 을 쓰는 것은 Windows 가 `localhost` 를 IPv6 로 먼저 붙어 보느라 늦어질 수 있어서다.

live 에서 회차를 시작하면 서버 모형의 강우가 켜진다(기본 보통 강우 60 mm/h). 이 값은 서버의 예측 모형에만 들어간다. 서버는 펌프나 보드를 움직이지 않는다.

### 8. 보드 없이 미리 해 보기 (창 3)

보드를 꽂기 전에, 컴퓨터가 보드 노릇을 하는 `host.py` 로 서버까지 가는 길을 확인한다. 창 2 에서 회차를 시작한다.

```bash
post /api/experiment/start '{}'
```

`live running EXP-<날짜>-<번호>` 가 나온다. 창 3 을 새로 열고 활성화한 뒤 가짜 수위 40 mm 를 20초 동안 보낸다.

```bash
cd firmware/python
python host.py --server http://localhost:8000 --mm 40 --seconds 20
```

`host.py` 는 잘 보내는 동안 아무것도 찍지 않고 실패만 찍는다. 그 20초 안에 창 2 에서 `state` 를 치면 `live running online A=40.0 measured valid` 가 나와야 한다. PowerShell 판에 따라 `A=40` 으로 보일 수 있다. 보내기 전에는 `offline` 과 `estimated` 이고, 보내기를 멈추면 5초 뒤 `offline` 이 되고 A 는 `estimated` 로 돌아간다. `--server` 를 `http://<노트북 IP>:8000` 으로 바꿔 한 번 더 돌리면 보드가 쓸 주소로도 확인된다. 끝나면 창 2 에서 멈춘다. `live stopped EXP-…` 가 나온다.

```bash
post /api/experiment/stop '{}'
```

창 3 에서는 펌웨어 공용 모듈 시험도 돌릴 수 있다. `53 passed` 와 `All checks passed!` 가 나오면 된다.

```bash
python -m pytest -q
ruff check .
```

### 9. Arduino IDE 와 포트

1. Arduino IDE 2.x 의 환경설정(영문 "Preferences". Windows 는 파일 메뉴, macOS 는 Arduino IDE 메뉴에 있다)에서 "추가 보드 관리자 URL"(영문 "Additional boards manager URLs") 에 `https://espressif.github.io/arduino-esp32/package_esp32_index.json` 을 넣는다.
2. 보드 매니저(영문 "Boards Manager", 왼쪽 막대의 보드 그림)에서 "esp32 by Espressif Systems" 를 설치한다.
3. 보드를 USB 로 꽂고 도구 > 보드 > esp32 에서 "ESP32 Dev Module", 도구 > 포트에서 보드 포트를 고른다. 업로드 속도는 921600(안 되면 115200)이다.

포트 이름은 OS 마다 다르다.

- Windows: 시작 버튼을 오른쪽 클릭해 장치 관리자를 열면 "포트(COM & LPT)" 아래에 `Silicon Labs CP210x USB to UART Bridge (COM3)` 나 `USB-SERIAL CH340 (COM5)` 처럼 보인다. 괄호 안의 `COM3` 이 포트다. "기타 장치" 에 느낌표와 함께 보이면 드라이버가 없다.
- macOS: 꽂기 전과 뒤에 `ls /dev/cu.*` 를 쳐서 새로 생긴 `cu.usbserial-…`, `cu.SLAB_USBtoUART`, `cu.wchusbserial…` 을 찾는다.

가상 환경을 켠 창에서 `mpremote devs` 를 쳐도 포트 목록이 나온다. 아무것도 새로 보이지 않으면 충전 전용 케이블일 수 있다. 데이터용 케이블로 바꾸고, 그래도 없으면 1단계의 드라이버를 깐다.

시리얼 모니터는 도구 > 시리얼 모니터이고 속도는 115200 이다. 포트 하나는 한 프로그램만 열 수 있다. `esptool`·`mpremote` 를 쓰기 전에는 시리얼 모니터를 닫는다. 열려 있으면 Windows 는 `could not open port` 나 `Access is denied`, macOS 는 `Resource busy` 같은 오류가 난다.

### 10. 부품 시험 1~6

Arduino IDE 에서 파일 > 열기로 `firmware/parts/<이름>/<이름>.ino` 를 연다. 업로드 버튼(오른쪽을 가리키는 화살표 모양. Windows 는 Ctrl+U, macOS 는 Cmd+U)을 누르고, 끝나면 시리얼 모니터를 115200 으로 연다. 두 OS 의 차이는 포트 이름뿐이다. 통과 기준은 "순서" 표 그대로다.

| 시험 | 폴더 | 시리얼에 보이는 줄 |
|---|---|---|
| 1 | `parts/led` | `chip ESP32-…, cpu … MHz, heap … B` 뒤로 0.5초마다 `… ms tick …` |
| 2 | `parts/net` | `SSID? `, `암호? `, `서버 URL? …` 에 한 줄씩 답하면 `IP …, RSSI … dBm` 과 `GET … -> 200` |
| 3 | `parts/reed` | 플로트를 돌릴 때마다 `… ms 닫힘(LOW)` 또는 `… ms 열림(HIGH)` |
| 4·5 | `parts/relay` | 3초마다 `… ms IN=LOW`(켬) 와 `… ms IN=HIGHZ`(끔, 입력 핀) 가 번갈아 |
| 6 | `parts/depth` | `… ms raw …  … mV` |

시험 2 는 4단계 서버를 먼저 띄워 둔다. 시리얼 모니터 아래의 줄 끝 설정을 "New Line" 으로 두고 물음마다 한 줄씩 보낸다. 서버 URL 은 이 시험에서만 경로까지 `http://<노트북 IP>:8000/api/state` 로 적는다. `-> 200` 이면 통과다. `-> -1` 처럼 음수면 서버에 닿지 못한 것이니 4~6단계를 다시 본다. `20초 안에 못 붙음` 이 나오면 SSID·암호와 2.4 GHz 망인지 본다. 물음을 놓쳤으면 보드의 EN 버튼을 눌러 처음부터 다시 받는다. 입력한 SSID·암호는 보드 안에 남을 수 있다(14단계에서 지운다).

시험 3·4 의 결과가 기본값과 다르면 `board.ino` 위쪽 상수를 바꾼다("순서" 표 아래). 시험 5 는 펌프를 물에 넣은 뒤에 어댑터를 꽂는다. 시험 3~6 의 값은 "적어 둘 값" 표에 적는다.

### 11. board 스케치 (시험 7·8)

접속 정보 파일을 견본에서 복사한다. `secrets.h` 는 저장소에 올라가지 않는다.

```bash
cp firmware/board/secrets.h.example firmware/board/secrets.h
```

Arduino IDE 로 `firmware/board/board.ino` 를 열면 `page.h`·`secrets.h` 가 옆 탭으로 보인다. `secrets.h` 탭에서 따옴표 안에 값을 적고 저장한다.

시험 7(서버 없이): `AP_PASS` 는 견본 값(조립서의 `flood1234`)이나 8자 이상의 다른 암호로 두고 나머지는 비운 채 올린다. 시리얼에 `관제 화면: http://192.168.4.1` 꼴의 줄이 찍힌다. 휴대폰을 와이파이 `SMART_FLOOD`(그 암호)에 붙이고 그 주소를 연다. 시리얼에는 1초마다 `t=… lv=…mm rate=… pump=…` 줄이 찍히고, `lv` 가 보드가 읽은 수위다. 통과 기준은 "순서" 표 7번(보정 뒤 자 눈금과 ±5 mm, 강우 회차의 주의·경계, 플로트를 들면 정지)이다.

시험 8(서버와 함께): `STA_SSID`·`STA_PASS` 에 노트북이 붙은 와이파이를, `SERVER_URL` 에 경로 없이 `http://<노트북 IP>:8000` 을 적고 다시 올린다. 서버는 7단계대로 live 로 두고, 창 2 에서 `post /api/experiment/start '{}'` 로 회차를 시작한다. 시리얼에 `와이파이 연결: <IP>` 와 `서버 전송 HTTP 200` 이 한 번씩 찍힌다. 창 2 의 `state` 가 `live running online A=<lv 값> measured valid` 이면 통과다. 물이 가만히 있으면 A 는 시리얼의 `lv` 와 같다. 시리얼 줄의 뜻과 할 일은 "board 스케치" 절의 표에 있다.

### 12. MicroPython 판으로 하기 (선택)

시험 8 은 `python/` 의 MicroPython 판으로도 할 수 있다. 펌프 제어(시험 7)는 MicroPython 판에 없다. MicroPython 을 올리면 Arduino 스케치가 지워지고, 스케치를 다시 올리면 MicroPython 이 지워진다.

아래 `<포트>` 는 Windows 면 `COM3` 같은 이름, macOS 면 `/dev/cu.usbserial-XXXX` 같은 경로다. 시리얼 모니터는 닫아 둔다. `<.bin 경로>` 는 받은 파일로 바꾼다. 보통 Windows 는 `$HOME\Downloads\ESP32_GENERIC-<판>.bin`, macOS 는 `~/Downloads/ESP32_GENERIC-<판>.bin` 이다.

```bash
python -m esptool --chip esp32 --port <포트> erase_flash
python -m esptool --chip esp32 --port <포트> --baud 460800 write_flash -z 0x1000 <.bin 경로>
```

esptool 판에 따라 밑줄 이름이 바뀌었다는 경고가 나오면 경고가 알려 주는 이름(`erase-flash`·`write-flash`)으로 친다. 그다음 접속 정보를 채운다.

```bash
cd firmware/python
cp secret.py.example secret.py
```

`secret.py` 의 `STA_SSID`·`STA_PASS`·`SERVER_URL`(`http://<노트북 IP>:8000`)을 채운다. Windows 는 `notepad secret.py` 로 열고 인코딩 "UTF-8" 로 저장한다("UTF-8(BOM)" 이나 "ANSI" 가 아니다). macOS 는 `open -e secret.py` 로 연다. 텍스트 편집기는 새로 친 따옴표를 둥근 따옴표로 바꿀 수 있으니, 이미 있는 `""` 사이에만 적는다. 그다음 코드를 올린다.

```bash
mpremote connect <포트> cp level.py ingest.py client.py node.py main.py secret.py :
mpremote connect <포트> reset
mpremote connect <포트> repl
```

REPL 에 `wifi <IP>` 가 찍히고 그 뒤로 조용하면 보내고 있다. `reset` 과 `repl` 사이에 지나간 줄은 보이지 않으니, `wifi <IP>` 를 놓쳤으면 REPL 에 붙은 채로 보드의 EN 버튼을 눌러 부팅부터 다시 본다. 서버 쪽 확인은 시험 8 과 같다(`state` 가 `online`·`measured`). REPL 은 Ctrl-] 또는 Ctrl-x 로 나간다. 서버로 보내는 동안은 감시 타이머가 켜져 있어, REPL 에서 Ctrl-C 를 누르면 8초 뒤 보드가 다시 부팅한다("보드에 올리기").

### 13. 관제 웹으로 보기 (선택)

보드나 `host.py` 가 보내는 값을 관제 웹 `/` 화면으로 본다. 창 4 를 연다. 관제 웹은 Node 24 에서 시험했다. 자세한 것은 `frontend/README.md` 에 있다.

Windows(PowerShell):

```powershell
cd frontend
npm ci
Set-Content -Encoding ascii .env.development.local 'NEXT_PUBLIC_API_BASE=http://localhost:8000'
npm run dev
```

`npm` 이 스크립트를 실행할 수 없다며 막히면 3단계의 `Set-ExecutionPolicy -Scope Process …` 줄을 먼저 치거나 `npm.cmd ci`·`npm.cmd run dev` 로 친다. Windows PowerShell 5.1 의 `echo … >` 는 UTF-16 으로 써서 Next.js 가 못 읽을 수 있어 `Set-Content -Encoding ascii` 를 쓴다.

macOS(터미널):

```bash
export PATH="/opt/homebrew/opt/node@24/bin:$PATH"
cd frontend
npm ci
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000' > .env.development.local
npm run dev
```

첫 줄은 Homebrew `node@24` 를 쓸 때다(인텔 맥은 `/usr/local/opt/node@24/bin`). 브라우저로 `http://localhost:3000` 을 연다. `127.0.0.1:3000` 은 서버의 CORS 설정이 받지 않는다. 보드가 보내는 동안 입력원이 "● 실측", A 구역 출처가 "실측", 장치 칸의 "ESP32 #1" 이 "정상" 으로 보이면 된다. 위쪽에 "가상 데이터(서버 미연결)" 가 보이면 웹이 서버에 한 번도 닿지 못한 것이다. 한 번 붙은 뒤 서버가 꺼지면 마지막 값과 "연결 끊김" 이 보인다.

### 14. 끝낼 때

창 2 에서 회차를 멈추고, 창 1 에서 Ctrl+C 로 서버를 끈다. 서버를 다시 띄우면 sim 으로 시작한다.

```bash
post /api/experiment/stop '{}'
```

보드나 노트북을 남에게 넘길 때는 접속 정보를 지운다.

- 보드: `python -m esptool --chip esp32 --port <포트> erase_flash` 로 플래시를 통째로 지운다. 시험 2 의 SSID·암호, 스케치와 설정이 함께 지워진다. MicroPython 의 `secret.py` 만 지울 때는 `mpremote rm :secret.py` 다.
- 노트북: `firmware/board/secrets.h` 와 `firmware/python/secret.py` 를 지운다(저장소에는 원래 올라가지 않는다).
- Windows 에서 8000 포트 규칙을 만들었으면 관리자 PowerShell 에서 `Remove-NetFirewallRule -DisplayName "SMART FLOOD 8000"` 로 지운다.

### 15. 막힐 때

| 증상 | 까닭 | 할 일 |
|---|---|---|
| Windows: `py` 를 찾을 수 없다 | Python 을 py 실행기 없이 깔았다 | python.org 설치 파일을 다시 돌려 "py launcher" 를 켠다. `python --version` 이 3.11 이면 `py -3.11` 대신 `python` 으로 쳐도 된다 |
| Windows: `Activate.ps1` 을 로드할 수 없다 | 스크립트 실행 정책 | 같은 창에서 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` 를 친 뒤 다시 |
| macOS: `externally-managed-environment` | 가상 환경 밖에서 `pip` 를 쳤다 | `source .venv/bin/activate` 뒤 다시 |
| `No module named uvicorn`, `No module named pytest`, macOS 의 `command not found: python` | 가상 환경이 꺼진 창이다 | 프롬프트의 `(.venv)` 를 보고 3단계대로 활성화한다 |
| 업로드가 `Connecting.....` 에서 멈춘다 | 보드가 업로드 모드로 들어가지 않았다 | BOOT 버튼을 누른 채로 기다리다 쓰기가 시작되면 뗀다 |
| 포트가 안 보인다 | 충전 전용 케이블이거나 드라이버가 없다 | 데이터 케이블로 바꾸고 1단계의 드라이버를 깐다 |
| `could not open port`, `Access is denied`, `Resource busy` | 다른 프로그램이 포트를 잡고 있다 | 시리얼 모니터와 다른 `mpremote` 창을 닫는다 |
| 시리얼 글자가 깨진다 | 속도가 다르다 | 시리얼 모니터를 115200 으로 둔다 |
| 시험 2 에서 `-> -1` 같은 음수 | 보드가 서버에 닿지 못했다 | 4~6단계(`0.0.0.0`, 방화벽, 같은 와이파이)를 다시 본다 |
| `와이파이 연결 안 됨…` 이 계속된다 | 이름·암호가 틀렸거나 5 GHz 망이다 | `STA_SSID`·`STA_PASS` 와 2.4 GHz 인지 본다. 아이폰 핫스팟은 "호환성 최대화" 를 켠다 |
| `서버 전송 실패…`, `전송 실패 seq N` | 서버에 닿지 못했다 | 6단계의 휴대폰 시험부터 다시 한다 |
| `서버 전송 HTTP 200` 인데 `state` 가 그대로다 | 서버가 sim 이거나 회차를 시작하지 않았다 | 7·8단계대로 live 로 바꾸고 회차를 시작한다 |
| `post` 가 409 | 회차가 도는 중에 입력원을 바꾸려 했다 | `post /api/experiment/stop '{}'` 를 친 뒤 다시 |
| `online` 인데 A 가 `estimated` 이고 품질이 `degraded`·`invalid` | 센서 이상이라 보드가 `null` 을 보냈거나, 거리가 `backend/config.yaml` 의 `sensors.A` 범위(200~650 mm) 밖이다 | 시험 6 의 mV 와 배선을 다시 본다 |
| 관제 웹 위쪽에 "가상 데이터(서버 미연결)" | 웹이 서버에 닿지 못했다 | 창 1 의 서버, `.env.development.local`, `localhost:3000` 으로 열었는지 본다 |
| `npm run dev` 가 3000 번 포트가 쓰이는 중이라며 멈춘다 | 다른 프로그램(예: Docker 컨테이너)이 3000 번을 쓴다 | 그 프로그램을 끈다. 서버가 `http://localhost:3000` 에서 연 화면의 요청만 받으므로 포트를 바꾸지 않는다. 끌 수 없으면 `frontend` 에서 `npm run build` 를 한 뒤 창 1 의 서버를 다시 띄우고(7단계 입력원 바꾸기도 다시) `http://localhost:8000/` 을 연다. 루트 README "실행" 절의 서버 한 대 방식이고 `sim` 과 같은 화면이 나온다 |
| `http://localhost:3000` 에 이 관제 웹이 아닌 다른 화면이 뜬다 | 다른 프로그램이 3000 번을 함께 쓴다 | 위 줄과 같다 |

## 준비

- Arduino IDE 2.x 를 설치한다. 환경설정 > 추가 보드 관리자 URL 에 `https://espressif.github.io/arduino-esp32/package_esp32_index.json` 을 넣고, 보드 매니저에서 "esp32 by Espressif Systems" 를 설치한다.
- 보드는 "ESP32 Dev Module", 업로드 속도 921600(안 되면 115200), 시리얼 모니터 115200.
- 포트: Windows 는 장치 관리자의 "포트(COM & LPT)" 에 `COM3` 처럼, macOS 는 `ls /dev/cu.*` 에 `cu.usbserial-…` 나 `cu.SLAB_USBtoUART` 로 새로 보인다("보드 시험 따라하기" 9단계). 안 보이면 데이터용 마이크로 USB 케이블인지 확인하고, 보드 USB 칩(CP2102 또는 CH340)에 맞는 드라이버를 설치한다.
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

REV15 부품(푸시 버튼 GPIO25, JSN-SR04T GPIO5·18, HX711 GPIO32·33)은 REV16 구성에 없다. 그 부품용 스케치(`parts/button`·`parts/sonar`·`parts/scale`·`node`)는 지웠다.

공통 규칙: 5 V 와 3V3 은 DevKitC 핀에서 끌어 쓰고 GND 는 모두 한 줄에 모은다. 12 V 어댑터 선은 릴레이 접점·펌프·수위센서에만 간다. ESP32 핀에 5 V 이상이 닿는 배선은 하지 않는다.

## board 스케치

100 ms 마다 수위를 읽고 펌프를 제어하며, 1초마다 최근 20초의 상승 속도로 A·B·C 구역의 침수 시각을 예측해 주의·경계·침수 알림을 낸다. 서버는 있어도 없어도 된다.

접속 정보는 `board/secrets.h.example` 을 `board/secrets.h` 로 복사해 채운다. 비워 둔 항목은 그 기능이 꺼진다.

| 항목 | 뜻 | 비우면 |
|---|---|---|
| `AP_PASS` | 보드가 여는 와이파이 `SMART_FLOOD` 의 암호. 8자 이상 | 관제 화면과 펌프 제어를 열지 않는다(암호 없는 AP 로 펌프를 제어하지 않기 위해) |
| `STA_SSID`·`STA_PASS` | 서버가 있는 와이파이 | 와이파이에 붙지 않는다 |
| `SERVER_URL` | `http://<노트북 IP>:8000`. 컴퓨터 이름 말고 IP 로 적는다. 끝의 `/` 는 있어도 된다 | 서버로 보내지 않는다 |
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

서버에는 1초마다 `POST /api/ingest` 로 `distA_mm = 600 - 수위` 를 보낸다. 600 은 `INSTALL_HEIGHT_MM` 이고 `backend/config.yaml` 의 `sensors.A.install_height_mm` 와 같아야 한다. B 구역과 무게는 `null`·`absent`, 센서 이상이면 `distA_mm` 가 `null` 이고 `A` 가 `fault` 다. 플로트 스위치는 `floatSwitch` 로 함께 보낸다. 급수통 물이 모자라면 `low`, 아니면 `normal` 이다. 서버가 꺼져 있어도 연결·읽기 제한이 각 400 ms 라 펌프 제어 루프가 오래 막히지 않는다. ntfy 는 TLS 인증서를 확인하지 않고(`setInsecure`) 보낸다.

와이파이가 끊기면 10초는 ESP32 코어의 자동 재접속에 맡기고, 그 뒤로는 10초(`REJOIN_MS`)마다 다시 붙어 본다. 부팅 때 공유기를 못 찾은 경우도 같다. 붙지 않은 동안에는 서버 전송과 ntfy 만 건너뛰고 수위 측정·펌프 제어·알림 판단은 그대로 돈다.

와이파이와 서버 전송 상태는 바뀔 때만 시리얼에 한 줄 찍는다. 와이파이 이름과 암호는 찍지 않는다.

| 시리얼 줄 | 뜻 | 할 일 |
|---|---|---|
| `와이파이 연결: <IP>` | 공유기에 붙었다 | 노트북과 같은 망인지 본다("서버에 닿게 하기") |
| `와이파이 연결 안 됨. 10초마다 다시 붙어 봄` | 공유기에 붙지 못했다. 부팅 직후에는 붙는 중이라 한 번 보일 수 있다 | 계속 보이면 `STA_SSID`·`STA_PASS` 와 2.4 GHz 망인지 확인한다 |
| `서버 전송 HTTP 200` | 서버가 받았다 | 서버가 live 가 아니면 받기만 하고 쓰지 않는다. "서버에 닿게 하기" 대로 live 로 바꾼다 |
| `서버 전송 HTTP 422` | 서버가 메시지를 거절했다. 보통 모르는 장치 이름이다 | `DEVICE_ID` 가 `backend/config.yaml` 의 `devices.allowed` 에 있는지 본다 |
| `서버 전송 HTTP 404`·`405` | 경로가 틀렸다 | `SERVER_URL` 은 `http://IP:8000` 까지만 적는다. `/api/ingest` 는 보드가 붙인다 |
| `서버 전송 실패: connection refused` 등 | 서버에 닿지 못했다 | 서버를 `--host 0.0.0.0` 으로 띄웠는지, 노트북 방화벽(Windows Defender 방화벽·macOS 방화벽), 같은 와이파이인지 본다 |
| `서버 주소를 읽지 못함` | `SERVER_URL` 을 읽지 못했다 | `http://IP:8000` 꼴로 고친다 |

알려진 특성: 강우 흉내가 ON·OFF 펄스라 20초 회귀 기울기가 출렁이고, 그래서 ETA 가 흔들리며 첫 알림이 명목 60초보다 이르게 올 수 있다. 수위가 최대 수위 근처일 때 C 구역에도 "주의"가 잠깐 뜰 수 있다(C 는 침수하지 않는다). 설계서 10장의 화면 스크립트에서 PDF 에 잘린 줄과 `cfg.z2` 오류는 `page.h` 머리에 적은 대로 고쳤다.

### 확인한 것

맥에서 WiFi·HTTPClient·WebServer·Preferences·ADC 의 대역을 만들어 `board.ino` 를 C++ 로 컴파일하고, `setup()`·`loop()` 를 가짜 시계(100 ms)와 가짜 수위로 돌렸다. 통과한 것: 부팅 직후 릴레이 꺼짐(고임피던스), `secrets.h` 가 없으면 와이파이·관제 화면·전송 없음, 1초마다 전송과 `seq` 증가, `SERVER_URL` 끝의 `/` 를 빼고 `/api/ingest` 를 붙인 주소, 와이파이가 25초 끊기면 전송을 멈추고 10초마다 다시 붙어 본 뒤 이어 보냄, 와이파이·전송 상태(연결·끊김·실패·422·200·주소 오류)를 바뀔 때 한 번씩 찍고 와이파이 이름·암호는 찍지 않음, 전송 본문 1108건이 서버의 `Message` 스키마와 live 모드 `/api/ingest` 를 통과, 강우 회차에서 A·B 순서 침수와 경보 선행 약 100초, 최대 수위 정지, 플로트 100 ms 정지, 센서 이상 정지와 `null` 전송, 수동 60초 정지, 설정 저장·재로드, 두 점 보정. 대역은 직접 만든 것이라 ESP32 코어 API 의 이름과 시그니처는 확인되지 않았다. 보드에서 처음 컴파일할 때 오류가 날 수 있다. 2026-11-04 에 ntfy 전송을 대기열과 별도 태스크로 옮긴 뒤에는 대역 헤더로 문법 검사만 했고 가짜 시계 실행은 다시 하지 않았다.

## python 노드(MicroPython)

`python/` 은 같은 ESP32 에서 돌아가는 MicroPython 판이다. 1단계 범위는 수위 읽기와 1초마다 `POST /api/ingest` 전송까지다. 펌프 제어·보정 명령(`cal1`·`cal2`·`calreset`)·20초 기울기 예측·주의/경계 단계·관제 화면·ntfy 는 아직 `board/` 스케치에만 있다. 릴레이 핀(GPIO26)은 입력으로 두어 펌프가 켜지지 않는다.

파일은 두 층이다. 순수 모듈은 컴퓨터(CPython)에서 pytest 로 돌고, 보드 층만 ESP32 API 를 쓴다. 공용 모듈은 MicroPython 에서도 돌아야 하므로 f-string·typing·dataclass 를 쓰지 않는다.

| 파일 | 뜻 | 어디서 도는가 |
|---|---|---|
| `level.py` | 전압(mV)→수위(mm) 직선, 센서 이상 범위(300~2800 mV), 100 ms 이동평균, 1점·2점 보정 직선(스케치 `cal1`·`cal2`·`calreset` 과 같은 식. 명령은 아직 없다) | 컴퓨터·보드 |
| `ingest.py` | 서버 `/api/ingest` 메시지. `distA_mm = 600 - 수위`, 이상이면 `null`·`fault` | 컴퓨터·보드 |
| `client.py` | `socket` 만 쓰는 HTTP POST. 연결·응답 각 400 ms 제한, http 만 | 컴퓨터·보드 |
| `node.py` | 100 ms 표본·1 s 전송 루프. 시각·ADC·전송은 보드 객체가 준다 | 컴퓨터·보드 |
| `main.py` | ESP32 보드 층. ADC(GPIO34) 64회 평균, 와이파이 접속, 감시 타이머 8초, 부팅 시 자동 실행 | 보드 |
| `host.py` | 컴퓨터 실행기. 가짜 수위나 표준입력의 mV 로 같은 루프를 돌려 서버에 보낸다 | 컴퓨터 |
| `secret.py.example` | 접속 정보 견본. `secret.py` 로 복사해 채운다. `secret.py` 는 저장소에 올리지 않는다 | - |

부품 시험 1~6 은 그대로 `parts/` 스케치로 한다. 8(서버 연동)은 `python/` 으로도 할 수 있고, 7(펌프 제어)은 아직 `board/` 만 된다.

### 컴퓨터에서 시험

가상 환경("보드 시험 따라하기" 3단계)을 켠 창에서 친다.

```bash
cd firmware/python
python -m pytest -q
ruff check .
```

보드 없이 서버 경로를 미리 확인하려면 서버를 띄우고 live 로 바꾼 뒤("보드 시험 따라하기" 4·7단계) 실행기를 돌린다. `--mm` 은 가짜 수위(mm), `--ramp` 는 초당 변화(mm/s), `--seconds` 는 보낼 횟수다. `--server` 를 비우면 서버 없이 메시지를 한 줄씩 찍는다.

```bash
python host.py --server http://localhost:8000 --mm 40 --ramp 0.5 --seconds 30
python host.py --mm 40 --seconds 3
```

시리얼 등에서 mV 값이 한 줄씩 들어오면 `--stdin` 으로 그 값을 센서 값으로 쓴다. 줄에 `mV` 토큰이 있으면 그 바로 앞 숫자를 읽고(`1500 ms raw 615  482 mV` 같은 스케치 출력 그대로), 없으면 첫 토큰이 숫자인 줄만 읽는다. `--server` 끝의 `/` 는 있어도 되고, `http://` 로 시작하지 않으면 시작 전에 거절한다.

### 보드에 올리기

도구와 MicroPython 펌웨어는 사람이 설치한다. 아래는 보드를 꽂은 뒤 한 번만 한다. `.bin` 은 micropython.org 의 ESP32_GENERIC 다운로드 페이지에서 받고, 파일명은 받은 판으로 바꾼다. `<포트>` 는 Windows 면 `COM3`, macOS 면 `/dev/cu.usbserial-XXXX` 꼴이다("보드 시험 따라하기" 9단계). esptool 판에 따라 밑줄 이름이 바뀌었다는 경고가 나오면 경고가 알려 주는 이름(`erase-flash`·`write-flash`)으로 친다.

```bash
python -m pip install esptool mpremote
python -m esptool --chip esp32 --port <포트> erase_flash
python -m esptool --chip esp32 --port <포트> --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-<판>.bin
```

그다음 코드를 올린다. `main.py` 는 부팅마다 자동으로 돈다.

```bash
cd firmware/python
cp secret.py.example secret.py                 # STA_SSID·STA_PASS·SERVER_URL 채움
mpremote connect <포트> cp level.py ingest.py client.py node.py main.py secret.py :
mpremote connect <포트> reset
mpremote connect <포트> repl    # 전송 실패가 있으면 여기 찍힌다. Ctrl-] 또는 Ctrl-x 로 나감
```

`secret.py` 가 없거나 `SERVER_URL`·`STA_SSID` 가 비면 와이파이에 붙지 않고 메시지를 REPL 에만 찍는다. `secret.py` 가 깨져 있거나(문법 오류) `SERVER_URL` 이 `http://` 로 시작하지 않아도 멈추지 않고 이유를 한 줄 찍은 뒤 같은 REPL 출력으로 넘어간다. `SERVER_URL` 끝의 `/` 는 있어도 된다. 보드를 남에게 넘길 때는 `mpremote rm :secret.py` 로 지운다.

부팅 때 15초 안에 와이파이에 붙지 못하면 `wifi 접속 실패. 보낼 때마다 다시 붙어 봄` 을 찍고 서버 주소는 그대로 둔다. 붙지 않은 동안에는 전송마다 `전송 실패 seq N: 와이파이 끊김` 을 찍고 10초에 한 번 다시 붙어 본다. 도는 중에 끊긴 경우도 같다. 다시 붙으면 `wifi <IP>` 를 찍고 이어 보낸다. 잘 보내는 동안에는 아무것도 찍지 않으므로 `wifi <IP>` 뒤에 `전송 실패` 줄이 없으면 보내고 있는 것이다. `서버 응답 422` 는 `ingest.py` 의 `DEVICE_ID` 가 서버의 `devices.allowed` 에 없다는 뜻이고, `서버 응답 404`·`405` 는 `SERVER_URL` 에 경로를 붙였다는 뜻이다. 그 밖의 `전송 실패`(시간 초과·연결 거절 등)는 서버에 닿지 못한 것이니 "서버에 닿게 하기" 를 본다.

서버로 보내도록 설정되어 있으면(`SERVER_URL`·`STA_SSID`) 감시 타이머 8초가 켜지고 끌 수 없다. REPL 에서 Ctrl-C 로 루프를 멈추면 8초 뒤 보드가 다시 부팅한다. REPL 에서 오래 작업하려면 `SERVER_URL` 을 비운 `secret.py` 를 올리고 다시 부팅한다. 코드를 다시 올리다 재부팅되면 같은 명령을 다시 한다.

### 확인한 것

맥에서 pytest 53건(변환·보정·메시지·HTTP 클라이언트·루프 타이밍·실행기·보드 층)과 ruff 가 통과했다. 루프는 표본 읽기가 1초씩 막히거나(표준입력) 전송이 600 ms 걸려도 1초 간격으로 보내고, 전송이 1초를 넘기면 밀린 전송을 몰아 보내지 않는다. 보드 층 `main.py` 는 `tests/test_main.py` 가 `machine`·`network`·`time.ticks_*` 대역을 끼워 CPython 에서 돌린다: 릴레이 핀이 입력으로 설정되고 핀 출력이 없으며, `seq` 0·1·2 가 `/api/ingest` 로 가고, 감시 타이머가 표본마다 먹여지며, 부팅 때나 도는 중에 와이파이가 끊기면 그 전송을 실패로 알리고 10초에 한 번만 다시 붙어 본 뒤 붙으면 IP 를 찍고 이어 보내며, 깨진 `secret.py`·잘못된 `SERVER_URL` 에서는 REPL 출력으로 넘어간다. `host.py` 로 로컬 서버(live)에 가짜 수위를 10초, 표준입력 mV 를 1초에 한 줄씩 보내 두 경우 모두 `tMs` 간격이 991~1011 ms 이고, 보내는 동안 `/api/state` 의 `devices.esp32_1` 이 online, A 구역 `source` 가 measured 인 것을 확인했다. MicroPython 실제 API(`ADC.read_uv`, `WDT`, `network.WLAN`)는 보드에서 아직 돌려 보지 않았다.

## 순서

앞 단계가 통과해야 다음으로 간다. 한 번에 하나만 꽂는다.

| 순서 | 부품 | 스케치 | 배선 | 통과 기준 |
|---|---|---|---|---|
| 1 | ESP32 단독 | `parts/led` | USB 만 | 업로드 성공. 시리얼에 칩 이름과 0.5초마다 tick 이 찍힌다. LED 가 깜빡인다 |
| 2 | ESP32 WiFi | `parts/net` | USB 만 | 시리얼 모니터에 SSID·암호·서버 URL 을 한 줄씩 입력(줄 끝 "New Line"). 서버 URL 은 `/api/state` 까지 적는다. IP 가 찍히고 `GET … -> 200` 과 `/api/state` 앞부분이 보인다 |
| 3 | 플로트 스위치 | `parts/reed` | GPIO27-스위치-GND | 플로트를 위아래로 돌리면 닫힘·열림이 바뀐다. 어느 방향이 "물 모자람"인지 적는다 |
| 4 | 릴레이(무부하) | `parts/relay` | IN GPIO26, VCC 5V, GND | 3초마다 딸깍 소리와 LED. `IN=LOW` 에 켜지고 `IN=HIGHZ` 에 꺼지면 조립서의 active-LOW 모듈이다. 켜지지 않으면 선 3·4·5 와 모듈 종류를 본다 |
| 5 | 릴레이 + 펌프 | `parts/relay` | 어댑터 + 를 COM, NO 를 펌프 +, 펌프 - 를 어댑터 - | 펌프를 물에 넣은 뒤에만 어댑터를 꽂는다(수중펌프는 공회전 금지). 3초 켜짐·꺼짐이 반복된다. 1분간 받은 물 양으로 L/min 을 적는다 |
| 6 | KIT0139 | `parts/depth` | 변환보드 출력을 GPIO34 에 | 물이 없을 때 mV 와 1분 동안의 흔들림(mV)을 적는다. 1 mV 가 약 2.6 mm 라 ±3 mV 면 수위 ±8 mm 다. 깊이 두 점에서 mV 를 적는다 |
| 7 | board(서버 없이) | `board` | 전부. `secrets.h` 에 `AP_PASS` 만 | 관제 화면에 수위가 보인다. `cal1`·`cal2` 보정 뒤 자 눈금과 ±5 mm 안에 든다. `start` 로 강우 회차를 돌리면 물이 A 기준(40 mm)에 닿기 전에 주의·경계가 뜨고, 플로트를 들면 바로 멈춘다 |
| 8 | board + 서버 | `board` | 전부. `STA_SSID`·`STA_PASS`·`SERVER_URL` 채움 | 시리얼에 `와이파이 연결: <IP>` 와 `서버 전송 HTTP 200` 이 찍힌다. 서버를 live 로 바꾸고 회차를 시작하면 `/api/state` 의 `devices.esp32_1` 이 online 이고 A 수위가 보드 값과 같다 |

시험 3·4 의 결과가 기본값과 다르면 `board.ino` 위쪽의 `FLOAT_LOW_WHEN_CLOSED`·`RELAY_ACTIVE_LOW` 를 바꾼 뒤 올린다.

## 서버에 닿게 하기

ESP32 가 노트북의 서버에 붙으려면 네 가지가 맞아야 한다. Windows·macOS 명령은 "보드 시험 따라하기" 4~8단계에 있다.

1. 서버를 모든 주소에서 듣게 띄운다. `backend/` 에서 `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
2. 노트북 방화벽이 8000 포트로 들어오는 연결을 받는다. 같은 와이파이에 붙은 휴대폰 브라우저로 `http://<노트북 IP>:8000/api/state` 가 열리면 된다. 노트북 안에서 친 `curl` 은 서버가 듣는지만 알려 준다.
3. ESP32 와 노트북이 같은 2.4 GHz 와이파이에 있다. 학교·회사 와이파이는 기기끼리의 연결을 막기도 하니, 그럴 때는 휴대폰 핫스팟에 둘 다 붙인다. 아이폰 핫스팟은 "호환성 최대화" 를 켠다.
4. 서버 입력원이 live 이고 회차가 돌고 있다. 서버는 기본이 시뮬레이션이다. 멈춘 상태에서 `/api/source` 에 `{"mode":"live"}` 를 보내고 `/api/experiment/start` 로 회차를 시작한다. live 가 아니어도 서버는 메시지를 받지만(200) 쓰지 않는다.

노트북 IP 는 Windows 면 `ipconfig` 의 Wi-Fi "IPv4 주소", macOS 면 `ipconfig getifaddr en0` 이다. 보드 시리얼의 `와이파이 연결: <IP>` 와 노트북 IP 는 보통 앞 세 마디(예 `192.168.0`)가 같다.

## 적어 둘 값

| 값 | 어디서 | 들어갈 곳 |
|---|---|---|
| 센서 설치 높이(바닥에서 센서 기준면까지, mm) | 모형에 단 뒤 | `board.ino` 의 `INSTALL_HEIGHT_MM`, `backend/config.yaml` 의 `sensors.A.install_height_mm`·`max_range_mm` |
| 0 mm 에서의 mV 와 1분 흔들림(mV) | 시험 6 | `cal1`·`cal2` 보정, 잡음이 커서 평균 시간을 늘릴지 판단 |
| 펌프 유량(L/min 또는 30초 mL) | 시험 5, `flowtest` | `flowset`, 강우 세기 환산 |
| 릴레이 켜지는 레벨, 플로트 "물 모자람" 방향 | 시험 3·4 | `RELAY_ACTIVE_LOW`, `FLOAT_LOW_WHEN_CLOSED` |
| 수면 면적(cm²) | 자로 재서 | 설정 `areaCm2`(기본 1700) 또는 `areaapply` |
| 구역 기준 높이(mm) | 모형에서 자로 | `/api/set` 의 `z0`·`z1`·`z2`, `backend/config.yaml` 의 임계값 |
