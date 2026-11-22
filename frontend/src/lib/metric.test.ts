import { describe, expect, it } from "vitest";
import { closure, mark, route, score, type Tally } from "./derive";
import type { Alert } from "./schema";

// 구역 A 의 비교 한 줄. 빠진 칸은 null
const line = (part: Partial<Tally>): Tally => ({
  zone: "A",
  judgement: null,
  forecast: null,
  arrival: null,
  lead: null,
  error: null,
  ...part,
});

describe("route", () => {
  // 경보 구역마다 우선순위대로 안내 한 줄을 고르는지 검사
  it("picks one guidance line by C, B, A priority", () => {
    const at = (...zones: Alert["zone"][]): Alert[] => zones.map((zone) => ({ zone, stage: "warning" }));
    expect(route([])).toBe("정상: 경로 A 이용 가능");
    expect(route(at("A"))).toBe("A 낮은 상가 도로 위험: 경로 B 로 우회하세요");
    expect(route(at("A", "B"))).toBe("B 주택 골목 위험: C 높은 광장으로 대피하세요");
    expect(route(at("B", "C", "A"))).toBe("C 높은 광장까지 위험: 실험을 멈추세요");
  });
});

describe("mark", () => {
  // 판단·도달·선행 시간으로 적중·누락·오경보·대기·줄표를 가르는지 검사
  it("gives each line a verdict", () => {
    expect(mark(line({ judgement: 1000, arrival: 9000, lead: 8 }), false)).toBe("적중");
    expect(mark(line({ judgement: 1000, arrival: 1000, lead: 0 }), false)).toBe("누락");
    expect(mark(line({ arrival: 9000 }), true)).toBe("누락");
    expect(mark(line({ judgement: 1000 }), false)).toBe("대기");
    expect(mark(line({ judgement: 1000 }), true)).toBe("오경보");
    expect(mark(line({}), true)).toBe("—");
  });
});

describe("score", () => {
  // 판정 수를 한 줄 글로 세는지 검사
  it("counts hits, misses and false alarms", () => {
    const lines = [
      line({ judgement: 1000, arrival: 9000, lead: 8 }),
      line({ zone: "B", arrival: 9000 }),
      line({ zone: "C", judgement: 1000 }),
    ];
    expect(score(lines, true)).toBe("적중 1 · 누락 1 · 오경보 1");
    expect(score(lines, false)).toBe("적중 1 · 누락 1 · 오경보 0");
  });
});

describe("closure", () => {
  // 지금 진행 중인 실험의 기록만 끝나지 않은 것으로 보는지 검사
  it("treats only the running experiment as not ended", () => {
    const now = { experimentId: "EXP-20261104-001", runState: "running" } as const;
    expect(closure(now, "EXP-20261104-001")).toBe(false);
    expect(closure(now, "EXP-20261103-002")).toBe(true);
    expect(closure({ ...now, runState: "stopped" }, "EXP-20261104-001")).toBe(true);
    expect(closure(null, "EXP-20261104-001")).toBe(false);
    expect(closure(now, null)).toBe(false);
  });
});
