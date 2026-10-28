import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ZodError } from "zod";
import { demo } from "./mock";

const T0 = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각(2026-10-25 01:00 UTC)
const BODY = demo(T0, { A: 45, B: 55, C: 65 });  // 계약을 통과하는 응답 본문
const CONFIG = { zones: { A: { threshold_mm: 45 }, B: { threshold_mm: 55 }, C: { threshold_mm: 65 } } };

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

  it("reads the zone thresholds from /api/config, waiting up to 5 s", async () => {
    const fetch = server(CONFIG);
    const { limits } = await instance(undefined);
    await expect(limits()).resolves.toEqual({ A: 45, B: 55, C: 65 });
    expect(fetch.mock.calls[0][0]).toBe("/api/config");

    const slow = silence();
    const pending = limits().catch((e: unknown) => e);
    vi.advanceTimersByTime(4999);
    expect(signal(slow)?.aborted).toBe(false);
    vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 5초)
    expect(signal(slow)?.aborted).toBe(true);
    expect(await pending).toBeInstanceOf(Error);
  });
});
