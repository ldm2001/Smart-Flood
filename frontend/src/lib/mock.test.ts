import { describe, expect, it } from "vitest";
import { MOCK_CYCLE_SEC, trail, demo } from "./mock";
import { stateSchema, type Snapshot, type Zone } from "./schema";

const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
const BASE = Date.UTC(2026, 9, 23, 1, 0, 0);  // 기준 시각(2026-10-23 01:00 UTC)
const frame = (e: number) => demo(BASE + e * 1000, THRESHOLDS);
const notice = (snapshot: Snapshot, zone: Zone) => snapshot.alerts.find((alert) => alert.zone === zone);

// 기준 시뮬레이션을 그대로 옮긴 비교 값(보통 강우, 부분 막힘)
function legacy(seconds: number) {
  const amount = (value: number) => Number(Math.max(0, value).toFixed(2));
  const rain = 0.7;
  const drain = 0.45;
  const rates = {  // 구역별 초당 증가량(mm)
    A: amount(0.82 * rain - 0.24 * drain),
    B: amount(0.62 * rain - 0.2 * drain),
    C: amount(0.38 * rain - 0.13 * drain),
  };
  let zones = { A: 12, B: 8, C: 4 };  // 시작 수위(mm)
  for (let i = 0; i < seconds; i += 1) {
    zones = {
      A: amount(Math.min(150, zones.A + rates.A)),  // A: 증가량을 더하고 150 에서 멈춤
      B: amount(Math.min(150, zones.B + rates.B)),  // B: 증가량을 더하고 150 에서 멈춤
      C: amount(Math.min(150, zones.C + rates.C)),  // C: 증가량을 더하고 150 에서 멈춤
    };
  }
  return { zones, rates };
}

describe("demo", () => {
  it("passes the /api/state schema at every second of the cycle", () => {
    for (let e = 0; e < MOCK_CYCLE_SEC; e += 1) {
      const result = stateSchema.safeParse(frame(e));
      expect(result.error?.issues, `e=${e}`).toBeUndefined();
    }
  });

  it("matches the legacy step-by-step simulation", () => {
    for (let e = 0; e < MOCK_CYCLE_SEC; e += 1) {
      const { zones, rates } = legacy(e);
      const snapshot = frame(e);
      for (const id of ["A", "B", "C"] as const) {
        expect(snapshot.zones[id].levelMm, `${id} e=${e}`).toBe(zones[id]);
        expect(snapshot.zones[id].rateMmSec).toBe(rates[id]);
        expect(snapshot.predictions[id]["30"]).toBe(Number((zones[id] + rates[id] * 30).toFixed(2)));
      }
    }
  });

  it("depends only on the whole second", () => {
    expect(demo(BASE + 42_999, THRESHOLDS)).toEqual(frame(42));
    expect(frame(42)).toEqual(frame(42));
  });

  it("starts from the legacy levels", () => {
    const first = frame(0);
    expect(first.elapsedSec).toBe(0);
    expect([first.zones.A.levelMm, first.zones.B.levelMm, first.zones.C.levelMm]).toEqual([12, 8, 4]);
    expect([first.zones.A.rateMmSec, first.zones.B.rateMmSec]).toEqual([0.47, 0.34]);
    expect(first.drain).toEqual({ volumeL: 0, flowLMin: 0.65 });
    expect(frame(60).drain.volumeL).toBe(0.65);
  });

  it("walks zone A through every stage", () => {
    expect(notice(frame(40), "A")).toBeUndefined();
    expect(notice(frame(41), "A")).toEqual({ zone: "A", stage: "caution", etaSec: 30 });
    expect(notice(frame(50), "A")).toEqual({ zone: "A", stage: "caution", etaSec: 30 });
    expect(notice(frame(51), "A")).toEqual({ zone: "A", stage: "caution", etaSec: 20 });
    expect(notice(frame(61), "A")).toEqual({ zone: "A", stage: "warning", etaSec: 10 });
    expect(frame(70).zones.A.levelMm).toBe(44.9);  // 70초 수위는 44.9 mm(한계 바로 아래)여야 함
    expect(notice(frame(70), "A")).toEqual({ zone: "A", stage: "warning", etaSec: 10 });
    expect(frame(71).zones.A.levelMm).toBe(45.37);  // 71초 수위는 45.37 mm(한계 넘음)여야 함
    expect(notice(frame(71), "A")).toEqual({ zone: "A", stage: "evacuate", etaSec: 0 });
  });

  it("walks zone B through every stage later", () => {
    expect(notice(frame(108), "B")).toBeUndefined();
    expect(notice(frame(109), "B")).toEqual({ zone: "B", stage: "caution", etaSec: 30 });
    expect(notice(frame(119), "B")).toEqual({ zone: "B", stage: "caution", etaSec: 20 });
    expect(notice(frame(129), "B")).toEqual({ zone: "B", stage: "warning", etaSec: 10 });
    expect(notice(frame(138), "B")?.stage).toBe("warning");
    expect(notice(frame(139), "B")).toEqual({ zone: "B", stage: "evacuate", etaSec: 0 });
  });

  it("keeps zone C safe and lists only non-safe zones", () => {
    for (let e = 0; e < MOCK_CYCLE_SEC; e += 1) expect(notice(frame(e), "C")).toBeUndefined();
    expect(frame(0).alerts).toEqual([]);
    expect(frame(75).alerts).toEqual([{ zone: "A", stage: "evacuate", etaSec: 0 }]);
  });

  it("uses the thresholds it is given", () => {
    expect(demo(BASE, { A: 10, B: 55, C: 65 }).alerts).toEqual([{ zone: "A", stage: "evacuate", etaSec: 0 }]);
  });

  it("starts a new experiment every 180 s", () => {
    const last = frame(MOCK_CYCLE_SEC - 1);
    expect(last.elapsedSec).toBe(179);
    expect([last.zones.A.levelMm, last.zones.B.levelMm]).toEqual([96.13, 68.86]);
    expect(last.experimentId).toBe(frame(0).experimentId);

    const next = frame(MOCK_CYCLE_SEC);
    expect(next.elapsedSec).toBe(0);
    expect(next.zones.A.levelMm).toBe(12);
    expect(next.experimentId).not.toBe(frame(0).experimentId);
    expect(frame(0).experimentId).toMatch(/^EXP-DEMO-\d{3}$/);
  });

  it("stamps KST whole seconds and a fresh prediction basis", () => {
    const snapshot = frame(42);
    expect(snapshot.timestamp).toBe("2026-10-23T10:00:42.000+09:00");
    expect(snapshot.predictionMeta?.basisTime).toBe(snapshot.timestamp);
    expect(snapshot.predictionMeta?.basisElapsedSec).toBe(42);
    expect(snapshot.predictionMeta?.validForSec).toBe(5);
  });

  it("looks like the server sim with outputs locked", () => {
    const snapshot = frame(0);
    expect(snapshot.dataSource).toBe("sim");
    expect(snapshot.mode).toBe("live");
    expect([snapshot.zones.A.source, snapshot.zones.B.source, snapshot.zones.C.source]).toEqual([
      "simulated",  // A: 가상 실측
      "simulated",  // B: 가상 실측
      "estimated",  // C: 모델 추정
    ]);
    expect(snapshot.blockage).toEqual({ location: "INLET-02", type: "partial", label: "빗물받이 ② 부분 막힘" });
    expect(snapshot.outputsLocked).toBe(true);
  });

  it("lists only the blocked inlet in the prediction assumptions, like the server", () => {
    expect(frame(0).predictionMeta?.assumptions.blockage).toEqual({ "INLET-02": "partial" });
  });
});

describe("trail", () => {
  it("has one sample per second from the cycle start, the same levels as demo", () => {
    const history = trail(BASE + 42_400);
    expect(history).toHaveLength(43);  // 0초부터 42초까지 43개여야 함
    for (const [e, sample] of history.entries()) {
      const { timestamp, zones } = frame(e);
      expect(sample, `e=${e}`).toEqual({ t: Date.parse(timestamp), A: zones.A.levelMm, B: zones.B.levelMm, C: zones.C.levelMm });
    }
  });

  it("starts over with each cycle", () => {
    expect(trail(BASE + (MOCK_CYCLE_SEC - 1) * 1000)).toHaveLength(MOCK_CYCLE_SEC);
    expect(trail(BASE + MOCK_CYCLE_SEC * 1000)).toEqual([{ t: BASE + MOCK_CYCLE_SEC * 1000, A: 12, B: 8, C: 4 }]);
  });
});
