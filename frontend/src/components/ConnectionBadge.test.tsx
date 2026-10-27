import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Signal } from "./ConnectionBadge";

// 기준 시각 10:00:00 KST. 끊김은 마지막 수신 후 4초가 넘을 때다
const T = Date.UTC(2026, 9, 25, 1, 0, 0);
// 태그를 지우고 글자만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("Signal", () => {  // 연결 배지 테스트 묶음
  // 첫 응답 전에는 시각 없이 연결 중인지 검사
  it("says it is connecting before the first answer, without a time", () => {
    // 응답이 없는 배지를 그린다
    const html = renderToStaticMarkup(<Signal view="connecting" now={null} receivedAt={null} />);
    expect(content(html)).toContain("연결 중");  // 연결 중 문구여야 함
    expect(html).toContain('data-conn="wait"');  // 대기 상태 표시여야 함
    expect(content(html)).not.toMatch(/\d{2}:\d{2}:\d{2}/);  // 시각이 보이면 안 됨
  });

  // 마지막 정상 응답이 4초 이내면 정상인지 검사
  it("is connected while the last good answer is at most 4 s old", () => {
    // 4초 지난 시점의 배지를 그린다
    const html = renderToStaticMarkup(<Signal view="server" now={T + 4000} receivedAt={T} />);
    expect(content(html)).toContain("연결 정상");  // 정상 문구여야 함
    expect(content(html)).toContain("마지막 수신 10:00:00");  // 마지막 수신 시각이 보여야 함
    expect(html).toContain('data-conn="ok"');  // 정상 상태 표시여야 함
  });

  // 4초가 넘으면 끊김이고 마지막 수신 시각을 계속 보이는지 검사
  it("is lost after 4 s and keeps showing the last receive time", () => {
    // 4.001초 지난 시점의 배지를 그린다
    const html = renderToStaticMarkup(<Signal view="server" now={T + 4001} receivedAt={T} />);
    expect(content(html)).toContain("연결 끊김");  // 끊김 문구여야 함
    expect(content(html)).toContain("마지막 수신 10:00:00");  // 마지막 수신 시각이 그대로여야 함
    expect(html).toContain('data-conn="lost"');  // 끊김 상태 표시여야 함
  });

  // 서버가 한 번도 답하지 않으면 시각 없이 끊김인지 검사
  it("is lost with no receive time when the server never answered", () => {
    // 수신 기록이 없는 배지를 그린다
    const html = renderToStaticMarkup(<Signal view="mock" now={T} receivedAt={null} />);
    expect(content(html)).toContain("연결 끊김");  // 끊김 문구여야 함
    expect(content(html)).toContain("마지막 수신 —");  // 시각 자리가 줄표여야 함
    expect(html).toContain('data-conn="lost"');  // 끊김 상태 표시여야 함
  });

  // 상태마다 다른 아이콘이 글 옆에 있는지 검사
  it("gives each state its own icon next to the text", () => {
    // 배지 안의 아이콘 글자를 뽑는 도우미
    const icon = (html: string) => html.match(/<span aria-hidden="true">([^<]+)<\/span>/)?.[1];
    const icons = [  // 세 상태의 아이콘을 모음
      // 대기 상태
      icon(renderToStaticMarkup(<Signal view="connecting" now={null} receivedAt={null} />)),
      icon(renderToStaticMarkup(<Signal view="server" now={T} receivedAt={T} />)),  // 정상 상태
      // 끊김 상태
      icon(renderToStaticMarkup(<Signal view="server" now={T + 5000} receivedAt={T} />)),
    ];
    expect(icons.every(Boolean)).toBe(true);  // 아이콘이 모두 있어야 함
    expect(new Set(icons).size).toBe(3);  // 세 아이콘이 서로 달라야 함
  });
});
