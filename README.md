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
| `firmware/` | ESP32 부품 시험 스케치(`parts/`)와 통합 시험(`node/`). 배선·순서·통과 기준은 `firmware/README.md`. 서버로 보내는 펌웨어는 M4 |

이 표는 `dev` 와 `main` 에서 본 모습이다. `sim` 에는 `backend/` 와 `frontend/` 만, `sensor` 에는 `firmware/` 만 있다. 자세한 것은 "브랜치" 절을 본다.

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

`/` 화면은 `/api/state` 를 1초마다 읽는다. 서버가 한 번도 답하지 않으면 가상 데이터를 보여 주고 위쪽에 "가상 데이터(서버 미연결)" 를 단다. FastAPI 한 대가 빌드된 `frontend/out/` 을 함께 내보내는 전시 구성은 S5 에서 확인한다.

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

## 브랜치

| 브랜치 | 담는 폴더 | 하는 일 |
|---|---|---|
| `main` | `backend/`, `frontend/`, `firmware/` | 시연과 제출에 쓰는 안정판 |
| `dev` | `backend/`, `frontend/`, `firmware/` | 통합 시험. `sim` 과 `sensor` 를 합쳐 시험한다 |
| `sim` | `backend/`, `frontend/` 만 | 백엔드 시뮬레이션과 관제 웹 |
| `sensor` | `firmware/` 만 | ESP32 와 센서 시험 |

시뮬레이션 공간과 센서 시험 공간은 따로 둔다. `sim` 에는 펌웨어가 없고 `sensor` 에는 백엔드와 웹이 없다.

`sim` 과 `sensor` 에서 각자 작업하고 `dev` 로 합친다(풀리퀘스트의 대상도 `dev` 다). `dev` 에서 위 "검증" 의 두 명령이 모두 통과해야 `main` 으로 올린다. 서버로 보내는 펌웨어가 생기면(M4) `dev` 를 위 "실행" 대로 띄우고 보드를 붙인 시험도 거친다. `main` 은 시험을 마친 `dev` 를 그대로 받고, `main` 과 `dev` 에서는 직접 고치지 않는다.

합치는 방향은 `sim`·`sensor` 에서 `dev` 로, `dev` 에서 `main` 으로 한쪽뿐이다. `sim` 과 `sensor` 가 `dev` 나 `main` 을 받으면 상대 공간의 폴더가 딸려 들어오므로 받지 않는다. 풀리퀘스트의 "Update branch" 버튼도 같은 일을 하니 누르지 않는다. `main` 으로 합칠 때는 "Create a merge commit" 을 쓴다. 그래야 `dev` 가 `git merge --ff-only origin/main` 으로 그대로 따라간다.

## 진행 상황

백엔드(검증 번호는 백엔드 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| M1 | 물수지 모델, 예측, 관측 보정 (검증 1·2·4·10·11) | 완료 |
| M2 | 가상 센서, 1 Hz tick, `/api/state`, 제어 API (검증 5) | 완료 |
| M3 | JSONL 실험 기록, 재생 (검증 3·7) | 완료. 리뷰 2차 지적 수정은 예정 |
| M4 | `/api/ingest`, 장치 상태·입력 품질 (검증 6·9) | 완료. 설계 수치(REV16) 반영과 리뷰 이관분은 예정 |
| M5 | 위험 단계, 시험용 알림 기록 (검증 8) | 예정 |
| M6 | 실제 SMS 발송. 시험용 조건이 모두 맞을 때만 | 예정 |

새 관제 웹(검증 번호는 프론트 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| S0 | 뼈대: 설정, zod 스키마, 파생 계산, 시계·설정 훅, mock 화면 (검증 1~9) | 완료 |
| S1 | 상태 배너, 구역 게이지, 수위 차트, 배지, 백엔드 연결 (검증 10) | 완료 |
| S2 | 도시 평면도, 알림 타임라인, 장치 상태, 이벤트 기록 | 예정 |
| S3 | `/ops` 제어·설정·확인 화면 | 예정 |
| S4 | `/logs` 실험 기록·재생 비교 | 예정 |
| S5 | 대비·글자 크기 점검, FastAPI 로 `out/` 서빙 | 예정 |

## 다음 작업

모형 설계서(REV16)와 코드를 2026-10-28 에 대조한 결과다. 단계가 끝날 때마다 고친다.

### 지금 되는 것

- 가상 센서(`sim`)로 실험을 돌리고 기록(JSONL)을 다시 재생(`replay`)한다. 실장치(`live`)는 `POST /api/ingest` 로 받은 메시지를 tick 마다 넣고, 장치 상태(마지막 수신 뒤 5초, 대기 중에도 읽을 때마다 판정)와 입력 품질(3초·10초)을 가른다. REV16 메시지(A 센서 하나, B·로드셀 `absent`)를 그대로 받는다.
- 실험 기록은 한 tick 의 줄을 한 번에 쓴다. 쓰다 끊기면 그 tick 의 줄은 하나도 남지 않고, 빈 회차 파일도 남지 않는다. 설치 높이보다 먼 거리(바닥 아래)는 수위 0 으로 본다.
- 관제 웹 `/` 가 서버에 붙어 수위·예측·연결 상태를 보여 준다. 위험 단계는 서버 `alerts` 만 따르므로 M5 전에는 비어 있다.
- 설계서의 플로트 스위치, 비상 정지, 장치 이름 `esp32_1` 은 `/api/state` 의 `devices` 에 이미 자리가 있다.
- 펌프 ON/OFF 는 ESP32 의 릴레이(GPIO26)·버튼·플로트가 맡는다. 서버는 펌프 출력을 하지 않는다.
- 설계서의 치수는 `backend/config.yaml` 값만 바꾸면 된다: 구역 바닥 높이 `z_m`, 한계 수위 `threshold_mm`(REV16 `z` 40·70·110), 바닥 면적 `model_area_m2`(REV16 1700 cm² = 0.17), 센서 설치 높이와 범위. 단위 시험이 지금 값(45·55·65, 0.48)을 글자로 들고 있어 함께 바꾼다.

### 할 것

| 순서 | 단계 | 내용 |
|---|---|---|
| 1 | 보드 시험 | 코드 작업과 병행. ESP32 와 부품을 하나씩 켜 보고 실측값(초음파 최소 거리, 설치 높이, 펌프 유량, 로드셀 보정값, 릴레이·플로트 레벨)을 적는다. 순서·배선·통과 기준은 `sensor` 브랜치의 `firmware/README.md` |
| 2 | M4 마무리 | REV16 수치 반영: 한계 수위 40·70·110 mm, 바닥 면적 0.17 m², 센서 계수(KIT0139 실측 뒤). 지금 계수로는 실측 수위가 70 mm 근처를 넘으면 모델 변화율이 ±20 mm/s 에서 포화해 보인다. `/api/ingest` 의 `bootId`·`seq` 되감김 처리. 리뷰 이관분: 포트 `entry`/`batch` 정리, `/api/logs` ndjson 의 `Flaw` 처리, 테스트 대역 정리(`Clip`·`Jam`·`Quota`), 되돌리기 실패 시 원래 오류 보존, 센서 기하 검증(최소 범위 ≤ 설치 높이 − 영점 ≤ 최대 범위, 배율 > 0), 불필요해진 `flush`·`max` 제거. 10-29 리뷰 이관분: `/api/ingest` 상태값(ok·absent·fault) 엄격 검사, `review()` 의 `devices` 설정 검사, 변화율이 NaN 이면 명시적 실패, 메시지 도착 시각 보관(따라잡기 때 한 tick 에 몰리지 않게), 장치 판정의 시각 기준 통일(응답과 state 줄), obs.raw 원본 보존, `Live` 의 포트 Protocol, 테스트 helpers 정리, 두 장치일 때 absent 합집합 |
| 3 | M5 전 확인 | 경보 4단계 이름(설계 정상·주의·경계·침수, 계약 `caution`·`warning`·`evacuate`), 설계 `z` 40·70·110 mm 가 구역별 한계인지 단계별 한계인지, 도달 시간 규칙(설계는 최근 20초 선형 회귀로 60초 안이면 주의·30초 안이면 경계, 코드는 모델 전진 계산), `/api/state` 에 한계 수위 추가. 지금 가정값 계수로는 어떤 강우·막힘도 한계의 10% 를 넘지 못하므로 실측 계수가 먼저다 |
| 4 | M5 | 위험 단계, 시험용 알림 기록(검증 8) |
| 5 | S2~S5 | 도시 평면도·알림 타임라인·장치 상태, `/ops`, `/logs`, 대비·글자 크기와 FastAPI 서빙 |
| 6 | M6 | 실제 SMS. `mode=sms`, 환경 변수, `armed` 세 조건이 모두 맞을 때만 허용 번호로 보낸다 |
| - | 결정 | `docs/api-contract.md` 를 저장소에 다시 넣을지. 없으면 새로 받은 곳에서 프론트 테스트 2개가 실패한다 |

### 모형 쪽에서 먼저 정할 것

코드로 풀 수 없어서 설계서를 고쳐야 하는 항목이다.

| 항목 | 설계서 | 문제 | 안 |
|---|---|---|---|
| 급수통 용량 | 95×55×60 mm, 0.31 L | 어항 바닥이 0.21 ㎡ 라 10 mm 올리는 데 2.1 L, 경로 A(Z 70)까지 14.7 L | 급수통을 키우거나 어항을 미리 채우고 마지막 수십 mm 만 펌프로 올린다. 로드셀 정격도 급수통 무게에 맞춘다 |
| 수위센서 위치 | 헤드 Z 140, 우측 벽 | 초음파 최소 거리가 200 mm(`min_range_mm`)라 수면이 Z 0~150 이면 못 잰다 | 테두리 위 브래킷(Z 400 이상)에 달고 실측한다 |
| 펌프 유량 | 12 V 수중펌프 연속 가동 | 보통 2~5 L/min 이라 570~1430 mm/h 에 해당한다. 강우 프리셋은 30·60·90, 최대 150 mm/h 다 | 유량을 실측(설계서 13-④)하고 릴레이 듀티로 맞춘다. 150 mm/h 면 약 13% 다 |
| 대피경로 표시 | 통합 시험 08 | 계약과 화면에 없다 | 넣을지 정한다. 넣으면 계약 추가와 화면 설계 변경이 따른다 |
| 웹 펌프 제어 | 핀맵 "웹 제어만 쓸 경우 버튼 생략" | 서버는 펌프 출력을 하지 않는다 | 버튼(GPIO25)을 남기고 ESP32 에서만 제어한다 |
