import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { stamp } from "@/lib/derive";
import type { StageEvent, Zone } from "@/lib/schema";
import { Compare } from "./Compare";

const T0 = Date.UTC(2026, 9, 22, 1, 0, 0);  // 회차 시작 시각(2026-10-22 10:00 KST)

// 경과 e 초에 구역이 previous 에서 stage 로 바뀐 사건
function shift(e: number, zone: Zone, previous: StageEvent["stage"], stage: StageEvent["stage"], etaSec: number | null) {
  return {
    type: "event",
    kind: "stage",
    elapsedSec: e,
    time: stamp(T0 + e * 1000),
    message: `${zone} 구역 ${stage}`,
    zone,
    stage,
    previous,
    etaSec,
  } as const satisfies StageEvent;
}

// 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("Compare", () => {
  // 판정 칸·현재 수위 경보 비교 문구·판정 수 줄을 보이는지 검사
  it("shows the verdict column, the level alarm note and the counts", () => {
    const events = [
      shift(10, "A", "safe", "warning", 20),
      shift(30, "A", "warning", "evacuate", 0),
      shift(40, "B", "safe", "warning", 15),
    ];
    const text = content(renderToStaticMarkup(<Compare events={events} />));
    expect(text).toContain("오차 판정");
    expect(text).toContain("20초 0초 적중");
    expect(text).toContain("대기");
    expect(text).toContain("현재 수위 경보는 한계에 닿을 때 울립니다. 선행 시간은 그보다 먼저 알린 초입니다.");
    expect(text).toContain("적중 1 · 누락 0 · 오경보 0");
    const ended = content(renderToStaticMarkup(<Compare events={events} ended />));
    expect(ended).toContain("적중 1 · 누락 0 · 오경보 1");
  });
});
