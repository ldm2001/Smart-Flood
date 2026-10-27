import { describe, expect, it } from "vitest";
import {
  notices,
  entry,
  caption,
  plot,
  EMPTY_HISTORY,
  leader,
  phrase,
  verdict,
  verdicts,
  figure,
  clock,
  fraction,
  HISTORY_LIMIT,
  outage,
  expiry,
  columns,
  lead,
  share,
  roster,
  stamp,
  peak,
  type Grade,
} from "./derive";
import type { Alert, Zone, Source } from "./schema";

const plateau = (v: number) => ({ "10": v, "20": v, "30": v });
const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
// 구역 등급 하나를 만드는 도우미
const status = (zoneId: Zone, stage: Grade["stage"], etaSec: number | null): Grade => ({
  zoneId,
  stage,
  etaSec,
});
const trio = (a: Grade, b: Grade, c: Grade) => ({ A: a, B: b, C: c });
const sources = (a: Source, b: Source, c: Source) => ({ A: { source: a }, B: { source: b }, C: { source: c } });
const SIM_SOURCES = sources("simulated", "simulated", "estimated");
const ALL_SAFE = trio(status("A", "safe", null), status("B", "safe", null), status("C", "safe", null));

describe("verdict", () => {
  it("44.9 mm is below a 45 mm threshold, 45.0 mm is at it", () => {
    expect(verdict("A", 44.9, plateau(44.9), 45)).toEqual(status("A", "safe", null));
    expect(verdict("A", 45.0, plateau(45.0), 45)).toEqual(status("A", "evacuate", 0));
  });

  it("a +10 s prediction at the threshold is warning with eta 10", () => {
    expect(verdict("A", 40, { "10": 45, "20": 50, "30": 55 }, 45)).toEqual(status("A", "warning", 10));
    expect(verdict("A", 40, { "10": 44.9, "20": 50, "30": 55 }, 45)).toEqual(status("A", "caution", 20));
  });

  // 30초 뒤 한계면 주의(30초), 바로 아래면 정상인지 검사
  it("a +30 s prediction at the threshold is caution with eta 30, just below is safe", () => {
    expect(verdict("A", 40, { "10": 44.9, "20": 44.9, "30": 45 }, 45)).toEqual(status("A", "caution", 30));
    expect(verdict("A", 40, { "10": 44.9, "20": 44.9, "30": 44.9 }, 45)).toEqual(status("A", "safe", null));
  });

  it("the current level wins over predictions", () => {
    expect(verdict("B", 60, plateau(0), 55)).toEqual(status("B", "evacuate", 0));
  });
});

describe("verdicts", () => {
  it("uses each zone's own threshold", () => {
    const snapshot = {
      zones: {
        A: { levelMm: 45, rateMmSec: 0, source: "simulated" as const },  // A 는 45 mm(한계 45)
        // B 는 45 mm(한계 55 라서 아직 정상)
        B: { levelMm: 45, rateMmSec: 0, source: "simulated" as const },
        C: { levelMm: 60, rateMmSec: 0, source: "estimated" as const },  // C 는 60 mm(한계 65)
      },
      predictions: { A: plateau(45), B: plateau(45), C: { "10": 61, "20": 63, "30": 65 } },
    };
    expect(verdicts(snapshot, THRESHOLDS)).toEqual(  // A 침수, B 정상, C 주의 30초여야 함
      trio(status("A", "evacuate", 0), status("B", "safe", null), status("C", "caution", 30)),
    );
  });
});

describe("stage priority", () => {
  it("the higher stage is worst regardless of zone order", () => {
    const zones = trio(status("A", "caution", 20), status("B", "warning", 10), status("C", "safe", null));
    expect(peak(zones).zoneId).toBe("B");
    expect(peak(trio(status("A", "safe", null), status("B", "warning", 10), status("C", "evacuate", 0))).zoneId).toBe("C");
  });

  it("within one stage the earlier eta is worst, then zone order", () => {
    expect(peak(trio(status("A", "caution", 30), status("B", "caution", 20), status("C", "safe", null))).zoneId).toBe("B");
    expect(peak(trio(status("A", "caution", 20), status("B", "caution", 20), status("C", "caution", 20))).zoneId).toBe("A");
  });

  // 모두 정상이면 최악도 정상이고 먼저 닿는 구역은 없는지 검사
  it("all safe gives a safe worst zone and no earliest zone", () => {
    const zones = trio(status("A", "safe", null), status("B", "safe", null), status("C", "safe", null));
    expect(peak(zones).stage).toBe("safe");
    expect(leader(zones)).toBeNull();  // 먼저 닿는 구역은 없어야 함(null)
  });

  it("earliest picks the smallest eta", () => {
    const zones = trio(status("A", "caution", 30), status("B", "safe", null), status("C", "caution", 20));
    expect(leader(zones)?.zoneId).toBe("C");  // 먼저 닿는 구역은 C 여야 함
  });

  it("alerts list only non-safe zones in A, B, C order", () => {
    const zones = trio(status("A", "warning", 10), status("B", "safe", null), status("C", "caution", 30));
    expect(notices(zones)).toEqual([
      { zone: "A", stage: "warning", etaSec: 10 },
      { zone: "C", stage: "caution", etaSec: 30 },  // C 주의 30초
    ]);
  });
});

describe("roster", () => {
  it("reads stage and eta from the server alerts and leaves the other zones safe", () => {
    expect(roster([{ zone: "A", stage: "warning", etaSec: 10 }])).toEqual(
      trio(status("A", "warning", 10), status("B", "safe", null), status("C", "safe", null)),
    );
    expect(roster([])).toEqual(ALL_SAFE);
  });

  it("treats a missing eta as unknown", () => {  // 남은 초가 없으면 모름(null)으로 보는지 검사
    expect(roster([{ zone: "B", stage: "caution" }]).B).toEqual(status("B", "caution", null));
    expect(roster([{ zone: "B", stage: "caution", etaSec: null }]).B).toEqual(status("B", "caution", null));
  });

  it("keeps the higher stage when the server repeats a zone", () => {
    const alerts: Alert[] = [
      { zone: "A", stage: "caution", etaSec: 20 },  // 주의 20초
      { zone: "A", stage: "evacuate", etaSec: 0 },  // 침수 0초(가장 높음)
      { zone: "A", stage: "warning", etaSec: 10 },  // 경고 10초(침수보다 낮음)
    ];
    expect(roster(alerts).A).toEqual(status("A", "evacuate", 0));
  });

  // mock 이 경보로 바꾼 등급이 그대로 돌아오는지 검사
  it("gives back the statuses the mock made its alerts from", () => {
    const zones = trio(status("A", "warning", 10), status("B", "safe", null), status("C", "caution", 30));
    expect(roster(notices(zones))).toEqual(zones);  // 경보로 바꿨다가 되돌려도 같아야 함
  });
});

describe("caption", () => {
  it("all safe", () => {
    const banner = caption(ALL_SAFE, SIM_SOURCES);
    expect(banner).toEqual({ stage: "safe", zoneId: null, message: "전 구역 정상 · 30초 안에 한계 도달 예상 없음" });
  });

  it("names the worst zone with its eta", () => {
    const banner = caption(trio(status("A", "caution", 20), status("B", "safe", null), status("C", "safe", null)), SIM_SOURCES);
    expect(banner).toEqual({ stage: "caution", zoneId: "A", message: "A 낮은 상가 도로 · 약 20초 후 침수 예상" });
  });

  it("marks zone C as a model estimate", () => {
    const banner = caption(trio(status("A", "safe", null), status("B", "safe", null), status("C", "warning", 10)), SIM_SOURCES);
    expect(banner.message).toBe("C 높은 광장 · 약 10초 후 침수 예상 (모델 추정)");
  });

  // 추정 표시는 구역 고정표가 아니라 구역의 출처를 따르는지 검사
  it("takes the estimate mark from the zone's source, not from a fixed zone list", () => {
    const aAtRisk = trio(status("A", "warning", 10), status("B", "safe", null), status("C", "safe", null));
    const cAtRisk = trio(status("A", "safe", null), status("B", "safe", null), status("C", "warning", 10));
    expect(caption(aAtRisk, sources("estimated", "measured", "estimated")).message).toBe(
      "A 낮은 상가 도로 · 약 10초 후 침수 예상 (모델 추정)",  // 기대하는 문구(모델 추정 포함)
    );
    expect(caption(cAtRisk, sources("measured", "measured", "measured")).message).toBe("C 높은 광장 · 약 10초 후 침수 예상");
  });

  it("evacuate says flooding has happened", () => {
    const banner = caption(trio(status("A", "evacuate", 0), status("B", "warning", 10), status("C", "safe", null)), SIM_SOURCES);
    expect(banner).toEqual({ stage: "evacuate", zoneId: "A", message: "A 낮은 상가 도로 · 침수 발생" });
  });

  it("a non-safe stage without eta still names the zone", () => {
    const banner = caption(trio(status("A", "safe", null), status("B", "caution", null), status("C", "safe", null)), SIM_SOURCES);
    expect(banner.message).toBe("B 주택 골목 · 침수 위험");
  });
});

describe("phrase", () => {
  it("says when each stage reaches the threshold, with the seconds apart so the card can show them large", () => {
    expect(phrase(status("A", "safe", null))).toEqual({ value: null, rest: "30초 안에 한계 도달 예상 없음" });
    expect(phrase(status("A", "caution", 20))).toEqual({ value: "약 20초", rest: "후 한계 도달 예상" });
    expect(phrase(status("A", "warning", 10))).toEqual({ value: "약 10초", rest: "후 한계 도달 예상" });
    expect(phrase(status("A", "evacuate", 0))).toEqual({ value: null, rest: "한계 도달" });
  });

  it("does not invent a time the server did not send", () => {
    expect(phrase(status("B", "caution", null))).toEqual({ value: null, rest: "한계 도달 예상 · 시각 미상" });
    expect(phrase(status("B", "warning", null))).toEqual({ value: null, rest: "한계 도달 예상 · 시각 미상" });
  });
});

describe("gauge", () => {
  it("ratio is level over threshold, clamped to 0..1", () => {
    expect(fraction(22.5, 45)).toBe(0.5);
    expect(fraction(45, 45)).toBe(1);
    expect(fraction(60, 45)).toBe(1);
    expect(fraction(0, 45)).toBe(0);
    expect(fraction(10, 0)).toBe(0);
  });

  it("percent rounds down so 100 % means the threshold is reached", () => {
    expect(share(44.9, 45)).toBe(99);  // 44.9 는 99 % 여야 함
    expect(share(45, 45)).toBe(100);  // 45 는 100 % 여야 함
    expect(share(60, 45)).toBe(133);  // 60 은 133 % 여야 함(한계를 넘는 값은 그대로)
    expect(share(25.65, 45)).toBe(57);  // 25.65 나누기 45 는 소수 오차를 보정해 57 % 여야 함
  });

  it("never shows 100 % below the threshold, the same boundary as the evacuate stage", () => {
    expect(share(44.9999999999, 45)).toBe(99);  // 44.9999999999 는 99 % 여야 함
    expect(share(54.99999999999, 55)).toBe(99);  // 54.99999999999 는 한계 55 아래라 99 % 여야 함
    expect(verdict("A", 44.9999999999, plateau(0), 45).stage).not.toBe("evacuate");
  });
});

describe("figure", () => {
  // 반올림 대신 0.1 mm 로 내려서 한계 아래 값이 한계로 안 읽히는지 검사
  it("cuts to 0.1 mm instead of rounding, so a level below the threshold never reads as the threshold", () => {
    expect(figure(44.96, 45)).toBe("44.9");
    expect(figure(44.9999999999, 45)).toBe("44.9");
    expect(figure(45, 45)).toBe("45.0");
    expect(figure(45.37, 45)).toBe("45.3");  // 45.37 은 45.3 이어야 함(내림)
  });

  it("keeps decimals that floats store a hair off", () => {
    expect(figure(0.1 * 3, 45)).toBe("0.3");
    expect(figure(0.7 * 3, 45)).toBe("2.1");
    expect(figure(31.8, 55)).toBe("31.8");  // 31.8 은 31.8 그대로여야 함
  });

  it("works before the threshold is known", () => {  // 한계를 알기 전에도 동작하는지 검사
    expect(figure(44.96, null)).toBe("44.9");
    expect(figure(0, null)).toBe("0.0");
  });
});

describe("level history", () => {
  const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각(2026-10-25 01:00 UTC)
  const RUN = { experimentId: "EXP-20261025-001", dataSource: "sim" as const };
  // 기준 시각에서 sec 초 뒤의 스냅샷을 만드는 도우미
  const frame = (sec: number, A = 10, run: { experimentId: string; dataSource: "sim" | "replay" | "live" } = RUN) => ({
    ...run,  // 실험 번호와 입력원을 그대로 씀
    timestamp: stamp(T + sec * 1000),
    zones: { A: { levelMm: A }, B: { levelMm: 8 }, C: { levelMm: 4 } },
  });

  it("adds one sample per new server timestamp", () => {
    const history = entry(entry(EMPTY_HISTORY, frame(0, 10)), frame(1, 11));
    expect(history.samples).toEqual([
      { t: T, A: 10, B: 8, C: 4 },
      { t: T + 1000, A: 11, B: 8, C: 4 },
    ]);
  });

  // 같은 시각이 또 오면 이력이 그대로인지 검사(정지·대기 중인 서버)
  it("keeps the same history for a repeated timestamp (stopped or idle server)", () => {
    const history = entry(EMPTY_HISTORY, frame(0));
    expect(entry(history, frame(0, 99))).toBe(history);
  });

  it("starts over when time goes backwards or the run changes", () => {
    const history = entry(entry(EMPTY_HISTORY, frame(0)), frame(1));
    expect(entry(history, frame(-5)).samples).toEqual([{ t: T - 5000, A: 10, B: 8, C: 4 }]);
    expect(entry(history, frame(2, 10, { ...RUN, experimentId: "EXP-20261025-002" })).samples).toHaveLength(1);
    expect(entry(history, frame(2, 10, { ...RUN, dataSource: "replay" })).samples).toHaveLength(1);
  });

  it("keeps the latest 600 samples", () => {
    let history = EMPTY_HISTORY;
    for (let sec = 0; sec < 605; sec += 1) history = entry(history, frame(sec));
    expect(HISTORY_LIMIT).toBe(600);
    expect(history.samples).toHaveLength(600);
    expect(history.samples[0].t).toBe(T + 5000);
    expect(history.samples.at(-1)?.t).toBe(T + 604_000);
  });
});

describe("expiry and disconnection", () => {
  const T = Date.UTC(2026, 9, 23, 1, 0, 0);  // 기준 시각(2026-10-23 01:00 UTC)

  it("a prediction is stale only when now - basis exceeds validity", () => {
    expect(expiry(T + 5000, T, 5)).toBe(false);
    expect(expiry(T + 5001, T, 5)).toBe(true);
    expect(expiry(T - 1000, T, 5)).toBe(false);
  });

  it("disconnected only when more than 4 s passed since the last good response", () => {
    expect(outage(T + 4000, T)).toBe(false);
    expect(outage(T + 4001, T)).toBe(true);
    expect(outage(T, null)).toBe(true);
  });

  // 선행 시간이 도달 시각에서 주의보 시각을 뺀 초인지 검사
  it("lead time is arrival minus caution, in seconds", () => {
    expect(lead(T, T + 20_000)).toBe(20);  // 주의보 20초 뒤 도달이면 20 이어야 함
    expect(lead(null, T)).toBeNull();  // 주의보가 없으면 null 이어야 함
    expect(lead(T, null)).toBeNull();
  });
});

describe("Seoul time", () => {
  it("formats an instant as KST ISO with milliseconds", () => {
    expect(stamp(Date.UTC(2026, 9, 22, 1, 0, 42))).toBe("2026-10-22T10:00:42.000+09:00");
    expect(stamp(Date.UTC(2026, 9, 22, 15, 30, 5, 123))).toBe("2026-10-23T00:30:05.123+09:00");
  });

  it("formats the clock as HH:MM:SS in KST", () => {  // 서울 시각을 시:분:초 글자로 바꾸는지 검사
    expect(clock(Date.UTC(2026, 9, 22, 1, 0, 42))).toBe("10:00:42");
    expect(clock(Date.UTC(2026, 9, 22, 15, 30, 5, 999))).toBe("00:30:05");
  });
});

describe("plot", () => {
  // 그림 크기. 안쪽 300px 가 150초(지난 120 + 예측 30)라 1초당 2px
  const options = { width: 354, height: 248 };
  const END = Date.UTC(2026, 9, 23, 1, 2, 0);  // 그래프 끝 시각(2026-10-23 01:02 UTC)
  const samples = [  // 1초 간격 표본 세 개
    { t: END - 2000, A: 10, B: 8, C: 4 },
    { t: END - 1000, A: 12, B: 8, C: 4.5 },
    { t: END, A: 14, B: 8, C: 5 },
  ];
  const predictions = { A: { "10": 16, "20": 18, "30": 20 }, B: plateau(8), C: plateau(5) };

  it("draws measured lines over the last 120 s with yMax from thresholds", () => {
    const chart = plot(samples, predictions, THRESHOLDS, options);
    expect(chart.yMax).toBe(80);
    expect(chart.measured.A).toBe("M 276 195 L 278 190 L 280 185");
    expect(chart.measured.B).toBe("M 276 200 L 278 200 L 280 200");
    expect(chart.nowX).toBe(280);
  });

  it("draws predictions from the last point to +30 s", () => {
    const chart = plot(samples, predictions, THRESHOLDS, options);
    expect(chart.predicted.A).toBe("M 280 185 L 300 180 L 320 175 L 340 170");
  });

  it("gives the y of each line's last point, where the zone letter goes", () => {
    expect(plot(samples, predictions, THRESHOLDS, options).endY).toEqual({ A: 185, B: 200, C: 207.5 });
  });

  it("puts threshold lines and gridlines on the same scale", () => {
    const chart = plot(samples, predictions, THRESHOLDS, options);
    expect(chart.thresholdY).toEqual({ A: 107.5, B: 82.5, C: 57.5 });
    expect(chart.gridlines).toEqual([  // 가로 눈금은 0 부터 80 까지 16 간격이어야 함
      { value: 0, y: 220 },
      { value: 16, y: 180 },
      { value: 32, y: 140 },
      { value: 48, y: 100 },
      { value: 64, y: 60 },
      { value: 80, y: 20 },
    ]);
  });

  it("raises yMax to fit values above the thresholds", () => {
    const high = [{ t: END, A: 150, B: 8, C: 4 }];
    expect(plot(high, null, THRESHOLDS, options).yMax).toBe(180);
    expect(plot([], { A: plateau(100), B: plateau(0), C: plateau(0) }, THRESHOLDS, options).yMax).toBe(80);
  });

  it("drops samples older than the window and breaks lines at gaps", () => {
    const chart = plot(
      [
        { t: END - 121_000, A: 40, B: 8, C: 4 },  // 121초 전 표본(범위 밖이라 버려짐)
        { t: END - 120_000, A: 10, B: 8, C: 4 },  // 120초 전 표본(범위 안 가장자리)
        { t: END - 10_000, A: 12, B: 8, C: 4 },
        { t: END, A: 14, B: 8, C: 4 },
      ],
      null,
      THRESHOLDS,
      options,
    );
    expect(chart.measured.A).toBe("M 40 195 M 260 190 M 280 185");
    expect(chart.predicted.A).toBe("");
  });

  it("marks samples with no neighbour inside the gap, since a lone move draws nothing", () => {
    const apart = [
      { t: END - 120_000, A: 10, B: 8, C: 4 },
      { t: END - 10_000, A: 12, B: 8, C: 4 },
      { t: END, A: 14, B: 8, C: 4 },
    ];
    expect(plot(apart, null, THRESHOLDS, options).isolated.A).toEqual([
      { x: 40, y: 195 },  // 120초 전 점
      { x: 260, y: 190 },  // 10초 전 점
      { x: 280, y: 185 },
    ]);
    expect(plot(samples, predictions, THRESHOLDS, options).isolated).toEqual({ A: [], B: [], C: [] });
  });

  it("leaves out threshold lines while the thresholds are unknown", () => {
    const chart = plot(samples, predictions, null, options);
    expect(chart.thresholdY).toBeNull();  // 한계선은 없어야 함(null)
    expect(chart.yMax).toBe(30);  // 값만으로 20 곱하기 1.15 = 23 을 올린 30 이어야 함
    expect(chart.measured.A).toBe("M 276 153.33 L 278 140 L 280 126.67");
  });

  it("is empty without samples", () => {
    const chart = plot([], predictions, THRESHOLDS, options);
    expect(chart.measured).toEqual({ A: "", B: "", C: "" });
    expect(chart.predicted).toEqual({ A: "", B: "", C: "" });
    expect(chart.nowX).toBeNull();
    expect(chart.endY).toBeNull();
    expect(chart.yMax).toBe(80);
    expect(chart.isolated).toEqual({ A: [], B: [], C: [] });
  });
});

describe("columns", () => {
  // 라벨이 선 위에 얹혀 겹치지 않도록, 멀면 모두 첫 칸인지 검사
  it("keeps every label in the first column while the lines are far apart", () => {
    // 실제 차트(높이 300, 여백 12, 최대 80)에서 45·55·65 mm 의 y 값이면 모두 0 칸
    expect(columns({ A: 132.75, B: 98.25, C: 63.75 }, 28)).toEqual({ A: 0, B: 0, C: 0 });
  });

  it("moves a label aside only while it would cover another in the same column", () => {
    expect(columns({ A: 150, B: 140, C: 110 }, 28)).toEqual({ A: 0, B: 1, C: 0 });
    expect(columns({ A: 150, B: 140, C: 130 }, 28)).toEqual({ A: 0, B: 1, C: 2 });
  });

  it("lets labels exactly one label height apart share a column", () => {
    expect(columns({ A: 150, B: 122, C: 94 }, 28)).toEqual({ A: 0, B: 0, C: 0 });
  });
});
