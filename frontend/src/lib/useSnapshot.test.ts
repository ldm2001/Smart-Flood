import { createRequire } from "node:module";
import { mutate } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";
import { demo } from "./mock";
import {
  CONFIG_SWR_OPTIONS,
  enrolment,
  handover,
  intake,
  ledger,
  retry,
  STATE_SWR_OPTIONS,
} from "./useSnapshot";

vi.mock("swr", async (original) => ({  // 전역 캐시 쓰기만 가짜로 바꿈
  ...(await original<typeof import("swr")>()),
  mutate: vi.fn(async () => undefined),
}));

const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각(2026-10-25 01:00 UTC)
const LIMITS = { A: 45, B: 55, C: 65 };  // 구역 한계(mm)
// 실험 번호와 시각을 정한 폴링 응답 하나
const receipt = (experimentId: string, t: number) => ({
  snapshot: { ...demo(t, LIMITS), experimentId },
  receivedAt: t,
});

// 상태 읽기 옵션 테스트 묶음(훅은 DOM 이 없어 지시서 7장 SWR 설정만 고정)
describe("state polling options", () => {
  it("polls every second without focus revalidation and keeps the last good data", () => {
    expect(STATE_SWR_OPTIONS).toMatchObject({
      refreshInterval: 1000,
      revalidateOnFocus: false,
      keepPreviousData: true,
      onErrorRetry: retry,  // 실패하면 재시도 함수를 씀
      onSuccess: intake,  // 성공한 응답은 모듈 기록에 더함
    });
  });

  it("dedupes for less than one poll interval, or every other poll would be skipped", () => {
    expect(STATE_SWR_OPTIONS.dedupingInterval).toBeLessThan(STATE_SWR_OPTIONS.refreshInterval);
  });

  it("keeps polling when the browser reports offline, since the backend may be on this PC", () => {
    expect(STATE_SWR_OPTIONS).toMatchObject({ refreshWhenOffline: true });
  });

  it("reads the config once and retries it the same way", () => {
    expect(CONFIG_SWR_OPTIONS).toMatchObject({
      refreshInterval: 0,
      revalidateOnFocus: false,
      revalidateIfStale: false,
      revalidateOnReconnect: false,
      onErrorRetry: retry,  // 실패하면 같은 재시도 함수를 씀
    });
  });
});

describe("retry", () => {
  afterEach(() => {
    vi.useRealTimers();  // 진짜 타이머로 되돌림
  });

  it("asks again after 1 s however many times it has failed", () => {
    vi.useFakeTimers();
    for (const retryCount of [1, 8, 50]) {
      const revalidate = vi.fn();
      const options = { retryCount, dedupe: true };  // 재시도 정보(실패 횟수)를 만듦
      retry(new Error("down"), "/api/state", STATE_SWR_OPTIONS as never, revalidate, options);
      vi.advanceTimersByTime(999);  // 0.999초를 보냄
      expect(revalidate).not.toHaveBeenCalled();
      vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 1초)
      expect(revalidate).toHaveBeenCalledExactlyOnceWith(options);
    }
  });
});

describe("handover", () => {
  it("puts a control answer into the state cache without asking again", async () => {
    const answer = receipt("EXP-20261101-100", T);
    await handover(answer);
    expect(mutate).toHaveBeenCalledExactlyOnceWith("/api/state", answer, { revalidate: false });
  });

  it("relies on swr 2.5.1, whose mutate drops the older polls still in flight", () => {
    expect(createRequire(import.meta.url)("swr/package.json").version).toBe("2.5.1");
  });
});

// 모듈 기록은 시험 사이에 남아 시험마다 다른 실험 번호를 씀
describe("history store", () => {
  it("adds a new poll and tells the watchers", () => {
    const watcher = vi.fn();
    const leave = enrolment(watcher);
    intake(receipt("EXP-20261101-101", T));
    intake(receipt("EXP-20261101-101", T + 1000));
    expect(ledger().samples.map(({ t }) => t)).toEqual([T, T + 1000]);
    expect(watcher).toHaveBeenCalledTimes(2);
    leave();
  });

  it("keeps the same object for a repeated poll and stays quiet", () => {
    intake(receipt("EXP-20261101-102", T));
    const before = ledger();
    const watcher = vi.fn();
    const leave = enrolment(watcher);
    intake(receipt("EXP-20261101-102", T));
    expect(ledger()).toBe(before);
    expect(watcher).not.toHaveBeenCalled();
    leave();
  });

  it("starts over when the run changes", () => {
    intake(receipt("EXP-20261101-103", T));
    intake(receipt("EXP-20261101-103", T + 1000));
    intake(receipt("EXP-20261101-104", T + 2000));
    expect(ledger()).toMatchObject({ run: "EXP-20261101-104|sim", samples: [{ t: T + 2000 }] });
  });

  it("stops telling a watcher that has left", () => {
    const watcher = vi.fn();
    enrolment(watcher)();
    intake(receipt("EXP-20261101-105", T));
    expect(watcher).not.toHaveBeenCalled();
  });
});
