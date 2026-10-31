import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = fileURLToPath(new URL("..", import.meta.url));  // frontend 폴더 경로
const CODE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;

// 파일 하나의 경로와 내용을 담는 타입
interface Entry {
  path: string;  // frontend 기준 경로(구분자는 슬래시)
  text: string;  // 파일 내용 글
}

// 폴더 아래 코드 파일과 하위 폴더를 모두 모으는 함수
function tree(relativeDir: string): { files: Entry[]; dirs: string[] } {
  const files: Entry[] = [];
  const dirs: string[] = [];
  for (const entry of readdirSync(join(ROOT, relativeDir), { recursive: true }) as string[]) {
    const path = `${relativeDir}/${entry.split("\\").join("/")}`;
    if (statSync(join(ROOT, path)).isDirectory()) dirs.push(path);
    else if (CODE.test(path)) files.push({ path, text: readFileSync(join(ROOT, path), "utf8") });
  }
  return { files, dirs };
}

// 4번 검사: 파생값을 뜻하는 낱말(심각도·남은 시간·비율·이름표·만료 등)
const DERIVED_WORD = /^(severity|severities|eta|etas|percent|percentage|ratio|ratios|label|labels|worst|stale|staleness)$/;

// 이름을 낱말 조각들로 나누는 함수
function words(name: string): string[] {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .split(/[\s_$]+/)
    .filter(Boolean)
    .map((word) => word.toLowerCase());
}

// 파생값 이름의 상태 훅과 [값, 설정] 꼴이 아닌 호출을 찾는 함수
function derivations(text: string): string[] {
  const problems: string[] = [];
  const calls = text.match(/\buseState\s*[<(]/g)?.length ?? 0;
  const declared = [...text.matchAll(/\[\s*([\w$]+)\s*(?:,\s*([\w$]+)\s*)?\]\s*=\s*(?:React\s*\.\s*)?useState\b/g)];
  if (declared.length !== calls) problems.push(`useState 호출 ${calls}개 중 ${declared.length}개만 [값, 설정] 꼴`);
  for (const match of declared) {
    for (const name of [match[1], match[2]]) {
      if (name && words(name).some((word) => DERIVED_WORD.test(word))) problems.push(name);
    }
  }
  return problems;
}

const IMPURE = [  // 5번 검사: 렌더 경로에서 직접 부르면 안 되는 시각·난수 호출 모양
  /\bDate\s*\.\s*now\s*\(/,
  /\bnew\s+Date\b/,
  /(?<![\w$.])Date\s*\(/,  // 날짜 함수를 그냥 부르는 모양(점 뒤는 제외)
  /\bMath\s*\.\s*random\s*\(/,
  /\bcrypto\s*\.\s*randomUUID\s*\(/,
];
const CLOCK_FILE = "src/lib/useNow.ts";

const impurities = (text: string) => IMPURE.filter((pattern) => pattern.test(text)).map(String);

const CLOCK_READERS = new Set([CLOCK_FILE, "src/lib/useNow.test.ts", "src/lib/api.ts"]);

// 허용 밖에서 벽시계를 쓰는 파일 경로를 모으는 함수
const readers = (files: Entry[]) =>
  files.filter((file) => !CLOCK_READERS.has(file.path) && /\bwall\b/.test(file.text)).map((file) => file.path);

const EXPORT_BLOCKERS = [  // 7번 검사: 정적 export 가 서비스할 수 없는 기능의 모양들
  /\buse server\b/,
  /\brewrites\s*\(/,
  /\bredirects\s*\(/,
  /\bheaders\s*\(/,
  /\bcookies\s*\(/,
  /\bnext\/(legacy\/)?image\b/,
];

const barriers = (text: string) => EXPORT_BLOCKERS.filter((pattern) => pattern.test(text)).map(String);

const CONFIG_BLOCKERS = [/\brewrites\s*:/, /\bredirects\s*:/, /\bheaders\s*:/];

const obstacles = (text: string) => [
  ...barriers(text),
  ...CONFIG_BLOCKERS.filter((pattern) => pattern.test(text)).map(String),
];

// generateStaticParams 없는 [id] 폴더와 가로채기 폴더(지시서 3장)를 찾는 함수
function routes(dirs: string[], files: Entry[]): string[] {
  const problems: string[] = [];
  for (const dir of dirs) {
    const name = dir.split("/").at(-1) ?? "";
    if (/^\(\.{1,3}\)/.test(name)) problems.push(dir);
    if (/^\[.+\]$/.test(name)) {
      const inside = files.filter((file) => file.path.startsWith(`${dir}/`));
      if (!inside.some((file) => file.text.includes("generateStaticParams"))) problems.push(dir);
    }
  }
  return problems;
}

const src = tree("src");
const viewFiles = src.files.filter((file) => /^src\/(components|app)\//.test(file.path));
const configFile: Entry = {
  path: "next.config.mjs",
  text: readFileSync(join(ROOT, "next.config.mjs"), "utf8"),
};

describe("check 4: no useState for derived values", () => {
  it("catches the forbidden names in a sample", () => {
    const sample = [
      "const [etaSec, setEtaSec] = useState<number | null>(null);",  // 남은 초 이름: 걸려야 함
      "const [isStale, setIsStale] = React.useState(false);",
      "const [zoneLabel, setZoneLabel] = useState('');",  // 이름표 이름: 걸려야 함
      "const [meta, setMeta] = useState(0);",
      "const [selectedZoneId, setSelectedZoneId] = useState<'A' | 'B' | 'C'>('A');",
      "const pair = useState(0);",  // 짝 꼴이 아닌 호출: 꼴 문제로 걸려야 함
    ].join("\n");
    expect(derivations(sample)).toEqual([
      "useState 호출 6개 중 5개만 [값, 설정] 꼴",
      "etaSec",
      "setEtaSec",
      "isStale",
      "setIsStale",
      "zoneLabel",
      "setZoneLabel",
    ]);
  });

  it("scans src/components and src/app", () => {
    expect(viewFiles.length).toBeGreaterThan(0);
    const found = viewFiles.flatMap((file) => derivations(file.text).map((name) => `${file.path}: ${name}`));
    expect(found).toEqual([]);
  });
});

describe("check 5: no clock or random reads outside useNow.ts", () => {
  it("catches direct calls in a sample", () => {
    // 조각을 이어 붙여 예시를 만듦. 이 파일이 스스로 걸리지 않게 나눠 둠
    const sample = ["const a = Date", ".now();", "const b = new ", "Date();", "const c = Math", ".random();"].join("");
    expect(impurities(sample)).toHaveLength(4);
    expect(impurities("const t = Date.UTC(2026, 9, 23); const p = Date.parse(s); type T = Date;")).toEqual([]);
  });

  it("catches wall outside the fetcher in a sample", () => {
    const files = [
      { path: "src/components/Clock.tsx", text: "import { wall } from '@/lib/useNow';\nconst t = wall();" },
      { path: "src/lib/derive.ts", text: "const tick = wall;" },
      { path: "src/lib/api.ts", text: "receivedAt: wall()," },
      { path: "src/lib/useNow.ts", text: "export function wall(): number {" },
      { path: "src/lib/schema.ts", text: "const wallpaper = 1;" },
    ];
    expect(readers(files)).toEqual(["src/components/Clock.tsx", "src/lib/derive.ts"]);
  });

  it("scans every file under src, tests included", () => {
    expect(src.files.some((file) => file.path === CLOCK_FILE)).toBe(true);
    const found = src.files
      .filter((file) => file.path !== CLOCK_FILE)
      .flatMap((file) => impurities(file.text).map((pattern) => `${file.path}: ${pattern}`));
    expect(found).toEqual([]);
  });

  it("lets only the fetcher in api.ts read the clock through wall", () => {
    expect(src.files.filter((file) => /\bwall\b/.test(file.text)).map((file) => file.path)).toContain("src/lib/api.ts");
    expect(readers(src.files)).toEqual([]);
  });
});

describe("check 7: nothing that static export cannot serve", () => {
  it("catches server-only features in a sample", () => {
    const sample = [
      "'use server';",
      "async rewrites() { return []; }",
      "async redirects() { return []; }",
      "async headers() { return []; }",
      "const jar = await cookies();",
      "import Image from 'next/image';",
    ].join("\n");
    expect(barriers(sample)).toHaveLength(6);
    expect(barriers("fetch(url, { headers: { Accept: 'application/json' } }); new Headers();")).toEqual([]);
  });

  it("catches the property form in next.config", () => {
    const sample = "export default { rewrites: async () => [], redirects: async () => [], headers: async () => [] };";
    expect(obstacles(sample)).toHaveLength(3);
    expect(obstacles('export default { output: "export", trailingSlash: true };')).toEqual([]);
  });

  it("catches dynamic folders without generateStaticParams and intercepting folders", () => {
    const dirs = ["src/app/logs", "src/app/logs/[id]", "src/app/runs/[run]", "src/app/(.)photo"];
    const files = [
      { path: "src/app/logs/[id]/page.tsx", text: "export default function Page() { return null; }" },
      { path: "src/app/runs/[run]/page.tsx", text: "export function generateStaticParams() { return []; }" },
    ];
    expect(routes(dirs, files)).toEqual(["src/app/logs/[id]", "src/app/(.)photo"]);
  });

  it("scans src and next.config.mjs", () => {
    const found = [
      ...src.files.flatMap((file) => barriers(file.text).map((pattern) => `${file.path}: ${pattern}`)),
      ...obstacles(configFile.text).map((pattern) => `${configFile.path}: ${pattern}`),
    ];
    expect(found).toEqual([]);
    expect(routes(src.dirs, src.files)).toEqual([]);
  });
});
