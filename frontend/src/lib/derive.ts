import type { Answer } from "./api";
import {
  CONTROL_NAMES,
  DEVICE_KEYS,
  DEVICE_LABELS,
  PLAN_VIEW,
  REPLAY_NAMES,
  ZONES,
} from "./layout-data";
import type {
  Alert,
  Blockage,
  Command,
  Control,
  Input,
  LogEvent,
  Notifier,
  Preset,
  Snapshot,
  Source,
  StageEvent,
  Zone,
} from "./schema";

// 경보 단계 타입(정상·주의·경계·침수)
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
export const MAX_THRESHOLD_MM = 500;  // 한계 수위 상한(mm). 상태 응답의 수위 상한과 같음

export const HORIZON_KEYS = ["10", "20", "30"] as const;  // 예측 시점 키(초)

// 등급 판정: 현재 ≥ 한계면 침수, 아니면 처음 닿는 시점
export function verdict(zoneId: Zone, levelMm: number, prediction: Prediction, thresholdMm: number): Grade {
  if (levelMm >= thresholdMm) return { zoneId, stage: "evacuate", etaSec: 0 };  // 이미 침수(0초)
  const hit = HORIZON_KEYS.find((key) => prediction[key] >= thresholdMm);
  if (hit === undefined) return { zoneId, stage: "safe", etaSec: null };  // 30초 내 미도달 = 정상
  const etaSec = Number(hit);
  return { zoneId, stage: etaSec <= 10 ? "warning" : "caution", etaSec };  // ≤10초 경계, 이후 주의
}

// 세 구역의 등급을 한 번에 구함
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

// 선행 시간(초): 실제 도달 시각 - 위험 판단 시각
export function lead(judgedAtMs: number | null, arrivalAtMs: number | null): number | null {
  if (judgedAtMs === null || arrivalAtMs === null) return null;
  return (arrivalAtMs - judgedAtMs) / 1000;
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

export const RECORD_ID = /^EXP-[0-9]{8}-[0-9]{3,}$/;  // 백엔드 EXPERIMENT_ID 와 같은 꼴
export const EVENT_ROWS = 30;  // 사건 기록 최대 줄 수

// 사건 읽기 키 타입: 이름, 실험 번호, 구역·단계 쌍, 실험 상태
export type Topic = readonly ["events", string, string, string];

// 받은 사건 목록과 그 실험 번호
export interface Pack {
  id: string;  // 실험 번호
  list: readonly LogEvent[];  // 기록 순서의 사건
}

// 구역 타임라인의 세 사건
export interface Milestones {
  judgement: StageEvent | null;  // 위험 판단: 회차 첫 사건
  request: StageEvent | null;  // 문자 요청: 회차의 첫 경계 이상
  arrival: StageEvent | null;  // 실제 도달: 회차의 침수
}

// 사건 읽기 키. 실험 번호가 기록 꼴이 아니면 null. 구역·단계 쌍은 서버의 A·B·C 순서
export function topic(snapshot: Snapshot | null): Topic | null {
  if (snapshot === null || !RECORD_ID.test(snapshot.experimentId)) return null;
  const pairs = snapshot.alerts.map((alert) => `${alert.zone}:${alert.stage}`).join(",");
  return ["events", snapshot.experimentId, pairs, snapshot.runState ?? "none"];
}

// 지금 보일 사건. 재생 중이면 지금 경과 초 이하만
export function scope(
  events: readonly LogEvent[],
  state: Pick<Snapshot, "mode" | "elapsedSec">,
): readonly LogEvent[] {
  if (state.mode !== "replay") return events;
  return events.filter((event) => event.elapsedSec <= state.elapsedSec);
}

// 사건 기록 줄. 최신이 위로 30개까지
export function rows(events: readonly LogEvent[]): LogEvent[] {
  return [...events].reverse().slice(0, EVENT_ROWS);
}

// 구역의 마지막 회차에서 판단·요청·도달 사건을 고름
export function milestones(events: readonly LogEvent[], zone: Zone): Milestones {
  const own = events.filter(
    (event): event is StageEvent => event.kind === "stage" && event.zone === zone,
  );
  let end = own.findIndex((event) => event.stage === "evacuate");  // 첫 침수
  for (let i = own.length - 1; end < 0 && i >= 0; i -= 1) {  // 침수가 없으면 마지막 비정상
    if (own[i].stage !== "safe") end = i;
  }
  if (end < 0) return { judgement: null, request: null, arrival: null };  // 회차 없음
  let start = 0;  // 정상에서 벗어난 자리가 없으면 처음
  for (let i = end; i >= 0; i -= 1) {
    if (own[i].previous === "safe") {
      start = i;
      break;
    }
  }
  const span = own.slice(start, end + 1);
  const request = span.find((event) => STAGE_ORDER[event.stage] >= STAGE_ORDER.warning) ?? null;
  const arrival = own[end].stage === "evacuate" ? own[end] : null;
  return { judgement: own[start], request, arrival };
}

// 장치 값의 표시 글과 정상 여부. 모르는 값은 그대로 보임
export function condition(value: string): { label: string; ok: boolean } {
  const known = Object.hasOwn(DEVICE_LABELS, value);  // constructor 같은 이름은 거름
  const label = known ? DEVICE_LABELS[value as keyof typeof DEVICE_LABELS] : value;
  return { label, ok: value === "online" || value === "normal" };
}

// 보호 입력 넷의 정상 여부
export function readiness(devices: Snapshot["devices"]): boolean {
  return DEVICE_KEYS.every((key) => condition(devices[key]).ok);
}

// 빗물받이 하나의 막힘 종류. 막힌 곳이 아니면 none
export function obstruction(blockage: Snapshot["blockage"], inlet: string): Blockage {
  return blockage.location === inlet ? blockage.type : "none";
}

// 지금 실험의 사건 목록. 읽을 번호가 없으면 빈 목록, 아직 못 받았으면 null
export function holding(id: string | null, pack: Pack | null): readonly LogEvent[] | null {
  if (id === null) return [];
  return pack !== null && pack.id === id ? pack.list : null;
}

// 평면도 좌표를 겹친 글자의 CSS 자리(%)로 변환
export function spot(x: number, y: number): { left: string; top: string } {
  const left = Math.round((x / PLAN_VIEW.width) * 10000) / 100;  // 소수 둘째 자리까지
  const top = Math.round((y / PLAN_VIEW.height) * 10000) / 100;
  return { left: `${left}%`, top: `${top}%` };
}

// 구역 칸 안의 물 높이. 아래에서부터 비율만큼 채움
export function pool(
  rect: { y: number; height: number },
  ratio: number,
): { y: number; height: number } {
  const height = rect.height * ratio;
  return { y: rect.y + rect.height - height, height };
}

// 끝에 / 를 붙인 경로. 정적 export 의 trailingSlash 와 같은 꼴
export function address(path: string): string {
  return path.endsWith("/") ? path : `${path}/`;
}

// 이웃한 눈금 사이 가운데 높이. 표척의 작은 눈금 자리
export function notches(gridlines: readonly { y: number }[]): number[] {
  return gridlines.slice(1).map((line, i) => (gridlines[i].y + line.y) / 2);
}

// 제어에 쓰는 연결 상태
export type Linkage = "connecting" | "mock" | "lost" | "online";
// 제어 하나의 켜짐. 꺼지면 이유 글과 그 글이 있는 자리
export type Gate = { on: true } | { on: false; reason: string; cue: "halt" | "note" | "own" };
// 확인 줄을 거치는 제어
export type Hazard = "stop" | "reset" | "sim" | "live" | "replay";
// 확인 줄에 들어오는 누름
export type Press =
  | { kind: "ask"; control: Hazard }  // 제어 단추: 그 줄을 엶
  | { kind: "yes" }
  | { kind: "no" }
  | { kind: "other" };  // 다른 제어를 누름
// 입력 검사 결과
export type Check<T = number> = { ok: true; value: T } | { ok: false; reason: string };
// 결과 줄의 종류: 반영·실패·반영 모름
export type Tone = "ok" | "fail" | "unsure";

// 보낸 제어와 결과. replay 는 보낼 때의 재생 여부
export interface Delivery {
  control: Control;
  answer: Answer;
  replay: boolean;
}

const ON: Gate = { on: true };  // 켜진 판정

// 그 칸의 이유 목록에 적고 끈 판정
const veto = (reason: string): Gate => ({ on: false, reason, cue: "own" });

// 여덟 제어 모두에 같은 판정
function blanket(gate: Gate): Record<Control, Gate> {
  return {
    start: gate,
    stop: gate,
    reset: gate,
    rain: gate,
    blockage: gate,
    sim: gate,
    live: gate,
    replay: gate,
  };
}

// 제어와 연결 표시가 함께 쓰는 연결 상태. 실패 없이 오래된 응답은 아직 연결 중
export function linkage(nowMs: number | null, receivedAt: number | null, failed: boolean): Linkage {
  if (nowMs === null) return "connecting";  // 시계를 아직 모름
  if (receivedAt === null) return failed ? "mock" : "connecting";  // 받은 적 없음
  if (!outage(nowMs, receivedAt)) return "online";
  return failed ? "lost" : "connecting";  // 화면을 옮겨 돌아온 직후는 실패가 없음
}

// online 이 아닐 때 제어를 끈 이유 글
function stoppage(link: Exclude<Linkage, "online">, receivedAt: number | null): string {
  if (link === "connecting") return "서버에 연결하는 중이라 제어를 끕니다";
  if (link === "mock") return "서버에 연결되지 않아 제어를 끕니다. 가상 데이터에는 보내지 않습니다";
  const last = receivedAt === null ? "—" : clock(receivedAt);  // 마지막 수신 시각
  return `연결이 끊겨 제어를 끕니다 · 마지막 수신 ${last} 기준`;
}

// 화면 위 멈춤 줄의 글. online 이면 null
export function halt(link: Linkage, receivedAt: number | null): string | null {
  return link === "online" ? null : stoppage(link, receivedAt);
}

// 제어마다 켜짐과 이유. 연결·재생·회차 상태 차례로 먼저 맞는 규칙이 이기고, 보내는 중이면 켜진 제어를 끔
export function gates(
  link: Linkage,
  receivedAt: number | null,
  snapshot: Snapshot | null,
  sending: Control | null,  // 답을 기다리는 제어
): Record<Control, Gate> {
  if (link !== "online" || snapshot === null) {  // 응답 없이 online 이면 연결 중과 같음
    const reason = stoppage(link === "online" ? "connecting" : link, receivedAt);
    return blanket({ on: false, reason, cue: "halt" });
  }
  const replay = snapshot.dataSource === "replay";
  if (sending !== null) {  // 제 이유로 꺼진 제어는 그 이유 줄을 둬 칸 높이가 그대로
    const busy: Gate = { on: false, reason: `${wording(sending, replay)} 보내는 중입니다`, cue: "note" };
    const rest = gates(link, receivedAt, snapshot, null);  // 보내기 전 판정
    const hold = (gate: Gate) => (gate.on ? busy : gate);  // 켜진 제어만 끔
    return {
      start: hold(rest.start),
      stop: hold(rest.stop),
      reset: hold(rest.reset),
      rain: hold(rest.rain),
      blockage: hold(rest.blockage),
      sim: hold(rest.sim),
      live: hold(rest.live),
      replay: hold(rest.replay),
    };
  }
  const run = snapshot.runState;
  if (replay) {
    return {
      start: veto("재생 중에는 회차를 시작할 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다"),
      stop: run === "running" ? ON : veto("재생이 멈춰 있습니다"),  // 대기·없음도 재생 정지로 봄
      reset: veto("재생 중에는 초기화할 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다"),
      rain: veto("재생 중에는 강우를 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다"),
      blockage: veto("재생 중에는 막힘을 바꿀 수 없습니다. 시뮬레이션으로 돌아간 뒤 합니다"),
      sim: ON,
      live: veto("재생 중에는 실측으로 바꿀 수 없습니다. 먼저 시뮬레이션으로 돌아갑니다"),
      replay: ON,  // 다른 기록은 처음부터 재생. 같은 기록은 rerun 이 끔
    };
  }
  if (run === null || run === undefined) {
    const unknown = veto("서버가 회차 상태를 보내지 않았습니다");
    return { ...blanket(unknown), reset: ON, rain: ON, blockage: ON };
  }
  const running = run === "running";
  const changeover = running  // 다른 입력원으로의 전환
    ? veto("회차가 진행 중이라 입력원을 바꿀 수 없습니다. 먼저 종료합니다")
    : ON;
  return {
    start: running ? veto("이미 진행 중입니다") : ON,
    stop: running ? ON : veto("진행 중이 아닙니다"),
    reset: ON,
    rain: ON,
    blockage: ON,
    sim: snapshot.dataSource === "sim" ? veto("이미 시뮬레이션입니다") : changeover,
    live: snapshot.dataSource === "live" ? veto("이미 실측입니다") : changeover,
    replay: running
      ? veto("회차가 도는 중이라 재생할 수 없습니다. 운영·설정에서 먼저 종료합니다")
      : ON,
  };
}

// 확인 줄의 다음 상태와 보낼 제어. 묻기는 열기만, 예는 열린 줄을 보냄, 나머지는 닫음
export function step(
  open: Hazard | null,  // 지금 열린 확인 줄
  press: Press,
): { open: Hazard | null; send: Hazard | null } {
  if (press.kind === "ask") return { open: press.control, send: null };
  if (press.kind === "yes") return { open: null, send: open };
  return { open: null, send: null };
}

// 앞뒤 빈칸을 지운 입력 글의 숫자. 빈칸이면 null, 숫자가 아니거나 무한이면 NaN
function quantity(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

// 강우 직접 입력 검사. 0 이상, 서버 상한 이하
export function rate(text: string, max: number | null): Check {
  if (max === null) return { ok: false, reason: "서버 강우 설정이 없어 직접 입력을 끕니다" };
  const value = quantity(text);
  if (value === null) return { ok: false, reason: `0 ~ ${max} 사이 숫자를 넣어 주세요` };
  if (Number.isNaN(value)) return { ok: false, reason: "숫자만 넣을 수 있습니다" };
  if (value < 0) return { ok: false, reason: "0 이상이어야 합니다" };
  if (value > max) return { ok: false, reason: `${max} mm/h 이하만 됩니다` };
  return { ok: true, value };
}

// 가상 데이터용 한계 수위 입력 검사. 0 보다 크고 500 mm 이하
export function brim(text: string): Check {
  const value = quantity(text);
  if (value === null) return { ok: false, reason: "숫자를 넣어 주세요" };
  if (Number.isNaN(value)) return { ok: false, reason: "숫자만 넣을 수 있습니다" };
  if (value <= 0) return { ok: false, reason: "0 보다 커야 합니다" };
  if (value > MAX_THRESHOLD_MM) return { ok: false, reason: `${MAX_THRESHOLD_MM} mm 이하만 됩니다` };
  return { ok: true, value };
}

// 본문 없는 회차 제어와 입력원 제어의 요청
export function command(control: "start" | "stop" | "reset" | "sim" | "live"): Command {
  if (control === "sim") return { control, body: { mode: "sim" } };
  if (control === "live") return { control, body: { mode: "live" } };
  return { control, body: {} };
}

// 재생 시작 요청. 본문은 입력원 재생과 기록 번호만
export function playback(id: string): Command {
  return { control: "replay", body: { mode: "replay", logId: id } };
}

// 재생 시작 검사. 그 기록을 이미 재생 중이면 실패
export function rerun(snapshot: Snapshot | null, id: string): Check<string> {
  if (snapshot?.dataSource === "replay" && snapshot.experimentId === id) {
    return { ok: false, reason: "이 기록을 재생하는 중입니다" };
  }
  return { ok: true, value: id };
}

// 강우 요청. 단계 이름이면 단계, 숫자면 직접 입력(mm/h)
export function shower(choice: Preset | number): Command {
  if (typeof choice === "number") return { control: "rain", body: { mmPerHour: choice } };
  return { control: "rain", body: { intensity: choice } };
}

// 막힘 요청. 부분·완전 막힘은 빗물받이가 있어야 함
export function plug(kind: Blockage, inlet: string | null): Check<Command> {
  if (kind === "none") return { ok: true, value: { control: "blockage", body: { type: "none" } } };
  if (inlet === null) return { ok: false, reason: "막을 빗물받이를 골라 주세요" };
  return { ok: true, value: { control: "blockage", body: { type: kind, location: inlet } } };
}

// 판정과 입력 검사를 합침. 꺼진 판정은 그대로, 검사 실패는 그 칸의 이유
export function pass(gate: Gate, check: Check<unknown>): Gate {
  if (!gate.on && gate.cue !== "note") return gate;  // 보내는 중(note)만 검사 실패에 자리를 내줌
  return check.ok ? gate : veto(check.reason);
}

// 단추 이름. 재생 중 종료와 시뮬레이션 전환은 재생 쪽 이름
export function wording(control: Control, replay: boolean): string {
  if (replay && (control === "stop" || control === "sim")) return REPLAY_NAMES[control];
  return CONTROL_NAMES[control];
}

const MODE_WORDS = { sim: "시뮬레이션", live: "실측" } as const;  // 입력원 전환 물음의 이름

// 확인 줄의 물음. 누르면 무엇이 사라지는지 알림
export function question(control: Hazard, snapshot: Snapshot): string {
  const replay = snapshot.dataSource === "replay";
  const tail = "대기로 돌아가고 강우·막힘 선택이 기본값이 됩니다";  // 입력원 전환 뒤 일
  const wipe = "멈춘 회차의 마지막 화면도 지워집니다. 기록 파일은 남습니다";
  if (control === "replay") {
    if (replay) return "지금 재생을 끝내고 이 기록을 처음부터 재생할까요?";
    return "이 기록을 처음부터 재생할까요? 멈춘 회차의 마지막 화면은 재생 화면으로 바뀝니다";
  }
  if (control === "stop") {
    if (replay) return "재생을 멈출까요? 멈춘 재생은 이어 볼 수 없습니다";
    return "회차를 종료할까요? 비가 그치고 마지막 상태가 남습니다";
  }
  if (control === "reset") {
    if (snapshot.runState === "idle") return "강우·막힘 선택만 기본값(보통 강우, 막힘 없음)으로 돌립니다";
    return "회차를 끝내고 대기로 돌아가며 강우·막힘 선택이 기본값이 됩니다. 기록 파일은 남습니다";
  }
  if (control === "sim" && replay) return `재생을 끝내고 시뮬레이션으로 돌아갈까요? ${tail}`;
  return `${MODE_WORDS[control]}으로 바꿀까요? ${tail}. ${wipe}`;
}

// 성공 글의 바뀐 것. 응답 상태로 씀
function effect(control: Control, snapshot: Snapshot, replay: boolean): string {
  if (control === "start") return `회차 시작 · ${snapshot.experimentId}`;
  if (control === "stop") return replay ? "재생 멈춤" : "회차 종료";
  if (control === "reset") return "초기화 · 대기";
  if (control === "rain") return `강우 ${snapshot.rain.mmPerHour} mm/h`;
  if (control === "blockage") return `막힘 설정 · ${snapshot.blockage.label}`;
  if (control === "sim") return replay ? "재생 끝냄 · 입력원 시뮬레이션" : "입력원 시뮬레이션";
  if (control === "replay") return `재생 시작 · ${snapshot.experimentId}`;
  return "입력원 실측";
}

// 결과 줄의 종류와 글. 성공은 받은 시각, 실패는 실패 시각
export function outcome(delivery: Delivery): { tone: Tone; text: string } {
  const { control, answer, replay } = delivery;
  if (answer.ok) {
    const { snapshot, receivedAt } = answer.receipt;
    const what = effect(control, snapshot, replay);  // 바뀐 것
    return { tone: "ok", text: `반영 · ${what} · ${clock(receivedAt)} 수신` };
  }
  const name = wording(control, replay);
  const at = clock(answer.at);  // 실패 시각
  const { fault } = answer;
  if (fault.kind === "refused") return { tone: "fail", text: `${name} 거절 · ${fault.text} · ${at}` };
  if (fault.kind === "status") {
    const what = fault.status === 422 ? "요청 모양 오류" : "서버 오류";  // 이유 없는 HTTP 실패
    return { tone: "fail", text: `${name} 실패 · ${what} HTTP ${fault.status} · ${at}` };
  }
  if (fault.kind === "network") return { tone: "fail", text: `${name} 실패 · 서버에 닿지 못했습니다 · ${at}` };
  if (fault.kind === "timeout") {
    const rest = "5초 안에 답이 없었습니다. 반영됐는지는 다음 수신으로 확인합니다";
    return { tone: "unsure", text: `${name} 응답 없음 · ${rest} · ${at}` };
  }
  const rest = "서버는 받았을 수 있습니다. 다음 수신으로 확인합니다";  // 200 인데 계약과 다름
  return { tone: "unsure", text: `${name} 응답 모양 이상 · ${rest} · ${at}` };
}

// 칸의 이유 목록 한 줄. id 는 그 글을 처음 가진 이름의 것
export interface Reason {
  id: string;
  text: string;
}

// 이유 목록에 적을 글. 켜짐·통과와 멈춤·결과 줄 자리의 이유는 null
function grounds(item: Gate | Check<unknown>): string | null {
  if ("on" in item) return !item.on && item.cue === "own" ? item.reason : null;
  return item.ok ? null : item.reason;
}

// 칸의 이유 목록과 이름마다 가리킬 줄. 같은 글은 한 줄로 모음
export function reasons(entries: readonly (readonly [string, Gate | Check<unknown>])[]): {
  lines: Reason[];
  links: Partial<Record<string, string>>;  // 이름마다 이유 줄 id. 이유가 없으면 빠짐
} {
  const lines: Reason[] = [];
  const links: Partial<Record<string, string>> = {};
  for (const [name, item] of entries) {
    const text = grounds(item);
    if (text === null) continue;
    let line = lines.find((each) => each.text === text);
    if (line === undefined) {
      line = { id: `ops-why-${name}`, text };
      lines.push(line);
    }
    links[name] = line.id;
  }
  return { lines, links };
}

// 한계 수위 칸의 보이는 글, 칸마다 검사, 저장 판정. 바뀐 값이 없으면 저장을 끔
export function amendment(
  draft: Partial<Record<Zone, string>>,  // 고치는 중인 글. 없는 칸은 저장값
  saved: Readonly<Thresholds>,
): { texts: Record<Zone, string>; checks: Record<Zone, Check>; save: Check<Thresholds> } {
  const text = (id: Zone) => draft[id] ?? String(saved[id]);
  const texts = { A: text("A"), B: text("B"), C: text("C") };
  // 이유 글 앞에 구역 이름을 붙인 검사
  const check = (id: Zone): Check => {
    const result = brim(texts[id]);
    return result.ok ? result : { ok: false, reason: `${id} 구역 · ${result.reason}` };
  };
  const checks = { A: check("A"), B: check("B"), C: check("C") };
  const values: Thresholds = { ...saved };
  for (const id of ZONE_IDS) {
    const result = checks[id];
    if (!result.ok) return { texts, checks, save: result };  // 처음 틀린 구역의 이유
    values[id] = result.value;
  }
  const changed = ZONE_IDS.some((id) => values[id] !== saved[id]);
  const save: Check<Thresholds> = changed
    ? { ok: true, value: values }
    : { ok: false, reason: "바뀐 값이 없습니다" };
  return { texts, checks, save };
}

// 구역 하나의 예측·실제 비교. 시각은 밀리초, 간격은 초. 모르는 칸은 null
export interface Tally {
  zone: Zone;
  judgement: number | null;  // 위험 판단 시각: 에피소드 시작 사건
  forecast: number | null;  // 예측 도달 시각: 판단 시각 + 그 사건의 etaSec
  arrival: number | null;  // 실제 도달 시각: 첫 침수 사건
  lead: number | null;  // 선행 시간: 실제 도달 - 위험 판단
  error: number | null;  // 오차: 실제 도달 - 예측 도달(부호 포함)
}

// 기록 사건으로 구역마다 예측 도달과 실제 도달을 견줌. 간격은 경과 초로 셈
export function tally(events: readonly LogEvent[]): Tally[] {
  return ZONE_IDS.map((zone) => {
    const { judgement, arrival } = milestones(events, zone);
    const eta = judgement?.etaSec ?? null;  // 판단 사건의 도달 남은 초
    const ahead = judgement !== null && eta !== null ? judgement.elapsedSec + eta : null;
    return {
      zone,
      judgement: judgement === null ? null : Date.parse(judgement.time),
      forecast: judgement !== null && eta !== null ? Date.parse(judgement.time) + eta * 1000 : null,
      arrival: arrival === null ? null : Date.parse(arrival.time),
      lead: lead(judgement && judgement.elapsedSec * 1000, arrival && arrival.elapsedSec * 1000),
      error: ahead === null || arrival === null ? null : arrival.elapsedSec - ahead,
    };
  });
}

// 초 간격 글. 없으면 줄표, signed 면 양수에 + 를 붙임
export function span(sec: number | null, signed = false): string {
  if (sec === null) return "—";
  const value = Math.round(sec);
  return `${signed && value > 0 ? "+" : ""}${value}초`;
}

// 문자 요청 줄의 발송 글. 지난 기록·재생은 결과를 모름. 문자 방식이고 무장했을 때만 실제 발송
export function relay(notifier: Notifier | null | undefined, past = false): string {
  if (past) return "발송 결과는 서버 로그에만 남음";  // 결과는 실험 기록에 없음
  if (notifier?.mode === "sms" && notifier.armed) return "실제 발송 켜짐, 허용 번호만";
  return "기록만, 실제 발송 차단";
}
