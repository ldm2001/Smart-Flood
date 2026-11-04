# SMART FLOOD

A·B·C 세 구역으로 나눈 도시 침수 모형 실험을 위한 백엔드와 관제 웹이다. 백엔드는 물수지 모델로 구역 수위를 계산하고 10·20·30초 뒤를 예측한다. 그 결과를 `/api/state` 로 내보낸다. 지금은 가상 센서(시뮬레이션)로 돌아간다. 나중에 ESP32 실센서가 같은 입력 경로로 붙는다.

> **시험용이다. 실제 재난 판단·재난문자에 쓸 수 없다.** 이 프로그램은 모형 실험과 시연을 위한 것이다. 서버는 펌프 제어 출력을 하지 않는다(`outputsLocked` 는 항상 `true`). 위험 알림은 기본으로 "SMS 예정" 기록만 남긴다. 시험 문자는 "시험 문자(M6)" 절의 세 조건이 모두 맞을 때만 허용 번호로 보낸다.
>
> **시뮬레이션 결과는 예측 성능의 근거로 쓰지 않는다.** 가상 센서는 운영 모델과 같은 식으로 참값을 만든다. 일부 계수만 15% 바꾸고 센서 잡음을 더할 뿐이다. 그래서 시뮬레이션에서 예측이 잘 맞아도, 실제 모형이나 실제 도시에서도 맞는다는 뜻은 아니다.
>
> **계수는 가정값이다.** `backend/config.yaml` 에 `ASSUMED` 가 붙은 값은 모형을 만들고 실측하기 전의 가정값이다.

## 구조

| 폴더 | 내용 |
|---|---|
| `backend/` | FastAPI 서버. `app/core/` 순수 모델·예측·보정, `app/ports/` 입출력 포트, `app/adapters/` 구현(가상 센서·시계·JSONL 기록·재생·SOLAPI 문자), `app/api/` 라우터, `scripts/sms.py` 수동 문자 스크립트 |
| `frontend/` | 새 관제 웹. Next.js 정적 export(`out/`). 준비·명령·검증은 `frontend/README.md` |
| `docs/api-contract.md` | `/api/state` 와 제어 API 계약 |
| `firmware/` | ESP32 펌웨어. 본 펌웨어(`board/`, Arduino)와 MicroPython 노드(`python/`)가 `/api/ingest` 로 보낸다. 부품 시험 스케치(`parts/`)와 통합 시험(`node/`)도 있다. 배선·순서·통과 기준·서버 연결과 Windows·macOS 보드 시험 따라하기는 `firmware/README.md` |

이 표는 `dev` 와 `main` 에서 본 모습이다. `sim` 에는 `backend/` 와 `frontend/` 만, `sensor` 에는 `firmware/` 만 있다. 자세한 것은 "브랜치" 절을 본다.

## 실행

Python 3.11 이 필요하다. 아래는 macOS 명령이다. Windows 명령과 보드를 붙일 때의 서버 띄우기(`--host 0.0.0.0`, 방화벽)는 `dev` 의 `firmware/README.md` "보드 시험 따라하기" 절에 있다.

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

`/` 화면은 `/api/state` 를 1초마다 읽는다. 서버가 한 번도 답하지 않으면 가상 데이터를 보여 주고 위쪽에 "가상 데이터(서버 미연결)" 를 단다. `/ops/` 화면에서는 회차·입력원·강우·막힘을 위 제어 API 로 바꾼다. `/logs/` 화면에서는 실험 기록을 골라 구역별 예측 도달과 실제 도달을 비교하고, "이 기록 재생" 으로 위 `POST /api/source` 재생을 시작한다.

전시 때는 서버 한 대로 띄운다. `frontend` 에서 `npm run build` 로 `frontend/out/` 을 만든 뒤 `backend` 에서 uvicorn 을 띄우면 FastAPI 가 `out/` 을 `StaticFiles` 로 함께 내보낸다. `http://localhost:8000/`, `/ops/`, `/logs/` 가 열리고(끝에 `/` 가 없는 `/ops`·`/logs` 는 307 로 `/ops/`·`/logs/` 로 간다), 화면과 API 가 같은 출처라 CORS 설정이 필요 없다.

```bash
cd frontend
npm run build
cd ../backend
uvicorn app.main:app --port 8000    # http://localhost:8000/
```

`sim` 과 `dev` 의 `frontend/`·`backend/` 는 같다(`dev` 는 여기에 `firmware/` 만 더한다). 두 브랜치의 화면이 다르게 보이면 코드보다 띄운 방식을 먼저 본다. `git log -1` 이 origin 과 같은지, 브랜치를 바꾸거나 받은 뒤 `npm run build` 를 다시 했는지(서버 한 대 방식은 마지막으로 만든 `out/` 을 내보낸다), `npm run dev` 라면 3000 번을 다른 프로그램이 쓰고 있지 않은지(`lsof -nP -iTCP:3000 -sTCP:LISTEN`)와 `frontend/.env.development.local` 이 있는지(없으면 서버 미연결 가상 데이터가 뜬다)를 본다. 입력원이 실측(`live`)이면 장치가 붙기 전까지 장치 오프라인과 입력 품질 경고가 보이는 것이 정상이다. 두 브랜치를 견줄 때는 위 서버 한 대 방식으로 띄운다.

## 시험 문자(M6)

기본은 `config.yaml` 의 `notifier.mode: stub` 이다. 위험 단계가 오르면 서버 로그에 "SMS 예정(mode stub)" 만 남기고 문자는 보내지 않는다. 실제 문자는 아래 세 조건이 모두 맞을 때만 허용 번호(`SMS_ALLOWED_TO`)로 보낸다.

| 조건 | 맞추는 곳 |
|---|---|
| 방식 | `backend/config.yaml` 의 `notifier.mode: sms` |
| 환경 변수 | `SOLAPI_API_KEY`·`SOLAPI_API_SECRET`·`SOLAPI_SENDER`·`SMS_ALLOWED_TO` |
| 무장 | `POST /api/notifier/arm` 에 `{"armed": true}` |

- 보내는 것은 단계가 경계(`warning`)나 침수(`evacuate`)로 오르는 전환뿐이고(`notifier.sms_stages`), (실험, 구역, 단계)마다 한 번이다. 한 실험에 10건이 상한이다(`max_sms_per_experiment`). 상한은 사건 수로 세고 `stub` 에도 걸린다. 재생 중에는 알림을 부르지 않는다.
- 시험 문자(`POST /api/notifier/test`, 본문은 없거나 `{}`)는 서버 실행당 3번까지 보낸다(`test_limit`). 답은 `to`·`body` 다.
- 무장은 재생 중이거나 `notifier.mode` 가 `sms` 가 아니거나 환경 변수가 없으면 409 로 거절된다. 시험 문자는 재생 중이거나 무장하지 않았거나 이미 3번 보냈으면 409, 보내지 못하면 502 다.
- 서버를 다시 띄우면 무장이 풀린다. 다시 무장해야 보낸다.
- 결과는 서버 로그에 WARNING 한 줄로만 남는다("SMS 예정(…)"·"SMS 보냄"·"SMS 차단"·"SMS 실패"·"SMS 상한"·"SMS 보냄(시험)"·"SMS 실패(시험)"). 번호는 뒤 4자리만 보인다. 실험 기록 JSONL 에는 넣지 않는다.
- 키와 번호는 `backend/.env` 에만 둔다. 코드·`config.yaml`·로그·커밋에 넣지 않는다.

macOS 에서는 이렇게 한다. `backend/.env.example` 을 `backend/.env` 로 복사해 값을 채우고(커밋하지 않는다), `config.yaml` 의 `notifier.mode` 를 `sms` 로 바꾼 뒤 환경 변수를 읽고 서버를 띄운다.

```bash
cd backend
cp .env.example .env    # 값을 채운다
set -a && . ./.env && set +a
uvicorn app.main:app --port 8000
```

다른 터미널에서 무장하고 시험 문자를 보낸다. 끝나면 무장을 푼다.

```bash
curl -X POST localhost:8000/api/notifier/arm -H 'Content-Type: application/json' -d '{"armed": true}'
curl -X POST localhost:8000/api/notifier/test -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8000/api/notifier/arm -H 'Content-Type: application/json' -d '{"armed": false}'
```

Windows PowerShell 에서는 `.env` 의 줄을 환경 변수로 넣고 띄운다. 무장과 시험 문자는 다른 PowerShell 창에서 `Invoke-RestMethod` 로 보낸다. PowerShell 명령은 돌려 보지 않았다.

```powershell
cd backend
Copy-Item .env.example .env    # 값을 채운다
Get-Content .env | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v }
uvicorn app.main:app --port 8000
```

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/notifier/arm -ContentType 'application/json' -Body '{"armed": true}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/notifier/test -ContentType 'application/json' -Body '{}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/notifier/arm -ContentType 'application/json' -Body '{"armed": false}'
```

서버 없이 한 건만 손으로 보내 볼 때는 `backend/scripts/sms.py` 를 쓴다. 기본은 보낼 글과 가린 번호만 보여 준다. `--send` 를 붙이고 `notifier.mode` 가 `sms` 일 때만 첫 허용 번호로 한 건 보낸다. 서버의 시험 문자 횟수에는 세지 않는다. 사용법은 `--help` 로 본다.

```bash
cd backend
set -a && . ./.env && set +a
python3 scripts/sms.py           # 보낼 글만 보여 준다
python3 scripts/sms.py --send    # 한 건 보낸다
```

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

`sim` 과 `sensor` 에서 각자 작업하고 `dev` 로 합친다(풀리퀘스트의 대상도 `dev` 다). `dev` 에서 위 "검증" 의 두 명령이 모두 통과해야 `main` 으로 올린다. 서버로 보내는 펌웨어(`firmware/board/`·`firmware/python/`)가 있으므로 `dev` 를 위 "실행" 대로 띄우고 보드를 붙인 시험도 거친다. `main` 은 시험을 마친 `dev` 를 그대로 받고, `main` 과 `dev` 에서는 직접 고치지 않는다.

합치는 방향은 `sim`·`sensor` 에서 `dev` 로, `dev` 에서 `main` 으로 한쪽뿐이다. `sim` 과 `sensor` 가 `dev` 나 `main` 을 받으면 상대 공간의 폴더가 딸려 들어오므로 받지 않는다. 풀리퀘스트의 "Update branch" 버튼도 같은 일을 하니 누르지 않는다. `main` 으로 합칠 때는 "Create a merge commit" 을 쓴다. 그래야 `dev` 가 `git merge --ff-only origin/main` 으로 그대로 따라간다.

## 진행 상황

백엔드(검증 번호는 백엔드 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| M1 | 물수지 모델, 예측, 관측 보정 (검증 1·2·4·10·11) | 완료 |
| M2 | 가상 센서, 1 Hz tick, `/api/state`, 제어 API (검증 5) | 완료 |
| M3 | JSONL 실험 기록, 재생 (검증 3·7) | 완료. 리뷰 2차 지적 수정은 예정 |
| M4 | `/api/ingest`, 장치 상태·입력 품질 (검증 6·9) | 완료. 설계 수치(REV16) 반영과 리뷰 이관분은 예정 |
| M5 | 위험 단계, 시험용 알림 기록 (검증 8) | 완료. 실측 계수 반영 뒤 재확인과 리뷰 이관분은 예정 |
| M6 | 실제 SMS 발송. 시험용 조건이 모두 맞을 때만 | 완료(시험은 네트워크 없이). 실제 계정으로 보내 보기와 리뷰 이관분은 예정 |

새 관제 웹(검증 번호는 프론트 지시서 9장):

| 단계 | 내용 | 상태 |
|---|---|---|
| S0 | 뼈대: 설정, zod 스키마, 파생 계산, 시계·설정 훅, mock 화면 (검증 1~9) | 완료 |
| S1 | 상태 배너, 구역 게이지, 수위 차트, 배지, 백엔드 연결 (검증 10) | 완료 |
| S2 | 도시 평면도, 알림 타임라인, 장치 상태, 이벤트 기록 | 완료 |
| S3 | `/ops` 제어·설정·확인 화면 | 완료 |
| S4 | `/logs` 실험 기록·재생 비교 | 완료 |
| S5 | 대비·글자 크기 점검, FastAPI 로 `out/` 서빙 | 완료 |

## 다음 작업

모형 설계서(REV16)와 코드를 2026-10-28 에 대조한 결과다. 단계가 끝날 때마다 고친다(마지막 2026-11-04, 조립서 대조와 브랜치별 화면 확인).

### 지금 되는 것

- 가상 센서(`sim`)로 실험을 돌리고 기록(JSONL)을 다시 재생(`replay`)한다. 실장치(`live`)는 `POST /api/ingest` 로 받은 메시지를 tick 마다 넣고, 장치 상태(마지막 수신 뒤 5초, 대기 중에도 읽을 때마다 판정)와 입력 품질(3초·10초)을 가른다. REV16 메시지(A 센서 하나, B·로드셀 `absent`)를 그대로 받는다.
- 실험 기록은 한 tick 의 줄을 한 번에 쓴다. 쓰다 끊기면 그 tick 의 줄은 하나도 남지 않고, 빈 회차 파일도 남지 않는다. 설치 높이보다 먼 거리(바닥 아래)는 수위 0 으로 본다.
- 위험 단계를 tick 마다 판정한다. 보정된 모델 수위와 관측 보정 전의 모델 변화율(보정이 수위를 옮긴 순간의 흐름은 넣지 않는다)로 한계 수위(`/api/state` 의 `zones.*.thresholdMm`, REV16 `z` 40·70·110 mm)까지의 도달 초를 구해 60초 안이면 주의, 30초 안이면 경계, 한계 이상이면 침수다. 응답과 기록의 도달 초(`etaSec`)는 올림한 정수 초다. 오름은 바로, 내림은 10초 유지 뒤에 반영하고 침수는 한계의 90% 아래로 내려가야 풀린다(모두 ASSUMED). 단계가 바뀌면 기록에 `stage` 이벤트를 남기고 알림 포트로 보낸다. 기본 알림은 서버 로그에 WARNING 으로만 남긴다(실제 문자는 "시험 문자(M6)" 절의 세 조건이 맞을 때만). 알림이 실패해도 회차는 이어 가고, 서버 로그에는 예외 종류만 남긴다. 규칙은 `docs/api-contract.md` 의 `alerts`.
- 관제 웹 `/` 가 서버에 붙어 수위·예측·연결 상태를 보여 준다. 위험 단계는 서버 `alerts` 만 따른다.
- 관제 웹에 S2 의 네 칸이 붙었다. 도시 모형 평면도(구역 물 높이, 빗물받이 막힘, 하부 배수 계량), 현장 장치 상태(장치 넷, 입력 품질, 출력 잠금 표시), 구역별 위험 판단 타임라인(위험 판단, 문자 요청, 실제 도달, 선행 시간), 이벤트 기록이다. 타임라인과 기록은 서버 기록의 `stage` 사건(`/api/logs/{id}/events`)만 보여 주고, 재생 중에는 지금 경과 초까지의 사건만 보인다. 문자 요청 줄은 무장한 `sms` 이면 "실제 발송 켜짐, 허용 번호만", 지난 기록 화면(`/logs/`)과 재생 중인 종합 관제에서는 "발송 결과는 서버 로그에만 남음", 그 밖에는 "기록만, 실제 발송 차단" 이다.
- 관제 웹 화면을 다듬었다(2026-11-02). 색은 위험 단계와 연결·막힘·장치 같은 상태를 알릴 때만 쓰고, 구역 색(A·B·C)은 수위 차트에만 남겼다. 아이콘은 글자 기호 대신 18 px·선 1.5 의 인라인 SVG 한 벌(`Glyph`)로 바꾸고 메뉴의 아이콘은 뺐다. 글자는 16 px 이상, 굵기는 400·500(쪽 제목과 로고 600)이고 시각·실험 번호·눈금 숫자는 고정폭이다. 계약과 서버 규칙, 화면의 칸 구성은 그대로다.
- 관제 웹에 S3 의 운영·설정 화면(`/ops/`)이 붙었다(2026-11-03). 회차("시작"·"종료"·"초기화"), 입력원("시뮬레이션으로 바꾸기"·"실측으로 바꾸기"), 강우(단계 단추 셋과 직접 입력 mm/h), 막힘(종류와 빗물받이)을 제어 API 로 바꾼다. 구역 한계 수위는 서버 값을 읽기만 하고, 가상 데이터용 값만 이 브라우저에 저장한다("기본값으로 되돌리기" 는 45·55·65 mm). "종료"·"초기화"·입력원 전환·"재생 멈춤" 은 칸 안의 확인 줄("예"·"취소")을 거치고, 브라우저 기본 대화상자는 쓰지 않는다. 연결 중·연결 끊김·가상 데이터이면 제어를 모두 끄고 위쪽에 이유를 적으며, 재생 중에는 "재생 멈춤" 과 "시뮬레이션으로 돌아가기" 만 켠다. 보내는 동안에는 켜져 있던 제어를 끄고, 결과 줄에 반영·거절·실패·응답 없음을 적는다. 수위 이력은 메뉴를 옮겨도 남고, 메뉴를 옮길 때 연결 배지가 "연결 끊김" 으로 깜박이지 않는다. 실제 브라우저에서 임시 서버에 붙여 확인했다.
- 관제 웹에 S4 의 기록·재생 화면(`/logs/`)이 붙었다(2026-11-03). 실험 기록 목록에서 기록을 고르면(`?id=`) 실험 번호·시작 시각·입력원·모델 버전, 구역별 비교 표("위험 판단"·"예측 도달"·"실제 도달"·"선행 시간"·"오차"), 그 기록의 사건 타임라인을 보여 준다. 예측 도달은 위험 판단 사건 시각에 그 사건의 `etaSec` 를 더한 시각이고, 오차는 실제 도달에서 예측 도달을 뺀 값이다. 모두 서버 기록(`/api/logs`, `/api/logs/{id}/events`)에서 계산하고 화면이 사건을 만들지 않는다. "이 기록 재생" 은 칸 안의 확인 줄("이 기록을 처음부터 재생할까요? 멈춘 회차의 마지막 화면은 재생 화면으로 바뀝니다")을 거쳐 `POST /api/source` 에 `{"mode": "replay", "logId": …}` 를 보내고, 반영되면 결과 줄에 "종합 관제에서 보기" 링크가 붙는다.
- S5 로 전시 구성을 마쳤다(2026-11-03). `npm run build` 뒤 uvicorn 한 대로 `/`·`/ops/`·`/logs/` 와 API 가 같은 출처에서 열린다("실행" 절). 대비·글자 크기 시험(`frontend/tests/contrast.test.ts`)을 더했다.
- M6 로 시험 문자 발송을 붙였다(2026-11-03). 기본은 여전히 기록만 남기고, "시험 문자(M6)" 절의 세 조건이 모두 맞을 때만 허용 번호로 보낸다. 발송은 tick 밖에서 따로 도는 스레드가 하고(응답 제한 5초, 재시도 없음), 실패하면 서버 로그에 예외 종류만 남긴다. `/api/state` 에 `notifier` 필드를 더했다(계약은 `docs/api-contract.md`). 발송 경로는 가짜 발송기와 바깥 연결을 막은 시험으로만 확인했고, 실제 SOLAPI 계정으로는 아직 보내 보지 않았다.
- 시뮬레이션 시험은 세 가지로 한다(2026-11-02 확인). 가상 센서(`sim`)는 실험·예측·기록·재생을 끝까지 돌리지만, 지금의 가정 계수로 시험한 조건에서는 위험 단계가 오르지 않았다. 강우 90·150 mm/h(150 은 입력 상한)에 막힘 없음과 빗물받이 하나 완전 막힘(①·②·③)을 900초씩 돌린 8회 모두 경보가 0건이었고, 최고 수위는 한계의 10.6%(B, 150 mm/h, ③ 막힘, 7.43 mm)였다. 단계 변화는 입력을 `live` 로 바꾸고 `POST /api/ingest` 에 `esp32_1` 메시지를 1초마다 보내며 A 거리를 줄이면 본다. 170초를 보낸 시험에서 63초에 A 침수, 84초에 B 경계, 153초에 B 침수가 났고 사건 8건이 기록·타임라인·이벤트 기록에 나왔다. 서버 없이 웹만 띄우면 180초 주기의 가상 데이터로 네 단계를 모두 보여 준다.
- 설계서의 플로트 스위치, 비상 정지, 장치 이름 `esp32_1` 은 `/api/state` 의 `devices` 에 이미 자리가 있다.
- 펌프 ON/OFF 는 ESP32 의 릴레이(GPIO26)·버튼·플로트가 맡는다. 서버는 펌프 출력을 하지 않는다.
- 설계서의 치수는 `backend/config.yaml` 에 넣었다: 한계 수위 `threshold_mm` 40·70·110, 바닥 면적 `model_area_m2` 0.17(REV16 1700 cm²), 저류 면적 `S_m2` 0.035·0.035·0.028. 월류 과도가 빨라져 적분 간격 `dt_s` 는 0.02 로 줄였다(1 mm 수렴 검사 기준). 모두 ASSUMED 표시를 유지한다. 구역 바닥 높이 `z_m`, 센서 설치 높이와 범위, 개구 면적·계수는 실측 뒤 바꾼다.

### 할 것

| 순서 | 단계 | 내용 |
|---|---|---|
| 1 | 보드 시험 | 코드 작업과 병행. ESP32 와 부품을 하나씩 켜 보고 실측값(0 mm 에서의 전압과 흔들림, 설치 높이, 펌프 유량, 릴레이·플로트 레벨)을 적는다. 센서 코드는 `sensor` 브랜치에 두 가지다: `firmware/python/`(MicroPython, 수위 측정과 서버 전송 1단계, 맥에서 pytest 와 실행기로 확인)과 `firmware/board/`(Arduino, 펌프 제어·예측 포함, 맥에서 Arduino API 대역으로 확인). 둘 다 와이파이가 끊기면 10초마다 다시 붙고, 연결 상태와 전송 실패를 시리얼에 찍는다(보드는 전송 성공의 HTTP 코드도 찍는다). 둘 다 아직 보드에서 돌려 보지 않았다. 순서·배선·통과 기준·보드에 올리는 법·서버 연결 확인과 Windows·macOS 따라하기는 `dev` 의 `firmware/README.md`("보드 시험 따라하기" 절). 2026-11-04 에 조립서(22쪽)와 대조했다. 핀·플래그·조립서에 나오는 관제 화면 문구(펌프 수동 ON·수위센서 이상 등)·공기 중 480 mV 는 이미 같았고, `board/secrets.h.example` 의 `AP_PASS` 를 조립서 기본값으로 두어 견본을 `secrets.h` 로 복사만 하면 SMART_FLOOD 와이파이와 관제 화면이 열린다. 보드 관제 화면의 구역·단계·한계 수위 이름은 관제 웹과 맞췄다(유량 mL/s 는 그대로). 조립 뒤 첫 실행은 같은 파일의 "조립서대로 연결한 뒤" 절 |
| 2 | M4 마무리 | 센서 계수(KIT0139 실측 뒤). REV16 한계 수위·바닥 면적은 M5 에서 넣었다. 지금 계수로는 실측 수위가 70 mm 근처를 넘으면 모델 변화율이 ±20 mm/s 에서 포화해 보인다. `/api/ingest` 의 `bootId`·`seq` 되감김 처리. 리뷰 이관분: 포트 `entry`/`batch` 정리, `/api/logs` ndjson 의 `Flaw` 처리, 테스트 대역 정리(`Clip`·`Jam`·`Quota`), 되돌리기 실패 시 원래 오류 보존, 센서 기하 검증(최소 범위 ≤ 설치 높이 − 영점 ≤ 최대 범위, 배율 > 0), 불필요해진 `flush`·`max` 제거. 10-29 리뷰 이관분: `/api/ingest` 상태값(ok·absent·fault) 엄격 검사, `review()` 의 `devices` 설정 검사, 변화율이 NaN 이면 명시적 실패, 메시지 도착 시각 보관(따라잡기 때 한 tick 에 몰리지 않게), 장치 판정의 시각 기준 통일(응답과 state 줄), obs.raw 원본 보존, `Live` 의 포트 Protocol, 테스트 helpers 정리, 두 장치일 때 absent 합집합. 11-02 확인분: 맥이 잠들면 `time.monotonic` 이 멈춰 상태 시각이 실제 시각보다 늦어지고, 화면은 새 실험을 시작할 때까지 "예측 만료" 를 띄운다 |
| 3 | M5 전 확인 | 2026-10-30 에 정했다. 단계 이름은 계약 `caution`·`warning`·`evacuate`, 화면 이름은 주의·경계·침수(정상은 목록에 안 담음). REV16 `z` 40·70·110 mm 는 구역별 한계(`zones.*.threshold_mm`)이고 모델 수위와 비교한다. 도달 시간은 서버가 모델 변화율로 계산하고(보드의 20초 회귀는 보드에 남김), 60·30초 상한과 10초 유지·90% 해제는 ASSUMED. `/api/state` 에 `zones.*.thresholdMm` 를 더했다. 강우 상한 150 과 프리셋 30·60·90 은 그대로 |
| 4 | M5 | 끝(10-31 리뷰 수정 반영). 위험 단계 판정, `stage` 이벤트, 기본 알림(기록만). 남은 것: 기본 설정에서는 가정값 개구(3 cm², Cd 0.6)가 150 mm/h 강우보다 훨씬 커 A 는 고이지 않고 B·C 도 한계에 닿지 않아, 경보 시험은 시험용 설정(배수 0, B 한계 6 mm)으로만 한다. 실측 계수를 넣은 뒤 기본 설정으로 다시 확인한다. 관측 보정으로 수위가 뛰면 주의 없이 바로 침수가 될 수 있다(보드의 20초 회귀가 보완). 10-31 리뷰 이관분: 경보 설정의 숫자형 검사(`true` 가 1 mm 로 통과, 문자열은 TypeError), `STAGE_LABELS` 와 `STAGES` 의 한곳 관리, 검증 8 의 `answer()` 중복 정리, 계약 시험의 `thresholdMm` ≤ 0 위반 사례 추가, `dt_s` 0.02 로 늘어난 tick 계산 시간 확인(리뷰 추정 약 2.2 ms 에서 10.4 ms) |
| 5 | S4~S5 | 끝. mock 판정(예측 수위로 10초 안 경계, 30초 안 주의)은 서버 규칙(변화율로 30초 안 경계, 60초 안 주의)과 달라도 그대로 두고(S2 D3), 한계 수위는 `/api/config` 에서 계속 읽는다(S2 D4). 11-01 S2 리뷰 이관분: 사건 읽기 키가 예전 값으로 돌아올 때 늦게 온 응답이 목록을 덮는 경우, 두 폴링 사이에 단계가 바뀌었다 돌아오면 사건을 다시 읽지 않는 것, 사건 읽기가 실패하면 숨은 탭에서도 1초마다 끝없이 다시 읽는 것과 예전 키의 오류가 남는 것, 재생 중 단계가 바뀔 때마다 사건 전체를 다시 읽는 것, `milestones` 주석과 `lead` 시험 이름이 코드와 어긋난 것, `at()` 의 초·밀리초 왕복과 시험 속 복사본, 장치 안내 글에 적어 둔 5초(`offline_after_s`), mock 단계 이름표 중복. 보고만 한 것: 사건 응답을 통째로 검사해 한 줄만 어긋나도 목록 전체가 오류 줄이 되는 것(S2 판정 45·52, 기록 목록 `/api/logs` 도 같다), 계산 오류로 멈춘 회차를 재생하면 그 사건이 끝까지 안 보이는 것(R17, 판정 32), 기록 꼴이 아닌 실험 번호면 사건을 읽지 않는 것(판정 48), 문자 요청 시각을 첫 경계 이상 사건으로 보는 것(R9, M6 의 발송 단계 `warning`·`evacuate` 와 같아 그대로 둔다), mock 이 단계 사건을 프론트에서 만드는 설계 예외. 11-02 화면 정리 이관분: 차트에 올리면 값을 보여 주는 층, 차트 값의 표 보기, 청황 색각에서 C·A 선의 색 차이가 작은 것(ΔE 5.9), 연결 표시 시각의 고정폭, 외딴 점 크기, 선행 시간의 줄표가 큰 글자라 다른 줄표와 어긋나는 것. 11-03 화면 이관분: 390px 화면에서 `/ops/` 아래쪽 칸의 단추를 누르면 결과 줄이 화면 밖에 있는 것, 390px 에서 막힘 "적용" 단추가 줄을 바꾸는 것 |
| 6 | M6 | 끝. 실제 SOLAPI 계정으로 시험 문자 한 건을 보내 받은 글을 확인한다. 계정 한도(하루 50건, 잔액 소액)가 있어 실험당 10건 상한과 시험 문자 3번 상한을 그대로 둔다. M5 리뷰 이관분 가운데 알림 호출의 시간 제한(발송을 따로 도는 스레드로 옮김), SMS 어댑터 자체 오류 기록(키·번호 제외), 알림 포트 주석의 예외 허용 명시는 M6 에서 했다. 남은 것은 초기화·새 시작 때 걸려 있던 단계의 해제 사건·알림 처리다. 발송 결과(보냄·실패)는 서버 로그에만 남고 실험 기록에는 없다 |
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
