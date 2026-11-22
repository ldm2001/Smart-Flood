import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { gates } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Blockage, Input, Snapshot } from "@/lib/schema";
import { BlockagePanel } from "./BlockagePanel";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
// 적용 단추의 여는 태그
const button = (html: string) => html.match(/<button[^>]* id="ops-blockage"[^>]*>/)?.[0] ?? "";
// 이름과 값이 맞는 라디오 태그
const radio = (html: string, name: string, value: string) =>
  html.match(new RegExp(`<input [^>]*name="${name}"[^>]* value="${value}"[^>]*>`))?.[0] ?? "";
// 빗물받이 묶음의 여는 태그
const inlets = (html: string) => html.match(/<fieldset[^>]*>(?=<legend[^>]*>빗물받이)/)?.[0] ?? "";
const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const LIMITS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
const CLEAR = { location: null, type: "none", label: "정상 배수" } as const;  // 막힘 없는 서버 값

// 입력원과 막힘을 정한 대기 상태. 막힘을 안 주면 demo 의 ② 부분 막힘
function state(dataSource: Input = "sim", blockage?: Snapshot["blockage"]): Snapshot {
  const snapshot = demo(T, LIMITS);
  return { ...snapshot, runState: "idle", dataSource, blockage: blockage ?? snapshot.blockage };
}

// online 판정으로 그린 막힘 칸. 고른 값을 줄 수 있음
function markup(
  snapshot: Snapshot | null,
  kind: Blockage | null = null,  // 고른 종류
  inlet: string | null = null,  // 고른 빗물받이
) {
  return renderToStaticMarkup(
    <BlockagePanel
      snapshot={snapshot}
      gate={gates("online", T, snapshot, null).blockage}
      onSend={() => Promise.resolve(false)}
      kind={kind}
      inlet={inlet}
      onKind={() => {}}
      onInlet={() => {}}
    />,
  );
}

describe("BlockagePanel", () => {
  it("shows the server blockage as a toned chip and checks its kind and inlet", () => {
    const html = markup(state());
    expect(html).toContain('<p class="chip border border-amber text-amber">');
    expect(content(html)).toContain("[half] 빗물받이 ② 부분 막힘");
    expect(radio(html, "ops-kind", "partial")).toContain('checked=""');
    expect(radio(html, "ops-inlet", "INLET-02")).toContain('checked=""');
    expect(radio(html, "ops-inlet", "INLET-01")).not.toContain('checked=""');
    expect(content(html)).toContain(
      "종류 [circle] 막힘 없음 [half] 부분 막힘 [ban] 완전 막힘 빗물받이 ① INLET-01 ② INLET-02 ③ INLET-03",
    );
    expect(button(html)).not.toContain('aria-disabled="');
  });

  it("blocks the inlet choice when nothing is blocked", () => {
    const html = markup(state("sim", CLEAR));
    expect(html).toContain('<p class="chip border border-line">');
    expect(content(html)).toContain("[circle] 정상 배수");
    expect(radio(html, "ops-kind", "none")).toContain('checked=""');
    expect(inlets(html)).toContain('disabled=""');
    expect(html.match(/name="ops-inlet"[^>]*checked/g)).toBeNull();
    expect(button(html)).not.toContain('aria-disabled="');
  });

  it("prefers the picked kind and inlet over the server values", () => {
    const html = markup(state(), "full", "INLET-03");
    expect(radio(html, "ops-kind", "full")).toContain('checked="" value="full"');
    expect(radio(html, "ops-kind", "partial")).not.toContain('checked=""');
    expect(radio(html, "ops-inlet", "INLET-03")).toContain('checked=""');
    expect(radio(html, "ops-inlet", "INLET-02")).not.toContain('checked=""');
    expect(inlets(html)).not.toContain('disabled=""');
  });

  it("keeps apply off until an inlet is picked for a blockage", () => {
    const html = markup(state("sim", CLEAR), "partial");
    expect(inlets(html)).not.toContain('disabled=""');
    expect(button(html)).toContain('aria-disabled="true" aria-describedby="ops-why-blockage"');
    expect(html).toContain('<li id="ops-why-blockage">막을 빗물받이를 골라 주세요</li>');
  });

  it("shows the reason of a replay and the halt line before the first answer", () => {
    const replay = markup(state("replay"));
    expect(button(replay)).toContain('aria-describedby="ops-why-blockage"');
    expect(replay).toContain(
      '<li id="ops-why-blockage">재생 중에는 막힘을 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다</li>',
    );
    const empty = markup(null);
    expect(empty).toContain('<p class="chip border border-line">—</p>');
    expect(button(empty)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    expect(radio(empty, "ops-kind", "none")).toContain('checked=""');
  });
});
