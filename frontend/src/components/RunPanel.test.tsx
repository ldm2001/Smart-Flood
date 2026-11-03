import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { gates, type Hazard } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Input, Run, Snapshot } from "@/lib/schema";
import { Round } from "./RunPanel";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
// 단추 하나의 여는 태그
const button = (html: string, id: string) =>
  html.match(new RegExp(`<button[^>]* id="${id}"[^>]*>`))?.[0] ?? "";
const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const LIMITS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)

// 회차 상태와 입력원을 정한 상태. runState 를 undefined 로 주면 그 칸을 뺌
function state(runState: Run | undefined, dataSource: Input = "sim"): Snapshot {
  const snapshot: Snapshot = { ...demo(T, LIMITS), runState, dataSource, elapsedSec: 42.9 };
  if (runState === undefined) delete snapshot.runState;
  return snapshot;
}

// online 판정으로 그린 회차 칸
function draw(snapshot: Snapshot | null, open: Hazard | null = null) {
  return renderToStaticMarkup(
    <Round
      snapshot={snapshot}
      gates={gates("online", T, snapshot, null)}
      open={open}
      onPress={() => {}}
      onSend={() => Promise.resolve(false)}
    />,
  );
}

describe("Round", () => {
  it("shows dashes and points every control at the halt line before the first answer", () => {
    const html = draw(null, "stop");
    expect(content(html)).toContain("상태 실험 — 실험 ID — 경과 —");
    for (const id of ["ops-start", "ops-stop", "ops-reset"]) {
      expect(button(html, id)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    }
    expect(html).not.toContain('role="group"');  // 상태가 없으면 확인 줄도 없음
  });

  it("lets an idle run start or reset, but not stop", () => {
    const html = draw(state("idle"));
    expect(content(html)).toContain("상태 [pause] 실험 대기");
    expect(content(html)).toMatch(/실험 ID EXP-DEMO-\d{3} 경과 42초/);  // 경과 초는 내림
    expect(button(html, "ops-start")).not.toContain('aria-disabled="');
    expect(button(html, "ops-reset")).not.toContain('aria-disabled="');
    expect(button(html, "ops-stop")).toContain('aria-describedby="ops-why-stop"');
    expect(html).toContain('<li id="ops-why-stop">진행 중이 아닙니다</li>');
  });

  it("lets a running round stop, but not start again", () => {
    const html = draw(state("running"));
    expect(content(html)).toContain("상태 [play] 실험 진행 중");
    expect(content(html)).toContain(" 시작 종료 초기화 ");
    expect(button(html, "ops-stop")).not.toContain('aria-disabled="');
    expect(button(html, "ops-start")).toContain('aria-describedby="ops-why-start"');
    expect(html).toContain('<li id="ops-why-start">이미 진행 중입니다</li>');
  });

  it("starts again from a stopped round", () => {
    const html = draw(state("stopped"));
    expect(content(html)).toContain("상태 [stop] 실험 정지");
    expect(button(html, "ops-start")).not.toContain('aria-disabled="');
    expect(button(html, "ops-stop")).toContain('aria-describedby="ops-why-stop"');
  });

  it("names stop for the replay and leaves only that on while it plays", () => {
    const html = draw(state("running", "replay"));
    expect(content(html)).toContain(" 시작 재생 멈춤 초기화 ");
    expect(button(html, "ops-stop")).not.toContain('aria-disabled="');
    expect(html).toContain(
      '<li id="ops-why-start">재생 중에는 회차를 시작할 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다</li>',
    );
    expect(button(html, "ops-reset")).toContain('aria-describedby="ops-why-reset"');
  });

  it("turns the replay stop off once the replay has stopped", () => {
    const html = draw(state("stopped", "replay"));
    expect(button(html, "ops-stop")).toContain('aria-describedby="ops-why-stop"');
    expect(html).toContain('<li id="ops-why-stop">재생이 멈춰 있습니다</li>');
  });

  // 회차 상태가 없으면 시작·종료가 한 이유 줄을 같이 가리키는지 검사
  it("shares one reason line between start and stop when the run state is missing", () => {
    const html = draw(state(undefined));
    const text = "서버가 회차 상태를 보내지 않았습니다";
    expect(content(html)).toContain("상태 실험 —");
    expect(button(html, "ops-start")).toContain('aria-describedby="ops-why-start"');
    expect(button(html, "ops-stop")).toContain('aria-describedby="ops-why-start"');
    expect(html.split(text)).toHaveLength(2);  // 이유 글은 한 번
    expect(button(html, "ops-reset")).not.toContain('aria-disabled="');
  });

  it("opens the check line of stop or reset inside the panel", () => {
    const stop = draw(state("running"), "stop");
    expect(stop).toContain('role="group" aria-label="종료 확인" data-opener="ops-stop"');
    expect(content(stop)).toContain("회차를 종료할까요? 비가 그치고 마지막 상태가 남습니다 예 취소");
    const reset = draw(state("idle"), "reset");
    expect(reset).toContain('aria-label="초기화 확인" data-opener="ops-reset"');
    expect(content(reset)).toContain("강우·막힘 선택만 기본값(보통 강우, 막힘 없음)으로 돌립니다");
    expect(draw(state("running"), "sim")).not.toContain('role="group"');  // 입력원 줄은 다른 칸
  });
});
