import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Gauge } from "./ZoneGauge";

// 태그를 지우고 글자만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
// 화면 낭독·복사로 읽히는 글자 그대로 남기는 도우미
const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const RISING = { "10": 49.6, "20": 54.3, "30": 58.9 };  // 상승 중인 예측 수위(mm)

describe("Gauge", () => {  // 구역 카드 테스트 묶음
  // 수위·한계·퍼센트·단계·eta·예측이 모두 보이는지 검사
  it("shows the level, threshold, percent, stage, eta and predictions of a zone", () => {
    const html = renderToStaticMarkup(  // 경계 단계 카드를 그린다
      <Gauge  // 카드를 연다
        zoneId="A"  // 구역 이름
        zone={{ levelMm: 44.96, source: "simulated" }}  // 현재 수위와 출처
        prediction={RISING}  // 예측 수위
        thresholdMm={45}  // 한계 수위
        status={{ zoneId: "A", stage: "warning", etaSec: 10 }}  // 서버가 알린 단계와 남은 초
      />,
    );
    const text = content(html);  // 화면 글자를 모음
    // 카드에 구역 속성과 단계 속성이 붙어야 함
    expect(html).toMatch(/^<article data-zone="A" data-stage="warning"/);
    for (const part of [  // 보여야 할 조각을 하나씩 확인
      "A 낮은 상가 도로",  // 구역 이름
      "가상 실측",  // 출처 문구
      "44.9 mm",  // 반올림하면 45.0 이 되어 한계에 닿은 것처럼 읽히므로 내림한 값
      "한계 45 mm",  // 한계 수위
      "한계 대비 99 %",  // 한계 대비 퍼센트
      "▲ 경계",  // 단계 알약
      "약 10초 후 한계 도달 예상",  // 도달 문구
      "+10초 49.6",  // 10초 예측
      "+20초 54.3",  // 20초 예측
      "+30초 58.9",  // 30초 예측
    ]) {  // 조각 목록을 닫는다
      expect(text).toContain(part);  // 화면 글자에 조각이 들어 있어야 함
    }
    expect(html).toContain('style="width:99.91%"');  // 채움 너비가 99.91% 여야 함
    // 한계를 넘는 예측은 게이지 끝에 서야 함
    expect(html.match(/style="left:100%"/g)).toHaveLength(3);
  });

  // 한계 대비 퍼센트와 남은 초를 핵심 수치로 보여 주는지 검사
  it("shows the percent of threshold and the seconds left as key figures", () => {
    // 카드를 그린다. 핵심 수치는 28px 이상이다(text-key, key-figures 테스트)
    const html = renderToStaticMarkup(
      <Gauge  // 카드를 연다
        zoneId="A"  // 구역 이름
        zone={{ levelMm: 44.96, source: "simulated" }}  // 현재 수위와 출처
        prediction={RISING}  // 예측 수위
        thresholdMm={45}  // 한계 수위
        status={{ zoneId: "A", stage: "warning", etaSec: 10 }}  // 서버가 알린 단계와 남은 초
      />,
    );
    // 퍼센트 99 가 text-key 글자여야 함
    expect(html).toMatch(/<span class="[^"]*\btext-key\b[^"]*">99</);
    // 남은 초도 text-key 글자여야 함
    expect(html).toMatch(/<span class="[^"]*\btext-key\b[^"]*">약 10초<\/span>/);
    // 큰 글자와 나머지 사이에 실제 공백이 있어야 함
    expect(plain(html)).toContain("약 10초 후 한계 도달 예상");
  });

  // 예측 눈금이 예측 수위 위치에 놓이는지 검사
  it("puts the prediction ticks where the predicted levels fall", () => {
    const html = renderToStaticMarkup(  // 안전 단계 카드를 그린다
      <Gauge  // 카드를 연다
        zoneId="B"  // 구역 B
        zone={{ levelMm: 11, source: "simulated" }}  // 현재 수위 11 mm
        prediction={{ "10": 22, "20": 33, "30": 44 }}  // 예측 22·33·44 mm
        thresholdMm={55}  // 한계 55 mm
        status={{ zoneId: "B", stage: "safe", etaSec: null }}  // 안전 단계, 도달 예상 없음
      />,
    );
    expect(html).toContain('style="width:20%"');  // 채움 너비는 11/55 이므로 20% 여야 함
    // 눈금 위치는 40·60·80% 여야 함
    for (const left of ["40%", "60%", "80%"]) expect(html).toContain(`style="left:${left}"`);
    expect(content(html)).toContain("✓ 정상");  // 안전 문구가 보여야 함
    // 도달 예상 없음 문구가 보여야 함
    expect(content(html)).toContain("30초 안에 한계 도달 예상 없음");
  });

  // 구역 출처에 따라 모델 추정 표시가 붙는지 검사
  it("marks a model estimate from the zone's source", () => {
    const estimated = content(  // 추정 값 카드의 글자를 모음
      renderToStaticMarkup(  // 카드를 서버용으로 그린다
        // 출처가 estimated 인 구역 C
        <Gauge zoneId="C" zone={{ levelMm: 18.7, source: "estimated" }} prediction={RISING} thresholdMm={65} status={null} />,
      ),
    );
    expect(estimated).toContain("C 높은 광장 추정");  // 제목 옆에 추정 표시가 붙어야 함
    expect(estimated).toContain("모델 추정");  // 출처 문구가 모델 추정이어야 함

    const measured = content(  // 실측 값 카드의 글자를 모음
      renderToStaticMarkup(  // 카드를 서버용으로 그린다
        // 출처가 measured 인 구역 C
        <Gauge zoneId="C" zone={{ levelMm: 18.7, source: "measured" }} prediction={RISING} thresholdMm={65} status={null} />,
      ),
    );
    expect(measured).toContain("실측");  // 출처 문구가 실측이어야 함
    expect(measured).not.toContain("추정");  // 추정 표시는 없어야 함
  });

  // 한계를 알기 전에는 한계·퍼센트·게이지를 빼는지 검사
  it("leaves the threshold, percent and gauge out until the threshold is known", () => {
    const html = renderToStaticMarkup(  // 한계가 없는 카드를 그린다
      <Gauge  // 카드를 연다
        zoneId="B"  // 구역 B
        zone={{ levelMm: 31.86, source: "simulated" }}  // 현재 수위 31.86 mm
        prediction={RISING}  // 예측 수위
        thresholdMm={null}  // 한계를 모른다
        status={{ zoneId: "B", stage: "safe", etaSec: null }}  // 서버가 알린 단계와 남은 초
      />,
    );
    const text = content(html);  // 화면 글자를 모음
    expect(text).toContain("31.8 mm");  // 수위는 보여야 한다(내림한 값)
    expect(text).toContain("한계 —");  // 한계 자리는 줄표여야 함
    expect(text).toContain("한계 대비 — %");  // 퍼센트 자리도 줄표여야 함
    expect(html).not.toContain("style=");  // 게이지 막대(style 속성)가 없어야 함
  });

  // 자료가 오기 전에는 구역 이름과 줄표만 보이는지 검사
  it("shows only the zone name and dashes before there is data", () => {
    const html = renderToStaticMarkup(  // 값이 모두 없는 카드를 그린다
      // 구역 B, 값 없음
      <Gauge zoneId="B" zone={null} prediction={null} thresholdMm={null} status={null} />,
    );
    const text = content(html);  // 화면 글자를 모음
    expect(text).toContain("B 주택 골목");  // 구역 이름은 보여야 함
    expect(text).toContain("한계 —");  // 한계는 줄표여야 함
    expect(text).toContain("+10초 —");  // 예측도 줄표여야 함
    expect(html).not.toContain("data-stage");  // 단계 속성은 없어야 함
    expect(text).not.toMatch(/정상|주의|경계|침수/);  // 단계 이름은 보이면 안 됨
    expect(text).not.toContain("mm");  // 단위 mm 도 없어야 함
  });
});
