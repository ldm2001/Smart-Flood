import { afterEach, describe, expect, it, vi } from "vitest";
import { CONFIG_SWR_OPTIONS, retry, STATE_SWR_OPTIONS } from "./useSnapshot";

// 상태 읽기 옵션 테스트 묶음(훅은 DOM 이 없어 지시서 7장 SWR 설정만 고정)
describe("state polling options", () => {
  it("polls every second without focus revalidation and keeps the last good data", () => {
    expect(STATE_SWR_OPTIONS).toMatchObject({
      refreshInterval: 1000,
      revalidateOnFocus: false,
      keepPreviousData: true,
      onErrorRetry: retry,  // 실패하면 재시도 함수를 씀
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
