import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Gauge } from "./ZoneGauge";

const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
// 화면 낭독·복사로 읽히는 글자 그대로 남기는 도우미
const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const RISING = { "10": 49.6, "20": 54.3, "30": 58.9 };  // 상승 중인 예측 수위(mm)

describe("Gauge", () => {
  it("shows the level, threshold, percent, stage, eta and predictions of a zone", () => {
    const html = renderToStaticMarkup(
      <Gauge
        zoneId="A"
        zone={{ levelMm: 44.96, source: "simulated" }}
        prediction={RISING}
        thresholdMm={45}
        status={{ zoneId: "A", stage: "warning", etaSec: 10 }}
      />,
    );
    const text = content(html);
    expect(html).toMatch(/^<article data-zone="A" data-stage="warning"/);
    for (const part of [
      "A 낮은 상가 도로",
      "가상 실측",
      "44.9 mm",  // 반올림하면 45.0 이 되어 한계에 닿은 것처럼 읽히므로 내림한 값
      "한계 45 mm",
      "한계 대비 99 %",
      "▲ 경계",
      "약 10초 후 한계 도달 예상",
      "+10초 49.6",
      "+20초 54.3",
      "+30초 58.9",
    ]) {
      expect(text).toContain(part);
    }
    expect(html).toContain('style="width:99.91%"');  // 채움 너비가 99.91% 여야 함
    expect(html.match(/style="left:100%"/g)).toHaveLength(3);
  });

  it("shows the percent of threshold and the seconds left as key figures", () => {
    // 카드를 그림. 핵심 수치는 28px 이상(text-key, key-figures 테스트)
    const html = renderToStaticMarkup(
      <Gauge
        zoneId="A"
        zone={{ levelMm: 44.96, source: "simulated" }}
        prediction={RISING}
        thresholdMm={45}
        status={{ zoneId: "A", stage: "warning", etaSec: 10 }}
      />,
    );
    expect(html).toMatch(/<span class="[^"]*\btext-key\b[^"]*">99</);
    expect(html).toMatch(/<span class="[^"]*\btext-key\b[^"]*">약 10초<\/span>/);
    expect(plain(html)).toContain("약 10초 후 한계 도달 예상");
  });

  it("puts the prediction ticks where the predicted levels fall", () => {
    const html = renderToStaticMarkup(
      <Gauge
        zoneId="B"
        zone={{ levelMm: 11, source: "simulated" }}
        prediction={{ "10": 22, "20": 33, "30": 44 }}
        thresholdMm={55}
        status={{ zoneId: "B", stage: "safe", etaSec: null }}
      />,
    );
    expect(html).toContain('style="width:20%"');  // 채움 너비는 11/55 이므로 20% 여야 함
    for (const left of ["40%", "60%", "80%"]) expect(html).toContain(`style="left:${left}"`);
    expect(content(html)).toContain("✓ 정상");
    expect(content(html)).toContain("30초 안에 한계 도달 예상 없음");
  });

  it("marks a model estimate from the zone's source", () => {
    const estimated = content(
      renderToStaticMarkup(
        <Gauge zoneId="C" zone={{ levelMm: 18.7, source: "estimated" }} prediction={RISING} thresholdMm={65} status={null} />,
      ),
    );
    expect(estimated).toContain("C 높은 광장 추정");
    expect(estimated).toContain("모델 추정");

    const measured = content(
      renderToStaticMarkup(
        <Gauge zoneId="C" zone={{ levelMm: 18.7, source: "measured" }} prediction={RISING} thresholdMm={65} status={null} />,
      ),
    );
    expect(measured).toContain("실측");
    expect(measured).not.toContain("추정");
  });

  // 한계를 알기 전에는 한계·퍼센트·게이지를 빼는지 검사
  it("leaves the threshold, percent and gauge out until the threshold is known", () => {
    const html = renderToStaticMarkup(
      <Gauge
        zoneId="B"
        zone={{ levelMm: 31.86, source: "simulated" }}
        prediction={RISING}
        thresholdMm={null}
        status={{ zoneId: "B", stage: "safe", etaSec: null }}
      />,
    );
    const text = content(html);
    expect(text).toContain("31.8 mm");  // 수위는 보여야 함(내림한 값)
    expect(text).toContain("한계 —");
    expect(text).toContain("한계 대비 — %");
    expect(html).not.toContain("style=");  // 게이지 막대(style 속성)가 없어야 함
  });

  // 자료가 오기 전에는 구역 이름과 줄표만 보이는지 검사
  it("shows only the zone name and dashes before there is data", () => {
    const html = renderToStaticMarkup(
      <Gauge zoneId="B" zone={null} prediction={null} thresholdMm={null} status={null} />,
    );
    const text = content(html);
    expect(text).toContain("B 주택 골목");
    expect(text).toContain("한계 —");
    expect(text).toContain("+10초 —");
    expect(html).not.toContain("data-stage");
    expect(text).not.toMatch(/정상|주의|경계|침수/);
    expect(text).not.toContain("mm");  // 단위 mm 도 없어야 함
  });
});
