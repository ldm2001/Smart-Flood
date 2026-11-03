import { z } from "zod";

const level = z.number().min(0).max(500);  // 수위(mm): 0 이상 500 이하의 숫자

const kstTime = z.iso  // 한국 시각(+09:00 오프셋이 붙은 ISO 시각)만 받는 규칙
  .datetime({ offset: true })  // 오프셋이 붙은 ISO 시각이어야 함
  .refine((value) => value.endsWith("+09:00"), { message: "시각은 +09:00(KST) 오프셋이어야 한다" });

export const zoneIdSchema = z.enum(["A", "B", "C"]);  // 구역 이름: A·B·C
export const stageSchema = z.enum(["caution", "warning", "evacuate"]);  // 경보 단계: 주의·경계·침수
export const sourceSchema = z.enum(["measured", "simulated", "estimated", "replay"]);
export const blockageTypeSchema = z.enum(["none", "partial", "full"]);  // 막힘 종류: 없음·부분·전체
export const dataSourceSchema = z.enum(["sim", "replay", "live"]);  // 입력원: 가상·재생·실측
export const runStateSchema = z.enum(["idle", "running", "stopped"]);  // 실험 상태: 대기·진행·정지
export const presetSchema = z.enum(["light", "medium", "heavy"]);  // 강우 단계: 약·보통·강

const zone = z.looseObject({  // 구역 하나의 현재 상태(추가 필드는 허용)
  levelMm: level,  // 현재 수위(mm)
  rateMmSec: z.number().min(-20).max(20),  // 수위 변화 속도(mm/s)
  source: sourceSchema,
});

const horizons = z.looseObject({ "10": level, "20": level, "30": level });

export const alertSchema = z.looseObject({
  zone: zoneIdSchema,
  stage: stageSchema,
  etaSec: z.number().int().min(0).nullable().optional(),  // 도달까지 남은 초. 없을 수 있음
});

const predictionMeta = z.looseObject({
  basisTime: kstTime,
  basisElapsedSec: z.number().min(0).max(864_000),  // 기준 시각의 경과 초(최대 10일)
  validForSec: z.number().gt(0),  // 예측이 유효한 초(0 초과)
  modelVersion: z.string(),
  assumptions: z.looseObject({
    rule: z.string(),
    rainMmPerHour: z.number().min(0),  // 가정한 강우(mm/h)
    blockage: z.record(z.string(), blockageTypeSchema),  // 가정한 막힘(위치별 종류)
  }),
});

export const stateSchema = z.looseObject({  // 상태 응답(/api/state) 전체. 추가 필드는 허용
  experimentId: z.string(),
  mode: z.enum(["live", "replay"]),
  timestamp: kstTime,
  elapsedSec: z.number().min(0).max(864_000),  // 경과 초(최대 10일)
  zones: z.looseObject({ A: zone, B: zone, C: zone }),
  predictions: z.looseObject({ A: horizons, B: horizons, C: horizons }),
  drain: z.looseObject({
    volumeL: z.number().min(0).max(10_000),  // 배수 누적량(L)
    flowLMin: z.number().min(0).max(1_000),  // 배수 유량(L/min)
  }),
  rain: z.looseObject({
    state: z.enum(["ON", "OFF"]),
    intensity: z.string(),
    mmPerHour: z.number().min(0),  // 강우량(mm/h)
  }),
  blockage: z.looseObject({
    location: z.string().nullable(),
    type: blockageTypeSchema,  // 막힘 종류
    label: z.string(),
  }),
  devices: z.looseObject({
    esp32_1: z.string(),
    esp32_2: z.string(),
    floatSwitch: z.string(),
    emergencyStop: z.string(),
  }),
  quality: z.enum(["valid", "degraded", "invalid"]),
  outputsLocked: z.literal(true),
  dataSource: dataSourceSchema,
  alerts: z.array(alertSchema),
  runState: runStateSchema.nullable().optional(),
  predictionMeta: predictionMeta.nullable().optional(),
  notifier: z  // 문자 알림 방식과 무장 여부. 없는 서버도 있음
    .looseObject({ mode: z.enum(["stub", "sms"]), armed: z.boolean() })
    .optional(),
});

// 사건 단계(정상·주의·경계·침수). 경보 단계와 달리 정상을 담음
export const eventStageSchema = z.enum(["safe", "caution", "warning", "evacuate"]);
const eventBase = {  // 두 사건 꼴의 공통 칸
  type: z.literal("event"),
  elapsedSec: z.number().min(0).max(864_000),
  time: kstTime,
  message: z.string(),
};
export const eventSchema = z.discriminatedUnion("kind", [  // 기록의 사건 한 줄. 모르는 칸은 남김
  z.looseObject({ ...eventBase, kind: z.literal("calc_error") }),
  z.looseObject({
    ...eventBase,
    kind: z.literal("stage"),
    zone: zoneIdSchema,
    stage: eventStageSchema,
    previous: eventStageSchema,
    etaSec: z.number().int().min(0).nullable(),  // 올림한 정수 초. 침수면 0, 안 오르면 null
  }),
]);
export const eventsSchema = z.looseObject({ events: z.array(eventSchema) });  // 사건 응답

export const logSchema = z.looseObject({  // 실험 기록 목록의 한 줄. 모르는 칸은 남김
  experimentId: z.string().regex(/^EXP-[0-9]{8}-[0-9]{3,}$/),  // 백엔드 실험 번호 꼴
  startTime: kstTime,
  dataSource: dataSourceSchema,
  modelVersion: z.string(),
  configHash: z.string(),
});
export const logsSchema = z.looseObject({ logs: z.array(logSchema) });  // 기록 목록 응답

// 서버 상태 타입
export type Snapshot = z.infer<typeof stateSchema>;
// 구역 이름 타입
export type Zone = z.infer<typeof zoneIdSchema>;
// 경보 단계 타입
export type Danger = z.infer<typeof stageSchema>;
// 값 출처 타입
export type Source = z.infer<typeof sourceSchema>;
// 막힘 종류 타입
export type Blockage = z.infer<typeof blockageTypeSchema>;
// 입력원 타입
export type Input = z.infer<typeof dataSourceSchema>;
// 실험 상태 타입
export type Run = z.infer<typeof runStateSchema>;
// 경보 타입
export type Alert = z.infer<typeof alertSchema>;
// 시점별 예측 타입
export type Horizons = z.infer<typeof horizons>;
// 기록 사건 타입
export type LogEvent = z.infer<typeof eventSchema>;
// 단계 전환 사건 타입
export type StageEvent = Extract<LogEvent, { kind: "stage" }>;
// 실험 기록 목록의 한 줄 타입
export type Log = z.infer<typeof logSchema>;
// 문자 알림 상태 타입
export type Notifier = NonNullable<Snapshot["notifier"]>;
// 강우 단계 타입
export type Preset = z.infer<typeof presetSchema>;
// 설정의 강우 단계값과 상한
export interface Rainfall {
  presets: Record<Preset, number>;  // 단계마다 mm/h
  maxMmPerHour: number;  // 직접 입력 상한(mm/h)
}
// 제어 요청. 본문은 백엔드 요청 모델(extra forbid)과 같은 모양
export type Command =
  | { control: "start" | "stop" | "reset"; body: Record<string, never> }
  | { control: "rain"; body: { intensity: Preset } | { mmPerHour: number } }
  | { control: "blockage"; body: { type: "none" } | { type: "partial" | "full"; location: string } }
  | { control: "sim"; body: { mode: "sim" } }
  | { control: "live"; body: { mode: "live" } }
  | { control: "replay"; body: { mode: "replay"; logId: string } };
// 제어 이름 타입
export type Control = Command["control"];

// 응답을 검사. 어긋나면 던지고 호출한 쪽(폴링)이 연결 오류로 처리
export function contract(body: unknown): Snapshot {
  return stateSchema.parse(body);
}

// 사건 응답을 검사해 사건 목록만 돌려줌
export function chronicle(body: unknown): LogEvent[] {
  return eventsSchema.parse(body).events;
}

// 기록 목록 응답을 검사해 목록만 돌려줌
export function catalog(body: unknown): Log[] {
  return logsSchema.parse(body).logs;
}

const thresholdMm = z.number().gt(0).max(500);  // 한계 수위(mm): 0 초과 500 이하
const zoneConfig = z.looseObject({ threshold_mm: thresholdMm });  // 구역 설정에서 한계 수위만 검사

export const configThresholdsSchema = z.looseObject({  // 설정 응답 중 구역 한계 수위 부분만 검사
  zones: z.looseObject({ A: zoneConfig, B: zoneConfig, C: zoneConfig }),
});

// 설정 응답을 검사해 구역별 한계 수위를 뽑음. 어긋나면 던짐
export function ceilings(body: unknown): Record<Zone, number> {
  const { zones } = configThresholdsSchema.parse(body);
  return { A: zones.A.threshold_mm, B: zones.B.threshold_mm, C: zones.C.threshold_mm };
}

const presetMm = z.number().min(0);  // 강우 단계값(mm/h): 0 이상
const rainfallSchema = z  // 설정의 강우 단계값(mm/h)과 직접 입력 상한. 모르는 칸은 남김
  .looseObject({
    rain_presets_mm_per_h: z.looseObject({ light: presetMm, medium: presetMm, heavy: presetMm }),
    rain_max_mm_per_h: z.number().gt(0),
  })
  // 아는 세 단계만 상한과 견줌. 모르는 단계 키는 보지 않음
  .refine(({ rain_presets_mm_per_h: p, rain_max_mm_per_h: max }) =>
    [p.light, p.medium, p.heavy].every((value) => value <= max),
  );
const detailSchema = z.looseObject({ detail: z.string().min(1) });  // 409·503 의 이유 글
const issuesSchema = z.looseObject({  // 422 의 검사 항목 목록
  detail: z.array(z.looseObject({ msg: z.string().min(1), type: z.string().optional() })).min(1),
});

// 설정의 강우 단계값과 상한을 꺼냄. 모양이 틀리면 null
export function rainfall(body: unknown): Rainfall | null {
  const parsed = rainfallSchema.safeParse(body);
  if (!parsed.success) return null;
  const { light, medium, heavy } = parsed.data.rain_presets_mm_per_h;  // 아는 세 단계만 꺼냄
  return { presets: { light, medium, heavy }, maxMmPerHour: parsed.data.rain_max_mm_per_h };
}

// 오류 응답의 이유 글. detail 글, 아니면 value_error 인 첫 msg, 둘 다 없으면 null
export function cause(body: unknown): string | null {
  const plain = detailSchema.safeParse(body);
  if (plain.success) return plain.data.detail;
  const issues = issuesSchema.safeParse(body);
  const first = issues.success ? issues.data.detail[0] : null;  // 422 의 첫 항목
  return first?.type === "value_error" ? first.msg : null;  // 영어 검증 글은 쓰지 않음
}
