import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { stamp, type Stage } from "@/lib/derive";
import type { StageEvent, Zone } from "@/lib/schema";
import type { Events } from "@/lib/useEvents";
import { Timeline } from "./AlertTimeline";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
const T0 = Date.UTC(2026, 9, 22, 1, 0, 0);  // 회차 시작 시각(2026-10-22 10:00 KST)
const PHONE = /휴대전화 도착 확인 · 확인 불가\(시험 번호 미연결\)/g;
const FAILURE = "[error] 이벤트를 읽지 못했습니다";

// 경과 e 초에 구역이 previous 에서 stage 로 바뀐 사건
function shift(e: number, zone: Zone, previous: Stage, stage: Stage, etaSec: number | null) {
  return {
    type: "event",
    kind: "stage",
    elapsedSec: e,
    time: stamp(T0 + e * 1000),
    message: `${zone} 구역 ${stage} (이전 ${previous})`,
    zone,
    stage,
    previous,
    etaSec,
  } as const;
}

const R3: StageEvent[] = [  // 설계 1.3 의 기울기 측정 r3
  shift(63, "A", "safe", "evacuate", 0),
  shift(84, "B", "safe", "warning", 27),
  shift(122, "B", "warning", "safe", null),
  shift(132, "C", "safe", "caution", 41),
  shift(133, "C", "caution", "warning", 27),
  shift(135, "B", "safe", "warning", 1),
  shift(151, "C", "warning", "safe", null),
  shift(153, "B", "warning", "evacuate", 0),
];
const draw = (log: Events | null) => content(renderToStaticMarkup(<Timeline log={log} />));

describe("Timeline", () => {
  it("shows the judgement, request, arrival and lead of each zone", () => {
    const text = draw({ list: R3, failed: false });
    for (const part of [
      "A 낮은 상가 도로 위험 판단 10:01:03 · [waves] 침수(경보) 문자 요청(SMS 예정) " +
        "10:01:03 · 기록만, 실제 발송 차단 실제 도달(경보) 10:01:03 선행 시간 0초",
      "B 주택 골목 위험 판단 10:02:15 · [triangle] 경계 문자 요청(SMS 예정) " +
        "10:02:15 · 기록만, 실제 발송 차단 실제 도달(경보) 10:02:33 선행 시간 18초",
      "C 높은 광장 위험 판단 10:02:12 · [alert] 주의 문자 요청(SMS 예정) " +
        "10:02:13 · 기록만, 실제 발송 차단 실제 도달(경보) — 선행 시간 —",
    ]) {
      expect(text).toContain(part);
    }
    expect(text.match(PHONE)).toHaveLength(1);
  });

  it("marks the lead with the key figure style and tags the heading with its zone", () => {
    const html = renderToStaticMarkup(<Timeline log={{ list: R3, failed: false }} />);
    expect(html).toContain('<dd class="text-key font-medium tabular-nums">18초</dd>');
    expect(html).toContain('<h3 data-zone="B" class="');
  });

  it("shows dashes for a zone without a run", () => {
    const text = draw({ list: R3.filter((event) => event.zone === "A"), failed: false });
    expect(text).toContain(
      "B 주택 골목 위험 판단 — 문자 요청(SMS 예정) — 실제 도달(경보) — 선행 시간 —",
    );
    expect(text).not.toContain(FAILURE);
  });

  it("keeps the rows it has under the failure line", () => {
    const text = draw({ list: R3, failed: true });
    expect(text).toContain(FAILURE);
    expect(text).toContain("선행 시간 18초");
    expect(text.indexOf(FAILURE)).toBeLessThan(text.indexOf("A 낮은 상가 도로"));
  });

  it("keeps the layout with dashes before the events arrive", () => {
    for (const log of [null, { list: null, failed: false }]) {
      const text = draw(log);
      expect(text.match(/—/g)).toHaveLength(12);
      expect(text.match(/선행 시간/g)).toHaveLength(3);
      expect(text.match(PHONE)).toHaveLength(1);
      expect(text).not.toMatch(/\d{2}:\d{2}:\d{2}/);
    }
  });
});
