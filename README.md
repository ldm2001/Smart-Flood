# SMART FLOOD sim

`sim` 은 시뮬레이션 공간이다

가상 센서로 실험을 돌리며 서버와 관제 웹을 만든다

`backend/` 와 `frontend/` 만 담고 펌웨어는 `sensor` 가 맡는다

여기서 만든 것은 `dev` 로 합친다

## 만든 것

### 물수지 모델과 보정

- `backend/app/core/model.py` 가 구역 A·B·C 의 물 부피를 강우 · 구역 사이 월류 · 빗물받이 배수로 적분한다
- `backend/app/core/calibration.py` 가 센서 거리를 수위로 바꾸고 관측 수위로 모델 상태를 보정한다
- 내부 계산은 SI 단위이고 API 는 mm · L · L/min 으로 낸다
- 모든 계수는 `backend/config.yaml` 에 있다

### 예측

- `backend/app/core/predictor.py` 가 보정한 상태에서 10·20·30초 뒤 수위를 낸다
- 실측 중에 3초 안의 A 관측이 있으면 지금 수위에 실측 기울기와 시간을 곱한 값을 더해 낸다 (보드 예측과 같은 식)
- 예측은 `/api/state` 의 `predictions` 로 나간다

### 입력원

| 입력원 | 관측이 오는 곳 | 어댑터 |
|---|---|---|
| `sim` | 가상 센서 | `adapters/sim_source.py` |
| `live` | `POST /api/ingest` 로 받은 장치 메시지 | `adapters/live.py` |
| `replay` | JSONL 실험 기록 | `adapters/replay_source.py` |

- 가상 센서는 운영 모델과 같은 식에서 계수 일부를 15% 바꾸고 잡음을 더해 참값을 만든다
- 실측에서는 장치 상태(마지막 수신 뒤 5초)와 입력 품질을 가른다
- 보드가 보낸 `floatSwitch` 는 장치 상태의 플로트 스위치 칸에만 쓴다
- 보드가 보낸 `running` 이 켜지면 서버가 회차를 돌리지 않는 동안 입력원을 `live` 로 바꾸고 회차를 연다
- `running` 이 꺼지면 그렇게 연 회차를 닫고 `/ops/` 에서 연 회차와 재생은 그대로 둔다 (`backend/config.yaml` 의 `live.follow`)

### 위험 단계

`backend/app/core/danger.py` 가 tick 마다 구역 단계를 판정한다

| 단계 | 계약 이름 | 조건 |
|---|---|---|
| 주의 | `caution` | 한계 수위 도달 예상 60초 안 |
| 경계 | `warning` | 도달 예상 30초 안 |
| 침수 | `evacuate` | 한계 수위 이상 |

- 시뮬레이션과 재생에서 오름은 바로 반영하고 내림은 10초 유지한 뒤 반영한다
- 침수는 한계의 90% 아래로 내려가야 풀린다
- 실측 중에는 3초 안의 관측이 있는 구역을 관측 수위와 최근 20초 최소제곱 기울기로 판정한다
- 센서가 없는 구역은 A 수면 높이에서 그 구역 바닥 높이를 뺀 수위와 A 기울기로 판정한다 (보드 높이 40·70·110 mm 와 같은 도달 초)
- 기울기는 표본 5개부터 쓰고 `0.005 mm/s` 이하는 오르지 않는 것으로 본다
- 실측 회차 동안 단계는 내려가지 않는다 (보드와 같다)
- 도달 초 `etaSec` 는 올림한 정수 초다
- 단계가 바뀌면 `stage` 사건을 기록하고 알림 포트로 보낸다

### 알림과 시험 문자

- 기본은 `notifier.mode: stub` 이고 서버 로그에 WARNING 한 줄만 남긴다
- 실제 문자는 세 조건이 모두 맞을 때만 허용 번호(`SMS_ALLOWED_TO`)로 보낸다

| 조건 | 맞추는 곳 |
|---|---|
| 방식 | `backend/config.yaml` 의 `notifier.mode: sms` |
| 환경 변수 | `SOLAPI_API_KEY` · `SOLAPI_API_SECRET` · `SOLAPI_SENDER` · `SMS_ALLOWED_TO` |
| 무장 | `POST /api/notifier/arm` 에 `{"armed": true}` |

- 문자는 경계와 침수로 오르는 전환에만 (실험 · 구역 · 단계)마다 한 번 간다
- 한 실험의 상한은 10건이고 시험 문자는 서버 실행당 3번이다
- 발송은 tick 밖의 스레드가 맡는다 (`adapters/dispatch.py` · `adapters/solapi.py`)
- 서버 로그의 번호는 뒤 4자리만 보인다
- `backend/scripts/sms.py` 로 서버 없이 한 건을 손으로 보내 본다

### 기록과 재생

- 회차마다 `backend/logs/` 에 JSONL 파일 하나를 쓴다
- 한 tick 의 관측 · 상태 · 사건 줄을 한 번에 쓴다
- `GET /api/logs` 로 목록을 읽고 `GET /api/logs/{id}/events` 로 사건을 읽는다
- 재생은 기록된 관측과 조작을 다시 넣고 지금의 `config.yaml` 로 다시 계산한다
- 재생 중에는 기록 쓰기와 알림을 멈춘다

### 관제 웹

| 화면 | 칸 |
|---|---|
| `/` 종합 관제 | 상태 배너 · 대피 안내 한 줄 · 구역 게이지 · 수위 차트 · 도시 평면도 · 현장 장치 상태 · 위험 판단 타임라인 · 이벤트 기록 |
| `/ops/` 운영·설정 | 회차 시작·종료·초기화 · 입력원 전환 · 강우 단계와 직접 입력 · 막힘 종류와 빗물받이 · 한계 수위 보기 |
| `/logs/` 기록·재생 | 실험 기록 목록 · 구역별 예측 도달과 실제 도달 비교 · 판정 칸(적중 · 누락 · 오경보 · 대기) · 기록 재생 시작 |

- 위험 단계와 사건은 서버 `alerts` 와 서버 기록만 따른다
- 장치 상태 칸은 급수통 플로트의 물 부족을 보여 준다
- 글꼴은 Pretendard 이고 자간 -3% 와 12 이상 짝수 글자 크기를 쓴다
- 여러 줄로 접히는 글은 줄 높이 150% 이고 한 줄 글은 기본 줄 높이다
- 서버가 한 번도 답하지 않으면 가상 데이터를 보여 주고 "가상 데이터(서버 미연결)" 를 단다
- 전시 때는 FastAPI 한 대가 `frontend/out/` 을 함께 내보낸다

### 단계별로 만든 것

| 단계 | 만든 것 |
|---|---|
| M1 | 물수지 모델 · 예측 · 관측 보정 |
| M2 | 가상 센서 · 1 Hz tick · `/api/state` · 제어 API |
| M3 | JSONL 실험 기록 · 재생 |
| M4 | `/api/ingest` · 장치 상태 · 입력 품질 |
| M5 | 위험 단계 · `stage` 사건 · 기록용 기본 알림 |
| M6 | 세 조건 시험 문자 발송 |
| S0 | 웹 뼈대 · zod 스키마 · 파생 계산 · mock 화면 |
| S1 | 상태 배너 · 구역 게이지 · 수위 차트 · 서버 연결 |
| S2 | 도시 평면도 · 장치 상태 · 위험 판단 타임라인 · 이벤트 기록 |
| S3 | `/ops/` 운영·설정 화면 |
| S4 | `/logs/` 기록·재생 화면 |
| S5 | 대비와 글자 크기 점검 · FastAPI 의 `out/` 서빙 |
| 2026-11-04 | 실측 구역의 관측 판정 · 대피 안내 한 줄 · 기록 화면 판정 칸 |
| 2026-11-05 | 보드 플로트 값의 장치 상태 표시 · Pretendard 글꼴과 글자 규칙 · 함수 이름 정리 · 보드 회차 따라가기와 보드 식 실측 판정 |

## 실행

Python `3.11` 이 필요하다

```bash
cd backend
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/api/state` 에서 상태를 본다

실험은 제어 API 로 시작하고 바꾼다

```bash
curl -X POST localhost:8000/api/experiment/start -H 'Content-Type: application/json' \
     -d '{"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}}'
curl -X POST localhost:8000/api/rain -H 'Content-Type: application/json' -d '{"mmPerHour": 75}'
curl -X POST localhost:8000/api/experiment/stop -H 'Content-Type: application/json' -d '{}'
```

기록 목록을 읽고 기록을 재생한 뒤 시뮬레이션으로 돌아온다

```bash
curl localhost:8000/api/logs
curl -X POST localhost:8000/api/source -H 'Content-Type: application/json' \
     -d '{"mode": "replay", "logId": "EXP-20261027-001"}'
curl -X POST localhost:8000/api/source -H 'Content-Type: application/json' -d '{"mode": "sim"}'
```

관제 웹은 Node 24 가 필요하고 다른 터미널에서 띄운다

PATH 와 환경 변수는 `frontend/README.md` 에 있다

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

전시 때는 서버 한 대로 띄운다

```bash
cd frontend
npm run build
cd ../backend
uvicorn app.main:app --port 8000    # http://localhost:8000/
```

시험 문자는 `backend/.env` 를 채우고 `notifier.mode` 를 `sms` 로 바꾼 뒤 띄운다

`backend/.env` 는 커밋하지 않는다

```bash
cd backend
cp .env.example .env    # 값을 채운다
set -a && . ./.env && set +a
uvicorn app.main:app --port 8000
```

다른 터미널에서 무장하고 시험 문자를 보낸 뒤 무장을 푼다

```bash
curl -X POST localhost:8000/api/notifier/arm -H 'Content-Type: application/json' -d '{"armed": true}'
curl -X POST localhost:8000/api/notifier/test -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8000/api/notifier/arm -H 'Content-Type: application/json' -d '{"armed": false}'
```

## 검증

```bash
cd backend
pytest && ruff check .
```

```bash
cd frontend
npm run lint && npm run typecheck && npm test && npm run build
```
