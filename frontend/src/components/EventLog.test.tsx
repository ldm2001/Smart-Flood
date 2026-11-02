import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { stamp } from "@/lib/derive";
import type { LogEvent } from "@/lib/schema";
import type { Events } from "@/lib/useEvents";
import { Journal } from "./EventLog";

const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const T0 = Date.UTC(2026, 9, 22, 1, 0, 0);  // 회차 시작 시각(2026-10-22 10:00 KST)
const FAULT: LogEvent = {  // 계산 오류 사건(154초)
  type: "event",
  kind: "calc_error",
  elapsedSec: 154,
  time: "2026-10-22T10:02:34.123456+09:00",
  message: "Underflow: A 저장량이 -0.001 m³ 다",
};
const FAILURE = "! 이벤트를 읽지 못했습니다.";

// 경과 e 초의 A 구역 주의 사건
function caution(e: number, message = `A 구역 주의 (이전 정상, 한계까지 ${e} 초)`): LogEvent {
  return {
    type: "event",
    kind: "stage",
    elapsedSec: e,
    time: stamp(T0 + e * 1000),
    message,
    zone: "A",
    stage: "caution",
    previous: "safe",
    etaSec: e,
  };
}

const draw = (log: Events | null) => renderToStaticMarkup(<Journal log={log} />);

describe("Journal", () => {
  it("shows the newest 30 of 31 events first", () => {
    const list = Array.from({ length: 31 }, (_, i) => caution(i + 1));
    const html = draw({ list, failed: false });
    const text = content(html);
    expect(html.match(/<li/g)).toHaveLength(30);
    expect(text.indexOf("10:00:31")).toBeLessThan(text.indexOf("10:00:30"));
    expect(text).toContain("10:00:02");
    expect(text).not.toContain("10:00:01");  // 가장 오래된 사건은 빠짐
    expect(text).toContain("10:00:31 △ A 구역 주의 (이전 정상, 한계까지 31 초)");
    expect(html).toContain(
      '<span aria-hidden="true" data-stage="caution" class="text-(--stage)">△</span>',
    );
  });

  it("marks a calculation error row", () => {
    const text = content(draw({ list: [caution(1), FAULT], failed: false }));
    expect(text).toContain("10:02:34 ! 계산 오류 Underflow: A 저장량이 -0.001 m³ 다");
    expect(text.indexOf("10:02:34")).toBeLessThan(text.indexOf("10:00:01"));
  });

  it("keeps the rows it has under the failure line", () => {
    const html = draw({ list: [caution(1)], failed: true });
    const text = content(html);
    expect(html.match(/<li/g)).toHaveLength(1);
    expect(text.indexOf(FAILURE)).toBeLessThan(text.indexOf("10:00:01"));
  });

  it("announces the list politely", () => {
    const logs = [null, { list: null, failed: false }, { list: [caution(1)], failed: true }];
    for (const log of logs) expect(draw(log)).toContain('<div aria-live="polite">');
  });

  it("shows markup in a message as text", () => {
    const html = draw({ list: [caution(1, "<b>A 구역</b>")], failed: false });
    expect(html).toContain("&lt;b&gt;A 구역&lt;/b&gt;");
    expect(html).not.toContain("<b>");
  });

  it("shows the waiting, loading, failed and empty states", () => {
    expect(content(draw(null))).toContain("이벤트 기록 —");
    expect(content(draw({ list: null, failed: false }))).toContain("이벤트를 읽는 중입니다.");
    const failed = content(draw({ list: null, failed: true }));
    expect(failed).toContain(FAILURE);
    expect(failed).not.toContain("읽는 중");
    expect(content(draw({ list: [], failed: false }))).toContain("표시할 이벤트가 없습니다.");
    const empty = content(draw({ list: [], failed: true }));
    expect(empty).toContain(FAILURE);
    expect(empty).toContain("표시할 이벤트가 없습니다.");
    expect(content(draw({ list: [], failed: false }))).not.toContain("!");
  });
});
