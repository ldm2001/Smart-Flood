import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// 전역 스타일 파일을 글자로 읽는다. 줄바꿈 결과는 브라우저에서만 재서 여기선 규칙만 확인
const css = readFileSync(fileURLToPath(new URL("../src/app/globals.css", import.meta.url)), "utf8");
// html 규칙 안쪽 글을 꺼낸다. 없으면 빈 글자
const htmlRule = css.match(/\bhtml\s*\{([^}]*)\}/)?.[1] ?? "";

describe("korean line breaking", () => {  // 한글 줄바꿈 테스트 묶음
  // 한글을 어절째 두고 한 줄보다 긴 낱말만 끊는지 검사
  it("keeps korean words whole and breaks only words longer than a line", () => {
    // 낱말 끊기는 어절 단위 유지(keep-all)여야 함
    expect(htmlRule).toMatch(/\bword-break:\s*keep-all;/);
    // 너무 긴 낱말은 중간에서 끊어야 한다(break-word)
    expect(htmlRule).toMatch(/\boverflow-wrap:\s*break-word;/);
  });
});
