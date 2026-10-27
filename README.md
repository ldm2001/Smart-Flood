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

## 진행 상황

백엔드(검증 번호는 백엔드 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| M1 | 물수지 모델, 예측, 관측 보정 (검증 1·2·4·10·11) | 완료 |
| M2 | 가상 센서, 1 Hz tick, `/api/state`, 제어 API (검증 5) | 완료 |
| M3 | JSONL 실험 기록, 재생 (검증 3·7) | 완료. 리뷰 2차 지적 수정은 예정 |
| M4 | `/api/ingest`, 장치 상태·입력 품질 (검증 6·9) | 예정 |
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

모형 설계서(REV 15 FINAL)와 코드를 2026-10-27 에 대조한 결과다. 단계가 끝날 때마다 고친다.

### 지금 되는 것

- 가상 센서(`sim`)로 실험을 돌리고 기록(JSONL)을 다시 재생(`replay`)한다. `live` 는 M4 전까지 501 을 돌려준다.
- 관제 웹 `/` 가 서버에 붙어 수위·예측·연결 상태를 보여 준다. 위험 단계는 서버 `alerts` 만 따르므로 M5 전에는 비어 있다.
- 설계서의 플로트 스위치, 비상 정지, 장치 이름 `esp32_1` 은 `/api/state` 의 `devices` 에 이미 자리가 있다.
- 펌프 ON/OFF 는 ESP32 의 릴레이(GPIO26)·버튼·플로트가 맡는다. 서버는 펌프 출력을 하지 않는다.
- 설계서의 치수는 `backend/config.yaml` 값만 바꾸면 된다: 구역 바닥 높이 `z_m`, 한계 수위 `threshold_mm`(설계 70·130·150), 바닥 면적 `model_area_m2`(설계 0.21), 센서 설치 높이와 범위.

### 할 것

| 순서 | 단계 | 내용 |
|---|---|---|
| 1 | 보드 시험 | 코드 작업과 병행. ESP32 와 부품을 하나씩 켜 보고 실측값(초음파 최소 거리, 설치 높이, 펌프 유량, 로드셀 보정값, 릴레이·플로트 레벨)을 적는다. 순서·배선·통과 기준은 `firmware/README.md` |
| 2 | 정리 | `frontend/src/lib/mock.ts`·`mock.test.ts` 에 남은 `legacy` 이름을 지운다 |
| 3 | M3 리뷰 2차 | 지적 1~7 을 테스트부터 쓰고 고친다: 쓰기 실패 시 되돌리기, 설치 높이보다 먼 거리는 수위 0, tick 기록 방식의 계약 설명, 시작 시각+경과 넘침, (600, 650] 구간 테스트, 빈 회차의 0바이트 파일. 8~11(포트 정리, 테스트 대역)은 M4 로 미룬다 |
| 4 | M4 | `POST /api/ingest`, `live` 입력원, 장치 상태·입력 품질(검증 6·9). 설계서 반영: 수위센서가 1개(E4)라 B 구역 입력 방식을 정한다. 로드셀은 급수통 무게 감소(유입량)라 `drain` 필드는 두고 새 필드를 더한다. 센서 실측 뒤 설치 높이·범위를 갱신한다. 수위 이동평균을 펌웨어와 서버 어디에 둘지 정한다 |
| 5 | M5 전 확인 | 경보 4단계 이름(설계 "대피", 화면 "침수(경보)"), 한계 수위 70·130·150, 도달 시간 규칙(설계는 선형 외삽, 코드는 모델 전진 계산), `/api/state` 에 한계 수위 추가. 지금 가정값 계수로는 어떤 강우·막힘도 한계의 10% 를 넘지 못하므로 실측 계수가 먼저다 |
| 6 | M5 | 위험 단계, 시험용 알림 기록(검증 8) |
| 7 | S2~S5 | 도시 평면도·알림 타임라인·장치 상태, `/ops`, `/logs`, 대비·글자 크기와 FastAPI 서빙 |
| 8 | M6 | 실제 SMS. `mode=sms`, 환경 변수, `armed` 세 조건이 모두 맞을 때만 허용 번호로 보낸다 |
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
