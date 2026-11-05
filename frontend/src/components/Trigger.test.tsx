import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Gate } from "@/lib/derive";
import { Reasons, Trigger } from "./Trigger";

const ON: Gate = { on: true };  // 켜진 판정
const press = () => {};  // 누름(하는 일 없음)

// 판정과 이유 줄 id 로 그린 시작 단추
function markup(gate: Gate, why?: string, current?: boolean) {
  return renderToStaticMarkup(
    <Trigger id="ops-start" gate={gate} why={why} current={current} onPress={press}>
      시작
    </Trigger>,
  );
}

describe("Trigger", () => {
  it("is a plain button that takes presses while on", () => {
    const html = markup(ON, "ops-why-start");
    expect(html).toMatch(/^<button type="button" id="ops-start" class="[^"]+">시작<\/button>$/);
    expect(html).not.toContain('aria-disabled="');
    expect(html).not.toContain('aria-describedby="');
    const element = Trigger({ id: "ops-start", gate: ON, onPress: press, children: "시작" });
    expect(element.props.onClick).toBe(press);
  });

  // 꺼진 이유의 자리마다 가리키는 줄과 누름을 버리는지 검사
  it("points an off gate at the line of its cue and drops presses", () => {
    const cues = [
      ["halt", "ops-halt"],
      ["note", "ops-note"],
      ["own", "ops-why-start"],
    ] as const;
    for (const [cue, target] of cues) {
      const gate: Gate = { on: false, reason: "이유", cue };
      const html = markup(gate, "ops-why-start");
      expect(html).toContain(`aria-disabled="true" aria-describedby="${target}"`);
      const element = Trigger({ id: "ops-start", gate, onPress: press, children: "" });
      expect(element.props.onClick).toBeUndefined();
    }
  });

  it("marks only the current preset", () => {
    expect(markup(ON, undefined, true)).toContain('aria-current="true"');
    expect(markup(ON, undefined, false)).not.toContain('aria-current="');
    expect(markup(ON)).not.toContain('aria-current="');
  });
});

describe("Reasons", () => {
  it("draws nothing without lines", () => {
    expect(renderToStaticMarkup(<Reasons lines={[]} />)).toBe("");
  });

  it("lists each reason under its own id", () => {
    const lines = [
      { id: "ops-why-start", text: "이미 진행 중입니다" },
      { id: "ops-why-sim", text: "이미 시뮬레이션입니다" },
    ];
    expect(renderToStaticMarkup(<Reasons lines={lines} />)).toBe(
      '<ul class="mt-3 text-soft"><li id="ops-why-start">이미 진행 중입니다</li>' +
        '<li id="ops-why-sim">이미 시뮬레이션입니다</li></ul>',
    );
  });
});
