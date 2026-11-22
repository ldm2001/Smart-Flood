import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// 빌드 뒤 out/ 검사(지시서 9장 6번). 빌드 끝에 postbuild 로 자동 실행
const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const PAGES = ["index.html", "ops/index.html", "logs/index.html"];  // 반드시 있어야 하는 세 화면
const ICON = "icon.svg";  // 탭 아이콘 파일 이름
// 탭 아이콘 링크 꼴. 없으면 브라우저가 /favicon.ico 를 찾다 404 를 냄
const ICON_LINK = /<link\b(?=[^>]*\brel="icon")(?=[^>]*\bhref="\/icon\.svg[?"])[^>]*>/;
const DISCLAIMER = "실제 재난 판단·재난문자에 쓸 수 없";  // 시험용 고지 문구의 일부
const DEV_API = "localhost:8000";  // 섞이면 안 되는 개발용 API 주소
const TEXT_FILE = /\.(html|js|txt|json)$/;  // 주소 검사 대상 글 파일 확장자

const problems = [];

for (const page of PAGES) {
  const path = join(OUT, page);
  if (!existsSync(path)) {
    problems.push(`없음: out/${page}`);
    continue;
  }
  const html = readFileSync(path, "utf8");
  if (!html.includes(DISCLAIMER)) problems.push(`시험용 고지 없음: out/${page}`);
  if (!ICON_LINK.test(html)) problems.push(`탭 아이콘 링크 없음: out/${page}`);
}
if (!existsSync(join(OUT, ICON))) problems.push(`없음: out/${ICON}`);

if (existsSync(OUT)) {
  for (const entry of readdirSync(OUT, { recursive: true })) {
    const path = join(OUT, entry);
    if (TEXT_FILE.test(entry) && statSync(path).isFile() && readFileSync(path, "utf8").includes(DEV_API)) {
      problems.push(`개발용 API 주소(${DEV_API}) 포함: out/${entry}`);
    }
  }
}

if (problems.length > 0) {
  console.error(`out/ 검사 실패\n${problems.map((problem) => `- ${problem}`).join("\n")}`);
  process.exit(1);
}
console.log(`out/ 검사 통과: ${[...PAGES, ICON].map((file) => `out/${file}`).join(", ")}`);
