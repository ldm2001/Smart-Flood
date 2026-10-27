// 빌드 뒤 out/ 을 검사하는 스크립트(지시서 9장 6번). 파일 도구를 가져온다
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
// 경로 잇기 도구를 가져온다
import { join } from "node:path";
// 주소를 경로로 바꾸는 도구를 가져온다
import { fileURLToPath } from "node:url";

// 검사할 out 폴더 경로. 빌드 끝에 postbuild 로 자동 실행된다
const OUT = fileURLToPath(new URL("../out/", import.meta.url));
// 반드시 있어야 하는 세 화면의 html
const PAGES = ["index.html", "ops/index.html", "logs/index.html"];
// 탭 아이콘 파일 이름
const ICON = "icon.svg";
// 탭 아이콘 링크 패턴. 없으면 브라우저가 /favicon.ico 를 찾다 404 를 낸다
const ICON_LINK = /<link\b(?=[^>]*\brel="icon")(?=[^>]*\bhref="\/icon\.svg[?"])[^>]*>/;
// 시험용 고지 문구의 일부
const DISCLAIMER = "실제 재난 판단·재난문자에 쓸 수 없";
// 섞이면 안 되는 개발용 API 주소
const DEV_API = "localhost:8000";
// 주소 검사 대상 글 파일 확장자
const TEXT_FILE = /\.(html|js|txt|json)$/;

// 찾은 문제를 모을 목록
const problems = [];

// 화면마다 확인한다
for (const page of PAGES) {
  // 화면 파일 경로
  const path = join(OUT, page);
  // 파일이 없으면
  if (!existsSync(path)) {
    // 없다고 문제에 적는다
    problems.push(`없음: out/${page}`);
    // 이 화면은 더 보지 않고 넘어간다
    continue;
  }
  // 화면 html 을 읽는다
  const html = readFileSync(path, "utf8");
  // 시험용 고지 문구가 없으면 문제로 적는다
  if (!html.includes(DISCLAIMER)) problems.push(`시험용 고지 없음: out/${page}`);
  // 탭 아이콘 링크가 없으면 문제로 적는다
  if (!ICON_LINK.test(html)) problems.push(`탭 아이콘 링크 없음: out/${page}`);
}
// 아이콘 파일이 없으면 문제로 적는다
if (!existsSync(join(OUT, ICON))) problems.push(`없음: out/${ICON}`);

// out 폴더가 있으면
if (existsSync(OUT)) {
  // 하위 모든 항목을 하나씩 본다
  for (const entry of readdirSync(OUT, { recursive: true })) {
    // 항목의 전체 경로
    const path = join(OUT, entry);
    // 글 파일이면서 개발용 API 주소가 들어 있으면
    if (TEXT_FILE.test(entry) && statSync(path).isFile() && readFileSync(path, "utf8").includes(DEV_API)) {
      // 문제로 적는다
      problems.push(`개발용 API 주소(${DEV_API}) 포함: out/${entry}`);
    }
  }
}

// 문제가 하나라도 있으면
if (problems.length > 0) {
  // 문제 목록을 오류로 찍는다
  console.error(`out/ 검사 실패\n${problems.map((problem) => `- ${problem}`).join("\n")}`);
  // 실패 코드 1 로 끝낸다
  process.exit(1);
}
// 통과하면 검사한 파일 목록을 알린다
console.log(`out/ 검사 통과: ${[...PAGES, ICON].map((file) => `out/${file}`).join(", ")}`);
