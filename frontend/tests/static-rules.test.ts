import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// frontend 폴더 경로. 검사마다 어긴 예시를 먼저 잡고 실제 코드를 확인
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const CODE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;  // 코드 파일 확장자 패턴

// 파일 하나의 경로와 내용을 담는 타입
interface Entry {
  path: string;  // frontend 기준 경로(구분자는 슬래시)
  text: string;  // 파일 내용 글
}

// 폴더 아래 코드 파일과 하위 폴더를 모두 모으는 함수
function tree(relativeDir: string): { files: Entry[]; dirs: string[] } {
  const files: Entry[] = [];  // 찾은 코드 파일 목록
  const dirs: string[] = [];  // 찾은 폴더 목록
  // 하위 모든 항목을 하나씩 확인
  for (const entry of readdirSync(join(ROOT, relativeDir), { recursive: true }) as string[]) {
    // 윈도 구분자를 슬래시로 통일한 경로를 만듦
    const path = `${relativeDir}/${entry.split("\\").join("/")}`;
    if (statSync(join(ROOT, path)).isDirectory()) dirs.push(path);  // 폴더면 폴더 목록에 담는다
    // 코드 파일이면 내용을 읽어 파일 목록에 담는다
    else if (CODE.test(path)) files.push({ path, text: readFileSync(join(ROOT, path), "utf8") });
  }
  return { files, dirs };  // 파일 목록과 폴더 목록을 반환
}

// 4번 검사: 파생값을 뜻하는 낱말(심각도·남은 시간·비율·이름표·만료 등)
const DERIVED_WORD = /^(severity|severities|eta|etas|percent|percentage|ratio|ratios|label|labels|worst|stale|staleness)$/;

// 이름을 낱말 조각들로 나누는 함수
function words(name: string): string[] {
  return name  // 이름을 받아 아래 순서로 가공해 반환
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")  // 소문자·숫자 뒤 대문자 앞에 공백을 넣음
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")  // 연속 대문자 뒤 새 낱말 앞에 공백을 넣음
    .split(/[\s_$]+/)  // 공백·밑줄·달러 기호로 자른다
    .filter(Boolean)  // 빈 조각을 버린다
    .map((word) => word.toLowerCase());  // 모두 소문자로 변환
}

// 파생값 이름의 상태 훅과 [값, 설정] 꼴이 아닌 호출을 찾는 함수
function derivations(text: string): string[] {
  const problems: string[] = [];  // 찾은 문제를 모을 목록
  const calls = text.match(/\buseState\s*[<(]/g)?.length ?? 0;  // 상태 훅 호출 수를 센다
  // [값, 설정] 꼴로 받는 호출을 모두 찾음
  const declared = [...text.matchAll(/\[\s*([\w$]+)\s*(?:,\s*([\w$]+)\s*)?\]\s*=\s*(?:React\s*\.\s*)?useState\b/g)];
  // 꼴이 다른 호출이 있으면 문제로 적는다
  if (declared.length !== calls) problems.push(`useState 호출 ${calls}개 중 ${declared.length}개만 [값, 설정] 꼴`);
  for (const match of declared) {  // 찾은 호출마다 확인
    for (const name of [match[1], match[2]]) {  // 값 이름과 설정 이름을 차례로 확인
      // 파생값 낱말이 들어 있으면 문제로 적는다
      if (name && words(name).some((word) => DERIVED_WORD.test(word))) problems.push(name);
    }
  }
  return problems;  // 찾은 문제를 반환
}

const IMPURE = [  // 5번 검사: 렌더 경로에서 직접 부르면 안 되는 시각·난수 호출 모양
  /\bDate\s*\.\s*now\s*\(/,  // 날짜 객체의 현재 시각 읽기 호출
  /\bnew\s+Date\b/,  // 새 날짜 객체 만들기
  /(?<![\w$.])Date\s*\(/,  // 날짜 함수를 그냥 부르는 모양(점 뒤는 제외)
  /\bMath\s*\.\s*random\s*\(/,  // 수학 도구의 난수 호출
  /\bcrypto\s*\.\s*randomUUID\s*\(/,  // 암호 도구의 무작위 ID 호출
];
const CLOCK_FILE = "src/lib/useNow.ts";  // 시각을 읽어도 되는 유일한 파일

// 글에서 걸리는 시각·난수 패턴을 글자로 돌려주는 함수
const impurities = (text: string) => IMPURE.filter((pattern) => pattern.test(text)).map(String);

// 시계 파일과 그 테스트, 받은 시각을 적는 api.ts(렌더 밖)만 벽시계를 기록
const CLOCK_READERS = new Set([CLOCK_FILE, "src/lib/useNow.test.ts", "src/lib/api.ts"]);

// 허용 밖에서 벽시계를 쓰는 파일 경로를 모으는 함수
const readers = (files: Entry[]) =>
  // 허용 목록 밖이면서 벽시계 낱말이 든 파일의 경로만 남김
  files.filter((file) => !CLOCK_READERS.has(file.path) && /\bwall\b/.test(file.text)).map((file) => file.path);

const EXPORT_BLOCKERS = [  // 7번 검사: 정적 export 가 서비스할 수 없는 기능의 모양들
  /\buse server\b/,  // 서버 액션 지시문
  /\brewrites\s*\(/,  // 주소 다시쓰기 설정 함수
  /\bredirects\s*\(/,  // 주소 넘기기 설정 함수
  /\bheaders\s*\(/,  // 응답 헤더 설정 함수
  /\bcookies\s*\(/,  // 쿠키 읽기 함수
  /\bnext\/(legacy\/)?image\b/,  // 넥스트 기본 이미지 컴포넌트
];

// 글에서 걸리는 서버 전용 기능 패턴을 글자로 돌려주는 함수
const barriers = (text: string) => EXPORT_BLOCKERS.filter((pattern) => pattern.test(text)).map(String);

// 설정 파일은 속성 꼴도 막는다. 소스의 요청 헤더 옵션은 정상이라 여기만 건다
const CONFIG_BLOCKERS = [/\brewrites\s*:/, /\bredirects\s*:/, /\bheaders\s*:/];

// 공통 패턴과 설정 파일 전용 패턴을 합쳐 돌려주는 함수
const obstacles = (text: string) => [
  ...barriers(text),  // 소스와 같은 패턴 결과
  // 설정 파일 전용 패턴 결과
  ...CONFIG_BLOCKERS.filter((pattern) => pattern.test(text)).map(String),
];

// generateStaticParams 없는 [id] 폴더와 가로채기 폴더(지시서 3장)를 찾는 함수
function routes(dirs: string[], files: Entry[]): string[] {
  const problems: string[] = [];  // 찾은 문제 폴더를 모을 목록
  for (const dir of dirs) {  // 폴더마다 확인
    const name = dir.split("/").at(-1) ?? "";  // 폴더의 마지막 이름을 구
    // 점 괄호로 시작하는 가로채기 폴더면 문제로 적는다
    if (/^\(\.{1,3}\)/.test(name)) problems.push(dir);
    if (/^\[.+\]$/.test(name)) {  // 대괄호로 감싼 동적 폴더면
      // 그 폴더 안의 파일들
      const inside = files.filter((file) => file.path.startsWith(`${dir}/`));
      // 정적 경로 목록 함수가 없으면 문제로 적는다
      if (!inside.some((file) => file.text.includes("generateStaticParams"))) problems.push(dir);
    }
  }
  return problems;  // 찾은 문제 폴더를 반환
}

const src = tree("src");  // src 아래 파일과 폴더를 한 번 읽어 둔다
// 화면을 그리는 components·app 파일만 선택
const viewFiles = src.files.filter((file) => /^src\/(components|app)\//.test(file.path));
const configFile: Entry = {  // 설정 파일 정보
  path: "next.config.mjs",  // 설정 파일 경로
  text: readFileSync(join(ROOT, "next.config.mjs"), "utf8"),  // 설정 파일 내용을 읽음
};

// 4번 검사 묶음: 파생값에 상태 훅을 쓰지 않음
describe("check 4: no useState for derived values", () => {
  it("catches the forbidden names in a sample", () => {  // 예시에서 금지 이름을 잡는지 검사
    const sample = [  // 일부러 어긴 예시 코드 줄들
      "const [etaSec, setEtaSec] = useState<number | null>(null);",  // 남은 초 이름: 걸려야 함
      // 만료 이름과 React 접두 호출: 걸려야 함
      "const [isStale, setIsStale] = React.useState(false);",
      "const [zoneLabel, setZoneLabel] = useState('');",  // 이름표 이름: 걸려야 함
      "const [meta, setMeta] = useState(0);",  // meta 는 낱말이 달라 걸리지 않아야 함
      // 선택한 구역 이름: 파생값이 아니라 걸리지 않아야 함
      "const [selectedZoneId, setSelectedZoneId] = useState<'A' | 'B' | 'C'>('A');",
      "const pair = useState(0);",  // 짝 꼴이 아닌 호출: 꼴 문제로 걸려야 함
    ].join("\n");  // 줄바꿈으로 이어 한 글로 만듦
    expect(derivations(sample)).toEqual([  // 찾은 문제가 아래 목록과 같아야 함
      "useState 호출 6개 중 5개만 [값, 설정] 꼴",  // 꼴 문제는 맨 앞에 한 번 나옴
      "etaSec",  // 남은 초 값 이름
      "setEtaSec",  // 남은 초 설정 이름
      "isStale",  // 만료 값 이름
      "setIsStale",  // 만료 설정 이름
      "zoneLabel",  // 이름표 값 이름
      "setZoneLabel",  // 이름표 설정 이름
    ]);
  });

  it("scans src/components and src/app", () => {  // 실제 화면 파일에 위반이 없는지 검사
    expect(viewFiles.length).toBeGreaterThan(0);  // 훑을 파일이 하나 이상 있어야 함
    // 파일마다 걸린 이름을 경로와 함께 모음
    const found = viewFiles.flatMap((file) => derivations(file.text).map((name) => `${file.path}: ${name}`));
    expect(found).toEqual([]);  // 걸린 것이 없어야 함
  });
});

// 5번 검사 묶음: 시계 파일 밖에서 시각·난수를 읽지 않음
describe("check 5: no clock or random reads outside useNow.ts", () => {
  it("catches direct calls in a sample", () => {  // 예시에서 직접 호출을 잡는지 검사
    // 조각을 이어 붙여 예시를 만든다. 이 파일이 스스로 걸리지 않게 나눠 둔다
    const sample = ["const a = Date", ".now();", "const b = new ", "Date();", "const c = Math", ".random();"].join("");
    // 시각 읽기·새 날짜·날짜 호출·난수 호출, 네 가지가 걸려야 함
    expect(impurities(sample)).toHaveLength(4);
    // 고정 시각 만들기·해석·타입 이름은 걸리지 않아야 함
    expect(impurities("const t = Date.UTC(2026, 9, 23); const p = Date.parse(s); type T = Date;")).toEqual([]);
  });

  // 받아오는 파일 밖의 벽시계 사용을 잡는지 검사
  it("catches wall outside the fetcher in a sample", () => {
    const files = [  // 예시 파일 목록
      // 컴포넌트가 벽시계를 쓰면 걸려야 함
      { path: "src/components/Clock.tsx", text: "import { wall } from '@/lib/useNow';\nconst t = wall();" },
      // 계산 파일이 벽시계를 쓰면 걸려야 함
      { path: "src/lib/derive.ts", text: "const tick = wall;" },
      { path: "src/lib/api.ts", text: "receivedAt: wall()," },  // 받아오는 파일은 허용이다
      // 시계 파일 자신은 허용이다
      { path: "src/lib/useNow.ts", text: "export function wall(): number {" },
      { path: "src/lib/schema.ts", text: "const wallpaper = 1;" },  // 낱말이 달라 걸리지 않아야 함
    ];
    // 걸린 두 파일이 순서대로 나와야 함
    expect(readers(files)).toEqual(["src/components/Clock.tsx", "src/lib/derive.ts"]);
  });

  // 테스트까지 포함해 src 의 모든 파일을 훑는지 검사
  it("scans every file under src, tests included", () => {
    // 시계 파일이 훑을 목록에 있어야 함
    expect(src.files.some((file) => file.path === CLOCK_FILE)).toBe(true);
    const found = src.files  // src 의 파일들에서 시작
      .filter((file) => file.path !== CLOCK_FILE)  // 시계 파일은 제외
      // 파일마다 걸린 패턴을 경로와 함께 모음
      .flatMap((file) => impurities(file.text).map((pattern) => `${file.path}: ${pattern}`));
    expect(found).toEqual([]);  // 걸린 것이 없어야 함
  });

  // 벽시계 통로로 시각을 읽는 곳이 api.ts 뿐인지 검사
  it("lets only the fetcher in api.ts read the clock through wall", () => {
    // 벽시계를 쓰는 파일 중에 api.ts 가 있어야 함
    expect(src.files.filter((file) => /\bwall\b/.test(file.text)).map((file) => file.path)).toContain("src/lib/api.ts");
    expect(readers(src.files)).toEqual([]);  // 허용 밖에서 쓰는 파일은 없어야 함
  });
});

// 7번 검사 묶음: 정적 export 가 서비스 못 하는 기능을 쓰지 않음
describe("check 7: nothing that static export cannot serve", () => {
  it("catches server-only features in a sample", () => {  // 예시에서 서버 전용 기능을 잡는지 검사
    const sample = [  // 일부러 어긴 예시 코드 줄들
      "'use server';",  // 서버 액션 지시문
      "async rewrites() { return []; }",  // 주소 다시쓰기 함수
      "async redirects() { return []; }",  // 주소 넘기기 함수
      "async headers() { return []; }",  // 응답 헤더 함수
      "const jar = await cookies();",  // 쿠키 읽기
      "import Image from 'next/image';",  // 넥스트 이미지 가져오기
    ].join("\n");  // 줄바꿈으로 이어 한 글로 만듦
    expect(barriers(sample)).toHaveLength(6);  // 여섯 가지가 모두 걸려야 함
    // 요청 헤더 옵션과 헤더 객체 만들기는 걸리면 안 됨
    expect(barriers("fetch(url, { headers: { Accept: 'application/json' } }); new Headers();")).toEqual([]);
  });

  it("catches the property form in next.config", () => {  // 설정 파일의 속성 꼴을 잡는지 검사
    // 세 속성을 모두 담은 설정 예시
    const sample = "export default { rewrites: async () => [], redirects: async () => [], headers: async () => [] };";
    expect(obstacles(sample)).toHaveLength(3);  // 세 가지가 걸려야 함
    // 정상 설정은 걸리면 안 됨
    expect(obstacles('export default { output: "export", trailingSlash: true };')).toEqual([]);
  });

  // 정적 경로 목록 없는 동적 폴더와 가로채기 폴더를 잡는지 검사
  it("catches dynamic folders without generateStaticParams and intercepting folders", () => {
    // 예시 폴더 목록
    const dirs = ["src/app/logs", "src/app/logs/[id]", "src/app/runs/[run]", "src/app/(.)photo"];
    const files = [  // 예시 파일 목록
      // 목록 함수가 없는 동적 폴더의 쪽 파일
      { path: "src/app/logs/[id]/page.tsx", text: "export default function Page() { return null; }" },
      // 목록 함수가 있는 동적 폴더의 쪽 파일
      { path: "src/app/runs/[run]/page.tsx", text: "export function generateStaticParams() { return []; }" },
    ];
    // 함수 없는 동적 폴더와 가로채기 폴더만 걸려야 함
    expect(routes(dirs, files)).toEqual(["src/app/logs/[id]", "src/app/(.)photo"]);
  });

  it("scans src and next.config.mjs", () => {  // src 와 설정 파일을 실제로 훑는지 검사
    const found = [  // 걸린 것들을 한 목록에 모음
      // src 파일마다 걸린 패턴을 경로와 함께 담는다
      ...src.files.flatMap((file) => barriers(file.text).map((pattern) => `${file.path}: ${pattern}`)),
      // 설정 파일에서 걸린 패턴을 경로와 함께 담는다
      ...obstacles(configFile.text).map((pattern) => `${configFile.path}: ${pattern}`),
    ];
    expect(found).toEqual([]);  // 걸린 것이 없어야 함
    expect(routes(src.dirs, src.files)).toEqual([]);  // 문제 폴더도 없어야 함
  });
});
