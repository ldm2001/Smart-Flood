import { useState } from "react";
import useSWR, { type Revalidator, type RevalidatorOptions } from "swr";
import { poll, limits, type Receipt } from "./api";
import { entry, EMPTY_HISTORY, type History, type Thresholds } from "./derive";

// 상태 폴링 키. 서버 상태는 SWR 캐시에 두고 이력만 성공 때 쌓는다
export const STATE_KEY = "/api/state";
export const CONFIG_KEY = "/api/config";  // 설정 읽기 키
const RETRY_MS = 1000;  // 재시도 간격(ms)

// 실패하면 늘 1초 뒤 다시 묻는다. SWR 기본은 5초부터 늘어난다
export function retry(
  _error: unknown,  // 오류(쓰지 않는다)
  _key: string,  // 키(쓰지 않는다)
  _config: unknown,  // 설정(쓰지 않는다)
  revalidate: Revalidator,  // 다시 묻는 함수
  options: Required<RevalidatorOptions>,  // 다시 묻기 옵션
): void {  // 돌려줄 값은 없다
  setTimeout(revalidate, RETRY_MS, options);  // 1초 뒤에 다시 질의
}

export const STATE_SWR_OPTIONS = {  // 상태 폴링 옵션
  refreshInterval: 1000,  // 1초마다 질의
  revalidateOnFocus: false,  // 창에 돌아와도 따로 묻지 않음
  keepPreviousData: true,  // 새 값이 오기 전에는 이전 값을 둔다
  dedupingInterval: 500,  // 폴링 간격보다 짧아야 매번 새로 묻는다(기본 2초면 걸러진다)
  refreshWhenOffline: true,  // 브라우저가 오프라인이라 해도 묻는다(서버가 같은 PC 면 답)
  onErrorRetry: retry,  // 실패하면 위 재시도 함수를 기록
} as const;  // 읽기 전용 값으로 굳힌다

// 설정 읽기 옵션. 한 번 받으면 다시 묻지 않고, 받기 전에는 1초마다 질의
export const CONFIG_SWR_OPTIONS = {
  refreshInterval: 0,  // 주기적으로 묻지 않음
  revalidateOnFocus: false,  // 창에 돌아와도 묻지 않음
  revalidateIfStale: false,  // 오래돼도 다시 묻지 않음
  revalidateOnReconnect: false,  // 연결이 돌아와도 묻지 않음
  onErrorRetry: retry,  // 실패하면 1초 뒤 다시 묻는다(받기 전까지)
} as const;  // 읽기 전용 값으로 굳힌다

// 화면이 받는 읽기 결과
export interface Feed {
  latest: Receipt | null;  // 계약을 통과한 마지막 응답. 뒤의 폴링이 실패해도 남음
  failed: boolean;  // 마지막 폴링이 실패했는가
  history: History;  // 수위 표본 이력
  thresholds: Thresholds | null;  // 서버 설정의 한계 수위. 받기 전에는 null
}

// 서버 상태를 1초마다 읽는 훅. 끊기면 마지막 정상 값을 둔다
export function useSnapshot(): Feed {
  // 표본 이력만 상태로 둔다. 폴링 성공 때 쌓는다
  const [history, setHistory] = useState<History>(EMPTY_HISTORY);
  const state = useSWR(STATE_KEY, () => poll(), {  // 상태를 주기적으로 읽음
    ...STATE_SWR_OPTIONS,  // 상태 옵션을 펼친다
    // 성공할 때마다 이력에 쌓는다
    onSuccess: (result) => setHistory((current) => entry(current, result.snapshot)),
  });
  const config = useSWR(CONFIG_KEY, () => limits(), CONFIG_SWR_OPTIONS);  // 한계 수위 설정을 읽음
  return {  // 화면이 쓸 값을 모아 반환
    latest: state.data ?? null,  // 마지막 정상 응답
    failed: state.error !== undefined,  // 오류가 났는가
    history,  // 표본 이력
    thresholds: config.data ?? null,  // 한계 수위. 없으면 null
  };
}
