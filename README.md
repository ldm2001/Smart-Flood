# SMART FLOOD dev

`dev` 는 통합 브랜치다

`sim` 의 서버와 웹을 `sensor` 의 펌웨어와 한곳에 모아 실제 보드로 시험한다

시험을 마친 `dev` 를 `main` 이 받는다

## 브랜치 흐름

```text
sim     (backend/ + frontend/) --+
                                 +--> dev (셋 모두) --> main
sensor  (firmware/) -------------+
```

- 합치는 방향은 한쪽뿐이다
- `sim` 과 `sensor` 는 `dev` 와 `main` 을 받지 않는다
- 받으면 상대 공간의 폴더가 딸려 오기 때문이다
- 풀리퀘스트의 대상은 `dev` 다
- `dev` 에서 검증 명령이 모두 통과하고 보드를 붙인 시험을 거치면 `main` 으로 올린다
- `main` 으로 합칠 때는 "Create a merge commit" 을 쓴다
- 코드는 `sim` 과 `sensor` 에서만 고친다
- README 는 브랜치마다 따로 두고 합칠 때 겹치면 받는 쪽 것을 남긴다

## 데이터 흐름

```text
[보드]  수위센서 --100 ms--> board.ino --> 릴레이 --> 펌프   (펌프는 보드 안에서만 제어)
           |
           |  POST /api/ingest  1초마다
           |  deviceId  bootId  seq  tMs  readings(distA_mm)  sensorStatus  floatSwitch
           v
[서버]  live 입력원이 메시지를 모음
           |
           v  1 Hz tick
        inbox > 관측 수위 환산 > 모델 한 걸음 > 관측 보정 > 위험 단계 판정
              > 10 20 30초 예측과 스냅숏 > JSONL 기록 > 알림 포트 (stub 또는 시험 문자)
           |
           |  GET /api/state
           v
[웹]    1초마다 읽음 > zod 검사 > lib/derive 파생 계산 > 화면
        단계가 바뀌면 GET /api/logs/{id}/events 로 사건을 다시 읽음
```

- 보드는 서버와 따로 돈다
- 서버가 꺼져도 보드의 측정 · 펌프 제어 · 알림 판단은 계속 돈다
- 서버의 출력 잠금(`outputsLocked`)은 늘 `true` 다
- `/api/ingest` 는 입력원이 `live` 일 때만 메시지를 tick 에 넣는다
- 다른 입력원에서는 200 으로 받기만 한다
- 장치는 마지막 수신 뒤 5초가 지나면 오프라인으로 본다
- 보드가 보낸 `floatSwitch` 는 `devices.floatSwitch` 로 나가 장치 상태 칸에 보인다
- 플로트 값은 장치 상태에만 쓰고 수위와 위험 판정에는 쓰지 않는다
- 서버 안은 SI 단위로 계산하고 API 는 mm · L · L/min 으로 낸다

## 입력원

| 입력원 | 관측이 오는 곳 | 판정에 쓰는 수위 |
|---|---|---|
| `sim` | 가상 센서 (`adapters/sim_source.py`) | 보정한 모델 수위와 모델 변화율 |
| `live` | 보드가 보낸 메시지 (`adapters/live.py`) | 3초 안의 관측이 있으면 관측 수위와 최근 20초 기울기 |
| `replay` | `backend/logs/` 의 JSONL 기록 (`adapters/replay_source.py`) | 기록을 지금의 `config.yaml` 로 다시 계산한 값 |

- 입력원은 `POST /api/source` 로 바꾼다
- 회차가 도는 중에 바꾸려 하면 409 로 거절된다
- 서버를 다시 띄우면 `sim` 으로 시작한다
- 재생 중에는 기록 쓰기와 알림을 멈춘다

## 모듈 계층

화살표는 가져다 쓰는 방향이다

```text
backend/app
├── main.py        조립: 어댑터를 골라 service 에 넣고 라우터와 frontend/out 을 붙임
├── api/           HTTP 라우터 state · control · logs              --> service · schemas · ports
├── service.py     회차 · 입력원 전환 · 1 Hz tick                   --> core · ports · schemas · adapters(live · replay · stub)
├── schemas.py     /api/state 와 ingest 메시지 꼴                    --> core
├── core/          순수 로직 model · predictor · calibration · danger · message
│                  시간은 인자로 받음                                 --> core 안에서만
├── ports/         Protocol source · clock · experiment_log · notifier --> core 의 형
└── adapters/      구현 sim_source · live · replay_source · clock
                   jsonl_log · stub · dispatch · solapi              --> ports · core · schemas

frontend/src
├── app/           쪽 / · /ops/ · /logs/                             --> components
├── components/    화면 칸 MonitorView · OpsView · LogsView 와 패널   --> lib
└── lib/
    ├── useSnapshot · useEvents · useNow · useSettings  구독 훅       --> api · derive · schema
    ├── api.ts     서버 요청과 zod 검사                               --> schema · useNow
    ├── schema.ts  /api/state 의 zod 스키마
    ├── derive.ts  순수 파생 계산 (시간은 인자)                       --> schema · layout-data · api
    └── layout-data.ts · mock.ts  이름표 · 평면도 자리 · 가상 데이터  --> derive · schema

firmware
├── board/         본 스케치 board.ino · page.h · secrets.h          --> POST /api/ingest
├── parts/         부품 시험 led · net · reed · relay · depth        --> 부품 하나씩
└── python/        MicroPython 판
    ├── main.py    보드 층 ADC · 와이파이 · 감시 타이머              --> node · level · ingest · client
    ├── host.py    컴퓨터 실행기                                     --> node · level · ingest · client
    └── node.py    100 ms 표본 · 1초 전송 루프                        --> level · ingest
```

- `core` 는 `adapters` 와 웹 프레임워크를 모르는 순수 계층이다
- 바깥 입출력은 `ports` 의 Protocol 로 받고 `adapters` 가 구현한다
- 웹과 서버는 `/api/*` JSON 으로만 이어진다
- 보드와 서버는 `POST /api/ingest` 메시지로만 이어진다
- `/api/state` 계약은 서버가 갖고 웹의 zod 스키마가 같은 제약을 지킨다

## 보드와 함께 띄우기

아래는 macOS 명령이다

Windows 명령은 `firmware/README.md` 의 "보드 시험 따라하기 (Windows·macOS)" 절에 있다

### 가상 환경 (처음 한 번)

저장소 맨 위에 가상 환경을 만든다

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt esptool mpremote
```

### 서버 (창 1)

모든 주소로 듣게 서버를 띄운다

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 입력원과 회차 (창 2)

상태를 보는 `state` 와 요청을 보내는 `post` 를 붙여 넣는다

```bash
state() { curl -s http://127.0.0.1:8000/api/state | python3 -c "import json,sys; s=json.load(sys.stdin); print(s['dataSource'], s['runState'], s['devices']['esp32_1'], 'A=%s' % s['zones']['A']['levelMm'], s['zones']['A']['source'], s['quality'])"; }
post() { curl -s -X POST "http://127.0.0.1:8000$1" -H 'Content-Type: application/json' -d "$2" | python3 -c "import json,sys; s=json.load(sys.stdin); print(s.get('detail') or '%s %s %s' % (s['dataSource'], s['runState'], s['experimentId']))"; }
```

입력원을 `live` 로 바꾸고 회차를 시작한다

```bash
post /api/source '{"mode":"live"}'
state
```

```bash
post /api/experiment/start '{}'
```

### 보드

접속 정보를 넣고 `firmware/board/board.ino` 를 올린다

```bash
cp firmware/board/secrets.h.example firmware/board/secrets.h
```

- `STA_SSID` · `STA_PASS` 에 노트북이 붙은 `2.4 GHz` 와이파이를 적는다
- `SERVER_URL` 에 경로 없이 `http://<노트북 IP>:8000` 을 적는다
- 시리얼에 `서버 전송 HTTP 200` 이 찍히면 서버가 받았다
- `state` 가 `live running online A=<수위> measured valid` 를 찍으면 이어진 것이다

### 보드 없이 (창 3)

컴퓨터가 보드 노릇을 하며 서버까지 가는 길을 확인한다

```bash
cd firmware/python
python host.py --server http://localhost:8000 --mm 40 --seconds 20
```

### 관제 웹 (창 4)

관제 웹을 띄우고 `http://localhost:3000` 을 연다

```bash
export PATH="/opt/homebrew/opt/node@24/bin:$PATH"
cd frontend
npm ci
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000' > .env.development.local
npm run dev
```

서버 한 대로 볼 때는 `frontend/out/` 을 만든 뒤 서버를 띄우고 `http://localhost:8000/` 을 연다

```bash
cd frontend
npm run build
cd ../backend
uvicorn app.main:app --port 8000    # http://localhost:8000/
```

### 끝낼 때

창 2 에서 회차를 멈추고 창 1 에서 Ctrl+C 로 서버를 끈다

```bash
post /api/experiment/stop '{}'
```

## 검증

`dev` 에서 셋이 모두 통과해야 `main` 으로 올린다

```bash
cd backend
pytest && ruff check .
```

```bash
cd frontend
npm run lint && npm run typecheck && npm test && npm run build
```

```bash
cd firmware/python
python -m pytest -q
ruff check .
```
