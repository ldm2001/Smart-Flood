import { ZONES } from "./layout-data";
import type { Alert, Input, Zone, Source } from "./schema";

// 경보 단계 타입(정상·주의·경고·침수)
export type Stage = "safe" | "caution" | "warning" | "evacuate";
// 구역별 한계 수위(mm) 타입
export type Thresholds = Record<Zone, number>;
// +10·20·30초 뒤 예측 수위(mm) 타입
export type Prediction = { "10": number; "20": number; "30": number };

// 구역 하나의 경보 등급 타입
export interface Grade {
  zoneId: Zone;  // 구역 이름(A·B·C)
  stage: Stage;  // 경보 단계
  etaSec: number | null;  // 한계까지 남은 초. 모르면 null
}

export const ZONE_IDS: readonly Zone[] = ["A", "B", "C"];  // 구역 이름 목록(A·B·C 순서 고정)
export const STAGE_ORDER: Record<Stage, number> = { safe: 0, caution: 1, warning: 2, evacuate: 3 };
export const DISCONNECT_AFTER_MS = 4000;  // 마지막 정상 수신 뒤 4초(4000ms)가 넘으면 끊김으로 봄

export const HORIZON_KEYS = ["10", "20", "30"] as const;  // 예측 시점 키(초)

// 등급 판정: 현재 ≥ 한계면 침수, 아니면 처음 닿는 시점
export function verdict(zoneId: Zone, levelMm: number, prediction: Prediction, thresholdMm: number): Grade {
  if (levelMm >= thresholdMm) return { zoneId, stage: "evacuate", etaSec: 0 };  // 이미 침수(0초)
  const hit = HORIZON_KEYS.find((key) => prediction[key] >= thresholdMm);
  if (hit === undefined) return { zoneId, stage: "safe", etaSec: null };  // 30초 내 미도달 = 정상
  const etaSec = Number(hit);
  return { zoneId, stage: etaSec <= 10 ? "warning" : "caution", etaSec };  // ≤10초 경고, 이후 주의
}

// 세 구역의 등급을 한 번에 구
export function verdicts(
  snapshot: { zones: Record<Zone, { levelMm: number }>; predictions: Record<Zone, Prediction> },
  thresholds: Thresholds,
): Record<Zone, Grade> {
  const item = (id: Zone) => verdict(id, snapshot.zones[id].levelMm, snapshot.predictions[id], thresholds[id]);
  return { A: item("A"), B: item("B"), C: item("C") };
}

const rank = (status: Grade) => status.etaSec ?? Number.POSITIVE_INFINITY;  // eta 없으면 맨 뒤

// 가장 위험한 구역: 단계 높은 순, 같으면 빨리 닿는 순, 같으면 A·B·C 순
export function peak(statuses: Record<Zone, Grade>): Grade {
  return ZONE_IDS.map((id) => statuses[id]).sort(
    (a, b) => STAGE_ORDER[b.stage] - STAGE_ORDER[a.stage] || rank(a) - rank(b),
  )[0];  // 맨 앞 하나가 가장 위험한 구역
}

// 가장 먼저 한계에 닿는 구역. 닿는 구역이 없으면 null
export function leader(statuses: Record<Zone, Grade>): Grade | null {
  const reaching = ZONE_IDS.map((id) => statuses[id]).filter((status) => status.etaSec !== null);
  return reaching.sort((a, b) => rank(a) - rank(b))[0] ?? null;  // 가장 빨리 닿는 구역을 돌려줌
}

// 서버 경보를 구역별 등급으로 변환(서버 모드는 이것만 씀). 없는 구역은 정상
export function roster(alerts: readonly Alert[]): Record<Zone, Grade> {
  const statuses: Record<Zone, Grade> = {  // 처음에는 모든 구역을 정상으로 둠
    A: { zoneId: "A", stage: "safe", etaSec: null },  // A 구역: 정상
    B: { zoneId: "B", stage: "safe", etaSec: null },  // B 구역: 정상
    C: { zoneId: "C", stage: "safe", etaSec: null },  // C 구역: 정상
  };
  for (const alert of alerts) {
    if (STAGE_ORDER[alert.stage] > STAGE_ORDER[statuses[alert.zone].stage]) {  // 동률은 먼저 온 것
      statuses[alert.zone] = { zoneId: alert.zone, stage: alert.stage, etaSec: alert.etaSec ?? null };
    }
  }
  return statuses;
}

// mock 이 쓰는 경보 목록 만듦(서버와 같은 모양). 정상 구역은 제외
export function notices(statuses: Record<Zone, Grade>): Alert[] {
  const alerts: Alert[] = [];
  for (const id of ZONE_IDS) {
    const { stage, etaSec } = statuses[id];
    if (stage !== "safe") alerts.push({ zone: id, stage, etaSec });
  }
  return alerts;
}

// 머리글에 보일 배너 타입
export interface Banner {
  stage: Stage;  // 배너 단계
  zoneId: Zone | null;  // 가장 위험한 구역. 모두 정상이면 null
  message: string;  // 화면에 보일 문구
}

// 배너 문구 만듦. 모델 추정 표시는 고정표가 아니라 응답의 source 를 따름
export function caption(
  statuses: Record<Zone, Grade>,
  zones: Record<Zone, { source: Source }>,
): Banner {
  const worst = peak(statuses);
  if (worst.stage === "safe") {
    return { stage: "safe", zoneId: null, message: "전 구역 정상 · 30초 안에 한계 도달 예상 없음" };
  }
  const zone = ZONES[worst.zoneId];
  const what =
    worst.stage === "evacuate" ? "침수 발생" : worst.etaSec === null ? "침수 위험" : `약 ${worst.etaSec}초 후 침수 예상`;
  const estimate = zones[worst.zoneId].source === "estimated" ? " (모델 추정)" : "";
  return { stage: worst.stage, zoneId: worst.zoneId, message: `${worst.zoneId} ${zone.name} · ${what}${estimate}` };
}

// 카드의 도달 문구: value(남은 초)는 큰 수치로, rest 는 뒤에 이어 씀
export function phrase(status: Grade): { value: string | null; rest: string } {
  if (status.stage === "evacuate") return { value: null, rest: "한계 도달" };
  if (status.stage === "safe") return { value: null, rest: "30초 안에 한계 도달 예상 없음" };
  // 서버가 남은 초를 안 보냈으면 시각을 지어내지 않음
  if (status.etaSec === null) return { value: null, rest: "한계 도달 예상 · 시각 미상" };
  return { value: `약 ${status.etaSec}초`, rest: "후 한계 도달 예상" };
}

// 게이지 채움 비율(0~1). 한계에 닿으면 가득 참
export function fraction(levelMm: number, thresholdMm: number): number {
  if (!(thresholdMm > 0)) return 0;  // 한계를 모르거나 0 이하면 0
  return Math.min(1, Math.max(0, levelMm / thresholdMm));
}

// 한계 대비 %(내림). 소수 오차는 보정하고, 100 % 는 한계에 닿았을 때만 나옴
export function share(levelMm: number, thresholdMm: number): number {
  if (!(thresholdMm > 0)) return 0;
  const percent = Math.floor((levelMm * 100) / thresholdMm + 1e-9);  // 부동소수 오차 보정(25.65/45)
  return levelMm < thresholdMm ? Math.min(percent, 99) : percent;  // 한계 미만은 100 % 금지
}

// 수위 표시 글자(0.1 mm 내림). 반올림하면 44.96 이 45.0 으로 보여 한계처럼 읽힘
export function figure(levelMm: number, thresholdMm: number | null): string {
  let tenths = Math.floor(levelMm * 10 + 1e-9);  // 0.1 mm 단위 정수로 내림(부동소수 오차 보정)
  if (thresholdMm !== null && levelMm < thresholdMm) {  // 한계 미만은 한계와 같은 숫자로 안 보임
    tenths = Math.min(tenths, Math.ceil(thresholdMm * 10 - 1e-9) - 1);
  }
  return (tenths / 10).toFixed(1);
}

// 예측 만료 여부: (지금 - 기준 시각)이 유효 기간(초)보다 크면 만료
export function expiry(nowMs: number, basisMs: number, validForSec: number): boolean {
  return nowMs - basisMs > validForSec * 1000;
}

// 연결 끊김 여부: 마지막 정상 수신 뒤 4초가 넘었거나 한 번도 못 받았으면 끊김
export function outage(nowMs: number, lastOkMs: number | null): boolean {
  return lastOkMs === null || nowMs - lastOkMs > DISCONNECT_AFTER_MS;
}

// 선행 시간(초): 실제 도달 시각 - 주의보 시각
export function lead(cautionAtMs: number | null, arrivalAtMs: number | null): number | null {
  if (cautionAtMs === null || arrivalAtMs === null) return null;
  return (arrivalAtMs - cautionAtMs) / 1000;
}

const SEOUL = new Intl.DateTimeFormat("en-US", {  // Asia/Seoul 고정(서머타임 없어 늘 +09:00)
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  fractionalSecondDigits: 3,
  hourCycle: "h23",  // 시는 0~23 시간제
});

// 밀리초 시각을 서울 시각의 항목별 글자로 나눔
function fields(ms: number): Record<string, string> {
  const parts: Record<string, string> = {};
  for (const part of SEOUL.formatToParts(ms)) parts[part.type] = part.value;
  return parts;
}

// 서울 시각 글자로 변환(밀리초까지, 오프셋 +09:00)
export function stamp(ms: number): string {
  const p = fields(ms);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}.${p.fractionalSecond}+09:00`;
}

// 서울 시각의 시:분:초 글자로 변환
export function clock(ms: number): string {
  const p = fields(ms);
  return `${p.hour}:${p.minute}:${p.second}`;  // 시:분:초를 이어 반환
}

// 차트 표본 타입. 여백·눈금·yMax 규칙은 고정, 가로축은 시간
export interface Sample {
  t: number;  // 서버 timestamp(밀리초)
  A: number;  // A 구역 수위(mm)
  B: number;  // B 구역 수위(mm)
  C: number;  // C 구역 수위(mm)
}

// 수위 이력 타입. 폴링 성공마다 서버 timestamp 하나에 표본 하나를 추가
export interface History {
  run: string | null;  // 실험 번호|입력원. 바뀌면 이력을 새로 시작
  samples: readonly Sample[];  // 시간순 표본 목록
}

export const HISTORY_LIMIT = 600;
export const EMPTY_HISTORY: History = { run: null, samples: [] };  // 비어 있는 이력(시작값)

// 표본 추가. 같은 timestamp 는 한 번만 넣고, 시간이 거꾸로 가면 새로 시작
export function entry(
  history: History,
  snapshot: {
    experimentId: string;
    dataSource: Input;
    timestamp: string;
    zones: Record<Zone, { levelMm: number }>;
  },
): History {
  const run = `${snapshot.experimentId}|${snapshot.dataSource}`;
  const { zones } = snapshot;
  const sample = { t: Date.parse(snapshot.timestamp), A: zones.A.levelMm, B: zones.B.levelMm, C: zones.C.levelMm };
  const last = history.samples.at(-1);
  if (run !== history.run || last === undefined || sample.t < last.t) return { run, samples: [sample] };
  if (sample.t === last.t) return history;  // 같은 시각이면 그대로 둠
  return { run, samples: [...history.samples, sample].slice(-HISTORY_LIMIT) };
}

// 차트 틀 옵션 타입
export interface Frame {
  width: number;  // 그림 너비(px)
  height: number;  // 그림 높이(px)
  windowSec?: number;  // 지난 시간 범위(초). 기본 120
  gapSec?: number;  // 표본 사이가 이 초보다 벌어지면 선을 잇지 않음. 기본 5
  pad?: { l: number; r: number; t: number; b: number };  // 여백(왼쪽·오른쪽·위·아래, px)
}

// 차트에 그릴 선과 눈금 묶음 타입
export interface Paths {
  yMax: number;  // 세로축 최대값(mm)
  measured: Record<Zone, string>;  // 구역별 실측 선 경로
  isolated: Record<Zone, { x: number; y: number }[]>;  // 앞뒤가 모두 끊긴 표본
  predicted: Record<Zone, string>;  // 구역별 예측 선 경로
  thresholdY: Record<Zone, number> | null;  // 구역별 한계선의 세로 위치
  gridlines: { value: number; y: number }[];  // 가로 눈금(값과 세로 위치)
  nowX: number | null;  // 현재 시각의 가로 위치. 표본이 없으면 null
  endY: Record<Zone, number> | null;  // 마지막 표본의 세로 위치(선 끝 구역 글자 자리). 없으면 null
}

export const CHART_PAD = { l: 40, r: 14, t: 20, b: 28 };  // 차트 여백(px)
const PREDICTION_SPAN_SEC = 30;

const decimal = (n: number) => Math.round(n * 100) / 100;

// 표본·예측·한계로 차트 선 경로를 만듦
export function plot(
  samples: readonly Sample[],
  predictions: Record<Zone, Prediction> | null,
  thresholds: Thresholds | null,
  options: Frame,
): Paths {
  const { width, height, windowSec = 120, gapSec = 5, pad = CHART_PAD } = options;
  const last = samples.at(-1);
  const end = last?.t ?? 0;  // 가로축 끝(현재) 시각. 표본이 없으면 0
  const start = end - windowSec * 1000;
  const visible = last ? samples.filter((s) => s.t >= start && s.t <= end) : [];
  const ahead = last ? predictions : null;

  const values = [
    0,
    ...(thresholds ? ZONE_IDS.map((id) => thresholds[id]) : []),
    ...visible.flatMap((s) => ZONE_IDS.map((id) => s[id])),
    ...(ahead ? ZONE_IDS.flatMap((id) => HORIZON_KEYS.map((key) => ahead[id][key])) : []),
  ];
  const yMax = Math.max(20, Math.ceil((Math.max(...values) * 1.15) / 10) * 10);

  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const spanMs = (windowSec + PREDICTION_SPAN_SEC) * 1000;  // 가로축 전체 길이(ms)
  const x = (t: number) => decimal(pad.l + ((t - start) / spanMs) * innerW);
  const y = (v: number) => decimal(pad.t + (1 - v / yMax) * innerH);

  const joined = visible.map((s, i) => i > 0 && s.t - visible[i - 1].t <= gapSec * 1000);
  // 구역의 실측 선 경로를 만듦
  const trace = (id: Zone) =>
    visible.map((s, i) => `${joined[i] ? "L" : "M"} ${x(s.t)} ${y(s[id])}`).join(" ");
  // 구역의 외톨이 점을 만듦
  const dots = (id: Zone) =>
    visible.filter((_, i) => !joined[i] && !joined[i + 1]).map((s) => ({ x: x(s.t), y: y(s[id]) }));
  // 구역의 예측 선 경로를 만듦
  const projection = (id: Zone) => {
    if (!last || !ahead) return "";  // 표본이나 예측이 없으면 빈 경로
    const points = HORIZON_KEYS.map((key) => `L ${x(end + Number(key) * 1000)} ${y(ahead[id][key])}`);
    return [`M ${x(end)} ${y(last[id])}`, ...points].join(" ");
  };

  return {
    yMax,
    measured: { A: trace("A"), B: trace("B"), C: trace("C") },
    isolated: { A: dots("A"), B: dots("B"), C: dots("C") },
    predicted: { A: projection("A"), B: projection("B"), C: projection("C") },
    thresholdY: thresholds ? { A: y(thresholds.A), B: y(thresholds.B), C: y(thresholds.C) } : null,
    gridlines: [0, 1, 2, 3, 4, 5].map((i) => ({ value: (yMax * i) / 5, y: y((yMax * i) / 5) })),
    nowX: last ? x(end) : null,  // 현재 시각 위치. 표본이 없으면 null
    endY: last ? { A: y(last.A), B: y(last.B), C: y(last.C) } : null,
  };
}

// 라벨 가로 칸 정함(0 이 선 끝, 클수록 멂). 세로로 height 보다 가까우면 다음 칸
export function columns(ys: Record<Zone, number>, height: number): Record<Zone, number> {
  const placed: { y: number; column: number }[] = [];  // 이미 놓은 라벨들의 세로 위치와 칸
  // 라벨 하나가 들어갈 칸을 결정
  const slot = (y: number) => {
    let column = 0;
    while (placed.some((p) => p.column === column && Math.abs(p.y - y) < height)) column += 1;
    placed.push({ y, column });
    return column;
  };
  return { A: slot(ys.A), B: slot(ys.B), C: slot(ys.C) };
}
