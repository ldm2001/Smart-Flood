import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { roster, type Thresholds } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Snapshot } from "@/lib/schema";
import { Plan } from "./CityPlan";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
const SIM = demo(Date.UTC(2026, 9, 23, 1, 1, 10), THRESHOLDS);  // 10:01:10 KST 의 가상 상태
const FULL = { location: "INLET-03", type: "full", label: "빗물받이 ③ 완전 막힘" } as const;
const CLEAR = { location: null, type: "none", label: "정상 배수" } as const;

// 상태의 alerts 로 단계를 구해 그린 평면도
function draw(snapshot: Snapshot | null, thresholds: Thresholds | null = THRESHOLDS) {
  const statuses = snapshot && roster(snapshot.alerts);
  return renderToStaticMarkup(
    <Plan snapshot={snapshot} statuses={statuses} thresholds={thresholds} />,
  );
}

describe("Plan", () => {
  it("marks a fully blocked inlet in red and a heavier weight", () => {
    const html = draw({ ...SIM, blockage: FULL });
    const text = content(html);
    expect(html).toMatch(/<span class="[^"]*font-medium text-\(--red\)" style="[^"]*">③<\/span>/);
    expect(html).toContain('<circle class="fill-panel stroke-(--red)');
    expect(html).toContain('<p class="chip border border-(--red) text-(--red)">');
    expect(text).toContain("[ban] 빗물받이 ③ 완전 막힘");
    expect(text).toContain("③ INLET-03 · B 구역 · [ban] 완전 막힘");
    expect(text).toContain("② INLET-02 · A 구역 · [circle] 막힘 없음");
  });

  it("marks the partial blockage of the simulation in amber", () => {
    const html = draw(SIM);
    expect(html).toMatch(/<span class="[^"]*font-medium text-amber" style="[^"]*">②<\/span>/);
    expect(html).toContain('<circle class="fill-panel stroke-amber');
    expect(content(html)).toContain("[half] 빗물받이 ② 부분 막힘");
  });

  it("shows a clear drain when nothing is blocked", () => {
    const html = draw({ ...SIM, blockage: CLEAR });
    const text = content(html);
    expect(html).toContain('<p class="chip border border-line">');
    expect(text).toContain("[circle] 정상 배수");
    expect(text.match(/\[circle\] 막힘 없음/g)).toHaveLength(3);
    expect(html).not.toMatch(/font-medium text-(amber|\(--red\))/);  // 굵은 막힘 색 번호 없음
  });

  it("fills the water from the bottom by the threshold ratio", () => {
    const zones = { ...SIM.zones, A: { ...SIM.zones.A, levelMm: 22.5 } };  // A 한계 45 의 절반
    expect(draw({ ...SIM, zones })).toContain(
      '<rect class="fill-brand/35" x="10" y="60" width="90" height="50"></rect>',
    );
    expect(draw(SIM, null)).not.toContain("fill-brand/35");
  });

  it("lists each zone with its level, stage and source", () => {
    const html = draw(SIM);
    const text = content(html);
    expect(text).toContain("A 낮은 상가 도로 · 44.9 mm · [triangle] 경계 · 가상 실측");
    expect(text).toContain("B 주택 골목 · 31.8 mm · [check] 정상 · 가상 실측");
    expect(text).toContain("C 높은 광장 · 18.7 mm · [check] 정상 · 모델 추정");
    expect(html.match(/>추정<\/span>/g)).toHaveLength(1);  // 추정 표시는 C 하나
    expect(html).toContain(
      '<rect data-stage="warning" class="fill-none stroke-(--alert,var(--muted))',
    );
  });

  it("shows the drain meter", () => {
    const text = content(draw(SIM));
    expect(text).toContain("하부 배수 계량 누적 배수량 0.76 L 유량 0.65 L/min");
  });

  it("shows the notes and no threshold text", () => {
    for (const snapshot of [SIM, null]) {
      const text = content(draw(snapshot));
      expect(text).toContain(
        "C 구역은 수위 센서가 없어 늘 모델로 추정합니다. " +
          "A·B 도 최근 관측이 없는 동안은 추정값입니다.",
      );
      expect(text).toContain(
        "위험 단계는 서버가 판정합니다. 실측 중 센서가 있는 구역은 관측 수위와 최근 20초 상승 " +
          "속도로, 그 밖에는 보정된 모델 수위로 판정합니다.",
      );
      expect(text).not.toMatch(/한계 —|한계 \d/);
    }
  });

  it("shows dashes while connecting", () => {
    const html = draw(null, null);
    const text = content(html);
    expect(text).toContain("① INLET-01 · A 구역 · —");
    expect(text).toContain("A 낮은 상가 도로 · —");
    expect(text).toContain("누적 배수량 — 유량 —");
    expect(html).not.toContain("fill-brand/35");
    expect(html).not.toContain("data-stage");
    expect(html).not.toContain("chip border");
    expect(text).not.toMatch(/\d{2}:\d{2}:\d{2}|가상|EXP-/);
  });
});
