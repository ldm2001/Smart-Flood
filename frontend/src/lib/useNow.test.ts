import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// 모듈 수준 상태(현재 값, 타이머)를 테스트마다 새로 받는 도우미
async function instance() {
  vi.resetModules();
  return import("./useNow");
}

const T0 = Date.UTC(2026, 9, 23, 1, 0, 0);  // 기준 시각(2026-10-23 01:00 UTC)

describe("useNow store", () => {
  beforeEach(() => {  // 테스트마다 먼저
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });

  afterEach(() => {
    vi.useRealTimers();  // 진짜 타이머로 되돌림
  });

  // 구독 전에는 서버 값이 null 이고 시각도 없는지 검사
  it("has a null server snapshot and no time before anyone subscribes", async () => {
    const { fallback, reading } = await instance();
    expect(fallback()).toBeNull();
    expect(reading()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("reads the clock on the first subscribe and then once per second", async () => {
    const { reading, subscription } = await instance();
    const listener = vi.fn();
    const unsubscribe = subscription(listener);
    expect(reading()).toBe(T0);

    vi.advanceTimersByTime(999);  // 0.999초를 보냄
    expect(listener).not.toHaveBeenCalled();
    expect(reading()).toBe(T0);  // 읽기 값도 그대로여야 함

    vi.advanceTimersByTime(1);  // 1밀리초 더 보냄(합계 1초)
    expect(listener).toHaveBeenCalledTimes(1);
    expect(reading()).toBe(T0 + 1000);
    unsubscribe();
  });

  it("returns the same value between ticks", async () => {
    const { reading, subscription } = await instance();
    const unsubscribe = subscription(() => {});
    vi.setSystemTime(T0 + 400);  // 시계를 0.4초 보냄. 틱 전에는 값이 그대로
    expect(reading()).toBe(T0);
    expect(reading()).toBe(reading());
    unsubscribe();
  });

  it("shares one interval and clears it after the last subscriber leaves", async () => {
    const { subscription } = await instance();
    const first = vi.fn();
    const second = vi.fn();
    const offFirst = subscription(first);
    const offSecond = subscription(second);
    expect(vi.getTimerCount()).toBe(1);

    vi.advanceTimersByTime(1000);
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);

    offFirst();
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(1000);
    expect(first).toHaveBeenCalledTimes(1);  // 해지한 수신자는 그대로 한 번이어야 함
    expect(second).toHaveBeenCalledTimes(2);

    offSecond();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("forgets the time after the last subscriber leaves, so a remount never paints an old time", async () => {
    const { reading, subscription } = await instance();
    const unsubscribe = subscription(() => {});
    expect(reading()).toBe(T0);
    unsubscribe();
    vi.setSystemTime(T0 + 60_000);  // 화면을 떠나 있던 1분을 보냄
    expect(reading()).toBeNull();
  });

  // 멈춘 뒤 다시 구독하면 시계를 새로 읽는지 검사
  it("reads the clock again when subscribed after a stop", async () => {
    const { reading, subscription } = await instance();
    subscription(() => {})();
    vi.setSystemTime(T0 + 60_000);  // 1분을 보냄
    const unsubscribe = subscription(() => {});
    expect(reading()).toBe(T0 + 60_000);
    unsubscribe();
  });

  it("gives the wall clock to code outside render, like a poll's receive time", async () => {
    const { reading, wall } = await instance();
    vi.setSystemTime(T0 + 1234);
    expect(wall()).toBe(T0 + 1234);
    expect(reading()).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
  });
});
