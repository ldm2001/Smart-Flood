import { afterEach, describe, expect, it, vi } from "vitest";
import { CONFIG_SWR_OPTIONS, retry, STATE_SWR_OPTIONS } from "./useSnapshot";

// 상태 읽기 옵션 테스트 묶음(훅은 DOM 이 없어 지시서 7장 SWR 설정만 고정)
describe("state polling options", () => {
  // 초마다 읽고 포커스 재검증 없이 마지막 좋은 자료를 유지하는지 검사
  it("polls every second without focus revalidation and keeps the last good data", () => {
    expect(STATE_SWR_OPTIONS).toMatchObject({  // 상태 옵션이 아래 값을 포함필요
      refreshInterval: 1000,  // 1초마다 다시 읽음
      revalidateOnFocus: false,  // 창에 돌아와도 다시 읽지 않음
      keepPreviousData: true,  // 실패해도 이전 자료를 남김
      onErrorRetry: retry,  // 실패하면 재시도 함수를 기록
    });
  });

  // 중복 제거 시간이 읽기 주기보다 짧은지 검사(아니면 격번으로 건너뛴다)
  it("dedupes for less than one poll interval, or every other poll would be skipped", () => {
    // 중복 제거 시간이 읽기 주기보다 짧아야 함
    expect(STATE_SWR_OPTIONS.dedupingInterval).toBeLessThan(STATE_SWR_OPTIONS.refreshInterval);
  });

  // 오프라인이라 해도 읽기를 이어 가는지 검사(백엔드가 이 PC 에 있을 수 있다)
  it("keeps polling when the browser reports offline, since the backend may be on this PC", () => {
    // 오프라인 표시여도 읽어야 한다. 와이파이가 끊겨도 로컬 서버는 산다
    expect(STATE_SWR_OPTIONS).toMatchObject({ refreshWhenOffline: true });
  });

  // 설정은 한 번만 읽고 재시도는 같은 방식인지 검사
  it("reads the config once and retries it the same way", () => {
    expect(CONFIG_SWR_OPTIONS).toMatchObject({  // 설정 옵션이 아래 값을 포함필요
      refreshInterval: 0,  // 주기적으로 다시 읽지 않음
      revalidateOnFocus: false,  // 창에 돌아와도 다시 읽지 않음
      revalidateIfStale: false,  // 오래돼도 다시 읽지 않음
      revalidateOnReconnect: false,  // 연결이 돌아와도 다시 읽지 않음
      onErrorRetry: retry,  // 실패하면 같은 재시도 함수를 기록
    });
  });
});

describe("retry", () => {  // 재시도 함수 테스트 묶음
  afterEach(() => {  // 테스트마다 끝난 뒤
    vi.useRealTimers();  // 진짜 타이머로 되돌린다
  });

  // 몇 번 실패했든 1초 뒤에 다시 묻는지 검사
  it("asks again after 1 s however many times it has failed", () => {
    vi.useFakeTimers();  // 타이머를 가짜로 변환
    for (const retryCount of [1, 8, 50]) {  // 실패 횟수 1·8·50 을 하나씩 확인
      const revalidate = vi.fn();  // 다시 읽기 호출을 셀 가짜 함수를 만듦
      const options = { retryCount, dedupe: true };  // 재시도 정보(실패 횟수)를 만듦
      // 오류와 함께 재시도 함수를 부른다
      retry(new Error("down"), "/api/state", STATE_SWR_OPTIONS as never, revalidate, options);
      vi.advanceTimersByTime(999);  // 0.999초를 전송
      expect(revalidate).not.toHaveBeenCalled();  // 아직 다시 읽지 않아야 함
      vi.advanceTimersByTime(1);  // 1밀리초 더 보낸다(합계 1초)
      // 같은 정보로 정확히 한 번 다시 읽어야 함
      expect(revalidate).toHaveBeenCalledExactlyOnceWith(options);
    }
  });
});
