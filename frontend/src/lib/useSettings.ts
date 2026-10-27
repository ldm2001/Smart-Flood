import { useSyncExternalStore } from "react";
import { ZONE_IDS, type Thresholds } from "./derive";

// 구역 한계 수위 설정. 옛 화면과 같은 저장 키·모양·검증 규칙을 기록
export interface Settings {
  readonly thresholds: Readonly<Thresholds>;  // 구역별 한계 수위(mm). 바꿀 수 없다
}

export const SETTINGS_KEY = "smartFloodSettings";  // 브라우저 저장소 키(옛 화면과 같다)
const MAX_THRESHOLD_MM = 500;  // 한계 수위 상한(mm). 상태 응답의 수위 상한과 같다

// 기본 설정(A 45·B 55·C 65 mm). 바꿀 수 없다
export const DEFAULT_SETTINGS: Settings = Object.freeze({ thresholds: Object.freeze({ A: 45, B: 55, C: 65 }) });

// 쓸 수 있는 한계 수위인지 가린다
const threshold = (value: unknown): value is number =>
  // 유한한 숫자이고 0 초과 상한 이하여야 함
  typeof value === "number" && Number.isFinite(value) && value > 0 && value <= MAX_THRESHOLD_MM;

// 구역마다 검사해 잘못된 값만 기본값으로 변환
function filter(input: unknown): Settings {
  // 객체가 아니면 빈 객체로 확인
  const source = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  const thresholds: Thresholds = { ...DEFAULT_SETTINGS.thresholds };  // 기본값에서 시작
  for (const id of ZONE_IDS) {  // 구역마다 확인
    const value = source[id];  // 그 구역 값을 꺼냄
    if (threshold(value)) thresholds[id] = value;  // 쓸 수 있는 값만 덮어기록
  }
  return { thresholds };  // 고친 설정을 반환
}

// 저장된 원문을 설정으로 푼다. 없거나 깨졌으면 기본값이다
export function decoding(raw: string | null): Settings {
  if (raw === null) return DEFAULT_SETTINGS;  // 저장된 값이 없으면 기본값
  let value: unknown;  // 풀어낸 값을 담을 자리
  try {  // 깨진 글자에 대비
    value = JSON.parse(raw);  // 원문을 JSON 으로 푼다
  } catch {  // 풀 수 없으면
    return DEFAULT_SETTINGS;  // 기본값을 반환
  }
  if (typeof value !== "object" || value === null) return DEFAULT_SETTINGS;  // 객체가 아니면 기본값
  return filter((value as { thresholds?: unknown }).thresholds);  // 한계 수위 부분만 검사해 반환
}

// 설정 저장소의 모양
export interface Store {
  subscription(listener: () => void): () => void;  // 바뀜을 구독하고 해제 함수를 반환
  reading(): Settings;  // 지금 설정을 읽음
  fallback(): Settings;  // 서버 렌더용 설정
  revision(next: Settings): void;  // 설정을 바꿔 저장
  defaults(): void;  // 저장값을 지워 기본값으로 되돌린다
}

// 저장소를 받아 설정 저장소를 만든다. 저장소를 못 써도 화면은 깨지지 않음
export function vault(getStorage: () => Storage | null): Store {
  const listeners = new Set<() => void>();  // 바뀜을 알릴 구독자 모음
  let memoryRaw: string | null = null;  // 저장소를 못 쓸 때 이 탭에서만 유지하는 값
  let unsaved = false;  // 마지막 저장이 실패했다. 옛 값 대신 memoryRaw 를 읽음
  let cachedRaw: string | null = null;  // 마지막으로 푼 원문
  let cached: Settings = DEFAULT_SETTINGS;  // 마지막으로 푼 설정(같은 원문이면 재사용)

  // 저장된 원문을 읽음
  function payload(): string | null {
    if (unsaved) return memoryRaw;  // 저장이 실패했으면 이 탭의 값을 기록
    try {  // 저장소 접근이 막힐 수 있다
      const storage = getStorage();  // 저장소를 얻음
      if (storage) return storage.getItem(SETTINGS_KEY);  // 저장소에 있는 원문을 반환
    } catch {  // 접근 거부. 이 탭에서 바꾼 값을 기록
    }
    return memoryRaw;  // 이 탭의 값을 반환
  }

  // 원문을 저장하고 구독자에게 알린다
  function deposit(raw: string | null) {
    memoryRaw = raw;  // 이 탭의 값을 먼저 변환
    try {  // 저장소에 기록
      const storage = getStorage();  // 저장소를 얻음
      if (raw === null) storage?.removeItem(SETTINGS_KEY);  // 원문이 없으면 저장값을 삭제
      else storage?.setItem(SETTINGS_KEY, raw);  // 있으면 저장
      unsaved = false;  // 저장에 성공했다
    } catch {  // 저장에 실패하면
      unsaved = true;  // 저장 실패. 이 탭에서만 유지됨
    }
    for (const listener of listeners) listener();  // 구독자 모두에게 알린다
  }

  return {  // 저장소를 반환
    subscription(listener) {  // 구독을 시작
      listeners.add(listener);  // 구독자를 모음에 넣음
      // 다른 탭의 바뀜은 창 이벤트로 받고, 다른 키는 읽기에서 걸러진다
      const target = typeof window === "undefined" ? null : window;
      target?.addEventListener("storage", listener);  // 저장소 변경 이벤트를 듣는다
      return () => {  // 구독 해제 함수
        listeners.delete(listener);  // 구독자를 모음에서 제외
        target?.removeEventListener("storage", listener);  // 이벤트 듣기를 그만둔다
      };
    },
    reading() {  // 지금 설정을 읽음
      const raw = payload();  // 저장된 원문을 읽음
      if (raw !== cachedRaw) {  // 원문이 바뀌었을 때만
        cachedRaw = raw;  // 새 원문을 기억
        cached = decoding(raw);  // 새로 풀어 둔다
      }
      return cached;  // 같은 원문이면 같은 설정 객체를 반환
    },
    fallback: () => DEFAULT_SETTINGS,  // 서버 렌더에서는 기본 설정이다
    revision(next) {  // 설정을 변환
      deposit(JSON.stringify(filter(next.thresholds)));  // 검사한 설정을 글자로 바꿔 저장
    },
    defaults() {  // 기본값으로 되돌린다
      deposit(null);  // 저장값을 삭제
    },
  };
}

// 브라우저 저장소를 쓰는 설정 저장소. 서버 렌더에는 저장소가 없다
const browserStore = vault(() => (typeof window === "undefined" ? null : window.localStorage));

export const revision = browserStore.revision;  // 설정 바꾸기 함수를 내전송
export const defaults = browserStore.defaults;  // 기본값 되돌리기 함수를 내전송

// 설정 훅. 다른 탭에서 바뀐 값도 따라감
export function useSettings(): Settings {
  // 구독·읽기·서버용 값을 연결
  return useSyncExternalStore(browserStore.subscription, browserStore.reading, browserStore.fallback);
}
