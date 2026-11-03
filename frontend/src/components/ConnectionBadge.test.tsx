import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Signal } from "./ConnectionBadge";

const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("Signal", () => {
  // 첫 응답 전에는 시각 없이 연결 중인지 검사
  it("says it is connecting before the first answer, without a time", () => {
    const html = renderToStaticMarkup(
      <Signal view="connecting" now={null} receivedAt={null} failed={false} />,
    );
    expect(content(html)).toContain("연결 중");
    expect(html).toContain('data-conn="wait"');
    expect(content(html)).not.toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("is connected while the last good answer is at most 4 s old", () => {
    const html = renderToStaticMarkup(  // 그 사이 실패가 있어도 4초 안이면 정상
      <Signal view="server" now={T + 4000} receivedAt={T} failed />,
    );
    expect(content(html)).toContain("연결 정상");
    expect(content(html)).toContain("마지막 수신 10:00:00");
    expect(html).toContain('data-conn="ok"');
  });

  it("is lost when a poll failed more than 4 s after the last answer, keeping that time", () => {
    const html = renderToStaticMarkup(
      <Signal view="server" now={T + 4001} receivedAt={T} failed />,
    );
    expect(content(html)).toContain("연결 끊김");
    expect(content(html)).toContain("마지막 수신 10:00:00");  // 마지막 수신 시각이 그대로여야 함
    expect(html).toContain('data-conn="lost"');
  });

  // 화면을 옮겨 돌아온 직후처럼 묵은 응답만 있고 실패가 없으면 끊김이 아님
  it("keeps connecting when the last answer is old but no poll has failed", () => {
    const html = renderToStaticMarkup(
      <Signal view="server" now={T + 4001} receivedAt={T} failed={false} />,
    );
    expect(content(html)).toContain("연결 중");
    expect(html).toContain('data-conn="wait"');
    expect(content(html)).not.toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("is lost with no receive time when the server never answered", () => {
    const html = renderToStaticMarkup(<Signal view="mock" now={T} receivedAt={null} failed />);
    expect(content(html)).toContain("연결 끊김");
    expect(content(html)).toContain("마지막 수신 —");
    expect(html).toContain('data-conn="lost"');
  });

  it("gives each state its own icon next to the text", () => {
    const icon = (badge: ReactElement) =>
      renderToStaticMarkup(badge).match(/data-icon="([^"]+)"/)?.[1];
    const icons = [
      icon(<Signal view="connecting" now={null} receivedAt={null} failed={false} />),
      icon(<Signal view="server" now={T} receivedAt={T} failed={false} />),
      icon(<Signal view="server" now={T + 5000} receivedAt={T} failed />),
    ];
    expect(icons.every(Boolean)).toBe(true);
    expect(new Set(icons).size).toBe(3);
  });
});
