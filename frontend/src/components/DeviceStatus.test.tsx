import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { demo } from "@/lib/mock";
import type { Snapshot } from "@/lib/schema";
import { Devices } from "./DeviceStatus";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
const SIM = demo(Date.UTC(2026, 9, 23, 1, 1, 10), { A: 45, B: 55, C: 65 });  // 가상 입력 상태
const REV16 = {  // REV16 실측 입력의 장치 값
  esp32_1: "online",
  esp32_2: "offline",
  floatSwitch: "unknown",
  emergencyStop: "unknown",
};
const NOTE =
  "가상·재생 입력에서는 장치 값이 늘 정상으로 나옵니다. 실측 입력에서는 마지막 메시지 뒤 " +
  "5초 안의 장치만 정상이고, 한 번도 오지 않은 장치는 끊김, 플로트 스위치·비상정지는 " +
  "메시지에 없어 미상으로 보입니다.";
const LOCK = '<span class="chip border border-line">출력 잠금</span>';
const draw = (snapshot: Snapshot | null) => renderToStaticMarkup(<Devices snapshot={snapshot} />);

describe("Devices", () => {
  it("shows healthy protection inputs for the simulation", () => {
    const html = draw(SIM);
    const text = content(html);
    for (const part of [
      "[check] 보호 입력 정상",
      "[check] ESP32 #1 · 정상",
      "[check] ESP32 #2 · 정상",
      "[check] 플로트 스위치 · 정상",
      "[check] 비상정지 · 정상",
      "[check] 입력 품질 · 정상",
    ]) {
      expect(text).toContain(part);
    }
    expect(html).toContain('<p class="text-lg font-medium text-(--green)">');
  });

  it("asks for a check when live devices are offline or unknown", () => {
    const html = draw({ ...SIM, dataSource: "live", devices: REV16 });
    const text = content(html);
    for (const part of [
      "[alert] 보호 상태 확인",
      "[check] ESP32 #1 · 정상",
      "[alert] ESP32 #2 · 끊김",
      "[alert] 플로트 스위치 · 미상",
      "[alert] 비상정지 · 미상",
    ]) {
      expect(text).toContain(part);
    }
    expect(text).not.toContain("보호 입력 정상");
    expect(html).toContain('<p class="text-lg font-medium text-amber">');
  });

  it("colours the three input qualities", () => {
    const cases = [
      ["valid", "[check] 입력 품질 · 정상", "text-(--green)"],
      ["degraded", "[alert] 입력 품질 · 확인 필요", "text-amber"],
      ["invalid", "[alert] 입력 품질 · 사용 중지", "text-(--red)"],
    ] as const;
    for (const [quality, line, tone] of cases) {
      const html = draw({ ...SIM, quality });
      expect(content(html)).toContain(line);
      expect(html).toContain(`<p class="mt-3 ${tone}">`);
    }
  });

  it("shows unknown device values as they are", () => {
    const devices = { ...REV16, esp32_1: "tripped", floatSwitch: "constructor" };
    const text = content(draw({ ...SIM, devices }));
    expect(text).toContain("[alert] ESP32 #1 · tripped");
    expect(text).toContain("[alert] 플로트 스위치 · constructor");
  });

  it("always shows the output lock and the two notes", () => {
    for (const snapshot of [SIM, null]) {
      const html = draw(snapshot);
      const text = content(html);
      expect(html).toContain(LOCK);
      expect(text).toContain("제어 출력 출력 잠금");
      expect(text).toContain(NOTE);
      expect(text).toContain("웹 화면은 안전 차단을 대신하지 않습니다.");
    }
  });

  it("shows dashes while connecting", () => {
    const html = draw(null);
    expect(content(html)).toContain(
      "현장 장치 상태 — ESP32 #1 · — ESP32 #2 · — 플로트 스위치 · — 비상정지 · — 입력 품질 · —",
    );
    expect(html).not.toContain("data-icon");  // 정상·확인 아이콘이 없어야 함
  });
});
