# SMART FLOOD 관제 웹

백엔드 `/api/state` 를 읽어 A·B·C 구역의 수위, 10·20·30초 예측, 알림 이력을 보여 주는 관제 화면이다. Next.js(App Router)로 만들고 `next build` 로 정적 파일(`out/`)을 내보낸다. 서버 기능은 쓰지 않는다. 전시 때는 FastAPI 한 대가 `out/` 과 API 를 함께 서빙한다(백엔드는 `frontend/out/` 이 있으면 `/` 에 붙인다).

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

`/` 화면은 이 주소에 `/api/state` 를 붙여 1초마다 부르고, `/api/config` 에서 구역 한계 수위를 받는다. 자세한 동작은 아래 "서버 연결" 절에 있다.

## AGENTS.md 를 만들지 않는 이유

`next dev` 는 AI 코딩 에이전트가 실행했다고 판단하면 `AGENTS.md` 를 만들거나 고친다. 이 저장소의 작업 규칙은 루트 `CLAUDE.md` 에 두므로 `next.config.mjs` 에서 `agentRules: false` 로 끈다.

## 구조

| 경로 | 내용 |
|---|---|
| `src/app/layout.tsx` | 공통 틀: 메뉴, 하단 시험용 고지 |
| `src/app/page.tsx` | `/` 종합 관제 |
| `src/app/ops/page.tsx` | `/ops/` 운영·설정 (S3 에서 채운다) |
| `src/app/logs/page.tsx` | `/logs/` 기록·재생 (S4 에서 채운다) |
| `src/app/icon.svg` | 탭 아이콘. 머리글의 ≋ 표시와 같은 모양이다. SVG 는 XML 이라 주석에 `--` 를 쓰면 그림이 깨진다 |
| `src/components/` | 화면 조각. 파일 이름과 내보내는 이름이 다르다: `MonitorView.tsx`(종합 관제 화면) → `Monitor`, `StatusBanner.tsx` → `Headline`, `ZoneGauge.tsx` → `Gauge`, `LevelChart.tsx` → `Chart`, `ModeBadge.tsx` → `Mode`, `ConnectionBadge.tsx` → `Signal`. `CityPlan`·`AlertTimeline`·`DeviceStatus` 는 S2 에서 붙인다 |
| `src/lib/schema.ts` | `/api/state` zod 스키마. 백엔드 계약(`docs/api-contract.md`)과 같은 제약 |
| `src/lib/api.ts` | `fetch` 래퍼. 기본 5초 제한, `/api/state` 는 3초. 응답을 받은 시각을 함께 돌려준다 |
| `src/lib/useSnapshot.ts` | `/api/state` 1초 폴링(SWR)과 수위 이력(최근 600개), `/api/config` 한계 수위 |
| `src/lib/derive.ts` | 위험 단계, 도달 시간, %, 예측 만료, 연결 끊김, 차트 경로를 계산하는 순수 함수. 시간은 인자로 받는다 |
| `src/lib/useNow.ts` | 1초마다 바뀌는 현재 시각. 정적 프리렌더 때는 `null` |
| `src/lib/useSettings.ts` | 구역 한계 수위 설정(브라우저 localStorage). 값이 없거나 깨지면 기본값 A 45·B 55·C 65 mm |
| `src/lib/mock.ts` | 서버 없이 보여 줄 가상 스냅샷 |
| `src/lib/layout-data.ts` | 구역 이름, 라벨, 아이콘 같은 고정 표 |
| `src/styles/tokens.css` | 색·글꼴 토큰 |
| `scripts/check-out.mjs` | 빌드 결과 검사(postbuild) |
| `scripts/check-state.mjs` | 실제 `/api/state` 응답 검사(`npm run check:state`). `src/lib/schema.ts` 를 그대로 읽는다 |
| `tests/` | ESLint 설정, 정적 규칙, 렌더 검사, 한글 줄바꿈·탭 아이콘·개발 서버 설정·핵심 수치 글자 크기 검사 |

## 검증 (지시서 9장)

| 번호 | 조건 | 확인하는 곳 |
|---|---|---|
| 1 | 타입 오류 0 | `npm run typecheck` |
| 2 | eslint 오류 0, react-hooks 여섯 규칙이 error | `npm run lint`, `tests/eslint-config.test.ts` |
| 3 | 임계값·예측 경계, 단계 우선순위, 예측 만료·연결 끊김, 차트 경로 | `src/lib/derive.test.ts` |
| 4 | 파생 값 이름의 `useState` 없음 | `tests/static-rules.test.ts` |
| 5 | 렌더 경로에 `Date.now(`·`new Date(`·`Math.random(` 없음(`useNow.ts` 제외). `useNow.ts` 의 `wall` 은 응답 받은 시각을 적는 `api.ts` 만 쓴다 | `tests/static-rules.test.ts` |
| 6 | 정적 export 성공, `out/` 에 세 화면의 `index.html` | `npm run build` 의 postbuild(`scripts/check-out.mjs`) |
| 7 | 정적 export 와 맞지 않는 기능 없음 | `tests/static-rules.test.ts` |
| 8 | zod 가 계약 예시를 통과시키고 범위 밖 값을 거부 | `src/lib/schema.test.ts` |
| 9 | 서버 미연결이면 "가상 데이터" 문구가 보임 | `tests/mock-render.test.tsx`(mock 화면 렌더 검사) |
| 10 | 실제 `/api/state` 응답이 zod 통과 | 백엔드를 띄우고 `npm run check:state`. 스크립트 자체는 `tests/check-state.test.ts` 가 검사한다 |

postbuild 검사는 6번 외에 세 가지를 더 본다. 세 화면 모두에 시험용 고지가 있는지, 세 화면 모두에 탭 아이콘 링크가 있고 `out/icon.svg` 가 있는지(없으면 브라우저가 `/favicon.ico` 를 찾다가 404 를 낸다), `out/` 의 텍스트 파일에 개발용 주소 `localhost:8000` 이 없는지.

## 서버 연결

- `/api/state` 를 1초마다 부른다. 3초 안에 답이 없거나, 오류 응답이거나, zod 계약을 통과하지 못하면 연결 실패로 본다. 실패하는 동안에도 1초마다 다시 묻는다. 브라우저가 오프라인이라고 알려도(와이파이만 끊긴 경우 등) 멈추지 않는다. 서버가 같은 컴퓨터에 있으면 계속 답하기 때문이다.
- 실패해도 마지막 정상 응답을 그대로 보여 준다. 마지막 정상 수신 뒤 4초가 넘으면 머리글 배지가 "연결 끊김 · 마지막 수신 HH:MM:SS" 로 바뀐다. 서버가 다시 답하면 새로 고침 없이 이어진다.
- 첫 응답이나 첫 실패 전(정적 프리렌더 포함)에는 배지에 "연결 중" 을 달고 값 자리를 "—" 로 둔다.
- 위험 단계와 도달 시간(eta)은 서버가 보낸 `alerts` 만 따른다. 화면이 단계 전환을 만들지 않는다.
- 한계 수위는 `/api/config` 에서 받는다. 한 번 받으면 다시 묻지 않고, 받기 전에는 1초마다 다시 묻는다. 받기 전에는 "한계 —" 로 둔다.
- 예측 기준 시각(`predictionMeta.basisTime`)에서 `validForSec` 이 지나면 머리글에 "예측 만료" 를 단다. 백엔드는 실험이 정지·대기 상태일 때 기준 시각을 멈추므로, 연결이 정상이어도 정지 몇 초 뒤부터 "예측 만료" 가 뜬다.
- 수위 이력(차트)은 화면이 받은 응답으로 쌓는다(최근 600개). 다른 메뉴로 갔다 오거나 실험 번호·입력원이 바뀌면 처음부터 다시 쌓는다.

## 가상 데이터(mock)

서버가 한 번도 답하지 않으면 `/` 는 `src/lib/mock.ts` 가 만든 가상 스냅샷을 보여 주고, 위쪽에 "가상 데이터(서버 미연결)" 를 크게 단다. 한 번이라도 답한 뒤에는 끊겨도 mock 으로 바꾸지 않고, 마지막 값과 "연결 끊김" 을 보여 준다.

- 기존 바닐라 화면의 데모(보통 강우, INLET-02 부분 막힘)를 180초 주기로 되풀이한다. 같은 시각이면 같은 값이 나온다.
- mock 의 위험 단계는 `derive.ts` 규칙으로 계산한다. 서버에 붙은 뒤에는 서버가 보낸 `alerts`·`events` 를 그대로 보여 준다.
- mock 의 한계 수위는 브라우저 설정(`useSettings`, 기본 A 45·B 55·C 65 mm)을 쓴다. 서버에 붙으면 서버 값을 쓴다.
- 서버 없이 정적 파일만 띄우면 `/api/state`·`/api/config` 가 1초마다 404 를 낸다. 브라우저 콘솔의 이 404 는 정상이다.

## 개발 규칙

루트 `CLAUDE.md` 의 frontend 절을 따른다. 계산할 수 있는 값은 state 로 두지 않고 렌더 중에 계산한다. 시간은 `useNow()` 로만 읽는다. 상태 관리 라이브러리, UI 키트, 차트 라이브러리, `next/image`, 동적 라우트, 서버 기능은 쓰지 않는다.

핵심 수치(지시서 6장: 28px 이상)는 현재 수위(48px, `text-5xl`), 한계 대비 %와 도달까지 남은 초(28px, `tokens.css` 의 `text-key`)다. 구역은 색만으로 구분하지 않는다. 카드 제목에 구역 글자를 쓰고, 차트는 선 끝에 구역 글자를 붙인다. 차트의 한계 라벨은 왼쪽 끝에 모은다.

한글은 어절 단위로 줄을 바꾼다. `globals.css` 의 `html` 에 `word-break: keep-all` 과 `overflow-wrap: break-word` 를 두어, 한 줄보다 긴 낱말만 중간에서 끊긴다. 좁은 칸에 긴 낱말을 넣을 때는 폭 390px 에서 넘치지 않는지 본다.

## 버전 메모

- `eslint` 는 9 에 둔다. `eslint-config-next` 가 쓰는 `eslint-plugin-react`·`eslint-plugin-import`·`eslint-plugin-jsx-a11y` 가 eslint 10 을 받지 않는다.
- `typescript` 는 5.9 에 둔다. `typescript-eslint` 8.72 가 `typescript <6.1` 만 받는다.
- 올리기 전에 `npm run lint` 와 `npm run typecheck` 가 도는지 확인한다.
- `package.json` 의 `"type": "module"` 은 `scripts/check-state.mjs` 가 `src/lib/schema.ts` 를 Node 24 로 바로 읽게 하려고 둔다. 없으면 Node 가 `.ts` 를 CommonJS 로 먼저 읽어 보고 `MODULE_TYPELESS_PACKAGE_JSON` 경고를 낸다. CommonJS 설정 파일이 필요하면 확장자를 `.cjs` 로 짓는다.
