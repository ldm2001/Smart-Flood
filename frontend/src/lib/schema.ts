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

const zone = z.looseObject({  // 구역 하나의 현재 상태(추가 필드는 허용)
  levelMm: level,  // 현재 수위(mm)
  rateMmSec: z.number().min(-20).max(20),  // 수위 변화 속도(mm/s)
  source: sourceSchema,
});

const horizons = z.looseObject({ "10": level, "20": level, "30": level });

export const alertSchema = z.looseObject({
  zone: zoneIdSchema,
  stage: stageSchema,
  etaSec: z.number().min(0).nullable().optional(),  // 도달까지 남은 초. 없을 수 있음
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
    // 막힘 종류
    type: blockageTypeSchema,
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
});

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

// 응답을 검사. 어긋나면 던지고 호출한 쪽(폴링)이 연결 오류로 처리
export function contract(body: unknown): Snapshot {
  return stateSchema.parse(body);
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
