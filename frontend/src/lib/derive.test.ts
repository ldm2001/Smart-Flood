import { describe, expect, it } from "vitest";
import {
  notices,
  entry,
  caption,
  plot,
  EMPTY_HISTORY,
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
  topic,
  scope,
  rows,
  milestones,
  condition,
  readiness,
  obstruction,
  holding,
  spot,
  pool,
  address,
  notches,
  EVENT_ROWS,
  linkage,
  halt,
  gates,
  step,
  rate,
  brim,
  command,
  shower,
  plug,
  pass,
  wording,
  question,
  outcome,
  reasons,
  amendment,
  type Delivery,
  type Gate,
  type Grade,
  type Milestones,
} from "./derive";
import { PLAN_ZONES } from "./layout-data";
import { demo } from "./mock";
import type { Fault } from "./api";
import type {
  Alert,
  Control,
  Input,
  LogEvent,
  Run,
  Snapshot,
  StageEvent,
  Zone,
  Source,
} from "./schema";

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

  it("all safe gives a safe worst zone", () => {  // 모두 정상이면 최악도 정상인지 검사
    const zones = trio(status("A", "safe", null), status("B", "safe", null), status("C", "safe", null));
    expect(peak(zones).stage).toBe("safe");
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
      { zone: "A", stage: "warning", etaSec: 10 },  // 경계 10초(침수보다 낮음)
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

const T0 = Date.UTC(2026, 9, 22, 1, 0, 0);  // 회차 시작 시각(2026-10-22 10:00 KST)
// 측정 기록의 단계 줄임말
const CODES = { s: "safe", c: "caution", w: "warning", e: "evacuate" } as const;

// 측정 기록 한 회("초 구역 이전 새 etaSec" 를 ; 로 이음)를 단계 사건 목록으로 바꾸는 도우미
function run(text: string): StageEvent[] {
  return text.split(";").map((line): StageEvent => {
    const [sec, zone, from, to, eta] = line.trim().split(" ");
    const stage = CODES[to as keyof typeof CODES];
    const previous = CODES[from as keyof typeof CODES];
    return {
      type: "event",
      kind: "stage",
      elapsedSec: Number(sec),
      time: stamp(T0 + Number(sec) * 1000),
      message: `${zone} 구역 ${stage} (이전 ${previous})`,
      zone: zone as Zone,
      stage,
      previous,
      etaSec: eta === "-" ? null : Number(eta),  // - 는 안 오름(null)
    };
  });
}

const R1 = run(  // 설계 1.3 의 기울기 측정 r1~r4
  "67 A s e 0; 97 B s c 43; 98 B c w 28; 140 B w s -; 143 C s c 44; 147 C c w 30; 155 B s w 1",
);
const R2 = run(
  "33 A s e 0; 50 B s w 5; 65 C s c 49; 66 B w s -; 67 B s w 1; 68 C c w 16; 77 B w e 0; " +
    "81 C w s -",
);
const R3 = run(
  "63 A s e 0; 84 B s w 27; 122 B w s -; 132 C s c 41; 133 C c w 27; 135 B s w 1; 151 C w s -; " +
    "153 B w e 0",
);
const R4 = run("123 A s e 0; 173 B s w 14; 203 B w s -; 223 B s w 1");
const FAULT: LogEvent = {  // 계산 오류 사건(154초)
  type: "event",
  kind: "calc_error",
  elapsedSec: 154,
  time: "2026-10-22T10:02:34.123456+09:00",
  message: "Underflow: A 저장량이 -0.001 m³ 다",
};
const LIVE = { ...demo(T0, THRESHOLDS), experimentId: "EXP-20261101-001" };  // 기록 꼴 번호의 상태

// 타임라인 세 사건의 경과 초. 없으면 null
const seconds = (m: Milestones) =>
  [m.judgement, m.request, m.arrival].map((event) => event?.elapsedSec ?? null);
// 사건의 경과 밀리초. 없으면 null
const at = (event: StageEvent | null) => (event === null ? null : event.elapsedSec * 1000);

describe("topic", () => {
  it("reads only record ids", () => {
    expect(topic(null)).toBeNull();
    expect(topic({ ...LIVE, experimentId: "EXP-STANDBY" })).toBeNull();
    expect(topic({ ...LIVE, experimentId: "EXP-DEMO-001" })).toBeNull();
    expect(topic(LIVE)?.[1]).toBe("EXP-20261101-001");
  });

  it("changes with stages and the run state but not with etaSec", () => {
    const alerts: Alert[] = [{ zone: "B", stage: "warning", etaSec: 27 }];
    const base = { ...LIVE, alerts };
    const variant = (alert: Alert) => topic({ ...base, alerts: [alert] });  // 경보 하나만 바꾼 키
    const key = topic(base);
    expect(key).toEqual(["events", "EXP-20261101-001", "B:warning", "running"]);
    expect(variant({ zone: "B", stage: "warning", etaSec: 5 })).toEqual(key);
    expect(variant({ zone: "B", stage: "evacuate", etaSec: 0 })).not.toEqual(key);
    expect(topic({ ...base, runState: "stopped" })).not.toEqual(key);
    expect(topic({ ...base, runState: undefined })?.[3]).toBe("none");
  });
});

describe("scope", () => {
  it("hides future events in a replay but keeps the same second", () => {
    const seen = scope(R3, { mode: "replay", elapsedSec: 135 }).map((event) => event.elapsedSec);
    expect(seen).toEqual([63, 84, 122, 132, 133, 135]);
  });

  it("leaves a live list alone, even an error one tick ahead", () => {
    const list = [...R3, FAULT];
    expect(scope(list, { mode: "live", elapsedSec: 153 })).toBe(list);
  });
});

describe("rows", () => {
  it("keeps the newest 30, newest first", () => {
    const list = rows(run(Array.from({ length: 31 }, (_, i) => `${i} A s c 50`).join(";")));
    expect(list).toHaveLength(EVENT_ROWS);
    expect(list[0].elapsedSec).toBe(30);
    expect(list.at(-1)?.elapsedSec).toBe(1);
  });
});

describe("milestones", () => {
  it("picks the episode that holds the first evacuate", () => {
    expect(seconds(milestones(R2, "B"))).toEqual([67, 67, 77]);
    expect(seconds(milestones(R3, "B"))).toEqual([135, 135, 153]);
  });

  it("uses the one evacuate event for all three when a zone jumps from safe", () => {
    for (const events of [R1, R2, R3, R4]) {
      const { judgement, request, arrival } = milestones(events, "A");
      expect(judgement?.stage).toBe("evacuate");
      expect(request).toBe(judgement);
      expect(arrival).toBe(judgement);
    }
  });

  it("falls back to the last episode that left safe, with no arrival", () => {
    expect(seconds(milestones(R1, "B"))).toEqual([155, 155, null]);
    expect(seconds(milestones(R1, "C"))).toEqual([143, 147, null]);
    expect(seconds(milestones(R2, "C"))).toEqual([65, 68, null]);
    expect(seconds(milestones(R3, "C"))).toEqual([132, 133, null]);
    expect(seconds(milestones(R4, "B"))).toEqual([223, 223, null]);
  });

  it("keeps the episode a replay cut at 122 s shows", () => {
    const cut = scope(R3, { mode: "replay", elapsedSec: 122 });
    expect(seconds(milestones(cut, "B"))).toEqual([84, 84, null]);
  });

  it("has no request while the episode stays at caution", () => {
    expect(seconds(milestones(run("5 C s c 50"), "C"))).toEqual([5, null, null]);
  });

  it("gives nothing without an episode", () => {
    expect(seconds(milestones(run("10 A c s -"), "A"))).toEqual([null, null, null]);  // 정상 사건만
    expect(seconds(milestones([], "A"))).toEqual([null, null, null]);
    expect(seconds(milestones(R4, "C"))).toEqual([null, null, null]);
  });

  it("skips calculation errors mixed into the list", () => {
    const mixed = [...R3.slice(0, 6), { ...FAULT, elapsedSec: 140 }, ...R3.slice(6)];
    expect(seconds(milestones(mixed, "B"))).toEqual([135, 135, 153]);
  });
});

describe("lead", () => {
  it("is arrival minus judgement from the event seconds", () => {
    const b2 = milestones(R2, "B");
    const b3 = milestones(R3, "B");
    const c3 = milestones(R3, "C");
    expect(lead(at(b2.judgement), at(b2.arrival))).toBe(10);
    expect(lead(at(b3.judgement), at(b3.arrival))).toBe(18);
    expect(lead(at(c3.judgement), at(c3.arrival))).toBeNull();
  });
});

describe("devices", () => {
  it("labels known values and shows unknown ones as they are", () => {
    expect(condition("online")).toEqual({ label: "정상", ok: true });
    expect(condition("normal")).toEqual({ label: "정상", ok: true });
    expect(condition("offline")).toEqual({ label: "끊김", ok: false });
    expect(condition("unknown")).toEqual({ label: "미상", ok: false });
    expect(condition("low")).toEqual({ label: "물 부족", ok: false });  // 실측 플로트 물 부족
    expect(condition("tripped")).toEqual({ label: "tripped", ok: false });
    expect(condition("constructor")).toEqual({ label: "constructor", ok: false });
  });

  it("is ready only when all four protection inputs are healthy", () => {
    expect(readiness(LIVE.devices)).toBe(true);  // 시뮬레이션 장치 값
    const rev16 = {  // REV16 실측 입력의 장치 값
      esp32_1: "online",
      esp32_2: "offline",
      floatSwitch: "unknown",
      emergencyStop: "unknown",
    };
    expect(readiness(rev16)).toBe(false);
    expect(readiness({ ...LIVE.devices, floatSwitch: "low" })).toBe(false);  // 물 부족이면 확인
  });
});

describe("obstruction and holding", () => {
  it("gives the blockage type only at the blocked inlet", () => {
    const blockage = {
      location: "INLET-02",
      type: "partial" as const,
      label: "빗물받이 ② 부분 막힘",
    };
    const clear = { location: null, type: "none" as const, label: "정상 배수" };
    expect(obstruction(blockage, "INLET-02")).toBe("partial");
    expect(obstruction(blockage, "INLET-03")).toBe("none");
    expect(obstruction(clear, "INLET-01")).toBe("none");
  });

  it("keeps a list only for the current record", () => {
    const pack = { id: "EXP-20261101-001", list: R3 };
    expect(holding(null, pack)).toEqual([]);
    expect(holding("EXP-20261101-001", pack)).toBe(R3);
    expect(holding("EXP-20261101-002", pack)).toBeNull();
    expect(holding("EXP-20261101-001", null)).toBeNull();
  });
});

describe("plan geometry", () => {
  it("turns plan coordinates into CSS percentages", () => {
    expect(spot(150, 80)).toEqual({ left: "50%", top: "50%" });
    expect(spot(35, 100)).toEqual({ left: "11.67%", top: "62.5%" });
  });

  it("fills a zone box from the bottom", () => {
    expect(pool(PLAN_ZONES.A, 0.5)).toEqual({ y: 60, height: 50 });
    expect(pool(PLAN_ZONES.A, 0)).toEqual({ y: 110, height: 0 });
    expect(pool(PLAN_ZONES.A, 1)).toEqual({ y: 10, height: 100 });
  });
});

describe("address", () => {
  it("ends every menu path with a slash", () => {
    expect(address("/")).toBe("/");
    expect(address("/ops")).toBe("/ops/");
    expect(address("/ops/")).toBe("/ops/");
  });
});

describe("notches", () => {
  it("puts a minor tick halfway between neighbouring gridlines", () => {
    expect(notches([{ y: 100 }, { y: 60 }, { y: 20 }])).toEqual([80, 40]);
    expect(notches([{ y: 10 }])).toEqual([]);
  });
});

// 회차 상태와 입력원을 정한 응답. runState 를 undefined 로 주면 그 칸을 뺌
function snap(runState: Run | null | undefined, dataSource: Input): Snapshot {
  const base: Snapshot = { ...demo(T0, THRESHOLDS), dataSource };
  if (runState === undefined) delete base.runState;
  else base.runState = runState;
  return base;
}
// 판정을 켜짐은 "on", 꺼짐은 "자리:이유" 글로 줄임
const brief = (all: Record<Control, Gate>) =>
  Object.fromEntries(
    Object.entries(all).map(([key, gate]) => [key, gate.on ? "on" : `${gate.cue}:${gate.reason}`]),
  );
const BUSY = "own:회차가 진행 중이라 입력원을 바꿀 수 없습니다. 먼저 종료합니다";  // 진행 중 입력원
const UNKNOWN = "own:서버가 회차 상태를 보내지 않았습니다";  // 회차 상태 없음
const IDLE = {
  start: "on",
  stop: "own:진행 중이 아닙니다",
  reset: "on",
  rain: "on",
  blockage: "on",
  replay: "on",
};
const RUNNING = {
  start: "own:이미 진행 중입니다",
  stop: "on",
  reset: "on",
  rain: "on",
  blockage: "on",
  replay: "own:회차가 도는 중이라 재생할 수 없습니다. 운영·설정에서 먼저 종료합니다",
};
const REPLAYING = {  // 재생 중 끈 제어와 이유
  start: "own:재생 중에는 회차를 시작할 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다",
  reset: "own:재생 중에는 초기화할 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다",
  rain: "own:재생 중에는 강우를 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다",
  blockage: "own:재생 중에는 막힘을 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다",
  live: "own:재생 중에는 실측으로 바꿀 수 없습니다. 먼저 시뮬레이션으로 돌아갑니다",
  sim: "on",
  replay: "on",  // 다른 기록으로 바꿈
};
const HALT = {  // 연결마다 제어를 끈 이유
  connecting: "서버에 연결하는 중이라 제어를 끕니다",
  mock: "서버에 연결되지 않아 제어를 끕니다. 가상 데이터에는 보내지 않습니다",
  lost: "연결이 끊겨 제어를 끕니다 · 마지막 수신 10:00:00 기준",
};
// 여덟 제어가 모두 같은 판정
const every = (text: string) =>
  Object.fromEntries(
    ["start", "stop", "reset", "rain", "blockage", "sim", "live", "replay"].map((key) => [
      key,
      text,
    ]),
  );

describe("linkage", () => {
  it("waits for the clock and the first answer, and calls a failed first try mock", () => {
    expect(linkage(null, T0, false)).toBe("connecting");
    expect(linkage(T0, null, false)).toBe("connecting");
    expect(linkage(T0, null, true)).toBe("mock");
  });

  it("calls the link lost only when a poll failed more than 4 s after the last answer", () => {
    expect(linkage(T0 + 4000, T0, true)).toBe("online");
    expect(linkage(T0 + 4001, T0, true)).toBe("lost");
    expect(linkage(T0 + 4001, T0, false)).toBe("connecting");  // 실패 없이 오래됨: 다시 묻는 중
  });
});

describe("halt", () => {
  it("names why the controls are off for each link", () => {
    expect(halt("online", T0)).toBeNull();
    expect(halt("connecting", null)).toBe(HALT.connecting);
    expect(halt("mock", null)).toBe(HALT.mock);
    expect(halt("lost", T0)).toBe(HALT.lost);
    expect(halt("lost", null)).toBe("연결이 끊겨 제어를 끕니다 · 마지막 수신 — 기준");
  });
});

describe("gates", () => {
  it("turns everything off with the halt text until the link is online", () => {
    const state = snap("idle", "sim");
    expect(brief(gates("connecting", null, null, null))).toEqual(every(`halt:${HALT.connecting}`));
    expect(brief(gates("mock", null, null, null))).toEqual(every(`halt:${HALT.mock}`));
    expect(brief(gates("lost", T0, state, null))).toEqual(every(`halt:${HALT.lost}`));
    expect(brief(gates("lost", T0, state, "start"))).toEqual(every(`halt:${HALT.lost}`));  // 끊김이 먼저
    expect(brief(gates("online", T0, null, null))).toEqual(every(`halt:${HALT.connecting}`));
  });

  it("turns the gates that were on off while a control is being sent", () => {
    const idle = gates("online", T0, snap("idle", "sim"), "start");
    expect(brief(idle)).toEqual({
      ...every("note:시작 보내는 중입니다"),
      stop: "own:진행 중이 아닙니다",  // 제 이유로 꺼진 제어는 그 이유를 둠
      sim: "own:이미 시뮬레이션입니다",
    });
    const replay = gates("online", T0, snap("running", "replay"), "stop");
    const busy = "note:재생 멈춤 보내는 중입니다";
    expect(brief(replay)).toEqual({ ...REPLAYING, stop: busy, sim: busy, replay: busy });
  });

  it("keeps the reason lines of every panel while a control is being sent", () => {
    const lines = (all: Record<Control, Gate>) => reasons(Object.entries(all)).lines;
    const states = [
      snap("idle", "sim"),
      snap("running", "live"),
      snap("stopped", "replay"),
      snap(null, "sim"),
    ];
    for (const state of states) {
      const rest = gates("online", T0, state, null);  // 보내기 전
      expect(lines(rest).length).toBeGreaterThan(0);
      expect(lines(gates("online", T0, state, "rain"))).toEqual(lines(rest));
    }
  });

  it("follows the run state and the input in sim and live", () => {
    const sim = { sim: "own:이미 시뮬레이션입니다", live: "on" };  // 지금 sim
    const live = { sim: "on", live: "own:이미 실측입니다" };  // 지금 live
    expect(brief(gates("online", T0, snap("idle", "sim"), null))).toEqual({ ...IDLE, ...sim });
    expect(brief(gates("online", T0, snap("idle", "live"), null))).toEqual({ ...IDLE, ...live });
    expect(brief(gates("online", T0, snap("stopped", "sim"), null))).toEqual({ ...IDLE, ...sim });
    expect(brief(gates("online", T0, snap("stopped", "live"), null))).toEqual({ ...IDLE, ...live });
    expect(brief(gates("online", T0, snap("running", "sim"), null))).toEqual({
      ...RUNNING,
      sim: "own:이미 시뮬레이션입니다",  // 같은 쪽 전환이 먼저
      live: BUSY,
    });
    expect(brief(gates("online", T0, snap("running", "live"), null))).toEqual({
      ...RUNNING,
      sim: BUSY,
      live: "own:이미 실측입니다",
    });
  });

  it("leaves only stop and the way back to sim during a replay", () => {
    const running = gates("online", T0, snap("running", "replay"), null);
    expect(brief(running)).toEqual({ ...REPLAYING, stop: "on" });
    const halted = { ...REPLAYING, stop: "own:재생이 멈춰 있습니다" };  // 재생 정지
    for (const runState of ["stopped", "idle", null, undefined] as const) {
      expect(brief(gates("online", T0, snap(runState, "replay"), null))).toEqual(halted);
    }
  });

  it("keeps reset, rain and blockage when the server sends no run state", () => {
    const unknown = {
      start: UNKNOWN,
      stop: UNKNOWN,
      reset: "on",
      rain: "on",
      blockage: "on",
      sim: UNKNOWN,
      live: UNKNOWN,
      replay: UNKNOWN,
    };
    expect(brief(gates("online", T0, snap(null, "sim"), null))).toEqual(unknown);
    expect(brief(gates("online", T0, snap(undefined, "live"), null))).toEqual(unknown);
  });
});

describe("step", () => {
  it("opens a row without sending, sends it on yes and closes on anything else", () => {
    expect(step(null, { kind: "ask", control: "stop" })).toEqual({ open: "stop", send: null });
    expect(step("stop", { kind: "ask", control: "reset" })).toEqual({ open: "reset", send: null });
    expect(step("reset", { kind: "yes" })).toEqual({ open: null, send: "reset" });
    expect(step("sim", { kind: "no" })).toEqual({ open: null, send: null });
    expect(step("live", { kind: "other" })).toEqual({ open: null, send: null });
    expect(step(null, { kind: "yes" })).toEqual({ open: null, send: null });
  });
});

describe("rate and brim", () => {
  it("checks the typed rain against the server ceiling", () => {
    expect(rate("60", null)).toEqual({ ok: false, reason: "서버 강우 설정이 없어 직접 입력을 끕니다" });
    expect(rate("  ", 150)).toEqual({ ok: false, reason: "0 ~ 150 사이 숫자를 넣어 주세요" });
    expect(rate("abc", 150)).toEqual({ ok: false, reason: "숫자만 넣을 수 있습니다" });
    expect(rate("Infinity", 150)).toEqual({ ok: false, reason: "숫자만 넣을 수 있습니다" });
    expect(rate("-0.1", 150)).toEqual({ ok: false, reason: "0 이상이어야 합니다" });
    expect(rate("150.1", 150)).toEqual({ ok: false, reason: "150 mm/h 이하만 됩니다" });
    expect(rate(" 0 ", 150)).toEqual({ ok: true, value: 0 });
    expect(rate("75.5", 150)).toEqual({ ok: true, value: 75.5 });
    expect(rate("150", 150)).toEqual({ ok: true, value: 150 });
  });

  it("checks a mock threshold against the 500 mm ceiling", () => {
    expect(brim("")).toEqual({ ok: false, reason: "숫자를 넣어 주세요" });
    expect(brim("4.5mm")).toEqual({ ok: false, reason: "숫자만 넣을 수 있습니다" });
    expect(brim("0")).toEqual({ ok: false, reason: "0 보다 커야 합니다" });
    expect(brim("500.1")).toEqual({ ok: false, reason: "500 mm 이하만 됩니다" });
    expect(brim("0.5")).toEqual({ ok: true, value: 0.5 });
    expect(brim(" 500 ")).toEqual({ ok: true, value: 500 });
  });
});

describe("command bodies", () => {
  it("builds only the keys the server models accept", () => {
    expect(command("start")).toEqual({ control: "start", body: {} });
    expect(command("stop")).toEqual({ control: "stop", body: {} });
    expect(command("reset")).toEqual({ control: "reset", body: {} });
    expect(command("sim")).toEqual({ control: "sim", body: { mode: "sim" } });
    expect(command("live")).toEqual({ control: "live", body: { mode: "live" } });
    expect(shower("heavy")).toEqual({ control: "rain", body: { intensity: "heavy" } });
    expect(shower(75.5)).toEqual({ control: "rain", body: { mmPerHour: 75.5 } });
  });

  it("asks for an inlet before a partial or full blockage", () => {
    const none = { control: "blockage", body: { type: "none" } };  // 빗물받이 없이 보냄
    expect(plug("none", "INLET-02")).toEqual({ ok: true, value: none });
    expect(plug("partial", "INLET-02")).toEqual({
      ok: true,
      value: { control: "blockage", body: { type: "partial", location: "INLET-02" } },
    });
    expect(plug("full", null)).toEqual({ ok: false, reason: "막을 빗물받이를 골라 주세요" });
  });

  it("keeps an off gate and turns a failed check into the panel's own reason", () => {
    const off: Gate = { on: false, reason: HALT.lost, cue: "halt" };
    const wrong = { ok: false, reason: "숫자만 넣을 수 있습니다" } as const;
    expect(pass(off, wrong)).toBe(off);
    expect(pass({ on: true }, wrong)).toEqual({ on: false, reason: "숫자만 넣을 수 있습니다", cue: "own" });
    expect(pass({ on: true }, { ok: true, value: 60 })).toEqual({ on: true });
    const busy = gates("online", T0, snap("running", "sim"), "rain").rain;  // 보내는 중
    expect(pass(busy, wrong)).toEqual({ on: false, reason: "숫자만 넣을 수 있습니다", cue: "own" });
    expect(pass(busy, { ok: true, value: 60 })).toBe(busy);  // 통과하면 보내는 중 그대로
  });
});

describe("wording and question", () => {
  it("renames stop and sim while a replay runs", () => {
    expect(wording("stop", false)).toBe("종료");
    expect(wording("stop", true)).toBe("재생 멈춤");
    expect(wording("sim", false)).toBe("시뮬레이션으로 바꾸기");
    expect(wording("sim", true)).toBe("시뮬레이션으로 돌아가기");
    expect(wording("rain", true)).toBe("강우 적용");
  });

  it("asks what each risky control will undo", () => {
    expect(question("stop", snap("running", "sim"))).toBe(
      "회차를 종료할까요? 비가 그치고 마지막 상태가 남습니다",
    );
    expect(question("stop", snap("running", "replay"))).toBe(
      "재생을 멈출까요? 멈춘 재생은 이어 볼 수 없습니다",
    );
    expect(question("reset", snap("idle", "sim"))).toBe(
      "강우·막힘 선택만 기본값(보통 강우, 막힘 없음)으로 돌립니다",
    );
    const end = "회차를 끝내고 대기로 돌아가며 강우·막힘 선택이 기본값이 됩니다. 기록 파일은 남습니다";
    expect(question("reset", snap("running", "sim"))).toBe(end);
    expect(question("reset", snap("stopped", "live"))).toBe(end);
    expect(question("reset", snap(null, "sim"))).toBe(end);  // 회차 상태를 모르면 무거운 쪽 물음
    const tail = "대기로 돌아가고 강우·막힘 선택이 기본값이 됩니다";  // 입력원 전환 뒤 일
    const wipe = "멈춘 회차의 마지막 화면도 지워집니다. 기록 파일은 남습니다";
    expect(question("sim", snap("idle", "live"))).toBe(`시뮬레이션으로 바꿀까요? ${tail}. ${wipe}`);
    expect(question("live", snap("stopped", "sim"))).toBe(`실측으로 바꿀까요? ${tail}. ${wipe}`);
    expect(question("sim", snap("stopped", "replay"))).toBe(
      `재생을 끝내고 시뮬레이션으로 돌아갈까요? ${tail}`,
    );
  });
});

describe("outcome", () => {
  // 성공한 제어. 받은 시각은 10:00:00
  const done = (control: Control, snapshot: Snapshot, replay = false): Delivery => ({
    control,
    replay,
    answer: { ok: true, receipt: { snapshot, receivedAt: T0 } },
  });
  // 실패한 제어. 실패 시각은 10:00:05
  const miss = (control: Control, fault: Fault, replay = false): Delivery => ({
    control,
    replay,
    answer: { ok: false, fault, at: T0 + 5000 },
  });

  it("says what changed and when it arrived", () => {
    const state = { ...snap("running", "sim"), experimentId: "EXP-20261101-001" };
    expect(outcome(done("start", state))).toEqual({
      tone: "ok",
      text: "반영 · 회차 시작 · EXP-20261101-001 · 10:00:00 수신",
    });
    expect(outcome(done("stop", state)).text).toBe("반영 · 회차 종료 · 10:00:00 수신");
    expect(outcome(done("stop", state, true)).text).toBe("반영 · 재생 멈춤 · 10:00:00 수신");
    expect(outcome(done("reset", state)).text).toBe("반영 · 초기화 · 대기 · 10:00:00 수신");
    expect(outcome(done("rain", state)).text).toBe("반영 · 강우 60 mm/h · 10:00:00 수신");
    expect(outcome(done("blockage", state)).text).toBe(
      "반영 · 막힘 설정 · 빗물받이 ② 부분 막힘 · 10:00:00 수신",
    );
    expect(outcome(done("sim", state)).text).toBe("반영 · 입력원 시뮬레이션 · 10:00:00 수신");
    expect(outcome(done("sim", state, true)).text).toBe(
      "반영 · 재생 끝냄 · 입력원 시뮬레이션 · 10:00:00 수신",
    );
    expect(outcome(done("live", state)).text).toBe("반영 · 입력원 실측 · 10:00:00 수신");
  });

  it("names each failure in the screen's words", () => {
    const text = "회차가 도는 중에는 입력원을 바꿀 수 없다. 먼저 종료한다";  // 서버의 409 글
    expect(outcome(miss("live", { kind: "refused", status: 409, text }))).toEqual({
      tone: "fail",
      text: `실측으로 바꾸기 거절 · ${text} · 10:00:05`,
    });
    expect(outcome(miss("rain", { kind: "status", status: 422 }))).toEqual({
      tone: "fail",
      text: "강우 적용 실패 · 요청 모양 오류 HTTP 422 · 10:00:05",
    });
    expect(outcome(miss("reset", { kind: "status", status: 500 }))).toEqual({
      tone: "fail",
      text: "초기화 실패 · 서버 오류 HTTP 500 · 10:00:05",
    });
    expect(outcome(miss("start", { kind: "network" }))).toEqual({
      tone: "fail",
      text: "시작 실패 · 서버에 닿지 못했습니다 · 10:00:05",
    });
    expect(outcome(miss("stop", { kind: "timeout" }, true))).toEqual({
      tone: "unsure",
      text: "재생 멈춤 응답 없음 · 5초 안에 답이 없었습니다. 반영됐는지는 다음 수신으로 확인합니다 · 10:00:05",
    });
    expect(outcome(miss("blockage", { kind: "format" }))).toEqual({
      tone: "unsure",
      text: "막힘 적용 응답 모양 이상 · 서버는 받았을 수 있습니다. 다음 수신으로 확인합니다 · 10:00:05",
    });
  });
});

describe("reasons", () => {
  it("keeps one line per text and points every holder at its first holder", () => {
    const veto = gates("online", T0, snap("running", "replay"), null).rain;  // 재생 중 강우 꺼짐
    const entries = [
      ["rain-light", veto],
      ["rain-medium", veto],
      ["rain-heavy", veto],
      ["rain", pass(veto, rate("", 150))],
      ["rain-mm", rate("", 150)],
    ] as const;
    expect(reasons(entries)).toEqual({
      lines: [
        {
          id: "ops-why-rain-light",
          text: "재생 중에는 강우를 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다",
        },
        { id: "ops-why-rain-mm", text: "0 ~ 150 사이 숫자를 넣어 주세요" },
      ],
      links: {
        "rain-light": "ops-why-rain-light",
        "rain-medium": "ops-why-rain-light",
        "rain-heavy": "ops-why-rain-light",
        rain: "ops-why-rain-light",
        "rain-mm": "ops-why-rain-mm",
      },
    });
  });

  it("leaves out gates that are on, texts of the halt and note lines, and passed checks", () => {
    const entries = [
      ["start", { on: true }],
      ["rain", gates("connecting", null, null, null).rain],  // 멈춤 줄의 이유
      ["blockage", gates("online", T0, snap("idle", "sim"), "start").blockage],  // 결과 줄의 이유
      ["rain-mm", rate("60", 150)],
    ] as const;
    expect(reasons(entries)).toEqual({ lines: [], links: {} });
  });
});

describe("amendment", () => {
  it("shows the saved values and keeps saving off until a value changes", () => {
    const form = amendment({}, THRESHOLDS);
    expect(form.texts).toEqual({ A: "45", B: "55", C: "65" });
    expect(form.save).toEqual({ ok: false, reason: "바뀐 값이 없습니다" });
    expect(amendment({ A: "45.0" }, THRESHOLDS).save).toEqual(form.save);  // 같은 수는 바뀜 아님
  });

  it("names the zone in each reason and blocks saving with the first wrong zone", () => {
    const form = amendment({ B: "", C: "600" }, THRESHOLDS);
    expect(form.texts).toEqual({ A: "45", B: "", C: "600" });
    expect(form.checks).toEqual({
      A: { ok: true, value: 45 },
      B: { ok: false, reason: "B 구역 · 숫자를 넣어 주세요" },
      C: { ok: false, reason: "C 구역 · 500 mm 이하만 됩니다" },
    });
    expect(form.save).toEqual(form.checks.B);
  });

  it("saves the trimmed number with the untouched zones", () => {
    expect(amendment({ A: " 40.5 " }, THRESHOLDS).save).toEqual({
      ok: true,
      value: { A: 40.5, B: 55, C: 65 },
    });
  });
});
