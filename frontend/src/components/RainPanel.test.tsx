import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { gates, type Gate } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Input, Rainfall, Snapshot } from "@/lib/schema";
import { RainPanel } from "./RainPanel";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
// 단추 하나의 여는 태그
const button = (html: string, id: string) =>
  html.match(new RegExp(`<button[^>]* id="${id}"[^>]*>`))?.[0] ?? "";
// 직접 입력 칸의 태그
const field = (html: string) => html.match(/<input[^>]* id="ops-rain-mm"[^>]*>/)?.[0] ?? "";
const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const LIMITS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
const RAIN: Rainfall = { presets: { light: 30, medium: 60, heavy: 90 }, maxMmPerHour: 150 };
const PRESETS = ["ops-rain-light", "ops-rain-medium", "ops-rain-heavy"];  // 단계 단추 id

// 입력원과 강우를 정한 대기 상태
function state(dataSource: Input = "sim", rain: Partial<Snapshot["rain"]> = {}): Snapshot {
  const snapshot = demo(T, LIMITS);
  return { ...snapshot, runState: "idle", dataSource, rain: { ...snapshot.rain, ...rain } };
}

// online 판정으로 그린 강우 칸
function markup(snapshot: Snapshot | null, draft = "", rain: Rainfall | null = RAIN) {
  const gate: Gate = gates("online", T, snapshot, null).rain;
  return renderToStaticMarkup(
    <RainPanel
      snapshot={snapshot}
      rain={rain}
      gate={gate}
      onSend={() => Promise.resolve(false)}
      draft={draft}
      onDraft={() => {}}
    />,
  );
}

describe("RainPanel", () => {
  it("shows dashes and points the controls at the halt line before the first answer", () => {
    const html = markup(null);
    expect(content(html)).toContain("단계 — 세기 — 상태 —");
    for (const id of [...PRESETS, "ops-rain"]) {
      expect(button(html, id)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    }
  });

  it("shows the server rain with its stage, rate and state icon", () => {
    const html = markup(state());
    expect(content(html)).toContain("단계 보통 강우 세기 60 mm/h 상태 [wave] 켜짐");
    expect(content(html)).toContain("약한 강우 30 mm/h 보통 강우 60 mm/h 강한 강우 90 mm/h");
    const off = markup(state("sim", { state: "OFF", mmPerHour: 0 }));
    expect(content(off)).toContain("세기 0 mm/h 상태 [pause] 꺼짐");
  });

  // 강우 설정이 없으면 단계 값은 줄표이고 입력 칸은 막히며 이유가 보이는지 검사
  it("blocks the typed rate without the server rain setting", () => {
    const html = markup(state(), "", null);
    expect(content(html)).toContain("약한 강우 — mm/h 보통 강우 — mm/h 강한 강우 — mm/h");
    expect(field(html)).toContain('disabled=""');
    expect(field(html)).toContain('aria-describedby="ops-why-rain"');
    expect(field(html)).not.toContain('aria-invalid="');
    expect(button(html, "ops-rain")).toContain('aria-describedby="ops-why-rain"');
    expect(html).toContain('<li id="ops-why-rain">서버 강우 설정이 없어 직접 입력을 끕니다</li>');
    expect(button(html, "ops-rain-light")).not.toContain('aria-disabled="');  // 단계는 서버가 앎
  });

  it("gives the range for an empty field without marking it invalid", () => {
    const html = markup(state());
    expect(field(html)).toContain('min="0" max="150" step="any"');
    expect(field(html)).not.toContain('disabled=""');
    expect(field(html)).not.toContain('aria-invalid="');
    expect(field(html)).toContain('aria-describedby="ops-why-rain"');
    expect(html).toContain('<li id="ops-why-rain">0 ~ 150 사이 숫자를 넣어 주세요</li>');
  });

  it("marks a rate over the limit invalid and keeps apply off", () => {
    const html = markup(state(), "200");
    expect(field(html)).toContain('value="200"');
    expect(field(html)).toContain('aria-invalid="true" aria-describedby="ops-why-rain"');
    expect(button(html, "ops-rain")).toContain(
      'aria-disabled="true" aria-describedby="ops-why-rain"',
    );
    expect(html).toContain('<li id="ops-why-rain">150 mm/h 이하만 됩니다</li>');
  });

  it("turns apply on for a rate in range and lists no reason", () => {
    const html = markup(state(), "75");
    expect(button(html, "ops-rain")).not.toContain('aria-disabled="');
    expect(field(html)).not.toContain("aria-");
    expect(html).not.toContain("<ul");
  });

  // 재생 중 단계 셋과 적용이 한 이유 줄을 같이 가리키고 글은 한 번인지 검사
  it("shares one reason line among the presets and apply during a replay", () => {
    const html = markup(state("replay"));
    const text = "재생 중에는 강우를 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다";
    for (const id of [...PRESETS, "ops-rain"]) {
      expect(button(html, id)).toContain(
        'aria-disabled="true" aria-describedby="ops-why-rain-light"',
      );
    }
    expect(html.split(text)).toHaveLength(2);  // 이유 글은 한 번
    expect(field(html)).toContain('aria-describedby="ops-why-rain-mm"');  // 빈칸 이유는 따로
  });

  it("marks only the preset that matches the server stage", () => {
    const html = markup(state("sim", { intensity: "강한 강우", mmPerHour: 90 }));
    expect(button(html, "ops-rain-heavy")).toContain('aria-current="true"');
    for (const id of ["ops-rain-light", "ops-rain-medium", "ops-rain"]) {
      expect(button(html, id)).not.toContain('aria-current="');
    }
    for (const intensity of ["직접 입력 75 mm/h", "강우 없음"]) {
      expect(markup(state("sim", { intensity }))).not.toContain('aria-current="');
    }
  });
});
