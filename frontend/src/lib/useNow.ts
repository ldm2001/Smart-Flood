import { useSyncExternalStore } from "react";

const TICK_MS = 1000;  // 화면 시계 간격(ms). 시각은 이 파일에서만 읽음

let current: number | null = null;  // 현재 시각(ms)
let timer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();  // 시각이 바뀌면 알려 줄 구독자 모음

// 한 번 째깍하는 함수
function tick() {
  current = Date.now();
  for (const listener of listeners) listener();
}

// 구독을 시작하고 해제 함수를 반환
export function subscription(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === null) {
    current = Date.now();
    timer = setInterval(tick, TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
      current = null;  // 다시 붙는 화면이 첫 프레임에 지난 시각을 그리지 않게 비움
    }
  };
}

// 저장된 시각을 읽음. 째깍 사이에는 같은 값
export function reading(): number | null {
  return current;  // 저장된 값을 그대로 반환
}

// 서버 렌더용 값. 시각을 모르니 null
export function fallback(): null {
  return null;
}

// 현재 시각 훅. 렌더는 이 값만 씀
export function useNow(): number | null {
  return useSyncExternalStore(subscription, reading, fallback);
}

// 렌더 밖(응답을 받은 순간 등)에서 쓰는 현재 시각. 렌더 중에는 부르지 않음
export function wall(): number {
  return Date.now();  // 지금 시각(ms)을 읽음
}
