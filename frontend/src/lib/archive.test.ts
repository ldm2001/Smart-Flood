import { describe, expect, it } from "vitest";
import {
  gates,
  outcome,
  pass,
  playback,
  question,
  relay,
  rerun,
  span,
  stamp,
  tally,
  type Stage,
} from "./derive";
import { demo } from "./mock";
import {
  catalog,
  contract,
  type Input,
  type Run,
  type Snapshot,
  type StageEvent,
  type Zone,
} from "./schema";

const T0 = Date.UTC(2026, 9, 22, 1, 0, 0);  // 회차 시작 시각(2026-10-22 10:00 KST)
const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
const ID = "EXP-20261022-001";  // 고른 기록 번호

// 경과 e 초에 구역이 previous 에서 stage 로 바뀐 사건
function shift(e: number, zone: Zone, previous: Stage, stage: Stage, etaSec: number | null) {
  return {
    type: "event",
    kind: "stage",
    elapsedSec: e,
    time: stamp(T0 + e * 1000),
    message: `${zone} 구역 ${stage} (이전 ${previous})`,
    zone,
    stage,
    previous,
    etaSec,
  } as const satisfies StageEvent;
}

// 회차 상태·입력원·실험 번호를 정한 응답
function snap(runState: Run, dataSource: Input, experimentId = ID): Snapshot {
  return { ...demo(T0, THRESHOLDS), runState, dataSource, experimentId };
}

// 기록 목록의 한 줄
const entry = (id: string) => ({
  experimentId: id,
  startTime: "2026-10-22T10:00:00.000+09:00",
  dataSource: "sim",
  modelVersion: "0.1-assumed",
  configHash: "abc123",
});

describe("tally", () => {
  it("leaves the arrival, lead and error blank when no flood came", () => {
    const [, b] = tally([shift(84, "B", "safe", "warning", 27)]);
    expect(b).toEqual({
      zone: "B",
      judgement: T0 + 84_000,
      forecast: T0 + 111_000,  // 판단 84 초 + 남은 27 초
      arrival: null,
      lead: null,
      error: null,
    });
    expect([span(b.lead), span(b.error, true)]).toEqual(["—", "—"]);
  });

  it("gives zero lead and zero error for a zone that floods at once", () => {
    const [a] = tally([shift(63, "A", "safe", "evacuate", 0)]);
    const flood = T0 + 63_000;  // 63 초에 바로 침수
    expect(a).toMatchObject({ judgement: flood, forecast: flood, arrival: flood });
    expect([a.lead, a.error]).toEqual([0, 0]);
    expect(span(a.error, true)).toBe("0초");
  });

  it("compares each zone on its own and keeps the sign of the error", () => {
    const rows = tally([
      shift(100, "B", "safe", "warning", 10),
      shift(132, "C", "safe", "caution", 41),
      shift(133, "C", "caution", "warning", 27),
      shift(113, "B", "warning", "evacuate", 0),
      shift(170, "C", "warning", "evacuate", 0),
    ]);
    expect(rows.map((row) => row.zone)).toEqual(["A", "B", "C"]);
    expect(rows[0]).toMatchObject({ judgement: null, forecast: null, arrival: null });
    expect([rows[1].lead, rows[1].error]).toEqual([13, 3]);  // 예측보다 3 초 늦게 도달
    expect([rows[2].lead, rows[2].error]).toEqual([38, -3]);  // 판단 132 초 + 41 초보다 3 초 빠름
    expect([span(3, true), span(-3, true), span(38)]).toEqual(["+3초", "-3초", "38초"]);
  });

  it("blanks the forecast when the judgement had no eta", () => {
    const [, b] = tally([
      shift(90, "B", "safe", "caution", null),
      shift(99, "B", "caution", "evacuate", 0),
    ]);
    expect([b.forecast, b.lead, b.error]).toEqual([null, 9, null]);
  });
});

describe("replay start", () => {
  it("sends exactly the replay mode and the record id", () => {
    const request = playback(ID);
    expect(request.control).toBe("replay");
    expect(JSON.stringify(request.body)).toBe(`{"mode":"replay","logId":"${ID}"}`);
  });

  it("is on while idle or stopped and off with its own reason while a run goes", () => {
    const gate = (state: Snapshot) =>
      pass(gates("online", T0, state, null).replay, rerun(state, ID));
    expect(gate(snap("idle", "sim"))).toEqual({ on: true });
    expect(gate(snap("stopped", "sim"))).toEqual({ on: true });
    expect(gate(snap("running", "sim"))).toEqual({
      on: false,
      reason: "회차가 도는 중이라 재생할 수 없습니다. 운영·설정에서 먼저 종료합니다",
      cue: "own",
    });
    expect(gate(snap("running", "replay"))).toEqual({
      on: false,
      reason: "이 기록을 재생하는 중입니다",
      cue: "own",
    });
    expect(gate(snap("running", "replay", "EXP-20261022-002"))).toEqual({ on: true });  // 다른 기록
  });

  it("keeps the halt and sending rules of the other controls", () => {
    expect(pass(gates("mock", null, null, null).replay, rerun(null, ID))).toMatchObject({
      on: false,
      cue: "halt",
    });
    const busy = pass(gates("online", T0, snap("idle", "sim"), "replay").replay, rerun(null, ID));
    expect(busy).toEqual({ on: false, reason: "재생 시작 보내는 중입니다", cue: "note" });
    const same = gates("online", T0, snap("stopped", "replay"), "replay").replay;  // 보내는 중
    expect(pass(same, rerun(snap("stopped", "replay"), ID))).toMatchObject({ cue: "own" });
  });

  it("asks before replaying and reports the result like the other controls", () => {
    expect(question("replay", snap("idle", "sim"))).toBe(
      "이 기록을 처음부터 재생할까요? 멈춘 회차의 마지막 화면은 재생 화면으로 바뀝니다",
    );
    expect(question("replay", snap("running", "replay", "EXP-20261022-002"))).toBe(
      "지금 재생을 끝내고 이 기록을 처음부터 재생할까요?",
    );
    const receipt = { snapshot: snap("running", "replay"), receivedAt: T0 };
    const ok = outcome({ control: "replay", answer: { ok: true, receipt }, replay: false });
    expect(ok).toEqual({ tone: "ok", text: `반영 · 재생 시작 · ${ID} · 10:00:00 수신` });
    const text = "회차가 도는 중에는 재생할 수 없다. 먼저 종료한다";
    const fault = { kind: "refused", status: 409, text } as const;
    const answer = { ok: false, fault, at: T0 } as const;  // 409 거절
    const refused = outcome({ control: "replay", answer, replay: false });
    expect(refused.text).toBe(`재생 시작 거절 · ${text} · 10:00:00`);
  });
});

describe("catalog", () => {
  it("reads the record list and keeps unknown fields", () => {
    const logs = catalog({ logs: [{ ...entry(ID), extra: 1 }] });
    expect(logs.map((log) => log.experimentId)).toEqual([ID]);
    expect(catalog({ logs: [] })).toEqual([]);
  });

  it("rejects a list with a bad id, time, source or a missing field", () => {
    expect(() => catalog({ logs: [entry("abc")] })).toThrow();
    const utc = { ...entry(ID), startTime: "2026-10-22T01:00:00Z" };  // KST 오프셋 없음
    expect(() => catalog({ logs: [utc] })).toThrow();
    expect(() => catalog({ logs: [{ ...entry(ID), dataSource: "file" }] })).toThrow();
    const rest = Object.fromEntries(
      Object.entries(entry(ID)).filter(([key]) => key !== "configHash"),
    );
    expect(() => catalog({ logs: [rest] })).toThrow();  // 설정 해시가 빠짐
    expect(() => catalog({})).toThrow();
  });
});

describe("notifier", () => {
  it("is optional in the state and must be stub or sms with a boolean armed", () => {
    const base = demo(T0, THRESHOLDS);
    expect(contract(base).notifier).toBeUndefined();
    const armed = contract({ ...base, notifier: { mode: "sms", armed: true } });
    expect(armed.notifier?.armed).toBe(true);
    expect(() => contract({ ...base, notifier: { mode: "mail", armed: true } })).toThrow();
    expect(() => contract({ ...base, notifier: { mode: "sms", armed: "yes" } })).toThrow();
  });

  it("says real sending is on only for an armed sms notifier", () => {
    const blocked = "기록만, 실제 발송 차단";
    expect(relay(undefined)).toBe(blocked);
    expect(relay({ mode: "stub", armed: true })).toBe(blocked);
    expect(relay({ mode: "sms", armed: false })).toBe(blocked);
    expect(relay({ mode: "sms", armed: true })).toBe("실제 발송 켜짐, 허용 번호만");
    const past = "발송 결과는 서버 로그에만 남음";  // 지난 기록·재생은 무장 여부와 관계없음
    expect(relay({ mode: "sms", armed: true }, true)).toBe(past);
    expect(relay(undefined, true)).toBe(past);
  });
});
