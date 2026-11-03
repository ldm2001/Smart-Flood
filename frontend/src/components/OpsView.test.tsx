import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Answer, Fault } from "@/lib/api";
import { gates, halt, linkage, type Delivery } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Control, Input, Rainfall, Run, Snapshot } from "@/lib/schema";
import { Sheet, type Board } from "./OpsView";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
// 단추 하나의 여는 태그
const button = (html: string, id: string) =>
  html.match(new RegExp(`<button[^>]* id="${id}"[^>]*>`))?.[0] ?? "";
// 결과 줄 안의 글. 아이콘은 [이름]
const note = (html: string) =>
  content(html.match(/<p id="ops-note"[^>]*>([\s\S]*?)<\/p>/)?.[1] ?? "").trim();
const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const LIMITS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
const RAIN: Rainfall = { presets: { light: 30, medium: 60, heavy: 90 }, maxMmPerHour: 150 };
const BARE = { rain: null, limits: null };  // 서버 설정을 받기 전
const REFUSED: Fault = { kind: "refused", status: 409, text: "이미 진행 중입니다" };  // 409 거절
const SERVER = [  // 서버로 보내는 제어 단추
  "ops-start",
  "ops-stop",
  "ops-reset",
  "ops-sim",
  "ops-live",
  "ops-rain-light",
  "ops-rain-medium",
  "ops-rain-heavy",
  "ops-rain",
  "ops-blockage",
];

// 시계, 마지막 수신, 폴링 실패로 정한 연결
interface Contact {
  now: number | null;
  receivedAt: number | null;
  failed: boolean;
}

const ONLINE: Contact = { now: T + 1000, receivedAt: T, failed: false };
const CONNECTING: Contact = { now: null, receivedAt: null, failed: false };
const MOCK: Contact = { now: T, receivedAt: null, failed: true };  // 받은 적 없이 실패
const LOST: Contact = { now: T + 5000, receivedAt: T, failed: true };  // 4초 넘게 못 받고 실패

// 회차 상태와 입력원을 정한 상태
function state(runState: Run = "idle", dataSource: Input = "sim"): Snapshot {
  return { ...demo(T, LIMITS), runState, dataSource };
}

// 보낸 제어와 답으로 만든 결과
const delivery = (control: Control, answer: Answer): Delivery => ({
  control,
  answer,
  replay: false,
});

// Desk 처럼 연결에서 멈춤 글과 판정을 구해 그린 운영 화면
function draw(snapshot: Snapshot | null, contact = ONLINE, extra: Partial<Board> = {}) {
  const link = linkage(contact.now, contact.receivedAt, contact.failed);
  const board: Board = {
    ...contact,
    link,
    halt: halt(link, contact.receivedAt),
    snapshot,
    rain: RAIN,
    limits: LIMITS,
    saved: LIMITS,
    gates: gates(link, contact.receivedAt, snapshot, extra.sending ?? null),
    open: null,
    sending: null,
    delivery: null,
    onPress: () => {},
    onSend: () => Promise.resolve(false),
    ...extra,
  };
  return renderToStaticMarkup(<Sheet {...board} />);
}

describe("Sheet", () => {
  it("turns every server control off with the halt line while connecting", () => {
    const html = draw(null, CONNECTING, BARE);
    expect(content(html)).toContain("A·B·C 구역 침수 모형 운영·설정 [circle] 모드 — [dots] 연결 중");
    expect(content(html)).toContain("[info] 서버에 연결하는 중이라 제어를 끕니다");
    for (const id of SERVER) {
      expect(button(html, id)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    }
    expect(html).toContain('<p id="ops-note" aria-live="polite"');  // 비어도 자리는 있음
    expect(note(html)).toBe("");
    expect(html).not.toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  it("marks mock data and keeps every control from reaching the server", () => {
    const html = draw(null, MOCK, BARE);
    expect(content(html)).toContain("가상 데이터(서버 미연결)");
    expect(content(html)).toContain("[nowifi] 연결 끊김 · 마지막 수신 —");
    expect(content(html)).toContain(
      "[info] 서버에 연결되지 않아 제어를 끕니다. 가상 데이터에는 보내지 않습니다",
    );
    for (const id of SERVER) {
      expect(button(html, id)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    }
    expect(html).not.toContain("EXP-");  // 가상 상태를 지어 보이지 않음
  });

  it("keeps the last values but turns controls off once the link is lost", () => {
    const html = draw(state("running"), LOST);
    expect(content(html)).toContain("[nowifi] 연결 끊김 · 마지막 수신 10:00:00");
    expect(content(html)).toContain("[info] 연결이 끊겨 제어를 끕니다 · 마지막 수신 10:00:00 기준");
    expect(content(html)).toContain("[play] 실험 진행 중");  // 마지막 정상 상태는 그대로
    for (const id of SERVER) {
      expect(button(html, id)).toContain('aria-disabled="true" aria-describedby="ops-halt"');
    }
  });

  it("drops the halt line online and opens what an idle run allows", () => {
    const html = draw(state("idle"));
    expect(html).not.toContain('id="ops-halt"');
    expect(content(html)).toContain("[target] 모드 가상 [wifi] 연결 정상 · 마지막 수신 10:00:00");
    const open = ["ops-start", "ops-reset", "ops-live", "ops-rain-medium", "ops-blockage"];
    for (const id of open) {
      expect(button(html, id)).not.toContain('aria-disabled="');
    }
    expect(button(html, "ops-stop")).toContain('aria-describedby="ops-why-stop"');
    expect(button(html, "ops-sim")).toContain('aria-describedby="ops-why-sim"');
    expect(button(html, "ops-save")).toContain('aria-describedby="ops-why-save"');  // 서버와 무관
    expect(button(html, "ops-defaults")).not.toContain('aria-disabled="');
  });

  it("lets a running round stop but holds start and the source switch", () => {
    const html = draw(state("running"));
    expect(button(html, "ops-stop")).not.toContain('aria-disabled="');
    expect(button(html, "ops-start")).toContain('aria-describedby="ops-why-start"');
    expect(button(html, "ops-live")).toContain('aria-describedby="ops-why-live"');
    expect(content(html)).toContain("회차가 진행 중이라 입력원을 바꿀 수 없습니다. 먼저 종료합니다");
  });

  it("names the replay controls and leaves only stop and the way back on", () => {
    const html = draw(state("running", "replay"));
    expect(content(html)).toContain(" 시작 재생 멈춤 초기화 ");
    expect(content(html)).toContain(" 시뮬레이션으로 돌아가기 실측으로 바꾸기 ");
    const on = ["ops-stop", "ops-sim"];
    for (const id of on) {
      expect(button(html, id)).not.toContain('aria-disabled="');
    }
    for (const id of SERVER.filter((each) => !on.includes(each))) {
      expect(button(html, id)).toContain('aria-disabled="true"');
    }
    const still = draw(state("stopped", "replay"));
    expect(button(still, "ops-stop")).toContain('aria-describedby="ops-why-stop"');
    expect(still).toContain('<li id="ops-why-stop">재생이 멈춰 있습니다</li>');
  });

  it("turns every control off and names what is on its way while sending", () => {
    const quiet = draw(state("idle"));  // 보내기 전
    const html = draw(state("idle"), ONLINE, { sending: "start" });
    expect(note(html)).toBe("[dots] 시작 보내는 중입니다");
    expect(html).not.toContain('id="ops-halt"');
    for (const id of SERVER) {
      expect(button(quiet, id)).not.toBe("");
      const own = button(quiet, id).match(/aria-describedby="([^"]+)"/)?.[1];  // 꺼져 있던 이유 줄
      const cue = own ?? "ops-note";  // 켜져 있던 제어는 결과 줄
      expect(button(html, id)).toContain(`aria-disabled="true" aria-describedby="${cue}"`);
    }
    const lines = (page: string) => page.match(/<li id="ops-why-[^"]+">[^<]*<\/li>/g) ?? [];
    expect(lines(quiet).length).toBeGreaterThan(1);
    expect(lines(html)).toEqual(lines(quiet));  // 이유 줄이 그대로라 칸 높이가 바뀌지 않음
    const late = delivery("start", { ok: false, fault: REFUSED, at: T });  // 지난 결과
    const again = draw(state("idle"), ONLINE, { sending: "rain", delivery: late });
    expect(note(again)).toBe("[dots] 강우 적용 보내는 중입니다");  // 보내는 동안 지난 결과는 가림
  });

  it("opens the confirm line inside the panel of the pressed control", () => {
    const html = draw(state("running"), ONLINE, { open: "stop" });
    const round = html.split('<section aria-label="입력원"')[0];  // 회차 칸까지
    expect(round).toContain('role="group" aria-label="종료 확인" data-opener="ops-stop"');
    expect(content(html)).toContain("회차를 종료할까요? 비가 그치고 마지막 상태가 남습니다 예 취소");
    const source = draw(state("idle"), ONLINE, { open: "live" });
    expect(source.split('<section aria-label="입력원"')[1]).toContain(
      'role="group" aria-label="실측으로 바꾸기 확인" data-opener="ops-live"',
    );
  });

  it("shows one outcome line for a landed, refused or unanswered control", () => {
    const cases: [Delivery, string][] = [
      [
        delivery("rain", { ok: true, receipt: { snapshot: state(), receivedAt: T } }),
        "[check] 반영 · 강우 60 mm/h · 10:00:00 수신",
      ],
      [
        delivery("start", { ok: false, fault: REFUSED, at: T }),
        "[error] 시작 거절 · 이미 진행 중입니다 · 10:00:00",
      ],
      [
        delivery("start", { ok: false, fault: { kind: "timeout" }, at: T }),
        "[triangle] 시작 응답 없음 · 5초 안에 답이 없었습니다. 반영됐는지는 다음 수신으로 확인합니다 · 10:00:00",
      ],
    ];
    for (const [given, text] of cases) {
      expect(note(draw(state(), ONLINE, { delivery: given }))).toBe(text);
    }
  });
});
