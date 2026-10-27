import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Headline } from "./StatusBanner";

// 태그를 지우고 글자만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("Headline", () => {  // 머리글 테스트 묶음
  // 단계 아이콘·이름·문구를 보여 주는지 검사
  it("shows the stage with its icon, label and message", () => {
    const html = renderToStaticMarkup(  // 경계 단계 배너를 그린다
      // 경계 단계, A 구역, 도달 문구를 가진 배너
      <Headline banner={{ stage: "warning", zoneId: "A", message: "A 낮은 상가 도로 · 약 10초 후 침수 예상" }} />,
    );
    // 구획에 낭독 속성과 단계 속성이 붙어야 함
    expect(html).toMatch(/^<section aria-live="polite" data-stage="warning"/);
    // 아이콘, 단계 이름, 문구가 차례로 보여야 함
    expect(content(html)).toContain("▲ 경계 A 낮은 상가 도로 · 약 10초 후 침수 예상");
  });

  // 자료가 오기 전에는 중립 문구로 기다리는지 검사
  it("waits with a neutral message before there is data", () => {
    const html = renderToStaticMarkup(<Headline banner={null} />);  // 배너 없이 그린다
    expect(html).toMatch(/^<section aria-live="polite"/);  // 낭독 속성은 있어야 함
    expect(html).not.toContain("data-stage");  // 단계 속성은 없어야 함
    // 자료 대기 문구가 보여야 함
    expect(content(html)).toContain("자료 대기 수위 자료를 기다리는 중입니다");
  });
});
