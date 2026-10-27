import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// 탭 아이콘 SVG 를 글자로 읽는다. 브라우저가 XML 로 읽어 틀리면 그림이 깨진다
const svg = readFileSync(fileURLToPath(new URL("../src/app/icon.svg", import.meta.url)), "utf8");
// SVG 안의 XML 주석 안쪽 글을 모두 모음
const comments = [...svg.matchAll(/<!--([\s\S]*?)-->/g)].map((match) => match[1]);

describe("tab icon", () => {  // 탭 아이콘 테스트 묶음
  it("keeps xml comments well-formed", () => {  // XML 주석 모양이 올바른지 검사
    // 하이픈 둘이 들었거나 하이픈으로 끝나는 주석이 없어야 함
    expect(comments.filter((comment) => comment.includes("--") || comment.endsWith("-"))).toEqual([]);
  });
});
