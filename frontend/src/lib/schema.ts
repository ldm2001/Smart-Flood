import { z } from "zod";

// 수위(mm): 0 이상 500 이하의 숫자. 문자열·NaN·무한대는 받지 않음
const level = z.number().min(0).max(500);

const kstTime = z.iso  // 한국 시각(+09:00 오프셋이 붙은 ISO 시각)만 받는 규칙
  .datetime({ offset: true })  // 오프셋이 붙은 ISO 시각이어야 함
  // 오프셋이 +09:00 이 아니면 거절
  .refine((value) => value.endsWith("+09:00"), { message: "시각은 +09:00(KST) 오프셋이어야 한다" });

export const zoneIdSchema = z.enum(["A", "B", "C"]);  // 구역 이름: A·B·C
export const stageSchema = z.enum(["caution", "warning", "evacuate"]);  // 경보 단계: 주의·경계·침수
// 값의 출처 네 가지
export const sourceSchema = z.enum(["measured", "simulated", "estimated", "replay"]);
export const blockageTypeSchema = z.enum(["none", "partial", "full"]);  // 막힘 종류: 없음·부분·전체
export const dataSourceSchema = z.enum(["sim", "replay", "live"]);  // 입력원: 가상·재생·실측
export const runStateSchema = z.enum(["idle", "running", "stopped"]);  // 실험 상태: 대기·진행·정지

const zone = z.looseObject({  // 구역 하나의 현재 상태(추가 필드는 허용)
  levelMm: level,  // 현재 수위(mm)
  rateMmSec: z.number().min(-20).max(20),  // 수위 변화 속도(mm/s)
  source: sourceSchema,  // 값의 출처
});

const horizons = z.looseObject({ "10": level, "20": level, "30": level });  // +10·20·30초 예측 수위

export const alertSchema = z.looseObject({  // 경보 하나
  zone: zoneIdSchema,  // 경보가 난 구역
  stage: stageSchema,  // 경보 단계
  etaSec: z.number().min(0).nullable().optional(),  // 도달까지 남은 초. 없을 수 있다
});

const predictionMeta = z.looseObject({  // 예측 기준 정보
  basisTime: kstTime,  // 예측 기준 시각
  basisElapsedSec: z.number().min(0).max(864_000),  // 기준 시각의 경과 초(최대 10일)
  validForSec: z.number().gt(0),  // 예측이 유효한 초(0 초과)
  modelVersion: z.string(),  // 모델 이름
  assumptions: z.looseObject({  // 예측 가정
    rule: z.string(),  // 가정 문구
    rainMmPerHour: z.number().min(0),  // 가정한 강우(mm/h)
    blockage: z.record(z.string(), blockageTypeSchema),  // 가정한 막힘(위치별 종류)
  }),
});

export const stateSchema = z.looseObject({  // 상태 응답(/api/state) 전체. 추가 필드는 허용
  experimentId: z.string(),  // 실험 번호
  mode: z.enum(["live", "replay"]),  // 실험 모드
  timestamp: kstTime,  // 기준 시각
  elapsedSec: z.number().min(0).max(864_000),  // 경과 초(최대 10일)
  zones: z.looseObject({ A: zone, B: zone, C: zone }),  // 구역별 현재 상태
  predictions: z.looseObject({ A: horizons, B: horizons, C: horizons }),  // 구역별 예측
  drain: z.looseObject({  // 배수 상태
    volumeL: z.number().min(0).max(10_000),  // 배수 누적량(L)
    flowLMin: z.number().min(0).max(1_000),  // 배수 유량(L/min)
  }),
  rain: z.looseObject({  // 강우 상태
    state: z.enum(["ON", "OFF"]),  // 강우 켜짐·꺼짐
    intensity: z.string(),  // 강우 세기 이름
    mmPerHour: z.number().min(0),  // 강우량(mm/h)
  }),
  blockage: z.looseObject({  // 막힘 상태
    location: z.string().nullable(),  // 막힌 위치. 없으면 null
    // 막힘 종류
    type: blockageTypeSchema,
    label: z.string(),  // 막힘 이름표
  }),
  devices: z.looseObject({  // 장치 상태
    esp32_1: z.string(),  // 첫째 보드 상태
    esp32_2: z.string(),  // 둘째 보드 상태
    floatSwitch: z.string(),  // 부표 스위치 상태
    emergencyStop: z.string(),  // 비상 정지 상태
  }),
  quality: z.enum(["valid", "degraded", "invalid"]),  // 자료 품질
  outputsLocked: z.literal(true),  // 출력 잠금. 늘 true 여야 함
  dataSource: dataSourceSchema,  // 입력원
  alerts: z.array(alertSchema),  // 경보 목록
  runState: runStateSchema.nullable().optional(),  // 실험 진행 상태. 없을 수 있다
  predictionMeta: predictionMeta.nullable().optional(),  // 예측 기준 정보. 없을 수 있다
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

// 응답을 검사한다. 어긋나면 던지고 호출한 쪽(폴링)이 연결 오류로 처리
export function contract(body: unknown): Snapshot {
  return stateSchema.parse(body);  // 통과한 값을 반환
}

// 한계 수위(mm): 0 초과 500 이하. 화면 설정과 같은 범위다
const thresholdMm = z.number().gt(0).max(500);
const zoneConfig = z.looseObject({ threshold_mm: thresholdMm });  // 구역 설정에서 한계 수위만 검사

export const configThresholdsSchema = z.looseObject({  // 설정 응답 중 구역 한계 수위 부분만 검사
  zones: z.looseObject({ A: zoneConfig, B: zoneConfig, C: zoneConfig }),  // 구역별 설정
});

// 설정 응답을 검사해 구역별 한계 수위를 뽑는다. 어긋나면 던진다
export function ceilings(body: unknown): Record<Zone, number> {
  const { zones } = configThresholdsSchema.parse(body);  // 검사를 통과한 구역 설정
  // 구역별 한계 수위만 반환
  return { A: zones.A.threshold_mm, B: zones.B.threshold_mm, C: zones.C.threshold_mm };
}
