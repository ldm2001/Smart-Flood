import { useState } from "react";
import useSWR from "swr";
import { z } from "zod";
import { logbook } from "./api";
import { holding, topic, type Pack, type Topic } from "./derive";
import type { LogEvent, Snapshot } from "./schema";
import { retry } from "./useSnapshot";

export const EVENTS_SWR_OPTIONS = {  // 키가 바뀔 때만 읽음
  refreshInterval: 0,
  dedupingInterval: 0,  // 같은 키로 곧 돌아와도 다시 읽음
  revalidateOnFocus: false,
  revalidateOnReconnect: false,
  shouldRetryOnError: (error: Error) => !(error instanceof z.ZodError),  // 계약 위반은 그만 읽음
  onErrorRetry: retry,  // 그 밖의 실패는 1초 뒤 다시 읽음
} as const;

// 사건 읽기 결과
export interface Events {
  list: readonly LogEvent[] | null;  // 지금 실험의 사건. 아직 못 받았으면 null
  failed: boolean;  // 마지막 읽기의 실패 여부
}

// 지금 실험의 사건을 키가 바뀔 때만 읽는 훅. 받은 목록은 실험 번호와 함께 둠
export function useEvents(snapshot: Snapshot | null): Events {
  const [kept, setKept] = useState<Pack | null>(null);  // 마지막으로 받은 사건
  const key = topic(snapshot);
  const response = useSWR(key, ([, id]: Topic) => logbook(id).then((list) => ({ id, list })), {
    ...EVENTS_SWR_OPTIONS,
    onSuccess: (pack: Pack) => setKept(pack),
  });
  return { list: holding(key === null ? null : key[1], kept), failed: response.error !== undefined };
}
