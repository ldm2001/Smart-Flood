import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Guard } from "./Guard";

const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const QUESTION = "회차를 종료할까요? 비가 그치고 마지막 상태가 남습니다";  // 종료 물음

// 종료 확인 줄
const html = renderToStaticMarkup(
  <Guard control="stop" name="종료" question={QUESTION} onYes={() => {}} onNo={() => {}} />,
);

describe("Guard", () => {
  it("is a named group holding the question, yes and cancel", () => {
    expect(html).toMatch(/^<div role="group" aria-label="종료 확인" data-opener="ops-stop" class=/);
    expect(content(html)).toBe(` ${QUESTION} 예 취소 `);
  });

  // 초점 자리 표시는 취소에만 있고 autofocus 는 없는지 검사
  it("marks only cancel for the first focus and leaves out autofocus", () => {
    expect(html.match(/data-cancel/g)).toHaveLength(1);
    expect(html).toMatch(/<button type="button" data-cancel="true" class="[^"]+">취소<\/button>/);
    expect(html).toMatch(/<button type="button" class="[^"]+">예<\/button>/);
    expect(html.toLowerCase()).not.toContain("autofocus");
  });

  it("names the button it opened from", () => {
    const live = renderToStaticMarkup(
      <Guard control="live" name="실측으로 바꾸기" question="?" onYes={() => {}} onNo={() => {}} />,
    );
    expect(live).toContain('aria-label="실측으로 바꾸기 확인" data-opener="ops-live"');
  });
});
