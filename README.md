# SMART FLOOD

A·B·C 세 구역으로 나눈 도시 침수 모형 실험을 위한 백엔드와 관제 웹이다. 백엔드는 물수지 모델로 구역 수위를 계산하고 10·20·30초 뒤를 예측한다. 그 결과를 `/api/state` 로 내보낸다. 지금은 가상 센서(시뮬레이션)로 돌아간다. 나중에 ESP32 실센서가 같은 입력 경로로 붙는다.

> **시험용이다.** 이 프로그램은 모형 실험과 시연을 위한 것이다. 실제 재난 판단이나 실제 문자 발송에 쓰지 않는다. 서버는 펌프 제어 출력과 SMS 발송을 하지 않는다(`outputsLocked` 는 항상 `true`). 위험 알림을 넣더라도 "SMS 예정" 기록만 남긴다.
>
> **시뮬레이션 결과는 예측 성능의 근거로 쓰지 않는다.** 가상 센서는 운영 모델과 같은 식으로 참값을 만든다. 일부 계수만 15% 바꾸고 센서 잡음을 더할 뿐이다. 그래서 시뮬레이션에서 예측이 잘 맞아도, 실제 모형이나 실제 도시에서도 맞는다는 뜻은 아니다.
>
> **계수는 가정값이다.** `backend/config.yaml` 에 `ASSUMED` 가 붙은 값은 모형을 만들고 실측하기 전의 가정값이다.

## 구조

| 폴더 | 내용 |
|---|---|
| `backend/` | FastAPI 서버. `app/core/` 순수 모델·예측·보정, `app/ports/` 입출력 포트, `app/adapters/` 구현(가상 센서·시계·JSONL 기록·재생), `app/api/` 라우터 |
| `frontend/` | 새 관제 웹. Next.js 정적 export(`out/`). 준비·명령·검증은 `frontend/README.md` |
| `docs/api-contract.md` | `/api/state` 와 제어 API 계약 |
| `firmware/` | 비어 있다 |

## 실행

Python 3.11 이 필요하다.

```bash
cd backend
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/api/state` 에서 상태를 볼 수 있다. 실험은 제어 API로 시작하고 바꾼다.

```bash
curl -X POST localhost:8000/api/experiment/start -H 'Content-Type: application/json' \
     -d '{"rain": "heavy", "blockage": {"type": "partial", "location": "INLET-02"}}'
curl -X POST localhost:8000/api/rain -H 'Content-Type: application/json' -d '{"mmPerHour": 75}'
curl -X POST localhost:8000/api/experiment/stop -H 'Content-Type: application/json' -d '{}'
```

회차는 `backend/logs/` 에 JSONL 로 기록된다(저장소에는 올라가지 않는다). 기록은 다시 재생할 수 있다.

```bash
curl localhost:8000/api/logs
curl -X POST localhost:8000/api/source -H 'Content-Type: application/json' \
     -d '{"mode": "replay", "logId": "EXP-20261027-001"}'
curl -X POST localhost:8000/api/source -H 'Content-Type: application/json' -d '{"mode": "sim"}'
```

재생은 기록된 관측과 조작을 다시 넣고 지금의 `config.yaml` 로 다시 계산한다. 기록 모양과 재생 규칙은 `docs/api-contract.md` 에 있다.

새 관제 웹은 Node 24 가 필요하다. 다른 터미널에서 띄운다. PATH 와 환경 변수는 `frontend/README.md` 를 본다.

```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

지금(S0)의 새 화면은 백엔드에 붙지 않고 가상 데이터를 보여 준다. 화면 위쪽에 "가상 데이터(서버 미연결)" 가 표시된다. FastAPI 한 대가 빌드된 `frontend/out/` 을 함께 내보내는 전시 구성은 S5 에서 확인한다.

## 검증

```bash
cd backend
pytest && ruff check .
```

백엔드 지시서 9장의 검증 항목은 번호대로 `backend/tests/test_checkNN_*.py` 에 있다. 12번 항목은 이 명령 자체다. "완료"는 이 테스트 결과로만 판정한다.

새 관제 웹은 다음 명령으로 검증한다. 프론트 지시서 9장의 항목별 위치는 `frontend/README.md` 의 "검증" 절에 있다.

```bash
cd frontend
npm run lint && npm run typecheck && npm test && npm run build
```

## 진행 상황

백엔드(검증 번호는 백엔드 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| M1 | 물수지 모델, 예측, 관측 보정 (검증 1·2·4·10·11) | 완료 |
| M2 | 가상 센서, 1 Hz tick, `/api/state`, 제어 API (검증 5) | 완료 |
| M3 | JSONL 실험 기록, 재생 (검증 3·7) | 완료 |
| M4 | `/api/ingest`, 장치 상태·입력 품질 (검증 6·9) | 예정 |
| M5 | 위험 단계, 시험용 알림 기록 (검증 8) | 예정 |

새 관제 웹(검증 번호는 프론트 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| S0 | 뼈대: 설정, zod 스키마, 파생 계산, 시계·설정 훅, mock 화면 (검증 1~9) | 완료 |
| S1 | 상태 배너, 구역 게이지, 수위 차트, 배지, 백엔드 연결 (검증 10) | 예정 |
| S2 | 도시 평면도, 알림 타임라인, 장치 상태, 이벤트 기록 | 예정 |
| S3 | `/ops` 제어·설정·확인 화면 | 예정 |
| S4 | `/logs` 실험 기록·재생 비교 | 예정 |
| S5 | 대비·글자 크기 점검, FastAPI 로 `out/` 서빙 | 예정 |
