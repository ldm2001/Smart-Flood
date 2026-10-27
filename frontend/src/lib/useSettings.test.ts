import { afterEach, describe, expect, it, vi } from "vitest";
import { vault, DEFAULT_SETTINGS, decoding, SETTINGS_KEY } from "./useSettings";

// 메모리에만 저장하는 가짜 저장소를 만드는 도우미
function memory(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));  // 처음 값으로 맵을 채운다
  return {  // 저장소 모양 객체를 반환
    get length() {  // 저장된 항목 수를 읽는 접근자
      return data.size;  // 맵 크기를 반환
    },
    clear: () => data.clear(),  // 모두 삭제
    getItem: (key) => data.get(key) ?? null,  // 키로 읽고 없으면 null
    key: (index) => [...data.keys()][index] ?? null,  // 번호로 키를 찾고 없으면 null
    removeItem: (key) => void data.delete(key),  // 키로 삭제
    setItem: (key, value) => void data.set(key, String(value)),  // 값을 글자로 바꿔 저장
  };
}

// 쿠키 차단 등으로 저장소 접근이 막힌 브라우저를 흉내 냄
const denial = (): Storage => {
  throw new DOMException("denied", "SecurityError");  // 접근 거부 오류를 던진다
};

// 한계 값을 저장 글자로 만드는 도우미
const payload = (thresholds: unknown) => JSON.stringify({ thresholds });

describe("decoding", () => {  // 저장 글자 해석 테스트 묶음
  it("gives the defaults when nothing is saved", () => {  // 저장된 게 없으면 기본값을 주는지 검사
    expect(decoding(null)).toBe(DEFAULT_SETTINGS);  // 빈 값은 기본 설정 객체 그대로여야 함
    // 기본 한계는 45·55·65 여야 함
    expect(DEFAULT_SETTINGS.thresholds).toEqual({ A: 45, B: 55, C: 65 });
  });

  it("reads saved thresholds", () => {  // 저장된 한계를 읽는지 검사
    // 저장한 한계 40·50·60 이 그대로 나와야 함
    expect(decoding(payload({ A: 40, B: 50, C: 60 })).thresholds).toEqual({ A: 40, B: 50, C: 60 });
  });

  // 깨진 글자는 기본값으로 돌아가는지 검사
  it("falls back to the defaults for broken text", () => {
    // 깨진 글자 여러 가지를 하나씩 확인
    for (const raw of ["{", "null", "[]", '"x"', "5", payload(5), payload(null), "{}"]) {
      // 기본 한계가 나와야 함
      expect(decoding(raw).thresholds).toEqual(DEFAULT_SETTINGS.thresholds);
    }
  });

  // 범위(0 초과 500 이하) 밖 값은 구역별로 기본값을 쓰는지 검사
  it("falls back per zone for values outside 0 < v <= 500", () => {
    // 범위 밖 값과 글자 값은 모두 기본값이어야 함
    expect(decoding(payload({ A: -1, B: "50", C: 600 })).thresholds).toEqual({ A: 45, B: 55, C: 65 });
    // A 는 0 이라 기본값, B 는 500 경계라 허용, C 는 0.5 라 허용
    expect(decoding(payload({ A: 0, B: 500, C: 0.5 })).thresholds).toEqual({ A: 45, B: 500, C: 0.5 });
    // A 만 있으면 나머지는 기본값이어야 함
    expect(decoding(payload({ A: 30 })).thresholds).toEqual({ A: 30, B: 55, C: 65 });
  });
});

describe("settings store", () => {  // 설정 저장소 테스트 묶음
  afterEach(() => {  // 테스트마다 끝난 뒤
    vi.unstubAllGlobals();  // 가짜 전역 값을 되돌린다
  });

  // 서버 렌더 값으로 기본 설정을 주는지 검사
  it("serves the defaults as the server snapshot", () => {
    // 저장된 값이 있는 가짜 저장소로 설정 저장소를 만듦
    const store = vault(() => memory({ [SETTINGS_KEY]: payload({ A: 1, B: 2, C: 3 }) }));
    expect(store.fallback()).toBe(DEFAULT_SETTINGS);  // 저장된 값과 상관없이 기본 설정이어야 함
  });

  // 저장 글자가 바뀌기 전에는 같은 객체를 주는지 검사
  it("returns the same object until the saved text changes", () => {
    // 한계 40·50·60 이 저장된 가짜 저장소를 만듦
    const storage = memory({ [SETTINGS_KEY]: payload({ A: 40, B: 50, C: 60 }) });
    const store = vault(() => storage);  // 그 저장소를 쓰는 설정 저장소를 만듦
    const first = store.reading();  // 처음 읽은 설정
    expect(store.reading()).toBe(first);  // 다시 읽어도 같은 객체여야 함

    // 다른 곳에서 저장 글자를 변환
    storage.setItem(SETTINGS_KEY, payload({ A: 41, B: 50, C: 60 }));
    const second = store.reading();  // 바뀐 뒤 읽은 설정
    expect(second).not.toBe(first);  // 새 객체여야 함
    expect(second.thresholds.A).toBe(41);  // A 한계가 41 로 바뀌어야 함
  });

  // 고친 값을 정리해 저장하고 구독자에게 알리는지 검사
  it("saves cleaned values and notifies subscribers", () => {
    const storage = memory();  // 빈 가짜 저장소를 만듦
    const store = vault(() => storage);  // 그 저장소를 쓰는 설정 저장소를 만듦
    const listener = vi.fn();  // 알림을 셀 가짜 수신자를 만듦
    const unsubscribe = store.subscription(listener);  // 구독하고 해지 함수를 받음

    store.revision({ thresholds: { A: 40, B: -5, C: 60 } });  // B 에 잘못된 값 -5 를 넣어 고친다
    expect(listener).toHaveBeenCalledTimes(1);  // 알림이 한 번 가야 함
    // 저장된 글자의 B 는 기본값 55 로 정리돼야 함
    expect(JSON.parse(storage.getItem(SETTINGS_KEY) ?? "null")).toEqual({ thresholds: { A: 40, B: 55, C: 60 } });
    // 읽은 설정도 같게 정리돼야 함
    expect(store.reading().thresholds).toEqual({ A: 40, B: 55, C: 60 });
    unsubscribe();  // 구독을 해지
  });

  it("reset removes the saved value", () => {  // 초기화가 저장 값을 지우는지 검사
    // 한계 40·50·60 이 저장된 가짜 저장소를 만듦
    const storage = memory({ [SETTINGS_KEY]: payload({ A: 40, B: 50, C: 60 }) });
    const store = vault(() => storage);  // 그 저장소를 쓰는 설정 저장소를 만듦
    const listener = vi.fn();  // 알림을 셀 가짜 수신자를 만듦
    const unsubscribe = store.subscription(listener);  // 구독하고 해지 함수를 받음

    store.defaults();  // 기본값으로 되돌린다
    expect(storage.getItem(SETTINGS_KEY)).toBeNull();  // 저장된 값이 지워져야 함
    expect(store.reading()).toBe(DEFAULT_SETTINGS);  // 읽은 설정은 기본 설정이어야 함
    expect(listener).toHaveBeenCalledTimes(1);  // 알림이 한 번 가야 함
    unsubscribe();  // 구독을 해지
  });

  // 저장소 접근이 막혀도 동작하고 이 탭의 변경은 유지하는지 검사
  it("works without storage access and keeps changes for this tab", () => {
    const store = vault(denial);  // 접근이 막힌 저장소로 설정 저장소를 만듦
    expect(store.reading()).toBe(DEFAULT_SETTINGS);  // 읽으면 기본 설정이어야 함
    // 고쳐도 오류가 없어야 함
    expect(() => store.revision({ thresholds: { A: 40, B: 50, C: 60 } })).not.toThrow();
    // 고친 값이 이 탭에서 읽혀야 함
    expect(store.reading().thresholds).toEqual({ A: 40, B: 50, C: 60 });
    expect(() => store.defaults()).not.toThrow();  // 되돌려도 오류가 없어야 함
    expect(store.reading()).toBe(DEFAULT_SETTINGS);  // 되돌린 뒤에는 기본 설정이어야 함
  });

  // 브라우저가 저장을 거부해도 이 탭의 변경은 유지하는지 검사
  it("keeps a change for this tab when the browser refuses to save it", () => {
    // 한계 40·50·60 이 저장된 가짜 저장소를 만듦
    const storage = memory({ [SETTINGS_KEY]: payload({ A: 40, B: 50, C: 60 }) });
    const write = storage.setItem;  // 원래 저장 함수를 따로 둔다
    storage.setItem = () => {  // 저장 함수를 실패하는 것으로 변환
      // 읽기는 되고 쓰기만 실패한다(저장 공간 부족)
      throw new DOMException("full", "QuotaExceededError");
    };
    const store = vault(() => storage);  // 그 저장소를 쓰는 설정 저장소를 만듦

    // 저장이 막혀도 고치기는 오류가 없어야 함
    expect(() => store.revision({ thresholds: { A: 30, B: 50, C: 60 } })).not.toThrow();
    // 고친 값이 이 탭에서 읽혀야 함
    expect(store.reading().thresholds).toEqual({ A: 30, B: 50, C: 60 });

    storage.setItem = write;  // 저장이 다시 되게 되돌린다(다른 탭의 변경도 보인다)
    store.revision({ thresholds: { A: 35, B: 50, C: 60 } });  // 이 탭에서 다시 고친다
    // 다른 탭이 저장 글자를 바꾼 것처럼 직접 기록
    write(SETTINGS_KEY, payload({ A: 20, B: 50, C: 60 }));
    expect(store.reading().thresholds.A).toBe(20);  // 저장소 값(20)을 따라야 함
  });

  // 구독 중에는 다른 탭의 변경 알림을 듣는지 검사
  it("listens for changes from other tabs while subscribed", () => {
    const target = new EventTarget();  // 이벤트를 받을 가짜 창을 만듦
    vi.stubGlobal("window", target);  // 전역 window 를 그 가짜로 변환
    const store = vault(() => memory());  // 빈 가짜 저장소로 설정 저장소를 만듦
    const listener = vi.fn();  // 알림을 셀 가짜 수신자를 만듦
    const unsubscribe = store.subscription(listener);  // 구독하고 해지 함수를 받음

    target.dispatchEvent(new Event("storage"));  // 다른 탭이 저장했다는 이벤트를 전송
    expect(listener).toHaveBeenCalledTimes(1);  // 알림이 한 번 와야 함

    unsubscribe();  // 구독을 해지
    target.dispatchEvent(new Event("storage"));  // 같은 이벤트를 다시 전송
    expect(listener).toHaveBeenCalledTimes(1);  // 해지 뒤에는 알림이 늘지 않아야 함
  });
});
