import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Signal } from "./ConnectionBadge";

const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("Signal", () => {
  // 첫 응답 전에는 시각 없이 연결 중인지 검사
  it("says it is connecting before the first answer, without a time", () => {
    const html = renderToStaticMarkup(<Signal view="connecting" now={null} receivedAt={null} />);
    expect(content(html)).toContain("연결 중");
    expect(html).toContain('data-conn="wait"');
    expect(content(html)).not.toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("is connected while the last good answer is at most 4 s old", () => {
    const html = renderToStaticMarkup(<Signal view="server" now={T + 4000} receivedAt={T} />);
    expect(content(html)).toContain("연결 정상");
    expect(content(html)).toContain("마지막 수신 10:00:00");
    expect(html).toContain('data-conn="ok"');
  });

  it("is lost after 4 s and keeps showing the last receive time", () => {
    const html = renderToStaticMarkup(<Signal view="server" now={T + 4001} receivedAt={T} />);
    expect(content(html)).toContain("연결 끊김");
    expect(content(html)).toContain("마지막 수신 10:00:00");  // 마지막 수신 시각이 그대로여야 함
    expect(html).toContain('data-conn="lost"');
  });

  it("is lost with no receive time when the server never answered", () => {
    const html = renderToStaticMarkup(<Signal view="mock" now={T} receivedAt={null} />);
    expect(content(html)).toContain("연결 끊김");
    expect(content(html)).toContain("마지막 수신 —");
    expect(html).toContain('data-conn="lost"');
  });

  it("gives each state its own icon next to the text", () => {
    const icon = (html: string) => html.match(/<span aria-hidden="true">([^<]+)<\/span>/)?.[1];
    const icons = [
      icon(renderToStaticMarkup(<Signal view="connecting" now={null} receivedAt={null} />)),
      icon(renderToStaticMarkup(<Signal view="server" now={T} receivedAt={T} />)),
      icon(renderToStaticMarkup(<Signal view="server" now={T + 5000} receivedAt={T} />)),
    ];
    expect(icons.every(Boolean)).toBe(true);
    expect(new Set(icons).size).toBe(3);
  });
});
