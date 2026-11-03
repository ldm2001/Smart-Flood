import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Zone } from "@/lib/schema";
import { LimitPanel } from "./LimitPanel";

const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
// 단추 하나의 여는 태그
const button = (html: string, id: string) =>
  html.match(new RegExp(`<button[^>]* id="${id}"[^>]*>`))?.[0] ?? "";
// 구역 입력 칸의 태그
const field = (html: string, id: Zone) =>
  html.match(new RegExp(`<input[^>]* id="ops-limit-${id}"[^>]*>`))?.[0] ?? "";
const LIMITS = { A: 45, B: 55, C: 65 };  // 서버와 저장값의 한계 수위(mm)
const NOTE = "가상 데이터용 값은 서버에 연결되지 않은 / 화면에만 쓰입니다.";  // 쓰이는 곳 안내 글

// 서버 값과 고치는 중인 글로 그린 한계 수위 칸
function draw(draft: Partial<Record<Zone, string>> = {}, limits: typeof LIMITS | null = LIMITS) {
  return renderToStaticMarkup(
    <LimitPanel limits={limits} saved={LIMITS} draft={draft} onDraft={() => {}} />,
  );
}

describe("LimitPanel", () => {
  it("shows dashes until the server setting arrives, then its values", () => {
    expect(content(draw({}, null))).toContain(
      "서버 설정(config.yaml) · 읽기 전용 A 낮은 상가 도로 — B 주택 골목 — C 높은 광장 —",
    );
    expect(content(draw())).toContain("A 낮은 상가 도로 45 mm B 주택 골목 55 mm C 높은 광장 65 mm");
  });

  it("fills the fields with the saved values and keeps save off without a change", () => {
    const html = draw();
    expect(content(html)).toContain("가상 데이터용(이 브라우저) A 낮은 상가 도로 mm B 주택 골목 mm");
    expect(field(html, "A")).toContain('min="0" max="500" step="any"');
    expect(field(html, "A")).toContain('value="45"');
    expect(field(html, "C")).toContain('value="65"');
    expect(field(html, "B")).not.toContain("aria-");
    expect(button(html, "ops-save")).toContain(
      'aria-disabled="true" aria-describedby="ops-why-save"',
    );
    expect(html).toContain('<li id="ops-why-save">바뀐 값이 없습니다</li>');
    expect(content(html)).toContain(NOTE);
  });

  // 처음 틀린 구역의 이유가 저장 줄이 되고 그 칸이 같은 줄을 가리키는지 검사
  it("marks a field over the limit and shares its reason with save", () => {
    const html = draw({ A: "600" });
    expect(field(html, "A")).toContain('value="600"');
    expect(field(html, "A")).toContain('aria-invalid="true" aria-describedby="ops-why-save"');
    expect(button(html, "ops-save")).toContain('aria-describedby="ops-why-save"');
    expect(html).toContain('<li id="ops-why-save">A 구역 · 500 mm 이하만 됩니다</li>');
    expect(field(html, "B")).not.toContain("aria-");
  });

  it("gives every bad field its own reason line", () => {
    const html = draw({ A: "0", C: "" });
    expect(field(html, "A")).toContain('aria-describedby="ops-why-save"');
    expect(field(html, "C")).toContain('aria-invalid="true" aria-describedby="ops-why-limit-C"');
    expect(content(html)).toContain("A 구역 · 0 보다 커야 합니다 C 구역 · 숫자를 넣어 주세요");
  });

  it("turns save on for a changed value in range", () => {
    const html = draw({ B: "50" });
    expect(field(html, "B")).toContain('value="50"');
    expect(button(html, "ops-save")).not.toContain('aria-disabled="');
    expect(html).not.toContain("<ul");
  });

  it("keeps the defaults button on in every case", () => {
    for (const draft of [{}, { A: "600" }, { B: "50" }]) {
      const html = draw(draft, null);
      expect(button(html, "ops-defaults")).not.toContain('aria-disabled="');
      expect(content(html)).toContain(" 저장 기본값으로 되돌리기 ");
    }
  });
});
