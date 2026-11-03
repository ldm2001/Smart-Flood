# SMART FLOOD 관제 웹

백엔드 `/api/state` 를 읽어 A·B·C 구역의 수위, 10·20·30초 예측, 알림 이력을 보여 주는 관제 화면이다. `/ops/` 에서는 제어 API 로 회차·입력원·강우·막힘을 바꾸고, `/logs/` 에서는 실험 기록을 골라 예측과 실제 도달을 비교하고 재생을 시작한다. Next.js(App Router)로 만들고 `next build` 로 정적 파일(`out/`)을 내보낸다. 서버 기능은 쓰지 않는다. 전시 때는 FastAPI 한 대가 `out/` 과 API 를 함께 서빙한다(백엔드는 `frontend/out/` 이 있으면 `/` 에 붙인다).

> **시험용이다. 실제 재난 판단·재난문자에 쓸 수 없다.** 이 화면은 펌프를 제어하거나 문자를 보내지 않는다. `outputsLocked` 는 값을 표시만 한다. 모든 화면 아래에 같은 고지가 붙는다.

## 준비

Node 24 LTS 가 필요하다(`package.json` 의 `engines`: `^24 || >=26`). Homebrew 로 설치한 `node@24` 는 keg-only 라서 PATH 에 직접 넣는다.

```bash
export PATH="/opt/homebrew/opt/node@24/bin:$PATH"
node -v    # v24.x
```

매번 넣기 번거로우면 기본 `node` 를 바꾼다: `brew unlink node && brew link --force node@24`. 되돌릴 때는 `brew unlink node@24 && brew link node`.

Next.js 는 익명 사용 통계를 보낸다. `npx next telemetry disable` 을 한 번 실행해 끄거나, 명령마다 `NEXT_TELEMETRY_DISABLED=1` 을 붙인다.

## 명령

```bash
cd frontend
npm install
npm run dev         # 개발 서버 http://localhost:3000 (이 컴퓨터에서만 열린다)
npm run lint        # eslint .
npm run typecheck   # tsc --noEmit
npm test            # vitest run
npm run build       # out/ 생성. 이어서 postbuild 가 out/ 을 검사한다
npm run check:state # 백엔드(8000)를 띄운 뒤, 실제 /api/state 응답을 zod 계약으로 검사한다
```

끝내기 전에 `npm run lint && npm run typecheck && npm test && npm run build` 를 모두 통과시킨다. 백엔드를 띄울 수 있으면 `npm run check:state` 도 돌린다.

개발 서버는 3000 번에서 띄운다. 백엔드 CORS 가 Next 개발 서버용으로 허용한 출처가 `http://localhost:3000` 이다(`backend/config.yaml` 의 `server.cors_origins`). 다른 프로그램(예: Docker 컨테이너)이 3000 번을 쓰고 있으면 그 프로그램을 먼저 끈다.

개발 서버는 `--hostname localhost` 로 띄워 이 컴퓨터에서만 열린다. 같은 네트워크의 다른 기기는 붙지 못한다. `127.0.0.1` 로 바꾸지 않는다. Next 는 `--hostname` 값을 그대로 화면 주소로 쓰므로 출처가 `http://127.0.0.1:3000` 이 되고, 백엔드 CORS 가 이 출처를 막는다. `tests/dev-server.test.ts` 가 두 가지를 확인한다.

## API 주소 (`NEXT_PUBLIC_API_BASE`)

| 상황 | 값 | 정하는 곳 |
|---|---|---|
| 개발(`npm run dev`) | `http://localhost:8000` | `.env.development.local` |
| 빌드(`npm run build`) | 비어 있음. 같은 출처의 `/api/...` 를 부른다 | 설정 없음 |

`.env.development.local` 은 `next dev` 에서만 읽힌다. `.env.local` 은 쓰지 않는다. `next build` 에도 읽혀서 개발용 주소가 `out/` 에 박히기 때문이다. postbuild 검사는 `out/` 에서 `localhost:8000` 을 찾으면 빌드를 실패시킨다.

`.env*` 는 `.gitignore` 에 걸려 저장소에 올라가지 않는다. 새로 받았다면 직접 만든다.

```bash
echo 'NEXT_PUBLIC_API_BASE=http://localhost:8000' > .env.development.local
```

`/` 와 `/ops/` 화면은 이 주소에 `/api/state` 를 붙여 1초마다 부르고, `/api/config` 에서 구역 한계 수위와 강우 단계값·상한을 받는다. `/ops/` 의 제어도 이 주소로 POST 를 보낸다. `/logs/` 는 `/api/logs` 와 `/api/logs/{id}/events` 를 읽는다. 자세한 동작은 아래 "서버 연결"·"운영 화면(`/ops/`)"·"기록·재생 화면(`/logs/`)" 절에 있다.

## AGENTS.md 를 만들지 않는 이유

`next dev` 는 AI 코딩 에이전트가 실행했다고 판단하면 `AGENTS.md` 를 만들거나 고친다. 이 저장소의 작업 규칙은 루트 `CLAUDE.md` 에 두므로 `next.config.mjs` 에서 `agentRules: false` 로 끈다.

## 구조

| 경로 | 내용 |
|---|---|
| `src/app/layout.tsx` | 공통 틀: 로고와 메뉴(넓으면 왼쪽, 좁으면 위), 하단 시험용 고지 |
| `src/app/page.tsx` | `/` 종합 관제 |
| `src/app/ops/page.tsx` | `/ops/` 운영·설정. 회차·입력원·강우·막힘 제어와 구역 한계 수위 |
| `src/app/logs/page.tsx` | `/logs/` 기록·재생. 기록 목록과 `?id=` 상세 |
| `src/app/icon.svg` | 탭 아이콘. 머리글 로고의 물결과 같은 모양이다. SVG 는 XML 이라 주석에 `--` 를 쓰면 그림이 깨진다 |
| `src/components/` | 화면 조각. 파일 이름과 내보내는 이름이 다르다. `MonitorView.tsx`(종합 관제 화면)는 `Monitor`, `StatusBanner.tsx` 는 `Headline`, `ZoneGauge.tsx` 는 `Gauge`, `LevelChart.tsx` 는 `Chart`, `ModeBadge.tsx` 는 `Mode`, `ConnectionBadge.tsx` 는 `Signal`, `CityPlan.tsx`("도시 모형 상태" 칸)는 `Plan`, `DeviceStatus.tsx`("현장 장치 상태" 칸)는 `Devices`, `AlertTimeline.tsx`("위험 판단·시험용 문자" 칸)는 `Timeline`, `EventLog.tsx`("이벤트 기록" 칸)는 `Journal` 을 내보낸다. `Glyph.tsx` 는 화면 전체가 쓰는 선 아이콘 한 벌(18px, 선 1.5, 색은 글자색), `Menu.tsx` 는 지금 쪽을 표시하는 메뉴다. 운영·설정 화면은 `OpsView.tsx` 가 `Desk`(상태를 읽고 제어를 보냄)·`Sheet`(화면 몸통)·`Board`(몸통이 받는 값)를 내보내고, 칸은 `RunPanel.tsx`("회차")가 `Round`, `SourcePanel.tsx`("입력원")가 `Origin`, `RainPanel.tsx`("강우")가 `Rain`, `BlockagePanel.tsx`("막힘")가 `Clog`, `LimitPanel.tsx`("구역 한계 수위")가 `Limits` 를 내보낸다. 뒤의 셋은 고르거나 입력 중인 값만 상태로 두고 그리기는 파일 이름과 같은 몸통 함수에 맡긴다. `Guard.tsx` 는 칸 안의 확인 줄 `Guard`, `Trigger.tsx` 는 제어 단추 `Trigger` 와 꺼진 이유 목록 `Reasons` 다. 기록·재생 화면은 `LogsView.tsx` 가 `Archive`·`Desk`·`Shelf`·`Waiting` 를, `Compare.tsx`("예측과 실제 비교" 칸)가 `Compare` 를 내보낸다. S2 의 네 칸과 S3 의 파일은 같은 이름의 `.test.tsx` 를 옆에 둔다 |
| `src/lib/schema.ts` | `/api/state` zod 스키마. 백엔드 계약(`docs/api-contract.md`)과 같은 제약. 기록 사건 응답(`/api/logs/{id}/events`)의 스키마와 검사 함수 `chronicle`, 제어 요청 모양(`Command`), 설정의 강우 단계값·상한을 꺼내는 `rainfall`, 오류 응답의 이유 글을 꺼내는 `cause`, 기록 목록 스키마(`logSchema`·`logsSchema`)와 검사 함수 `catalog`, 문자 알림 상태(`notifier`)도 둔다 |
| `src/lib/api.ts` | `fetch` 래퍼. 기본 5초 제한, `/api/state` 는 3초. 응답을 받은 시각을 함께 돌려준다. `setup` 은 `/api/config` 의 한계 수위와 강우 단계값·상한을 읽는다. `records` 는 기록 목록(`/api/logs`)을 읽는다. `logbook` 은 기록 사건을 읽고, 기록이 없어 404 면 빈 목록을 돌려준다. `order` 는 제어를 POST 로 보내고(5초 제한), 던지지 않고 결과(반영된 상태, 또는 거절·HTTP 실패·응답 없음·닿지 못함·응답 모양 이상)를 돌려준다 |
| `src/lib/useSnapshot.ts` | `/api/state` 1초 폴링(SWR), 수위 이력(최근 600개), `/api/config` 의 한계 수위와 강우 단계값·상한. 이력은 모듈에 두고 `useSyncExternalStore` 로 읽어 화면을 옮겨도 남는다. `handover` 는 제어 응답의 상태를 폴링 캐시에 바로 넣는다 |
| `src/lib/useEvents.ts` | 기록 사건 읽기(SWR). 실험 번호, 경보(구역과 단계), 실행 상태로 만든 키가 바뀔 때만 읽는다. 받은 목록은 실험 번호와 함께 두어, 다시 읽는 동안이나 읽기가 실패해도 같은 실험이면 그대로 보여 준다 |
| `src/lib/derive.ts` | 위험 단계, 도달 시간, %, 예측 만료, 연결 상태(`linkage`), 차트 경로, 사건 키와 재생 범위, 타임라인 시각, 장치 상태, 평면도 좌표를 계산하는 순수 함수. 운영 화면 쪽은 제어마다 켜짐과 꺼진 이유(`gates`), 확인 줄의 다음 상태(`step`), 보낼 요청(`command`·`shower`·`plug`), 입력 검사, 결과 줄 글(`outcome`)이다. 기록 화면 쪽은 구역별 예측·실제 비교(`tally`)와 간격 글(`span`), 재생 시작 요청(`playback`)과 검사(`rerun`), 문자 요청 줄 글(`relay`)이다. 시간은 인자로 받는다 |
| `src/lib/useNow.ts` | 1초마다 바뀌는 현재 시각. 정적 프리렌더 때는 `null` |
| `src/lib/useSettings.ts` | 구역 한계 수위 설정(브라우저 localStorage). 값이 없거나 깨지면 기본값 A 45·B 55·C 65 mm. `/ops/` 의 "가상 데이터용(이 브라우저)" 에서 고친다 |
| `src/lib/mock.ts` | 서버 없이 보여 줄 가상 스냅샷과 가상 사건(`diary`). 사건 글은 서버 기록과 같은 꼴이다 |
| `src/lib/layout-data.ts` | 구역 이름, 라벨, 아이콘 같은 고정 표. 평면도 좌표(구역 칸, 빗물받이, 배수관, 계량 상자)와 장치·입력 품질·막힘의 표시 글, 제어 단추 이름·강우 단계 이름·결과 줄 아이콘도 둔다 |
| `src/styles/tokens.css` | 색·글꼴 토큰 |
| `scripts/check-out.mjs` | 빌드 결과 검사(postbuild) |
| `scripts/check-state.mjs` | 실제 `/api/state` 응답 검사(`npm run check:state`). `src/lib/schema.ts` 를 그대로 읽는다 |
| `tests/` | ESLint 설정, 정적 규칙(브라우저 기본 대화상자 금지 포함), 렌더 검사, 한글 줄바꿈·탭 아이콘·개발 서버 설정·핵심 수치 글자 크기 검사 |

## 검증 (지시서 9장)

| 번호 | 조건 | 확인하는 곳 |
|---|---|---|
| 1 | 타입 오류 0 | `npm run typecheck` |
| 2 | eslint 오류 0, react-hooks 여섯 규칙이 error | `npm run lint`, `tests/eslint-config.test.ts` |
| 3 | 임계값·예측 경계, 단계 우선순위, 예측 만료·연결 끊김, 차트 경로, 사건 키·재생 범위·타임라인·장치 상태·평면도 계산, 운영 화면의 연결 상태·제어 판정·확인 줄·요청 모양·입력 검사·결과 글, 기록 화면의 구역별 비교(`tally`)·재생 요청 | `src/lib/derive.test.ts` |
| 4 | 파생 값 이름의 `useState` 없음 | `tests/static-rules.test.ts` |
| 5 | 렌더 경로에 `Date.now(`·`new Date(`·`Math.random(` 없음(`useNow.ts` 제외). `useNow.ts` 의 `wall` 은 응답 받은 시각을 적는 `api.ts` 만 쓴다 | `tests/static-rules.test.ts` |
| 6 | 정적 export 성공, `out/` 에 세 화면의 `index.html` | `npm run build` 의 postbuild(`scripts/check-out.mjs`) |
| 7 | 정적 export 와 맞지 않는 기능 없음 | `tests/static-rules.test.ts` |
| 8 | zod 가 계약 예시를 통과시키고 범위 밖 값을 거부. 기록 사건 응답 예시도 같은 방식으로 보고, 설정의 강우 단계값·상한(`rainfall`)과 오류 응답의 이유 글(`cause`)도 본다 | `src/lib/schema.test.ts` |
| 9 | 서버 미연결이면 "가상 데이터" 문구가 보임. 연결 중에도 S2 의 네 칸이 보이고, 가상 사건이 타임라인과 기록에 차며, 재생 중에는 지금 경과 초 뒤의 사건을 숨김. `/ops/` 는 프리렌더(연결 중)에서 서버 제어가 모두 꺼짐 | `tests/mock-render.test.tsx`(mock 화면 렌더 검사), 네 칸과 운영 화면 파일 옆의 `.test.tsx` |
| 10 | 실제 `/api/state` 응답이 zod 통과. 실제 기록 사건 응답도 `chronicle` 통과 | 백엔드를 띄우고 `npm run check:state`. 스크립트 자체는 `tests/check-state.test.ts` 가 검사한다. 사건 응답은 `curl` 로 받은 `/api/logs/{id}/events` 본문을 `chronicle` 에 넣어 본다 |

postbuild 검사는 6번 외에 세 가지를 더 본다. 세 화면 모두에 시험용 고지가 있는지, 세 화면 모두에 탭 아이콘 링크가 있고 `out/icon.svg` 가 있는지(없으면 브라우저가 `/favicon.ico` 를 찾다가 404 를 낸다), `out/` 의 텍스트 파일에 개발용 주소 `localhost:8000` 이 없는지.

`tests/contrast.test.ts` 는 대비와 글자 크기를 본다(S5). 본문 글과 바탕의 짝은 모두 4.5:1 이상이어야 하고(가장 낮은 짝은 `raised` 위 `muted` 4.95:1), 본문은 16px, `text-key` 는 28px, `text-figure` 는 32px 이다.

`tests/static-rules.test.ts` 는 지시서 9장 밖의 규칙 하나를 더 본다. `src/` 의 모든 파일(시험 포함)에 브라우저 기본 대화상자 호출(`alert(`·`confirm(`·`prompt(`)이 없어야 한다. 확인은 화면 안의 확인 줄로 받는다.

## 서버 연결

- `/api/state` 를 1초마다 부른다. 3초 안에 답이 없거나, 오류 응답이거나, zod 계약을 통과하지 못하면 연결 실패로 본다. 실패하는 동안에도 1초마다 다시 묻는다. 브라우저가 오프라인이라고 알려도(와이파이만 끊긴 경우 등) 멈추지 않는다. 서버가 같은 컴퓨터에 있으면 계속 답하기 때문이다.
- 실패해도 마지막 정상 응답을 그대로 보여 준다. 마지막 정상 수신 뒤 4초가 넘고 그 뒤 폴링이 실패했으면 머리글 배지가 "연결 끊김 · 마지막 수신 HH:MM:SS" 로 바뀐다. 실패 없이 4초가 넘었으면(다른 메뉴로 갔다 와서 캐시의 응답만 오래된 경우) "연결 중" 으로 두어, 메뉴를 옮길 때 "연결 끊김" 이 잠깐 뜨지 않는다. 서버가 다시 답하면 새로 고침 없이 이어진다.
- 첫 응답이나 첫 실패 전(정적 프리렌더 포함)에는 배지에 "연결 중" 을 달고 값 자리를 "—" 로 둔다.
- 위험 단계와 도달 시간(eta)은 서버가 보낸 `alerts` 만 따른다. 화면이 단계 전환을 만들지 않는다.
- 타임라인 칸과 "이벤트 기록" 칸은 서버 기록의 사건(`/api/logs/{id}/events`)만 보여 준다. 실험 번호가 기록 번호 꼴(`RECORD_ID`)일 때만 읽고, 키(실험 번호, 경보, 실행 상태)가 바뀔 때만 다시 읽는다. 5초 제한이고, 404 는 빈 목록으로 본다. 계약 위반은 다시 묻지 않고, 그 밖의 실패는 1초 뒤 다시 묻는다. 재생 중에는 재생하는 기록의 번호로 읽고 지금 경과 초까지의 사건만 보인다. `/` 는 POST 를 보내지 않는다. POST 는 `/ops/` 의 제어(아래 "운영 화면" 절)와 `/logs/` 의 "이 기록 재생"(아래 "기록·재생 화면" 절)만 보낸다.
- 한계 수위는 `/api/config` 에서 받는다. 한 번 받으면 다시 묻지 않고, 받기 전에는 1초마다 다시 묻는다. 받기 전에는 "한계 —" 로 둔다. 강우 단계값과 직접 입력 상한(`rain_presets_mm_per_h`·`rain_max_mm_per_h`)도 같은 응답에서 읽고, 모양이 틀리면 단계 단추의 값 자리를 "—" 로 둔다.
- 예측 기준 시각(`predictionMeta.basisTime`)에서 `validForSec` 이 지나면 머리글에 "예측 만료" 를 단다. 백엔드는 실험이 정지·대기 상태일 때 기준 시각을 멈추므로, 연결이 정상이어도 정지 몇 초 뒤부터 "예측 만료" 가 뜬다.
- 전시 때는 `npm run build` 로 만든 `out/` 을 백엔드 FastAPI 가 `StaticFiles` 로 함께 서빙한다. `backend` 에서 uvicorn 한 대만 띄우면 `http://localhost:8000/`, `/ops/`, `/logs/` 가 열린다(끝에 `/` 가 없는 `/ops`·`/logs` 는 307 로 `/ops/`·`/logs/` 로 간다). 화면과 API 가 같은 출처라 CORS 설정이 필요 없고, 빌드의 API 주소는 비어 있어 같은 출처의 `/api/...` 를 부른다.
- 수위 이력(차트)은 화면이 받은 응답으로 쌓는다(최근 600개). `/`·`/ops/`·`/logs/` 가 같은 이력에 더하므로 다른 메뉴로 갔다 와도 남고, 응답을 받지 않은 사이는 빈틈으로 그린다. 실험 번호·입력원이 바뀌거나 서버 시각이 거꾸로 가면 처음부터 다시 쌓는다. 새로 고침하면 비운다.

## 운영 화면 (`/ops/`)

`/` 와 같은 방식으로 `/api/state` 를 읽고, 칸 다섯으로 실험을 바꾼다. 단추 하나가 제어 API(`docs/api-contract.md`)에 POST 하나를 보낸다.

| 칸 | 단추·입력 | 보내는 곳 |
|---|---|---|
| 회차 | "시작"·"종료"·"초기화". 상태·실험 ID·경과도 보인다 | `/api/experiment/start`·`stop`·`reset` |
| 입력원 | "시뮬레이션으로 바꾸기"·"실측으로 바꾸기" | `/api/source` |
| 강우 | 단계 단추 셋("약한 강우"·"보통 강우"·"강한 강우", 값은 `/api/config`)과 "직접 입력(mm/h)" 뒤 "적용" | `/api/rain` |
| 막힘 | 종류("막힘 없음"·"부분 막힘"·"완전 막힘")를 고르고, 막힘이면 빗물받이도 고른 뒤 "적용" | `/api/blockage` |
| 구역 한계 수위 | 서버 값(`config.yaml`)은 읽기만 한다. "가상 데이터용(이 브라우저)" A·B·C 는 "저장" 하면 이 브라우저에만 남고, "기본값으로 되돌리기" 는 45·55·65 mm 로 돌린다 | 보내지 않는다 |

- "종료"·"초기화"·입력원 전환·"재생 멈춤" 은 그 칸 안의 확인 줄(물음과 "예"·"취소")을 거친다. 초점은 "취소" 에서 시작해 Enter 로 바로 보내지 않고, Esc 는 취소다. 줄이 닫히면 초점은 연 단추로 돌아간다. "시작"·강우·막힘은 확인 없이 보낸다. 브라우저 기본 대화상자는 어디에도 쓰지 않는다.
- 연결 중·연결 끊김·가상 데이터(mock)이면 서버 제어를 모두 끄고, 위쪽 멈춤 줄에 이유를 적는다(예: "서버에 연결되지 않아 제어를 끕니다. 가상 데이터에는 보내지 않습니다"). mock 에서는 아무것도 보내지 않는다.
- 재생 중에는 "재생 멈춤"(재생이 진행 중일 때)과 "시뮬레이션으로 돌아가기" 만 켜진다. 재생 시작 단추는 `/ops/` 에 없다. 재생은 `/logs/` 의 "이 기록 재생" 으로 시작한다.
- 꺼진 단추도 Tab 으로 닿고, 칸 아래 이유 줄(예: "회차가 진행 중이라 입력원을 바꿀 수 없습니다. 먼저 종료합니다")을 가리킨다. 직접 입력이나 빗물받이 고르기가 맞지 않으면 "적용" 을 끄고 이유를 적는다.
- 보내는 동안에는 켜져 있던 제어를 끄고 결과 줄에 "{이름} 보내는 중입니다" 를 띄운다(예: "강우 적용 보내는 중입니다"). 원래 꺼져 있던 단추의 이유 줄은 그대로 두어 단추가 움직이지 않는다. 두 번 눌러도 POST 는 하나만 간다.
- 답이 오면 결과 줄이 "반영 · {바뀐 것} · HH:MM:SS 수신", "{이름} 거절 · {서버 이유} · HH:MM:SS", "{이름} 실패 · …", "{이름} 응답 없음 · 5초 안에 답이 없었습니다. …" 가운데 하나가 된다. 200 인데 계약과 다르면 "{이름} 응답 모양 이상" 이다. 반영되면 응답의 상태를 바로 화면에 넣고 다음 폴링이 이어 받는다.

## 기록·재생 화면 (`/logs/`)

서버 기록만 읽어 보여 준다. 화면이 사건을 만들지 않는다.

- `/logs/` 는 실험 기록 목록(`/api/logs`)이다. 기록을 고르면 `/logs/?id={실험 번호}` 상세로 간다. 정적 export 라 동적 라우트 대신 쿼리를 쓴다.
- 상세는 실험 번호·시작 시각·입력원·모델 버전, "예측과 실제 비교" 표, 그 기록의 사건 타임라인(`/api/logs/{id}/events`)이다. 고르기 전에는 "목록에서 기록을 고르면 비교 표와 재생 단추가 나옵니다." 를, 목록에 없는 번호면 "고른 실험 기록이 목록에 없습니다." 를 적는다.
- 표 아래에 "예측 도달은 위험 판단 시각에 그때 남은 초를 더한 값이고, 오차는 실제 도달에서 예측 도달을 뺀 초입니다." 를 적는다.
- 타임라인의 문자 요청 줄은 "발송 결과는 서버 로그에만 남음" 이다. 지난 기록의 발송 결과는 실험 기록에 없다.
- 비교 표의 열은 "위험 판단"·"예측 도달"·"실제 도달"·"선행 시간"·"오차" 다. 예측 도달은 위험 판단 사건 시각에 그 사건의 `etaSec` 를 더한 시각이고, 오차는 실제 도달에서 예측 도달을 뺀 값(부호 포함)이다. 계산은 `derive.ts` 의 `tally` 가 한다.
- 회차가 도는 중이면 재생 단추를 끄고 "회차가 도는 중이라 재생할 수 없습니다. 운영·설정에서 먼저 종료합니다" 를 적는다. 그 기록을 이미 재생 중이면 "이 기록을 재생하는 중입니다" 다.
- "이 기록 재생" 은 칸 안의 확인 줄("이 기록을 처음부터 재생할까요? 멈춘 회차의 마지막 화면은 재생 화면으로 바뀝니다" 와 "예"·"취소")을 거쳐 `POST /api/source` 에 `{"mode": "replay", "logId": …}` 를 보낸다. 반영되면 결과 줄에 "종합 관제에서 보기" 링크가 붙는다. 브라우저 기본 대화상자는 쓰지 않는다.

## 가상 데이터(mock)

서버가 한 번도 답하지 않으면 `/` 는 `src/lib/mock.ts` 가 만든 가상 스냅샷을 보여 주고, 위쪽에 "가상 데이터(서버 미연결)" 를 크게 단다. 한 번이라도 답한 뒤에는 끊겨도 mock 으로 바꾸지 않고, 마지막 값과 "연결 끊김" 을 보여 준다. `/ops/` 는 가상 스냅샷을 쓰지 않고 제어를 모두 끈다.

- 기존 바닐라 화면의 데모(보통 강우, INLET-02 부분 막힘)를 180초 주기로 되풀이한다. 같은 시각이면 같은 값이 나온다.
- mock 의 위험 단계는 `derive.ts` 규칙으로 계산한다. 서버에 붙은 뒤에는 서버가 보낸 `alerts`·`events` 를 그대로 보여 준다.
- mock 의 한계 수위는 브라우저 설정(`useSettings`, 기본 A 45·B 55·C 65 mm)을 쓴다. 이 값은 `/ops/` 의 "가상 데이터용(이 브라우저)" 에서 고치고 이 브라우저에만 저장된다. 서버에 붙으면 서버 값을 쓴다.
- mock 은 같은 180초 주기에 맞춘 가상 사건(`diary`)도 만들어 타임라인과 기록 칸을 채운다. 사건 글은 서버 기록과 같은 꼴이다.
- 서버 없이 정적 파일만 띄우면 `/api/state`·`/api/config` 가 1초마다 404 를 낸다. 브라우저 콘솔의 이 404 는 정상이다.

## 개발 규칙

루트 `CLAUDE.md` 의 frontend 절을 따른다. 계산할 수 있는 값은 state 로 두지 않고 렌더 중에 계산한다. 시간은 `useNow()` 로만 읽는다. 상태 관리 라이브러리, UI 키트, 차트 라이브러리, `next/image`, 동적 라우트, 서버 기능은 쓰지 않는다.

핵심 수치(지시서 6장: 28px 이상)는 현재 수위(32px, `tokens.css` 의 `text-figure`), 한계 대비 %와 도달까지 남은 초(28px, `text-key`)다. 구역은 색만으로 구분하지 않는다. 카드 제목에 구역 글자를 쓰고, 차트는 선 끝에 구역 글자를 붙인다. 차트의 한계 라벨은 왼쪽 끝에 모은다.

색은 위험 단계와 연결·막힘·장치 같은 상태를 알릴 때만 쓰고, 구역 색은 수위 차트에만 쓴다. 아이콘은 `Glyph` 한 벌만 쓰고 글자 기호를 아이콘으로 쓰지 않는다. 글자는 16px 이상, 굵기는 400·500(쪽 제목과 로고 600)이고 시각·실험 번호·눈금 숫자는 고정폭(`font-mono`)이다.

한글은 어절 단위로 줄을 바꾼다. `globals.css` 의 `html` 에 `word-break: keep-all` 과 `overflow-wrap: break-word` 를 두어, 한 줄보다 긴 낱말만 중간에서 끊긴다. 좁은 칸에 긴 낱말을 넣을 때는 폭 390px 에서 넘치지 않는지 본다.

## 버전 메모

- `eslint` 는 9 에 둔다. `eslint-config-next` 가 쓰는 `eslint-plugin-react`·`eslint-plugin-import`·`eslint-plugin-jsx-a11y` 가 eslint 10 을 받지 않는다.
- `typescript` 는 5.9 에 둔다. `typescript-eslint` 8.72 가 `typescript <6.1` 만 받는다.
- 올리기 전에 `npm run lint` 와 `npm run typecheck` 가 도는지 확인한다.
- `package.json` 의 `"type": "module"` 은 `scripts/check-state.mjs` 가 `src/lib/schema.ts` 를 Node 24 로 바로 읽게 하려고 둔다. 없으면 Node 가 `.ts` 를 CommonJS 로 먼저 읽어 보고 `MODULE_TYPELESS_PACKAGE_JSON` 경고를 낸다. CommonJS 설정 파일이 필요하면 확장자를 `.cjs` 로 짓는다.
