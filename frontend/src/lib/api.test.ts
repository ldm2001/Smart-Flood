import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ZodError } from "zod";
import { demo } from "./mock";
import type { Command } from "./schema";

const T0 = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각(2026-10-25 01:00 UTC)
const BODY = demo(T0, { A: 45, B: 55, C: 65 });  // 계약을 통과하는 응답 본문
const CONFIG = { zones: { A: { threshold_mm: 45 }, B: { threshold_mm: 55 }, C: { threshold_mm: 65 } } };
const RAINY = {  // 강우 단계값과 직접 입력 상한까지 있는 설정
  ...CONFIG,
  rain_presets_mm_per_h: { light: 30, medium: 60, heavy: 90 },
  rain_max_mm_per_h: 150,
};
const LIMITS = { A: 45, B: 55, C: 65 };  // 설정에서 읽은 구역 한계(mm)
const EVENT = {  // 단계 전환 사건 한 줄
  type: "event",
  kind: "stage",
  elapsedSec: 25,
  time: "2026-10-22T09:00:25.000000+09:00",
  message: "B 구역 주의 (이전 정상, 한계까지 60 초)",
  zone: "B",
  stage: "caution",
  previous: "safe",
  etaSec: 60,
};

// API_BASE 는 모듈을 읽을 때 정해져(빌드 값) 테스트마다 새로 읽음
async function instance(base?: string) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_API_BASE", base);
  return import("./api");
}

// 정해진 응답을 주는 가짜 서버를 만듦
function server(body: unknown, status = 200) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
    Response.json(body, { status }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

// 응답이 없는 가짜 서버. 요청이 끊기면 그 이유로 실패
function silence() {
  const fetch = vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

// JSON 이 아닌 본문을 주는 가짜 서버를 만듦
function noise(status: number) {
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
    new Response("<html>오류</html>", { status }),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

// 닿지 못하는 가짜 서버. 브라우저처럼 TypeError 로 실패
function blackout() {
  vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
}

// 머리만 오고 본문이 멈춘 가짜 서버. 요청이 끊기면 본문 읽기가 실패
function stall() {
  const fetch = vi.fn(
    async (_url: string, init?: RequestInit) =>
      ({
        ok: true,
        status: 200,
        json: () =>
          new Promise((_, reject) => {
            const halt = () => reject(init?.signal?.reason);  // 끊긴 이유로 실패
            if (init?.signal?.aborted) halt();
            else init?.signal?.addEventListener("abort", halt);
          }),
      }) as unknown as Response,
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const signal = (fetch: ReturnType<typeof silence>) => fetch.mock.calls[0][1]?.signal;

describe("api", () => {
  beforeEach(() => {  // 테스트마다 먼저
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    vi.setSystemTime(T0);
  });

  afterEach(() => {
    vi.useRealTimers();  // 진짜 타이머로 되돌림
    vi.unstubAllGlobals();  // 가짜 전역 값을 모두 되돌림
    vi.unstubAllEnvs();  // 가짜 환경변수를 모두 되돌림
  });

  it("reads /api/state from the same origin and stamps the receive time", async () => {
    const fetch = server(BODY);
    const { poll } = await instance(undefined);  // 주소 없이(같은 출처) 통신 모듈을 읽음
    vi.setSystemTime(T0 + 300);

    const result = await poll();
    expect(fetch).toHaveBeenCalledWith("/api/state", expect.objectContaining({ cache: "no-store" }));
    expect(result.snapshot.experimentId).toBe(BODY.experimentId);
    expect(result.receivedAt).toBe(T0 + 300);  // 받은 시각이 시계 값(+0.3초)이어야 함
    expect(vi.getTimerCount()).toBe(0);
  });

  it("puts the build-time API base in front of the path", async () => {
    const fetch = server(BODY);
    const { poll } = await instance("http://127.0.0.1:8000");
    await poll();
    expect(fetch.mock.calls[0][0]).toBe("http://127.0.0.1:8000/api/state");
  });

  it("refuses a body that breaks the contract", async () => {  // 계약을 어긴 응답은 거부하는지 검사
    server({ ...BODY, outputsLocked: false });
    const { poll } = await instance(undefined);
    await expect(poll()).rejects.toThrow(ZodError);  // 계약 검사 오류로 실패해야 함
  });

  it("refuses a non-2xx response with its status", async () => {
    server({ detail: "tick failed" }, 503);
    const { poll, Failure } = await instance(undefined);
    const error = await poll().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Failure);
    expect(error).toMatchObject({ status: 503, message: "HTTP 503" });
  });

  it("gives up on a poll after 3 s", async () => {
    const fetch = silence();
    const { poll } = await instance(undefined);
    const result = poll().catch((e: unknown) => e);

    vi.advanceTimersByTime(2999);
    expect(signal(fetch)?.aborted).toBe(false);
    vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 3초)
    expect(signal(fetch)?.aborted).toBe(true);
    expect(await result).toBeInstanceOf(Error);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("reads the thresholds and the rain settings from /api/config, waiting up to 5 s", async () => {
    const fetch = server(RAINY);
    const { setup } = await instance(undefined);
    await expect(setup()).resolves.toEqual({
      thresholds: LIMITS,
      rain: { presets: { light: 30, medium: 60, heavy: 90 }, maxMmPerHour: 150 },
    });
    expect(fetch.mock.calls[0][0]).toBe("/api/config");

    const slow = silence();
    const pending = setup().catch((e: unknown) => e);
    vi.advanceTimersByTime(4999);
    expect(signal(slow)?.aborted).toBe(false);
    vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 5초)
    expect(signal(slow)?.aborted).toBe(true);
    expect(await pending).toBeInstanceOf(Error);
  });

  it("keeps the thresholds when the rain settings are missing or broken", async () => {
    server(CONFIG);
    const { setup } = await instance(undefined);
    await expect(setup()).resolves.toEqual({ thresholds: LIMITS, rain: null });
    server({ ...RAINY, rain_max_mm_per_h: 0 });
    await expect(setup()).resolves.toEqual({ thresholds: LIMITS, rain: null });
  });

  it("throws when the thresholds are broken", async () => {
    server({ ...RAINY, zones: {} });
    const { setup } = await instance(undefined);
    await expect(setup()).rejects.toThrow(ZodError);
  });

  it("posts each control to its own path", async () => {
    const fetch = server(BODY);
    const { order } = await instance(undefined);
    const commands: Command[] = [  // 제어 일곱 가지
      { control: "start", body: {} },
      { control: "stop", body: {} },
      { control: "reset", body: {} },
      { control: "rain", body: { intensity: "heavy" } },
      { control: "blockage", body: { type: "none" } },
      { control: "sim", body: { mode: "sim" } },
      { control: "live", body: { mode: "live" } },
    ];
    for (const command of commands) await order(command);
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "/api/experiment/start",
      "/api/experiment/stop",
      "/api/experiment/reset",
      "/api/rain",
      "/api/blockage",
      "/api/source",
      "/api/source",
    ]);
  });

  it("sends the body as JSON without caching", async () => {
    const fetch = server(BODY);
    const { order } = await instance(undefined);
    await order({ control: "rain", body: { intensity: "heavy" } });
    await order({ control: "blockage", body: { type: "partial", location: "INLET-02" } });
    await order({ control: "start", body: {} });
    expect(fetch.mock.calls[0][1]).toMatchObject({
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: '{"intensity":"heavy"}',
    });
    expect(fetch.mock.calls[1][1]?.body).toBe('{"type":"partial","location":"INLET-02"}');
    expect(fetch.mock.calls[2][1]?.body).toBe("{}");
  });

  it("puts the build-time API base in front of a control path", async () => {
    const fetch = server(BODY);
    const { order } = await instance("http://127.0.0.1:8000");
    await order({ control: "rain", body: { mmPerHour: 75 } });
    expect(fetch.mock.calls[0][0]).toBe("http://127.0.0.1:8000/api/rain");
  });

  it("hands back the changed state with its receive time", async () => {
    server(BODY);
    const { order } = await instance(undefined);
    vi.setSystemTime(T0 + 300);
    const answer = await order({ control: "start", body: {} });
    expect(answer).toMatchObject({ ok: true, receipt: { receivedAt: T0 + 300 } });
    expect(answer.ok && answer.receipt.snapshot.experimentId).toBe(BODY.experimentId);
    expect(vi.getTimerCount()).toBe(0);  // 5초 타이머를 지움
  });

  it("calls a 200 that breaks the contract a format fault", async () => {
    server({ ...BODY, outputsLocked: false });
    const { order } = await instance(undefined);
    const format = { ok: false, fault: { kind: "format" }, at: T0 };  // 받았을 수도 있는 실패
    expect(await order({ control: "stop", body: {} })).toEqual(format);
    noise(200);
    expect(await order({ control: "stop", body: {} })).toEqual(format);
  });

  it("passes on the reason the server gives with a refusal", async () => {
    const text = "회차가 도는 중에는 입력원을 바꿀 수 없다. 먼저 종료한다";  // 서버의 409 글
    server({ detail: text }, 409);
    const { order } = await instance(undefined);
    expect(await order({ control: "live", body: { mode: "live" } })).toEqual({
      ok: false,
      fault: { kind: "refused", status: 409, text },
      at: T0,
    });
    server({ detail: "실험 기록을 쓸 수 없다: 디스크가 가득 찼다" }, 503);
    expect(await order({ control: "start", body: {} })).toMatchObject({
      fault: { kind: "refused", status: 503, text: "실험 기록을 쓸 수 없다: 디스크가 가득 찼다" },
    });
  });

  it("uses a 422 message only when the server wrote it", async () => {
    const msg = "강우는 0~150 mm/h 여야 한다: 999.0";  // 서버 검사기의 한국어 글
    server({ detail: [{ loc: ["body", "mmPerHour"], msg, type: "value_error" }] }, 422);
    const { order } = await instance(undefined);
    expect(await order({ control: "rain", body: { mmPerHour: 999 } })).toMatchObject({
      fault: { kind: "refused", status: 422, text: msg },
    });
    const english = {  // pydantic 기본 검사의 영어 글
      type: "greater_than_equal",
      msg: "Input should be greater than or equal to 0",
    };
    server({ detail: [english] }, 422);
    expect(await order({ control: "rain", body: { mmPerHour: -1 } })).toEqual({
      ok: false,
      fault: { kind: "status", status: 422 },
      at: T0,
    });
  });

  it("keeps only the status when a failure has no reason", async () => {
    noise(500);
    const { order } = await instance(undefined);
    expect(await order({ control: "reset", body: {} })).toEqual({
      ok: false,
      fault: { kind: "status", status: 500 },
      at: T0,
    });
  });

  it("tells a network failure apart from a timeout", async () => {
    blackout();
    const { order } = await instance(undefined);
    const answer = order({ control: "start", body: {} });
    await expect(answer).resolves.toEqual({ ok: false, fault: { kind: "network" }, at: T0 });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("gives up on a control after 5 s without throwing", async () => {
    const fetch = silence();
    const { order } = await instance(undefined);
    const pending = order({ control: "stop", body: {} });
    vi.advanceTimersByTime(4999);
    expect(signal(fetch)?.aborted).toBe(false);
    vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 5초)
    expect(signal(fetch)?.aborted).toBe(true);
    expect(await pending).toEqual({ ok: false, fault: { kind: "timeout" }, at: T0 + 5000 });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("counts a body that stops arriving as a timeout", async () => {
    stall();
    const { order } = await instance(undefined);
    const pending = order({ control: "start", body: {} });
    vi.advanceTimersByTime(5000);
    expect(await pending).toEqual({ ok: false, fault: { kind: "timeout" }, at: T0 + 5000 });
  });

  it("reads the events of a record, wrapping the id in the path", async () => {
    const fetch = server({ events: [EVENT] });
    const { logbook } = await instance(undefined);
    await expect(logbook("EXP-20261101-001")).resolves.toEqual([EVENT]);
    expect(fetch.mock.calls[0][0]).toBe("/api/logs/EXP-20261101-001/events");
    await logbook("a/b c");
    expect(fetch.mock.calls[1][0]).toBe("/api/logs/a%2Fb%20c/events");  // 주소 글자로 감쌈
  });

  it("treats a missing record as an empty list", async () => {
    server({ detail: "Not Found" }, 404);
    const { logbook } = await instance(undefined);
    await expect(logbook("EXP-20261101-009")).resolves.toEqual([]);
  });

  it("throws other failures and contract breaks from the events read", async () => {
    server({ detail: "log read failed" }, 500);
    const { logbook, Failure } = await instance(undefined);
    await expect(logbook("EXP-20261101-001")).rejects.toBeInstanceOf(Failure);
    server({ events: [{ ...EVENT, kind: "pump" }] });
    await expect(logbook("EXP-20261101-001")).rejects.toThrow(ZodError);
  });

  it("gives up on the events read after 5 s", async () => {
    const fetch = silence();
    const { logbook } = await instance(undefined);
    const pending = logbook("EXP-20261101-001").catch((e: unknown) => e);
    vi.advanceTimersByTime(4999);
    expect(signal(fetch)?.aborted).toBe(false);
    vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 5초)
    expect(signal(fetch)?.aborted).toBe(true);
    expect(await pending).toBeInstanceOf(Error);
  });
});
