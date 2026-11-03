import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { gates, type Hazard } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Input, Run, Snapshot } from "@/lib/schema";
import { Origin } from "./SourcePanel";

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
const NOTE = "재생 시작은 기록·재생 화면에서 합니다.";  // 재생 시작 안내 글

// 회차 상태와 입력원을 정한 상태
function state(runState: Run, dataSource: Input): Snapshot {
  return { ...demo(T, LIMITS), runState, dataSource };
}

// online 판정으로 그린 입력원 칸
function draw(snapshot: Snapshot | null, open: Hazard | null = null) {
  return renderToStaticMarkup(
    <Origin
      snapshot={snapshot}
      gates={gates("online", T, snapshot, null)}
      open={open}
      onPress={() => {}}
    />,
  );
}

describe("Origin", () => {
  it("shows an empty source and the halt line before the first answer", () => {
    const html = draw(null, "live");
    expect(content(html)).toContain("[circle] 입력원 —");
    for (const id of ["ops-sim", "ops-live"]) {
      expect(button(html, id)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    }
    expect(html).not.toContain('role="group"');  // 상태가 없으면 확인 줄도 없음
    expect(content(html)).toContain(NOTE);
  });

  it("offers live from an idle simulation", () => {
    const html = draw(state("idle", "sim"));
    expect(content(html)).toContain("[target] 입력원 가상 시뮬레이션으로 바꾸기 실측으로 바꾸기");
    expect(button(html, "ops-sim")).toContain('aria-describedby="ops-why-sim"');
    expect(html).toContain('<li id="ops-why-sim">이미 시뮬레이션입니다</li>');
    expect(button(html, "ops-live")).not.toContain('aria-disabled="');
    expect(content(html)).toContain(NOTE);
  });

  it("offers the simulation from idle live", () => {
    const html = draw(state("idle", "live"));
    expect(content(html)).toContain("[radio] 입력원 실측");
    expect(button(html, "ops-sim")).not.toContain('aria-disabled="');
    expect(button(html, "ops-live")).toContain('aria-describedby="ops-why-live"');
    expect(html).toContain('<li id="ops-why-live">이미 실측입니다</li>');
  });

  it("names the way back from a replay and keeps live off", () => {
    const html = draw(state("running", "replay"));
    expect(content(html)).toContain("[rotate] 입력원 재생 시뮬레이션으로 돌아가기 실측으로 바꾸기");
    expect(button(html, "ops-sim")).not.toContain('aria-disabled="');
    expect(html).toContain(
      '<li id="ops-why-live">재생 중에는 실측으로 바꿀 수 없습니다. 먼저 시뮬레이션으로 돌아갑니다</li>',
    );
  });

  // 진행 중 sim 에서 두 단추의 이유가 달라 서로 다른 줄을 가리키는지 검사
  it("points each button at its own reason while a simulated round runs", () => {
    const html = draw(state("running", "sim"));
    expect(button(html, "ops-sim")).toContain('aria-describedby="ops-why-sim"');
    expect(button(html, "ops-live")).toContain('aria-describedby="ops-why-live"');
    expect(html).toContain('<li id="ops-why-sim">이미 시뮬레이션입니다</li>');
    expect(html).toContain(
      '<li id="ops-why-live">회차가 진행 중이라 입력원을 바꿀 수 없습니다. 먼저 종료합니다</li>',
    );
  });

  it("opens the check line of a source change inside the panel", () => {
    const live = draw(state("idle", "sim"), "live");
    expect(live).toContain('role="group" aria-label="실측으로 바꾸기 확인" data-opener="ops-live"');
    expect(content(live)).toContain(
      "실측으로 바꿀까요? 대기로 돌아가고 강우·막힘 선택이 기본값이 됩니다. " +
        "멈춘 회차의 마지막 화면도 지워집니다. 기록 파일은 남습니다 예 취소",
    );
    const back = draw(state("running", "replay"), "sim");
    expect(back).toContain('aria-label="시뮬레이션으로 돌아가기 확인" data-opener="ops-sim"');
    expect(content(back)).toContain(
      "재생을 끝내고 시뮬레이션으로 돌아갈까요? 대기로 돌아가고 강우·막힘 선택이 기본값이 됩니다 예",
    );
    expect(draw(state("running", "sim"), "stop")).not.toContain('role="group"');  // 종료 줄은 회차 칸
  });
});
