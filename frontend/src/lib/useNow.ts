import { useSyncExternalStore } from "react";

const TICK_MS = 1000;  // 화면 시계 간격(ms). 시각은 이 파일에서만 읽음

// 현재 시각(ms). 구독 전·프리렌더 때는 null 이라 시각 자리는 줄표다
let current: number | null = null;
let timer: ReturnType<typeof setInterval> | null = null;  // 돌고 있는 타이머. 없으면 null
const listeners = new Set<() => void>();  // 시각이 바뀌면 알려 줄 구독자 모음

// 한 번 째깍하는 함수
function tick() {
  current = Date.now();  // 지금 시각을 읽어 저장
  for (const listener of listeners) listener();  // 구독자 모두에게 알린다
}

// 구독을 시작하고 해제 함수를 반환
export function subscription(listener: () => void): () => void {
  listeners.add(listener);  // 구독자를 모음에 넣음
  if (timer === null) {  // 첫 구독자면
    current = Date.now();  // 바로 첫 값을 읽어 둔다
    timer = setInterval(tick, TICK_MS);  // 간격마다 째깍하게
  }
  return () => {  // 구독 해제 함수를 반환
    listeners.delete(listener);  // 구독자를 모음에서 제외
    if (listeners.size === 0 && timer !== null) {  // 구독자가 하나도 없으면
      clearInterval(timer);  // 타이머를 멈춘다
      timer = null;  // 타이머를 비운다
      current = null;  // 다시 붙는 화면이 첫 프레임에 지난 시각을 그리지 않게 비운다
    }
  };
}

// 저장된 시각을 읽는다. 째깍 사이에는 같은 값이다
export function reading(): number | null {
  return current;  // 저장된 값을 그대로 반환
}

// 서버 렌더용 값. 시각을 모르니 null 이다
export function fallback(): null {
  return null;  // 시각을 모른다고 알린다
}

// 현재 시각 훅. 렌더는 이 값만 기록
export function useNow(): number | null {
  return useSyncExternalStore(subscription, reading, fallback);  // 구독·읽기·서버용 값을 연결
}

// 렌더 밖(응답을 받은 순간 등)에서 쓰는 현재 시각. 렌더 중에는 부르지 않음
export function wall(): number {
  return Date.now();  // 지금 시각(ms)을 읽음
}
