import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { plot, ZONE_IDS } from "@/lib/derive";
import { CHART_OPTIONS, Chart } from "./LevelChart";

const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각 10:00:00 KST
const LONE = { t: T - 60_000, A: 9, B: 7, C: 3 };  // 앞뒤 5초 안에 이웃이 없는 외톨이 표본
// 1초마다 늘어나는 이어진 표본 3개
const RUN = [0, 1, 2].map((s) => ({ t: T + s * 1000, A: 10 + s, B: 8 + s, C: 4 + s }));
const SAMPLES = [LONE, ...RUN];
const PREDICTIONS = {  // 구역별 예측 수위(10·20·30초)
  A: { "10": 20, "20": 30, "30": 40 },
  B: { "10": 14, "20": 18, "30": 22 },
  C: { "10": 7, "20": 9, "30": 11 },
};
const THRESHOLDS = { A: 45, B: 55, C: 65 };

const tags = (html: string) => html.match(/<[^>]+>/g) ?? [];
const tag = (html: string, attribute: string) => tags(html).find((tag) => tag.includes(attribute));
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const label = (html: string, text: string) => html.match(new RegExp(`(<span[^>]*>)${text}</span>`))?.[1];
const left = (tag: string | undefined) => Number.parseFloat(tag?.match(/left:([\d.]+)/)?.[1] ?? "NaN");
const pct = (value: number, whole: number) => `${Math.round((value / whole) * 10000) / 100}%`;
const end = (html: string, id: string) => html.match(new RegExp(`(<span[^>]*data-end[^>]*>)${id}</span>`))?.[1];
// 기준 시각 세로선에서 왼쪽으로 띄운 거리(rem)를 읽는 도우미
const extent = (tag: string | undefined) =>
  // left:calc(80% - 0.25rem) 꼴에서 rem 값을 추출
  Number.parseFloat(tag?.match(/left:calc\([\d.]+% - ([\d.]+)rem\)/)?.[1] ?? "NaN");

describe("Chart", () => {
  const html = renderToStaticMarkup(<Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={THRESHOLDS} />);
  const chart = plot(SAMPLES, PREDICTIONS, THRESHOLDS, CHART_OPTIONS);

  it("stretches to its box and keeps strokes at their screen width", () => {
    expect(tag(html, "<svg")).toContain('preserveAspectRatio="none"');
    expect(tag(html, "<svg")).toContain(`viewBox="0 0 ${CHART_OPTIONS.width} ${CHART_OPTIONS.height}"`);
    const strokes = tags(html).filter((tag) => /^<(path|line)\b/.test(tag));
    expect(strokes.length).toBeGreaterThan(0);
    for (const tag of strokes) expect(tag).toContain('vector-effect="non-scaling-stroke"');
  });

  it("draws measured lines solid and predictions dashed", () => {
    for (const id of ZONE_IDS) {
      expect(tag(html, `d="${chart.measured[id]}"`)).not.toContain("stroke-dasharray");
      expect(tag(html, `d="${chart.predicted[id]}"`)).toContain("stroke-dasharray");
    }
  });

  it("draws a lone sample as a dot", () => {
    const [dot] = chart.isolated.A;
    expect(tag(html, `d="M ${dot.x} ${dot.y} h 0"`)).toContain('stroke-linecap="round"');
  });

  it("draws one labelled threshold line per zone and a line at the prediction basis", () => {
    for (const id of ZONE_IDS) {
      const y = chart.thresholdY?.[id];
      expect(tag(html, `y1="${y}" x2="${CHART_OPTIONS.width}" y2="${y}"`)).toBeDefined();
      expect(content(html)).toContain(`${id} 한계 ${THRESHOLDS[id]}`);
    }
    expect(tag(html, `x1="${chart.nowX}"`)).toContain(`x2="${chart.nowX}"`);
  });

  it("keeps chart labels on one line so a narrow screen cannot stack them", () => {
    for (const id of ZONE_IDS) expect(label(html, `${id} 한계 ${THRESHOLDS[id]}`)).toContain("whitespace-nowrap");
    const timeAxis = html.slice(html.lastIndexOf("<div", html.indexOf("기준 시각")));
    expect(tags(timeAxis)[0]).toContain("whitespace-nowrap");
  });

  it("lines threshold labels up at the left edge and moves one aside only when its line is close to another", () => {
    for (const id of ZONE_IDS) expect(left(label(html, `${id} 한계 ${THRESHOLDS[id]}`))).toBe(0);

    const close = renderToStaticMarkup(
      <Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={{ A: 45, B: 47, C: 65 }} />,
    );
    expect(left(label(close, "A 한계 45"))).toBe(0);
    expect(left(label(close, "B 한계 47"))).toBeGreaterThan(0);
    expect(left(label(close, "C 한계 65"))).toBe(0);
  });

  it("marks the end of each measured line with its zone letter, beside the basis line", () => {
    // 구역마다 봄. 글자는 색만으로 구분하지 않으려는 것이고 범례가 읽어 주므로 낭독에서 제외
    for (const id of ZONE_IDS) {
      const tag = end(html, id);
      expect(tag).toContain(`data-zone="${id}"`);
      expect(tag).toContain('aria-hidden="true"');
      expect(tag).toContain(`top:${pct(chart.endY?.[id] ?? Number.NaN, CHART_OPTIONS.height)}`);
      expect(tag).toContain(`left:calc(${pct(chart.nowX ?? Number.NaN, CHART_OPTIONS.width)} - `);
    }
    const unknown = renderToStaticMarkup(<Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={null} />);
    for (const id of ZONE_IDS) expect(end(unknown, id)).toBeDefined();
  });

  it("moves a zone letter aside only while its line end is close to another", () => {
    const offsets = (markup: string) => ZONE_IDS.map((id) => extent(end(markup, id)));
    // 기본 표본의 끝(A 12·B 10·C 6 mm)은 글자 하나 높이보다 가까움
    const [a, b, c] = offsets(html);
    expect(a).toBeGreaterThan(0);
    expect(b).toBeGreaterThan(a);
    expect(c).toBeGreaterThan(b);

    const apart = [{ t: T, A: 40, B: 20, C: 2 }];
    const far = renderToStaticMarkup(<Chart samples={apart} predictions={PREDICTIONS} thresholds={THRESHOLDS} />);
    expect(new Set(offsets(far))).toEqual(new Set([a]));
  });

  it("labels the value axis, the time axis and the legend in text", () => {
    const text = content(html);
    for (const { value } of chart.gridlines) expect(text).toContain(` ${value} `);
    // 시간 눈금·범례·단위 글자를 하나씩 확인
    for (const label of ["−2분", "기준", "+30초", "A 낮은 상가 도로", "B 주택 골목", "C 높은 광장", "단위 mm"]) {
      expect(text).toContain(label);
    }
  });

  it("leaves out threshold lines while the thresholds are unknown", () => {
    const unknown = renderToStaticMarkup(<Chart samples={SAMPLES} predictions={PREDICTIONS} thresholds={null} />);
    expect(content(unknown)).not.toMatch(/[ABC] 한계/);
    const lines = (markup: string) => tags(markup).filter((tag) => tag.startsWith("<line")).length;
    expect(lines(html) - lines(unknown)).toBe(3);
  });

  // 첫 표본 전에는 선과 시간 라벨 없이 기다리는지 검사
  it("waits with no lines and no time labels before the first sample", () => {
    const empty = renderToStaticMarkup(<Chart samples={[]} predictions={null} thresholds={THRESHOLDS} />);
    expect(content(empty)).toContain("수위 자료 대기");
    expect(empty).not.toContain("<path");
    expect(empty).not.toContain("data-end");
    expect(content(empty)).not.toContain("기준");
  });
});
