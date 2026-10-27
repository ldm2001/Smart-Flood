import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// 모듈 수준 상태(현재 값, 타이머)를 테스트마다 새로 받는 도우미
async function instance() {
  vi.resetModules();  // 읽어 둔 모듈을 비운다
  return import("./useNow");  // 화면 시계 모듈을 새로 읽어 반환
}

const T0 = Date.UTC(2026, 9, 23, 1, 0, 0);  // 기준 시각(2026-10-23 01:00 UTC)

describe("useNow store", () => {  // 화면 시계 저장소 테스트 묶음
  beforeEach(() => {  // 테스트마다 먼저
    vi.useFakeTimers();  // 타이머와 시계를 가짜로 변환
    vi.setSystemTime(T0);  // 시계를 기준 시각에 맞춤
  });

  afterEach(() => {  // 테스트마다 끝난 뒤
    vi.useRealTimers();  // 진짜 타이머로 되돌린다
  });

  // 구독 전에는 서버 값이 null 이고 시각도 없는지 검사
  it("has a null server snapshot and no time before anyone subscribes", async () => {
    const { fallback, reading } = await instance();  // 새 모듈에서 서버 값 함수와 읽기 함수를 꺼냄
    expect(fallback()).toBeNull();  // 서버 렌더 값은 null 이어야 함
    expect(reading()).toBeNull();  // 구독 전 읽기 값은 null 이어야 함
    expect(vi.getTimerCount()).toBe(0);  // 타이머가 없어야 함
  });

  // 처음 구독할 때 시계를 읽고 이후 초마다 읽는지 검사
  it("reads the clock on the first subscribe and then once per second", async () => {
    const { reading, subscription } = await instance();  // 읽기 함수와 구독 함수를 꺼냄
    const listener = vi.fn();  // 알림을 셀 가짜 수신자를 만듦
    const unsubscribe = subscription(listener);  // 구독하고 해지 함수를 받음
    expect(reading()).toBe(T0);  // 구독하자마자 기준 시각을 읽어야 함

    vi.advanceTimersByTime(999);  // 0.999초를 전송
    expect(listener).not.toHaveBeenCalled();  // 아직 알림이 없어야 함
    expect(reading()).toBe(T0);  // 읽기 값도 그대로여야 함

    vi.advanceTimersByTime(1);  // 1밀리초 더 보낸다(합계 1초)
    expect(listener).toHaveBeenCalledTimes(1);  // 알림이 한 번 와야 함
    expect(reading()).toBe(T0 + 1000);  // 읽기 값이 1초 앞서야 함
    unsubscribe();  // 구독을 해지
  });

  it("returns the same value between ticks", async () => {  // 틱 사이에는 같은 값을 주는지 검사
    const { reading, subscription } = await instance();  // 읽기 함수와 구독 함수를 꺼냄
    const unsubscribe = subscription(() => {});  // 빈 수신자로 구독
    vi.setSystemTime(T0 + 400);  // 시계를 0.4초 보낸다. 틱 전에는 값이 그대로다
    expect(reading()).toBe(T0);  // 값은 여전히 기준 시각이어야 함
    expect(reading()).toBe(reading());  // 연속해서 읽어도 같아야 함
    unsubscribe();  // 구독을 해지
  });

  // 타이머를 하나만 공유하고 마지막 구독자가 떠나면 치우는지 검사
  it("shares one interval and clears it after the last subscriber leaves", async () => {
    const { subscription } = await instance();  // 구독 함수를 꺼냄
    const first = vi.fn();  // 첫 수신자
    const second = vi.fn();  // 둘째 수신자
    const offFirst = subscription(first);  // 첫 수신자를 구독
    const offSecond = subscription(second);  // 둘째 수신자를 구독
    expect(vi.getTimerCount()).toBe(1);  // 타이머는 하나뿐이어야 함

    vi.advanceTimersByTime(1000);  // 1초를 전송
    expect(first).toHaveBeenCalledTimes(1);  // 첫 수신자에 알림이 한 번 와야 함
    expect(second).toHaveBeenCalledTimes(1);  // 둘째 수신자에도 한 번 와야 함

    offFirst();  // 첫 수신자를 해지
    expect(vi.getTimerCount()).toBe(1);  // 아직 구독자가 있어 타이머가 남아야 함
    vi.advanceTimersByTime(1000);  // 1초를 더 전송
    expect(first).toHaveBeenCalledTimes(1);  // 해지한 수신자는 그대로 한 번이어야 함
    expect(second).toHaveBeenCalledTimes(2);  // 남은 수신자는 두 번째 알림을 받아야 함

    offSecond();  // 마지막 수신자를 해지
    expect(vi.getTimerCount()).toBe(0);  // 타이머가 모두 치워져야 함
  });

  // 마지막 구독자가 떠나면 시각을 잊어 다시 그릴 때 옛 시각이 안 보이는지 검사
  it("forgets the time after the last subscriber leaves, so a remount never paints an old time", async () => {
    const { reading, subscription } = await instance();  // 읽기 함수와 구독 함수를 꺼냄
    const unsubscribe = subscription(() => {});  // 빈 수신자로 구독
    expect(reading()).toBe(T0);  // 구독 중에는 기준 시각을 읽어야 함
    unsubscribe();  // 구독을 해지
    vi.setSystemTime(T0 + 60_000);  // 화면을 떠나 있던 1분을 전송
    expect(reading()).toBeNull();  // 읽기 값은 비어 있어야 함
  });

  // 멈춘 뒤 다시 구독하면 시계를 새로 읽는지 검사
  it("reads the clock again when subscribed after a stop", async () => {
    const { reading, subscription } = await instance();  // 읽기 함수와 구독 함수를 꺼냄
    subscription(() => {})();  // 구독했다가 곧바로 해지
    vi.setSystemTime(T0 + 60_000);  // 1분을 전송
    const unsubscribe = subscription(() => {});  // 다시 구독
    expect(reading()).toBe(T0 + 60_000);  // 새로 읽은 시각이어야 함
    unsubscribe();  // 구독을 해지
  });

  // 화면 그리기 밖 코드에 현재 시각을 주는지 검사(통신 받은 시각 등)
  it("gives the wall clock to code outside render, like a poll's receive time", async () => {
    const { reading, wall } = await instance();  // 읽기 함수와 현재 시각 함수를 꺼냄
    vi.setSystemTime(T0 + 1234);  // 시계를 1.234초 전송
    expect(wall()).toBe(T0 + 1234);  // 현재 시각 함수는 바뀐 시각을 줘야 함
    expect(reading()).toBeNull();  // 화면 시계는 건드리지 않아야 함
    expect(vi.getTimerCount()).toBe(0);  // 타이머도 만들지 않아야 함
  });
});
