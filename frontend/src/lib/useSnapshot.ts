import { useState } from "react";
import useSWR, { type Revalidator, type RevalidatorOptions } from "swr";
import { poll, limits, type Receipt } from "./api";
import { entry, EMPTY_HISTORY, type History, type Thresholds } from "./derive";

export const STATE_KEY = "/api/state";  // 서버 상태는 SWR 캐시, 이력만 성공 때 쌓음
export const CONFIG_KEY = "/api/config";
const RETRY_MS = 1000;  // 재시도 간격(ms)

// 실패하면 늘 1초 뒤 다시 물음. SWR 기본은 5초부터 늘어남
export function retry(
  _error: unknown,  // 오류(쓰지 않음)
  _key: string,  // 키(쓰지 않음)
  _config: unknown,  // 설정(쓰지 않음)
  revalidate: Revalidator,
  options: Required<RevalidatorOptions>,
): void {
  setTimeout(revalidate, RETRY_MS, options);  // 1초 뒤에 다시 질의
}

export const STATE_SWR_OPTIONS = {
  refreshInterval: 1000,
  revalidateOnFocus: false,
  keepPreviousData: true,  // 새 값이 오기 전에는 이전 값을 둠
  dedupingInterval: 500,  // 폴링 간격보다 짧아야 매번 새로 물음(기본 2초면 걸러짐)
  refreshWhenOffline: true,  // 브라우저가 오프라인이라 해도 물음(서버가 같은 PC 면 답)
  onErrorRetry: retry,  // 실패하면 위 재시도 함수를 씀
} as const;

export const CONFIG_SWR_OPTIONS = {  // 한 번 받으면 재질의 없음, 받기 전엔 1초마다 질의
  refreshInterval: 0,
  revalidateOnFocus: false,
  revalidateIfStale: false,
  revalidateOnReconnect: false,
  onErrorRetry: retry,  // 실패하면 1초 뒤 다시 물음(받기 전까지)
} as const;

// 화면이 받는 읽기 결과
export interface Feed {
  latest: Receipt | null;  // 계약을 통과한 마지막 응답. 뒤의 폴링이 실패해도 남음
  failed: boolean;  // 마지막 폴링이 실패했는가
  history: History;  // 수위 표본 이력
  thresholds: Thresholds | null;  // 서버 설정의 한계 수위. 받기 전에는 null
}

// 서버 상태를 1초마다 읽는 훅. 끊기면 마지막 정상 값을 둠
export function useSnapshot(): Feed {
  const [history, setHistory] = useState<History>(EMPTY_HISTORY);  // 이력만 상태, 폴링 성공 때 쌓음
  const state = useSWR(STATE_KEY, () => poll(), {
    ...STATE_SWR_OPTIONS,
    onSuccess: (result) => setHistory((current) => entry(current, result.snapshot)),
  });
  const config = useSWR(CONFIG_KEY, () => limits(), CONFIG_SWR_OPTIONS);
  return {
    latest: state.data ?? null,
    failed: state.error !== undefined,
    history,
    thresholds: config.data ?? null,
  };
}
