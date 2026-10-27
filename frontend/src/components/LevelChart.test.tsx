import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { plot, ZONE_IDS } from "@/lib/derive";
import { CHART_OPTIONS, Chart } from "./LevelChart";

// 기준 시각 10:00:00 KST. 실측 실선·예측 점선·한계선·기준 시각 세로선을 시험
const T = Date.UTC(2026, 9, 25, 1, 0, 0);
const LONE = { t: T - 60_000, A: 9, B: 7, C: 3 };  // 앞뒤 5초 안에 이웃이 없는 외톨이 표본
// 1초마다 늘어나는 이어진 표본 3개
const RUN = [0, 1, 2].map((s) => ({ t: T + s * 1000, A: 10 + s, B: 8 + s, C: 4 + s }));
const SAMPLES = [LONE, ...RUN];  // 외톨이와 이어진 표본을 합친다
const PREDICTIONS = {  // 구역별 예측 수위(10·20·30초)
  A: { "10": 20, "20": 30, "30": 40 },  // A 구역 예측
  B: { "10": 14, "20": 18, "30": 22 },  // B 구역 예측
  C: { "10": 7, "20": 9, "30": 11 },  // C 구역 예측
};
const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위

// HTML 에서 태그만 뽑는 도우미
const tags = (html: string) => html.match(/<[^>]+>/g) ?? [];
// 속성 글자가 든 첫 태그를 찾는 도우미
const tag = (html: string, attribute: string) => tags(html).find((tag) => tag.includes(attribute));
// 태그를 지우고 글자만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
// 해당 글자를 가진 라벨 태그를 찾는 도우미
const label = (html: string, text: string) => html.match(new RegExp(`(<span[^>]*>)${text}</span>`))?.[1];
// 태그의 left 값을 읽는 도우미
const left = (tag: string | undefined) => Number.parseFloat(tag?.match(/left:([\d.]+)/)?.[1] ?? "NaN");
// 값을 전체 대비 퍼센트 글자로 바꾸는 도우미
const pct = (value: number, whole: number) => `${Math.round((value / whole) * 10000) / 100}%`;
// 선 끝 구역 글자 태그를 찾는 도우미
const end = (html: string, id: string) => html.match(new RegExp(`(<span[^>]*data-end[^>]*>)${id}</span>`))?.[1];
// 기준 시각 세로선에서 왼쪽으로 띄운 거리(rem)를 읽는 도우미
const extent = (tag: string | undefined) =>
  // left:calc(80% - 0.25rem) 꼴에서 rem 값을 추출
  Number.parseFloat(tag?.match(/left:calc\([\d.]+% - ([\d.]+)rem\)/)?.[1] ?? "NaN");

describe("Chart", () => {  // 차트 테스트 묶음
  // 표본·예측·한계를 모두 준 차트를 그린다
  const html = renderToStaticMarkup(<Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={THRESHOLDS} />);
  // 같은 값으로 계산한 좌표(기대값)
  const chart = plot(SAMPLES, PREDICTIONS, THRESHOLDS, CHART_OPTIONS);

  // 상자에 맞춰 늘어나고 굵기는 화면 픽셀로 유지하는지 검사
  it("stretches to its box and keeps strokes at their screen width", () => {
    expect(tag(html, "<svg")).toContain('preserveAspectRatio="none"');  // 비율을 고정하지 않아야 함
    // 좌표계 크기가 설정과 같아야 함
    expect(tag(html, "<svg")).toContain(`viewBox="0 0 ${CHART_OPTIONS.width} ${CHART_OPTIONS.height}"`);
    // 선과 경로 태그를 모음
    const strokes = tags(html).filter((tag) => /^<(path|line)\b/.test(tag));
    expect(strokes.length).toBeGreaterThan(0);  // 하나 이상 있어야 함
    // 모두 굵기 고정 속성이 있어야 함
    for (const tag of strokes) expect(tag).toContain('vector-effect="non-scaling-stroke"');
  });

  // 실측은 실선, 예측은 점선인지 검사
  it("draws measured lines solid and predictions dashed", () => {
    for (const id of ZONE_IDS) {  // 구역마다 확인
      // 실측 선에는 점선 속성이 없어야 함
      expect(tag(html, `d="${chart.measured[id]}"`)).not.toContain("stroke-dasharray");
      // 예측 선에는 점선 속성이 있어야 함
      expect(tag(html, `d="${chart.predicted[id]}"`)).toContain("stroke-dasharray");
    }
  });

  it("draws a lone sample as a dot", () => {  // 외톨이 표본을 점으로 그리는지 검사
    const [dot] = chart.isolated.A;  // A 구역의 외톨이 점 하나
    // 둥근 끝으로 그려야 함
    expect(tag(html, `d="M ${dot.x} ${dot.y} h 0"`)).toContain('stroke-linecap="round"');
  });

  // 구역마다 한계선과 라벨, 기준 시각 세로선을 그리는지 검사
  it("draws one labelled threshold line per zone and a line at the prediction basis", () => {
    for (const id of ZONE_IDS) {  // 구역마다 확인
      const y = chart.thresholdY?.[id];  // 한계선 높이
      // 그 높이의 가로선이 있어야 함
      expect(tag(html, `y1="${y}" x2="${CHART_OPTIONS.width}" y2="${y}"`)).toBeDefined();
      // 한계 라벨 글자가 있어야 함
      expect(content(html)).toContain(`${id} 한계 ${THRESHOLDS[id]}`);
    }
    // 기준 시각 세로선이 있어야 함
    expect(tag(html, `x1="${chart.nowX}"`)).toContain(`x2="${chart.nowX}"`);
  });

  // 좁은 화면에서도 라벨이 한 줄로 유지되는지 검사
  it("keeps chart labels on one line so a narrow screen cannot stack them", () => {
    // 한계 라벨에 줄바꿈 금지 클래스가 있어야 함
    for (const id of ZONE_IDS) expect(label(html, `${id} 한계 ${THRESHOLDS[id]}`)).toContain("whitespace-nowrap");
    // 시간 눈금 줄부터 뒤쪽을 잘라 냄
    const timeAxis = html.slice(html.lastIndexOf("<div", html.indexOf("기준 시각")));
    expect(tags(timeAxis)[0]).toContain("whitespace-nowrap");  // 시간 눈금 줄도 줄바꿈 금지여야 함
  });

  // 한계 라벨은 왼쪽 끝에 서고 가까운 선일 때만 옆으로 옮기는지 검사
  it("lines threshold labels up at the left edge and moves one aside only when its line is close to another", () => {
    // 기본 한계에서는 모두 왼쪽 끝(0)이어야 함
    for (const id of ZONE_IDS) expect(left(label(html, `${id} 한계 ${THRESHOLDS[id]}`))).toBe(0);

    const close = renderToStaticMarkup(  // B 한계를 A 에 가깝게 만든 차트를 그린다
      // A 45, B 47 로 두 선이 가깝다
      <Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={{ A: 45, B: 47, C: 65 }} />,
    );
    expect(left(label(close, "A 한계 45"))).toBe(0);  // A 는 왼쪽 끝에 있어야 함
    expect(left(label(close, "B 한계 47"))).toBeGreaterThan(0);  // B 는 옆 칸으로 옮겨져야 함
    expect(left(label(close, "C 한계 65"))).toBe(0);  // C 는 왼쪽 끝에 있어야 함
  });

  // 실측 선 끝에 구역 글자가 기준 시각선 옆에 붙는지 검사
  it("marks the end of each measured line with its zone letter, beside the basis line", () => {
    // 구역마다 본다. 글자는 색만으로 구분하지 않으려는 것이고 범례가 읽어 주므로 낭독에서 제외
    for (const id of ZONE_IDS) {
      const tag = end(html, id);  // 선 끝 글자 태그
      expect(tag).toContain(`data-zone="${id}"`);  // 구역 속성이 있어야 함
      expect(tag).toContain('aria-hidden="true"');  // 낭독에서 빠져야 함
      // 세로 위치는 선 끝 높이여야 함
      expect(tag).toContain(`top:${pct(chart.endY?.[id] ?? Number.NaN, CHART_OPTIONS.height)}`);
      // 가로 위치는 기준 시각선 왼쪽이어야 함
      expect(tag).toContain(`left:calc(${pct(chart.nowX ?? Number.NaN, CHART_OPTIONS.width)} - `);
    }
    // 한계를 모르는 차트를 그린다
    const unknown = renderToStaticMarkup(<Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={null} />);
    // 한계가 없어도 선 끝 글자는 있어야 함
    for (const id of ZONE_IDS) expect(end(unknown, id)).toBeDefined();
  });

  // 선 끝이 가까울 때만 글자를 옆으로 옮기는지 검사
  it("moves a zone letter aside only while its line end is close to another", () => {
    // 구역별 띄운 거리를 모으는 도우미
    const offsets = (markup: string) => ZONE_IDS.map((id) => extent(end(markup, id)));
    // 기본 표본의 끝(A 12·B 10·C 6 mm)은 글자 하나 높이보다 가깝다
    const [a, b, c] = offsets(html);
    expect(a).toBeGreaterThan(0);  // A 도 기준선에서 띄운다
    expect(b).toBeGreaterThan(a);  // B 는 A 보다 더 멀리 옮긴다
    expect(c).toBeGreaterThan(b);  // C 는 B 보다 더 멀리 옮긴다

    const apart = [{ t: T, A: 40, B: 20, C: 2 }];  // 끝이 서로 멀리 떨어진 표본
    // 멀리 떨어진 차트를 그린다
    const far = renderToStaticMarkup(<Chart samples={apart} predictions={PREDICTIONS} thresholds={THRESHOLDS} />);
    expect(new Set(offsets(far))).toEqual(new Set([a]));  // 모두 같은 기본 거리여야 함
  });

  // 수위 눈금, 시간 눈금, 범례가 글자로 있는지 검사
  it("labels the value axis, the time axis and the legend in text", () => {
    const text = content(html);  // 화면 글자를 모음
    // 눈금 값이 모두 글자로 있어야 함
    for (const { value } of chart.gridlines) expect(text).toContain(` ${value} `);
    // 시간 눈금·범례·단위 글자를 하나씩 확인
    for (const label of ["−2분", "기준", "+30초", "A 낮은 상가 도로", "B 주택 골목", "C 높은 광장", "단위 mm"]) {
      expect(text).toContain(label);  // 그 글자가 있어야 함
    }
  });

  // 한계를 모르면 한계선을 빼는지 검사
  it("leaves out threshold lines while the thresholds are unknown", () => {
    // 한계 없는 차트를 그린다
    const unknown = renderToStaticMarkup(<Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={null} />);
    expect(content(unknown)).not.toMatch(/[ABC] 한계/);  // 한계 라벨이 없어야 함
    // 선 태그 수를 세는 도우미
    const lines = (markup: string) => tags(markup).filter((tag) => tag.startsWith("<line")).length;
    expect(lines(html) - lines(unknown)).toBe(3);  // 한계선 3개만큼 차이가 나야 함
  });

  // 첫 표본 전에는 선과 시간 라벨 없이 기다리는지 검사
  it("waits with no lines and no time labels before the first sample", () => {
    // 표본이 없는 차트를 그린다
    const empty = renderToStaticMarkup(<Chart samples={[]} predictions={null} thresholds={THRESHOLDS} />);
    expect(content(empty)).toContain("수위 자료 대기");  // 대기 안내가 보여야 함
    expect(empty).not.toContain("<path");  // 선 경로는 없어야 함
    expect(empty).not.toContain("data-end");  // 선 끝 글자도 없어야 함
    expect(content(empty)).not.toContain("기준");  // 기준 시각 라벨도 없어야 함
  });
});
