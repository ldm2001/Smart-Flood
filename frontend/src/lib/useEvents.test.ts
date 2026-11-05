import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { EVENTS_SWR_OPTIONS, useEvents } from "./useEvents";
import { retry } from "./useSnapshot";

// 훅 값을 글자로 그리는 시험용 컴포넌트
function Probe() {
  const { list, failed } = useEvents(null);
  return createElement("output", { "data-failed": String(failed) }, JSON.stringify(list));
}

describe("event reading options", () => {
  it("reads only when the key changes and retries a second later", () => {
    expect(EVENTS_SWR_OPTIONS).toMatchObject({
      refreshInterval: 0,
      dedupingInterval: 0,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      onErrorRetry: retry,  // 상태 읽기와 같은 재시도 함수
    });
  });

  it("stops retrying only on a contract breach", () => {
    expect(EVENTS_SWR_OPTIONS.shouldRetryOnError(new z.ZodError([]))).toBe(false);
    expect(EVENTS_SWR_OPTIONS.shouldRetryOnError(new Error("down"))).toBe(true);
  });
});

describe("useEvents", () => {
  it("gives an empty list and no failure without a record to read", () => {
    const html = renderToStaticMarkup(createElement(Probe));
    expect(html).toBe('<output data-failed="false">[]</output>');
  });
});
