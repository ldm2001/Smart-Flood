import { ZONES } from "./layout-data";
import type { Alert, Input, Zone, Source } from "./schema";

// 경보 단계 타입(정상·주의·경고·침수)
export type Stage = "safe" | "caution" | "warning" | "evacuate";
// 구역별 한계 수위(mm) 타입
export type Thresholds = Record<Zone, number>;
// +10·20·30초 뒤 예측 수위(mm) 타입
export type Prediction = { "10": number; "20": number; "30": number };

// 구역 하나의 경보 등급 타입을 연다
export interface Grade {
  zoneId: Zone;  // 구역 이름(A·B·C)
  stage: Stage;  // 경보 단계
  etaSec: number | null;  // 한계까지 남은 초. 모르면 null
}

export const ZONE_IDS: readonly Zone[] = ["A", "B", "C"];  // 구역 이름 목록(A·B·C 순서 고정)
// 단계 높낮이 값(클수록 위험하다)
export const STAGE_ORDER: Record<Stage, number> = { safe: 0, caution: 1, warning: 2, evacuate: 3 };
export const DISCONNECT_AFTER_MS = 4000;  // 마지막 정상 수신 뒤 4초(4000ms)가 넘으면 끊김으로 확인

// 예측 시점 키(초). 읽기 전용 값으로 굳힌다
export const HORIZON_KEYS = ["10", "20", "30"] as const;

// 등급 판정(옛 프론트와 같은 규칙): 현재 ≥ 한계면 침수, 아니면 처음 닿는 시점
export function verdict(zoneId: Zone, levelMm: number, prediction: Prediction, thresholdMm: number): Grade {
  // 현재 수위가 한계 이상이면 침수다. 도달까지 0초
  if (levelMm >= thresholdMm) return { zoneId, stage: "evacuate", etaSec: 0 };
  // 한계에 처음 닿는 예측 시점을 찾음
  const hit = HORIZON_KEYS.find((key) => prediction[key] >= thresholdMm);
  // 30초 안에 닿지 않으면 정상이다
  if (hit === undefined) return { zoneId, stage: "safe", etaSec: null };
  const etaSec = Number(hit);  // 시점 글자를 초 숫자로 변환
  // 10초 이하면 경고, 더 늦으면 주의다
  return { zoneId, stage: etaSec <= 10 ? "warning" : "caution", etaSec };
}

// 세 구역의 등급을 한 번에 구
export function verdicts(
  // 스냅샷: 구역별 현재 수위와 예측 수위
  snapshot: { zones: Record<Zone, { levelMm: number }>; predictions: Record<Zone, Prediction> },
  thresholds: Thresholds,  // 구역별 한계 수위
): Record<Zone, Grade> {  // 구역별 등급을 반환
  // 구역 하나의 등급을 구하는 도우미
  const item = (id: Zone) => verdict(id, snapshot.zones[id].levelMm, snapshot.predictions[id], thresholds[id]);
  return { A: item("A"), B: item("B"), C: item("C") };  // A·B·C 등급을 묶어 반환
}

// 도달 순서 값. 남은 초가 없으면 무한대라 맨 뒤다
const rank = (status: Grade) => status.etaSec ?? Number.POSITIVE_INFINITY;

// 가장 위험한 구역: 단계 높은 순, 같으면 빨리 닿는 순, 같으면 A·B·C 순
export function peak(statuses: Record<Zone, Grade>): Grade {
  return ZONE_IDS.map((id) => statuses[id]).sort(  // 구역 등급을 정렬
    // 단계가 높은 쪽이 앞, 같으면 빨리 닿는 쪽이 앞
    (a, b) => STAGE_ORDER[b.stage] - STAGE_ORDER[a.stage] || rank(a) - rank(b),
  )[0];  // 맨 앞 하나가 가장 위험한 구역이다
}

// 가장 먼저 한계에 닿는 구역. 닿는 구역이 없으면 null
export function leader(statuses: Record<Zone, Grade>): Grade | null {
  // 도달 시각이 있는 구역만 남김
  const reaching = ZONE_IDS.map((id) => statuses[id]).filter((status) => status.etaSec !== null);
  // 가장 빨리 닿는 구역을 돌려준다. 없으면 null
  return reaching.sort((a, b) => rank(a) - rank(b))[0] ?? null;
}

// 서버 경보를 구역별 등급으로 바꾼다(서버 모드는 이것만 쓴다). 없는 구역은 정상
export function roster(alerts: readonly Alert[]): Record<Zone, Grade> {
  const statuses: Record<Zone, Grade> = {  // 처음에는 모든 구역을 정상으로 둔다
    A: { zoneId: "A", stage: "safe", etaSec: null },  // A 구역: 정상
    B: { zoneId: "B", stage: "safe", etaSec: null },  // B 구역: 정상
    C: { zoneId: "C", stage: "safe", etaSec: null },  // C 구역: 정상
  };
  for (const alert of alerts) {  // 서버 경보를 하나씩 확인
    // 같은 구역 경보가 여러 건이면 높은 단계를 남긴다(같으면 먼저 온 것)
    if (STAGE_ORDER[alert.stage] > STAGE_ORDER[statuses[alert.zone].stage]) {
      // 그 구역 등급을 경보 값으로 바꾼다. eta 가 없으면 null
      statuses[alert.zone] = { zoneId: alert.zone, stage: alert.stage, etaSec: alert.etaSec ?? null };
    }
  }
  return statuses;  // 구역별 등급을 반환
}

// mock 이 쓰는 경보 목록 만들기(서버와 같은 모양). 정상 구역은 제외
export function notices(statuses: Record<Zone, Grade>): Alert[] {
  const alerts: Alert[] = [];  // 경보를 모을 목록
  for (const id of ZONE_IDS) {  // A·B·C 순서로 구역을 확인
    const { stage, etaSec } = statuses[id];  // 그 구역의 단계와 남은 초
    if (stage !== "safe") alerts.push({ zone: id, stage, etaSec });  // 정상이 아니면 경보로 담는다
  }
  return alerts;  // 경보 목록을 반환
}

// 머리글에 보일 배너 타입을 연다
export interface Banner {
  stage: Stage;  // 배너 단계
  zoneId: Zone | null;  // 가장 위험한 구역. 모두 정상이면 null
  message: string;  // 화면에 보일 문구
}

// 배너 문구 만들기. 모델 추정 표시는 고정표가 아니라 응답의 source 를 따름
export function caption(
  statuses: Record<Zone, Grade>,  // 구역별 등급
  zones: Record<Zone, { source: Source }>,  // 구역별 데이터 출처
): Banner {  // 배너를 반환
  const worst = peak(statuses);  // 가장 위험한 구역을 선택
  if (worst.stage === "safe") {  // 모두 정상이면
    // 정상 배너를 반환
    return { stage: "safe", zoneId: null, message: "전 구역 정상 · 30초 안에 한계 도달 예상 없음" };
  }
  const zone = ZONES[worst.zoneId];  // 그 구역의 이름 정보
  const what =  // 상황 문구를 선택
    // 침수면 발생, 남은 초를 모르면 위험, 아니면 남은 초를 기록
    worst.stage === "evacuate" ? "침수 발생" : worst.etaSec === null ? "침수 위험" : `약 ${worst.etaSec}초 후 침수 예상`;
  // 모델 추정 값이면 표시를 붙임
  const estimate = zones[worst.zoneId].source === "estimated" ? " (모델 추정)" : "";
  // 구역·이름·상황 문구를 이어 배너를 반환
  return { stage: worst.stage, zoneId: worst.zoneId, message: `${worst.zoneId} ${zone.name} · ${what}${estimate}` };
}

// 카드의 도달 문구: value(남은 초)는 큰 수치로, rest 는 뒤에 이어 기록
export function phrase(status: Grade): { value: string | null; rest: string } {
  // 침수면 한계 도달이다
  if (status.stage === "evacuate") return { value: null, rest: "한계 도달" };
  // 정상이면 30초 안에 도달 예상이 없다
  if (status.stage === "safe") return { value: null, rest: "30초 안에 한계 도달 예상 없음" };
  // 서버가 남은 초를 안 보냈으면 시각을 지어내지 않음
  if (status.etaSec === null) return { value: null, rest: "한계 도달 예상 · 시각 미상" };
  // 남은 초와 뒷 문구를 나눠 반환
  return { value: `약 ${status.etaSec}초`, rest: "후 한계 도달 예상" };
}

// 게이지 채움 비율(0~1). 한계에 닿으면 가득 찬다
export function fraction(levelMm: number, thresholdMm: number): number {
  if (!(thresholdMm > 0)) return 0;  // 한계를 모르거나 0 이하면 0 이다
  return Math.min(1, Math.max(0, levelMm / thresholdMm));  // 0~1 범위로 자른다
}

// 한계 대비 %(내림). 소수 오차는 보정하고, 100 % 는 한계에 닿았을 때만 나옴
export function share(levelMm: number, thresholdMm: number): number {
  if (!(thresholdMm > 0)) return 0;  // 한계를 모르면 0 이다
  // 내림 퍼센트. 부동소수 오차(25.65/45)를 아주 작은 값으로 보결정
  const percent = Math.floor((levelMm * 100) / thresholdMm + 1e-9);
  // 한계 아래면 99 % 까지만, 닿으면 그대로 반환
  return levelMm < thresholdMm ? Math.min(percent, 99) : percent;
}

// 수위 표시 글자(0.1 mm 내림). 반올림하면 44.96 이 45.0 으로 보여 한계처럼 읽힌다
export function figure(levelMm: number, thresholdMm: number | null): string {
  let tenths = Math.floor(levelMm * 10 + 1e-9);  // 0.1 mm 단위 정수로 내린다(부동소수 오차 보정)
  // 한계 아래 값은 한계와 같은 숫자로 보이지 않게
  if (thresholdMm !== null && levelMm < thresholdMm) {
    // 한계 숫자보다 한 칸 아래로 묶는다(침수 경계와 같게)
    tenths = Math.min(tenths, Math.ceil(thresholdMm * 10 - 1e-9) - 1);
  }
  return (tenths / 10).toFixed(1);  // 소수 한 자리 글자로 반환
}

// 예측 만료 여부: (지금 - 기준 시각)이 유효 기간(초)보다 크면 만료
export function expiry(nowMs: number, basisMs: number, validForSec: number): boolean {
  return nowMs - basisMs > validForSec * 1000;  // 초를 밀리초로 맞춰 비교
}

// 연결 끊김 여부: 마지막 정상 수신 뒤 4초가 넘었거나 한 번도 못 받았으면 끊김
export function outage(nowMs: number, lastOkMs: number | null): boolean {
  // 한 번도 못 받았거나 4초가 넘으면 참이다
  return lastOkMs === null || nowMs - lastOkMs > DISCONNECT_AFTER_MS;
}

// 선행 시간(초): 실제 도달 시각 - 주의보 시각
export function lead(cautionAtMs: number | null, arrivalAtMs: number | null): number | null {
  // 둘 중 하나라도 없으면 계산하지 않음
  if (cautionAtMs === null || arrivalAtMs === null) return null;
  return (arrivalAtMs - cautionAtMs) / 1000;  // 밀리초 차이를 초로 변환
}

// 시각 표시 서식. Asia/Seoul 고정(서머타임이 없어 늘 +09:00)
const SEOUL = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Seoul",  // 시간대는 서울
  year: "numeric",  // 연도는 숫자
  month: "2-digit",  // 월은 두 자리
  day: "2-digit",  // 일은 두 자리
  hour: "2-digit",  // 시는 두 자리
  minute: "2-digit",  // 분은 두 자리
  second: "2-digit",  // 초는 두 자리
  fractionalSecondDigits: 3,  // 밀리초는 3자리
  hourCycle: "h23",  // 시는 0~23 시간제
});

// 밀리초 시각을 서울 시각의 항목별 글자로 나눈다
function fields(ms: number): Record<string, string> {
  const parts: Record<string, string> = {};  // 항목 이름별 값을 담을 객체
  // 서식이 나눈 조각을 이름(연·월·일…)으로 담는다
  for (const part of SEOUL.formatToParts(ms)) parts[part.type] = part.value;
  return parts;  // 나눈 항목을 반환
}

// 서울 시각 글자로 바꾼다(밀리초까지, 오프셋 +09:00)
export function stamp(ms: number): string {
  const p = fields(ms);  // 항목별로 나눈다
  // 연-월-일T시:분:초.밀리초+09:00 모양으로 연결
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}.${p.fractionalSecond}+09:00`;
}

// 서울 시각의 시:분:초 글자로 변환
export function clock(ms: number): string {
  const p = fields(ms);  // 항목별로 나눈다
  return `${p.hour}:${p.minute}:${p.second}`;  // 시:분:초를 이어 반환
}

// 차트 표본 타입. 옛 차트의 여백·눈금·yMax 규칙을 따르고 가로축은 시간이다
export interface Sample {
  t: number;  // 서버 timestamp(밀리초)
  A: number;  // A 구역 수위(mm)
  B: number;  // B 구역 수위(mm)
  C: number;  // C 구역 수위(mm)
}

// 수위 이력 타입. 폴링 성공마다 서버 timestamp 하나에 표본 하나를 합산
export interface History {
  run: string | null;  // 실험 번호|입력원. 바뀌면 이력을 새로 시작
  samples: readonly Sample[];  // 시간순 표본 목록
}

export const HISTORY_LIMIT = 600;  // 이력은 최대 600개까지만 남김
export const EMPTY_HISTORY: History = { run: null, samples: [] };  // 비어 있는 이력(시작값)

// 표본 더하기. 같은 timestamp 는 한 번만 넣고, 시간이 거꾸로 가면 새로 시작
export function entry(
  history: History,  // 지금까지의 이력
  snapshot: {  // 새로 받은 스냅샷
    experimentId: string;  // 실험 번호
    dataSource: Input;  // 입력원 종류
    timestamp: string;  // 서버 시각 글자
    zones: Record<Zone, { levelMm: number }>;  // 구역별 현재 수위
  },
): History {  // 새 이력을 반환
  // 실험 번호와 입력원을 합친 구분 값
  const run = `${snapshot.experimentId}|${snapshot.dataSource}`;
  const { zones } = snapshot;  // 구역별 수위를 꺼냄
  // 스냅샷에서 표본 하나를 만든다(시각은 밀리초로 바꾼다)
  const sample = { t: Date.parse(snapshot.timestamp), A: zones.A.levelMm, B: zones.B.levelMm, C: zones.C.levelMm };
  const last = history.samples.at(-1);  // 가장 최근 표본
  // 구분 값이 바뀌었거나 시간이 거꾸로 갔으면 새로 시작
  if (run !== history.run || last === undefined || sample.t < last.t) return { run, samples: [sample] };
  // 같은 시각이면 그대로 둔다(정지 중인 서버는 같은 값을 계속 보낸다)
  if (sample.t === last.t) return history;
  // 표본을 더하고 최근 600개만 남김
  return { run, samples: [...history.samples, sample].slice(-HISTORY_LIMIT) };
}

// 차트 틀 옵션 타입을 연다
export interface Frame {
  width: number;  // 그림 너비(px)
  height: number;  // 그림 높이(px)
  windowSec?: number;  // 지난 시간 범위(초). 기본 120
  gapSec?: number;  // 표본 사이가 이 초보다 벌어지면 선을 잇지 않는다. 기본 5
  pad?: { l: number; r: number; t: number; b: number };  // 여백(왼쪽·오른쪽·위·아래, px)
}

// 차트에 그릴 선과 눈금 묶음 타입을 연다
export interface Paths {
  yMax: number;  // 세로축 최대값(mm)
  measured: Record<Zone, string>;  // 구역별 실측 선 경로
  // 앞뒤가 모두 끊긴 표본. 선이 없어 점으로 그린다
  isolated: Record<Zone, { x: number; y: number }[]>;
  predicted: Record<Zone, string>;  // 구역별 예측 선 경로
  // 구역별 한계선의 세로 위치. 한계를 모르면(설정 수신 전) 그리지 않음
  thresholdY: Record<Zone, number> | null;
  gridlines: { value: number; y: number }[];  // 가로 눈금(값과 세로 위치)
  nowX: number | null;  // 현재 시각의 가로 위치. 표본이 없으면 null
  endY: Record<Zone, number> | null;  // 마지막 표본의 세로 위치(선 끝 구역 글자 자리). 없으면 null
}

// 기본 여백(px): 왼쪽 40, 오른쪽 14, 위 20, 아래 28
export const CHART_PAD = { l: 40, r: 14, t: 20, b: 28 };
const PREDICTION_SPAN_SEC = 30;  // 예측 구간은 오른쪽 30초

// 소수 둘째 자리로 반올림
const decimal = (n: number) => Math.round(n * 100) / 100;

// 표본·예측·한계로 차트 선 경로를 만듦
export function plot(
  samples: readonly Sample[],  // 수위 표본 목록
  predictions: Record<Zone, Prediction> | null,  // 구역별 예측 수위. 없으면 null
  thresholds: Thresholds | null,  // 구역별 한계 수위. 없으면 null
  options: Frame,  // 그림 크기와 범위 옵션
): Paths {  // 그릴 경로 묶음을 반환
  // 옵션을 꺼내고 빠진 값은 기본값으로 채운다
  const { width, height, windowSec = 120, gapSec = 5, pad = CHART_PAD } = options;
  const last = samples.at(-1);  // 가장 최근 표본
  const end = last?.t ?? 0;  // 가로축 끝(현재) 시각. 표본이 없으면 0
  const start = end - windowSec * 1000;  // 가로축 시작 시각
  // 범위 안에 든 표본만 남김
  const visible = last ? samples.filter((s) => s.t >= start && s.t <= end) : [];
  const ahead = last ? predictions : null;  // 표본이 있을 때만 예측을 기록

  const values = [  // 세로축 최대값을 정할 모든 값
    0,  // 0 부터 시작
    ...(thresholds ? ZONE_IDS.map((id) => thresholds[id]) : []),  // 한계 수위들
    ...visible.flatMap((s) => ZONE_IDS.map((id) => s[id])),  // 보이는 표본의 수위들
    // 예측 수위들
    ...(ahead ? ZONE_IDS.flatMap((id) => HORIZON_KEYS.map((key) => ahead[id][key])) : []),
  ];
  // 최대값보다 15 % 크게 10 단위로 올리고, 최소 20 으로
  const yMax = Math.max(20, Math.ceil((Math.max(...values) * 1.15) / 10) * 10);

  const innerW = width - pad.l - pad.r;  // 그림 안쪽 너비
  const innerH = height - pad.t - pad.b;  // 그림 안쪽 높이
  // 가로축 전체 길이(지난 구간 + 예측 30초, 밀리초)
  const spanMs = (windowSec + PREDICTION_SPAN_SEC) * 1000;
  // 시각을 가로 위치로 변환
  const x = (t: number) => decimal(pad.l + ((t - start) / spanMs) * innerW);
  // 수위를 세로 위치로 바꾼다(위가 큰 값)
  const y = (v: number) => decimal(pad.t + (1 - v / yMax) * innerH);

  // 앞 표본과 가까우면 선으로 연결
  const joined = visible.map((s, i) => i > 0 && s.t - visible[i - 1].t <= gapSec * 1000);
  // 구역의 실측 선 경로를 만듦
  const trace = (id: Zone) =>
    // 이으면 L, 끊기면 M 으로 시작해 글자 하나로 연결
    visible.map((s, i) => `${joined[i] ? "L" : "M"} ${x(s.t)} ${y(s[id])}`).join(" ");
  // 구역의 외톨이 점을 만듦
  const dots = (id: Zone) =>
    // 앞뒤가 모두 끊긴 표본만 점 위치로 변환
    visible.filter((_, i) => !joined[i] && !joined[i + 1]).map((s) => ({ x: x(s.t), y: y(s[id]) }));
  // 구역의 예측 선 경로를 만듦
  const projection = (id: Zone) => {
    if (!last || !ahead) return "";  // 표본이나 예측이 없으면 빈 경로다
    // 현재 이후 10·20·30초 지점을 선으로 연결
    const points = HORIZON_KEYS.map((key) => `L ${x(end + Number(key) * 1000)} ${y(ahead[id][key])}`);
    // 마지막 표본에서 출발해 예측 점으로 연결
    return [`M ${x(end)} ${y(last[id])}`, ...points].join(" ");
  };

  return {  // 차트에 그릴 경로 묶음을 반환
    yMax,  // 세로축 최대값
    measured: { A: trace("A"), B: trace("B"), C: trace("C") },  // 구역별 실측 선
    isolated: { A: dots("A"), B: dots("B"), C: dots("C") },  // 구역별 외톨이 점
    predicted: { A: projection("A"), B: projection("B"), C: projection("C") },  // 구역별 예측 선
    // 구역별 한계선 위치. 한계를 모르면 null
    thresholdY: thresholds ? { A: y(thresholds.A), B: y(thresholds.B), C: y(thresholds.C) } : null,
    // 0 부터 최대값까지 5등분한 가로 눈금
    gridlines: [0, 1, 2, 3, 4, 5].map((i) => ({ value: (yMax * i) / 5, y: y((yMax * i) / 5) })),
    nowX: last ? x(end) : null,  // 현재 시각 위치. 표본이 없으면 null
    // 마지막 표본의 세로 위치. 없으면 null
    endY: last ? { A: y(last.A), B: y(last.B), C: y(last.C) } : null,
  };
}

// 라벨 가로 칸 정하기(0 이 선 끝, 클수록 멀다). 세로로 height 보다 가까우면 다음 칸
export function columns(ys: Record<Zone, number>, height: number): Record<Zone, number> {
  const placed: { y: number; column: number }[] = [];  // 이미 놓은 라벨들의 세로 위치와 칸
  // 라벨 하나가 들어갈 칸을 결정
  const slot = (y: number) => {
    let column = 0;  // 0 번 칸부터 시도
    // 같은 칸에 너무 가까운 라벨이 있으면 다음 칸으로 옮긴다
    while (placed.some((p) => p.column === column && Math.abs(p.y - y) < height)) column += 1;
    placed.push({ y, column });  // 놓은 라벨로 기록
    return column;  // 정한 칸을 반환
  };
  return { A: slot(ys.A), B: slot(ys.B), C: slot(ys.C) };  // A, B, C 순서로 칸을 정해 반환
}
