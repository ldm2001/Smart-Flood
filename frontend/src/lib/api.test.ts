import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ZodError } from "zod";
import { demo } from "./mock";

const T0 = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각(2026-10-25 01:00 UTC)
const BODY = demo(T0, { A: 45, B: 55, C: 65 });  // 계약을 통과하는 응답 본문
// 구역별 한계(threshold_mm)가 든 설정 응답
const CONFIG = { zones: { A: { threshold_mm: 45 }, B: { threshold_mm: 55 }, C: { threshold_mm: 65 } } };

// API_BASE 는 모듈을 읽을 때 정해져(빌드 값) 테스트마다 새로 읽음
async function instance(base?: string) {
  vi.resetModules();  // 읽어 둔 모듈을 비운다
  vi.stubEnv("NEXT_PUBLIC_API_BASE", base);  // 빌드 때 박히는 주소 환경변수를 흉내 냄
  return import("./api");  // 통신 모듈을 새로 읽어 반환
}

// 정해진 응답을 주는 가짜 서버를 만듦
function server(body: unknown, status = 200) {
  // 가짜 요청 함수. 부를 때마다 같은 응답을 냄
  const fetch = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () =>
    Response.json(body, { status }),  // 본문과 상태 코드로 응답을 만듦
  );
  vi.stubGlobal("fetch", fetch);  // 전역 요청 함수를 가짜로 변환
  return fetch;  // 호출 기록을 볼 수 있게 반환
}

// 응답이 없는 가짜 서버. 요청이 끊기면 그 이유로 실패
function silence() {
  const fetch = vi.fn(  // 가짜 요청 함수
    (_url: string, init?: RequestInit) =>  // 주소와 옵션을 받음
      new Promise<Response>((_, reject) => {  // 끝나지 않는 약속을 만듦
        // 요청이 끊기면 그 이유로 실패시킨다
        init?.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      }),
  );
  vi.stubGlobal("fetch", fetch);  // 전역 요청 함수를 가짜로 변환
  return fetch;  // 호출 기록을 볼 수 있게 반환
}

// 첫 호출에 넘긴 끊기 신호를 꺼냄
const signal = (fetch: ReturnType<typeof silence>) => fetch.mock.calls[0][1]?.signal;

describe("api", () => {  // 서버 통신 테스트 묶음
  beforeEach(() => {  // 테스트마다 먼저
    // 타이머와 시계를 가짜로 변환
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    vi.setSystemTime(T0);  // 시계를 기준 시각에 맞춤
  });

  afterEach(() => {  // 테스트마다 끝난 뒤
    vi.useRealTimers();  // 진짜 타이머로 되돌린다
    vi.unstubAllGlobals();  // 가짜 전역 값을 모두 되돌린다
    vi.unstubAllEnvs();  // 가짜 환경변수를 모두 되돌린다
  });

  // 같은 출처의 상태 주소를 읽고 받은 시각을 찍는지 검사
  it("reads /api/state from the same origin and stamps the receive time", async () => {
    const fetch = server(BODY);  // 정상 응답을 주는 가짜 서버를 둔다
    const { poll } = await instance(undefined);  // 주소 없이(같은 출처) 통신 모듈을 읽음
    vi.setSystemTime(T0 + 300);  // 시계를 0.3초 앞으로 전송

    const result = await poll();  // 상태를 한 번 읽음
    // 상태 주소를 캐시 없이 불러야 함
    expect(fetch).toHaveBeenCalledWith("/api/state", expect.objectContaining({ cache: "no-store" }));
    // 응답 본문의 실험 번호가 같아야 함
    expect(result.snapshot.experimentId).toBe(BODY.experimentId);
    expect(result.receivedAt).toBe(T0 + 300);  // 받은 시각이 시계 값(+0.3초)이어야 함
    expect(vi.getTimerCount()).toBe(0);  // 시간 제한 타이머가 치워져 0 개여야 함
  });

  // 빌드 때 박힌 API 주소가 경로 앞에 붙는지 검사
  it("puts the build-time API base in front of the path", async () => {
    const fetch = server(BODY);  // 정상 응답을 주는 가짜 서버를 둔다
    const { poll } = await instance("http://127.0.0.1:8000");  // 로컬 주소를 넣고 통신 모듈을 읽음
    await poll();  // 상태를 한 번 읽음
    // 주소와 경로를 합친 값으로 불러야 함
    expect(fetch.mock.calls[0][0]).toBe("http://127.0.0.1:8000/api/state");
  });

  it("refuses a body that breaks the contract", async () => {  // 계약을 어긴 응답은 거부하는지 검사
    server({ ...BODY, outputsLocked: false });  // 출력 잠금이 풀린 응답을 주는 서버를 둔다
    const { poll } = await instance(undefined);  // 주소 없이 통신 모듈을 읽음
    await expect(poll()).rejects.toThrow(ZodError);  // 계약 검사 오류로 실패필요
  });

  // 2xx 가 아닌 응답은 상태 코드와 함께 거부하는지 검사
  it("refuses a non-2xx response with its status", async () => {
    server({ detail: "tick failed" }, 503);  // 503 오류를 주는 서버를 둔다
    const { poll, Failure } = await instance(undefined);  // 통신 모듈과 실패 오류 타입을 읽음
    const error = await poll().catch((e: unknown) => e);  // 실패한 이유를 받아 둔다
    expect(error).toBeInstanceOf(Failure);  // 실패 오류 타입이어야 함
    // 상태 503 과 메시지 HTTP 503 이 들어 있어야 함
    expect(error).toMatchObject({ status: 503, message: "HTTP 503" });
  });

  it("gives up on a poll after 3 s", async () => {  // 읽기가 3초 뒤 포기되는지 검사
    const fetch = silence();  // 응답 없는 서버를 둔다
    const { poll } = await instance(undefined);  // 통신 모듈을 읽음
    const result = poll().catch((e: unknown) => e);  // 읽기를 시작하고 실패 이유를 받을 준비를

    vi.advanceTimersByTime(2999);  // 시계를 2.999초 전송
    expect(signal(fetch)?.aborted).toBe(false);  // 아직 끊기지 않아야 함
    vi.advanceTimersByTime(1);  // 1밀리초 더 보낸다(합계 3초)
    expect(signal(fetch)?.aborted).toBe(true);  // 이제 끊겨야 함
    expect(await result).toBeInstanceOf(Error);  // 오류로 실패필요
    expect(vi.getTimerCount()).toBe(0);  // 남은 타이머가 없어야 함
  });

  // 설정 주소에서 구역 한계를 읽고 최대 5초 기다리는지 검사
  it("reads the zone thresholds from /api/config, waiting up to 5 s", async () => {
    const fetch = server(CONFIG);  // 설정 응답을 주는 가짜 서버를 둔다
    const { limits } = await instance(undefined);  // 한계 읽기 함수를 가져옴
    // 구역별 한계 45·55·65 가 나와야 함
    await expect(limits()).resolves.toEqual({ A: 45, B: 55, C: 65 });
    expect(fetch.mock.calls[0][0]).toBe("/api/config");  // 설정 주소를 불러야 함

    const slow = silence();  // 응답 없는 서버로 변환
    // 한계 읽기를 시작하고 실패 이유를 받을 준비를
    const pending = limits().catch((e: unknown) => e);
    vi.advanceTimersByTime(4999);  // 시계를 4.999초 전송
    expect(signal(slow)?.aborted).toBe(false);  // 아직 끊기지 않아야 함
    vi.advanceTimersByTime(1);  // 1밀리초 더 보낸다(합계 5초)
    expect(signal(slow)?.aborted).toBe(true);  // 이제 끊겨야 함
    expect(await pending).toBeInstanceOf(Error);  // 오류로 실패필요
  });
});
