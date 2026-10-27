import { useSyncExternalStore } from "react";
import { ZONE_IDS, type Thresholds } from "./derive";

// 구역 한계 수위 설정. 저장 키·모양·검증 규칙을 담음
export interface Settings {
  readonly thresholds: Readonly<Thresholds>;  // 구역별 한계 수위(mm). 바꿀 수 없음
}

export const SETTINGS_KEY = "smartFloodSettings";  // 브라우저 저장소 키
const MAX_THRESHOLD_MM = 500;  // 한계 수위 상한(mm). 상태 응답의 수위 상한과 같음

export const DEFAULT_SETTINGS: Settings = Object.freeze({ thresholds: Object.freeze({ A: 45, B: 55, C: 65 }) });

// 쓸 수 있는 한계 수위인지 가림
const threshold = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value > 0 && value <= MAX_THRESHOLD_MM;

// 구역마다 검사해 잘못된 값만 기본값으로 변환
function filter(input: unknown): Settings {
  const source = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  const thresholds: Thresholds = { ...DEFAULT_SETTINGS.thresholds };
  for (const id of ZONE_IDS) {
    const value = source[id];
    if (threshold(value)) thresholds[id] = value;
  }
  return { thresholds };
}

// 저장된 원문을 설정으로 풂. 없거나 깨졌으면 기본값
export function decoding(raw: string | null): Settings {
  if (raw === null) return DEFAULT_SETTINGS;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return DEFAULT_SETTINGS;
  }
  if (typeof value !== "object" || value === null) return DEFAULT_SETTINGS;
  return filter((value as { thresholds?: unknown }).thresholds);
}

// 설정 저장소의 모양
export interface Store {
  subscription(listener: () => void): () => void;  // 바뀜을 구독하고 해제 함수를 반환
  reading(): Settings;
  fallback(): Settings;
  revision(next: Settings): void;
  defaults(): void;  // 저장값을 지워 기본값으로 되돌림
}

// 저장소를 받아 설정 저장소를 만듦. 저장소를 못 써도 화면은 깨지지 않음
export function vault(getStorage: () => Storage | null): Store {
  const listeners = new Set<() => void>();
  let memoryRaw: string | null = null;  // 저장소를 못 쓸 때 이 탭에서만 유지하는 값
  let unsaved = false;  // 마지막 저장이 실패. 옛 값 대신 memoryRaw 를 읽음
  let cachedRaw: string | null = null;
  let cached: Settings = DEFAULT_SETTINGS;  // 마지막으로 푼 설정(같은 원문이면 재사용)

  // 저장된 원문을 읽음
  function payload(): string | null {
    if (unsaved) return memoryRaw;  // 저장이 실패했으면 이 탭의 값을 씀
    try {
      const storage = getStorage();
      if (storage) return storage.getItem(SETTINGS_KEY);
    } catch {  // 접근 거부. 이 탭에서 바꾼 값을 씀
    }
    return memoryRaw;
  }

  // 원문을 저장하고 구독자에게 알림
  function deposit(raw: string | null) {
    memoryRaw = raw;  // 이 탭의 값을 먼저 변환
    try {
      const storage = getStorage();
      if (raw === null) storage?.removeItem(SETTINGS_KEY);
      else storage?.setItem(SETTINGS_KEY, raw);
      unsaved = false;
    } catch {  // 저장에 실패하면
      unsaved = true;
    }
    for (const listener of listeners) listener();
  }

  return {
    subscription(listener) {
      listeners.add(listener);
      const target = typeof window === "undefined" ? null : window;  // 다른 탭 변경은 창 이벤트로
      target?.addEventListener("storage", listener);
      return () => {
        listeners.delete(listener);
        target?.removeEventListener("storage", listener);
      };
    },
    reading() {
      const raw = payload();
      if (raw !== cachedRaw) {
        cachedRaw = raw;
        cached = decoding(raw);
      }
      return cached;  // 같은 원문이면 같은 설정 객체를 반환
    },
    fallback: () => DEFAULT_SETTINGS,
    revision(next) {
      deposit(JSON.stringify(filter(next.thresholds)));  // 검사한 설정을 글자로 바꿔 저장
    },
    defaults() {  // 기본값으로 되돌림
      deposit(null);
    },
  };
}

const browserStore = vault(() => (typeof window === "undefined" ? null : window.localStorage));

export const revision = browserStore.revision;
export const defaults = browserStore.defaults;  // 기본값 복원 함수를 내보냄

// 설정 훅. 다른 탭에서 바뀐 값도 따라감
export function useSettings(): Settings {
  return useSyncExternalStore(browserStore.subscription, browserStore.reading, browserStore.fallback);
}
