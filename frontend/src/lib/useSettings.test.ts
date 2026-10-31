import { afterEach, describe, expect, it, vi } from "vitest";
import { vault, DEFAULT_SETTINGS, decoding, SETTINGS_KEY } from "./useSettings";

// 메모리에만 저장하는 가짜 저장소를 만드는 도우미
function memory(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, String(value)),
  };
}

// 쿠키 차단 등으로 저장소 접근이 막힌 브라우저를 흉내 냄
const denial = (): Storage => {
  throw new DOMException("denied", "SecurityError");
};

const payload = (thresholds: unknown) => JSON.stringify({ thresholds });

describe("decoding", () => {
  it("gives the defaults when nothing is saved", () => {
    expect(decoding(null)).toBe(DEFAULT_SETTINGS);  // 빈 값은 기본 설정 객체 그대로여야 함
    expect(DEFAULT_SETTINGS.thresholds).toEqual({ A: 45, B: 55, C: 65 });
  });

  it("reads saved thresholds", () => {
    expect(decoding(payload({ A: 40, B: 50, C: 60 })).thresholds).toEqual({ A: 40, B: 50, C: 60 });
  });

  it("falls back to the defaults for broken text", () => {
    for (const raw of ["{", "null", "[]", '"x"', "5", payload(5), payload(null), "{}"]) {
      expect(decoding(raw).thresholds).toEqual(DEFAULT_SETTINGS.thresholds);
    }
  });

  it("falls back per zone for values outside 0 < v <= 500", () => {
    expect(decoding(payload({ A: -1, B: "50", C: 600 })).thresholds).toEqual({ A: 45, B: 55, C: 65 });
    expect(decoding(payload({ A: 0, B: 500, C: 0.5 })).thresholds).toEqual({ A: 45, B: 500, C: 0.5 });
    expect(decoding(payload({ A: 30 })).thresholds).toEqual({ A: 30, B: 55, C: 65 });
  });
});

describe("settings store", () => {
  afterEach(() => {
    vi.unstubAllGlobals();  // 가짜 전역 값을 되돌림
  });

  it("serves the defaults as the server snapshot", () => {
    const store = vault(() => memory({ [SETTINGS_KEY]: payload({ A: 1, B: 2, C: 3 }) }));
    expect(store.fallback()).toBe(DEFAULT_SETTINGS);
  });

  // 저장 글자가 바뀌기 전에는 같은 객체를 주는지 검사
  it("returns the same object until the saved text changes", () => {
    const storage = memory({ [SETTINGS_KEY]: payload({ A: 40, B: 50, C: 60 }) });
    const store = vault(() => storage);
    const first = store.reading();
    expect(store.reading()).toBe(first);

    storage.setItem(SETTINGS_KEY, payload({ A: 41, B: 50, C: 60 }));
    const second = store.reading();
    expect(second).not.toBe(first);
    expect(second.thresholds.A).toBe(41);
  });

  it("saves cleaned values and notifies subscribers", () => {
    const storage = memory();
    const store = vault(() => storage);
    const listener = vi.fn();
    const unsubscribe = store.subscription(listener);

    store.revision({ thresholds: { A: 40, B: -5, C: 60 } });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(JSON.parse(storage.getItem(SETTINGS_KEY) ?? "null")).toEqual({ thresholds: { A: 40, B: 55, C: 60 } });
    expect(store.reading().thresholds).toEqual({ A: 40, B: 55, C: 60 });
    unsubscribe();
  });

  it("reset removes the saved value", () => {
    const storage = memory({ [SETTINGS_KEY]: payload({ A: 40, B: 50, C: 60 }) });
    const store = vault(() => storage);
    const listener = vi.fn();
    const unsubscribe = store.subscription(listener);

    store.defaults();  // 기본값으로 되돌림
    expect(storage.getItem(SETTINGS_KEY)).toBeNull();
    expect(store.reading()).toBe(DEFAULT_SETTINGS);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("works without storage access and keeps changes for this tab", () => {
    const store = vault(denial);
    expect(store.reading()).toBe(DEFAULT_SETTINGS);
    expect(() => store.revision({ thresholds: { A: 40, B: 50, C: 60 } })).not.toThrow();
    expect(store.reading().thresholds).toEqual({ A: 40, B: 50, C: 60 });
    expect(() => store.defaults()).not.toThrow();  // 되돌려도 오류가 없어야 함
    expect(store.reading()).toBe(DEFAULT_SETTINGS);  // 되돌린 뒤에는 기본 설정이어야 함
  });

  it("keeps a change for this tab when the browser refuses to save it", () => {
    const storage = memory({ [SETTINGS_KEY]: payload({ A: 40, B: 50, C: 60 }) });
    const write = storage.setItem;
    storage.setItem = () => {
      throw new DOMException("full", "QuotaExceededError");
    };
    const store = vault(() => storage);

    expect(() => store.revision({ thresholds: { A: 30, B: 50, C: 60 } })).not.toThrow();
    expect(store.reading().thresholds).toEqual({ A: 30, B: 50, C: 60 });

    storage.setItem = write;  // 저장이 다시 되게 되돌림(다른 탭의 변경도 보임)
    store.revision({ thresholds: { A: 35, B: 50, C: 60 } });
    write(SETTINGS_KEY, payload({ A: 20, B: 50, C: 60 }));
    expect(store.reading().thresholds.A).toBe(20);  // 저장소 값(20)을 따라야 함
  });

  it("listens for changes from other tabs while subscribed", () => {
    const target = new EventTarget();
    vi.stubGlobal("window", target);
    const store = vault(() => memory());
    const listener = vi.fn();
    const unsubscribe = store.subscription(listener);

    target.dispatchEvent(new Event("storage"));
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    target.dispatchEvent(new Event("storage"));
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
