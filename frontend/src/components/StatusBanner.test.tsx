import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Headline } from "./StatusBanner";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");

describe("Headline", () => {
  it("shows the stage with its icon, label and message", () => {
    const html = renderToStaticMarkup(
      <Headline banner={{ stage: "warning", zoneId: "A", message: "A 낮은 상가 도로 · 약 10초 후 침수 예상" }} />,
    );
    expect(html).toMatch(/^<section aria-live="polite" data-stage="warning"/);
    expect(content(html)).toContain("[triangle] 경계 A 낮은 상가 도로 · 약 10초 후 침수 예상");
  });

  // 자료가 오기 전에는 중립 문구로 기다리는지 검사
  it("waits with a neutral message before there is data", () => {
    const html = renderToStaticMarkup(<Headline banner={null} />);
    expect(html).toMatch(/^<section aria-live="polite"/);
    expect(html).not.toContain("data-stage");
    expect(content(html)).toContain("[dots] 자료 대기 수위 자료를 기다리는 중입니다");
  });
});
