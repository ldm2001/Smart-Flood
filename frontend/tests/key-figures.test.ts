import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// 토큰 스타일 파일을 글자로 읽음. 핵심 수치(한계 대비 %, 남은 초)는 text-key 를 씀
const css = readFileSync(fileURLToPath(new URL("../src/styles/tokens.css", import.meta.url)), "utf8");
const theme = css.match(/@theme\s+inline\s*\{([^}]*)\}/)?.[1] ?? "";

describe("key figure size", () => {
  it("makes text-key 28 px", () => {  // text-key 가 28px 인지 검사(지시서 6장: 28px 이상)
    // 1.75rem 이어야 함(html 이 크기를 정하지 않아 기본 16px 이므로 28px)
    expect(theme).toMatch(/--text-key:\s*1\.75rem;/);
  });
});
