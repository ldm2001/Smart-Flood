import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { ZodError } from "zod";
import { ceilings, contract, stateSchema } from "./schema";

// 계약 문서 'GET /api/state' 아래 첫 json 블록(응답 예시)을 읽는 도우미
function example(): Record<string, unknown> {
  // 계약 문서를 글자로 읽음
  const md = readFileSync(new URL("../../../docs/api-contract.md", import.meta.url), "utf8");
  const section = md.slice(md.indexOf("## GET /api/state"));  // 상태 항목 제목부터 끝까지 자른다
  const match = section.match(/```json\n([\s\S]*?)\n```/);  // 첫 json 코드 블록을 찾음
  // 블록이 없으면 오류를 냄
  if (!match) throw new Error("api-contract.md 에서 예시 json 블록을 찾지 못했다");
  return JSON.parse(match[1]);  // 블록 안의 글을 객체로 바꿔 반환
}

// 백엔드 지시서 4.1 응답 예시(원문). runState·predictionMeta 와 밀리초가 없다
const BRIEF_EXAMPLE = {
  experimentId: "EXP-20261022-001",  // 실험 번호
  mode: "live",  // 모드는 live
  timestamp: "2026-10-22T10:00:00+09:00",  // 서울 시각 문자열(밀리초 없음)
  elapsedSec: 42,  // 경과 시간 42초
  zones: {  // 구역별 수위 묶음
    A: { levelMm: 31.2, rateMmSec: 0.24, source: "simulated" },  // A 구역: 수위·증가량·가상 실측
    B: { levelMm: 22.7, rateMmSec: 0.16, source: "simulated" },  // B 구역: 수위·증가량·가상 실측
    C: { levelMm: 15.4, rateMmSec: 0.1, source: "estimated" },  // C 구역: 수위·증가량·모델 추정
  },
  predictions: {  // 구역별 10·20·30초 예측 수위
    A: { "10": 33.6, "20": 36.0, "30": 38.4 },  // A 구역 예측
    B: { "10": 24.3, "20": 25.9, "30": 27.5 },  // B 구역 예측
    C: { "10": 16.4, "20": 17.4, "30": 18.4 },  // C 구역 예측
  },
  drain: { volumeL: 1.84, flowLMin: 1.12 },  // 배수량(L)과 유량(L/min)
  rain: { state: "ON", intensity: "보통 강우", mmPerHour: 60 },  // 강우 상태·세기·시간당 mm
  // 막힘 위치·종류·이름
  blockage: { location: "INLET-02", type: "partial", label: "빗물받이 ② 부분 막힘" },
  // 장치 상태 묶음
  devices: { esp32_1: "online", esp32_2: "online", floatSwitch: "normal", emergencyStop: "normal" },
  quality: "valid",  // 자료 품질은 정상
  outputsLocked: true,  // 출력은 늘 잠김
  dataSource: "sim",  // 입력원은 sim
  alerts: [{ zone: "A", stage: "caution", etaSec: 20 }],  // 경보 목록: A 구역 주의 20초
};

// 무엇이든 담는 JSON 객체 타입(테스트용)
type Json = Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any

// 예시를 복사해 고친 사본을 만드는 도우미
function variant(mutate: (body: Json) => void): Json {
  const body = structuredClone(BRIEF_EXAMPLE) as Json;  // 예시를 깊이 복사
  mutate(body);  // 받은 함수로 사본을 고친다
  return body;  // 고친 사본을 반환
}

describe("stateSchema", () => {  // 상태 검사 틀 테스트 묶음
  it("accepts the docs/api-contract.md example", () => {  // 계약 문서 예시를 받아들이는지 검사
    const result = stateSchema.safeParse(example());  // 문서 예시를 검사 틀로 확인
    expect(result.error?.issues).toBeUndefined();  // 문제 목록이 없어야 함
    expect(result.success).toBe(true);  // 통과필요
  });

  it("accepts the backend brief 4.1 example", () => {  // 백엔드 지시서 4.1 예시를 받아들이는지 검사
    const result = stateSchema.safeParse(BRIEF_EXAMPLE);  // 지시서 예시를 검사 틀로 확인
    expect(result.error?.issues).toBeUndefined();  // 문제 목록이 없어야 함
    expect(result.success).toBe(true);  // 통과필요
  });

  // 수위 501 은 거부하고 0·500 경계는 받는지 검사
  it("rejects levelMm 501 and accepts the 0 and 500 edges", () => {
    // 501 mm 는 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.zones.A.levelMm = 501))).success).toBe(false);
    // 500 mm 는 받아야 함
    expect(stateSchema.safeParse(variant((b) => (b.zones.A.levelMm = 500))).success).toBe(true);
    // 0 mm 는 받아야 함
    expect(stateSchema.safeParse(variant((b) => (b.zones.A.levelMm = 0))).success).toBe(true);
    // 음수 수위는 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.zones.A.levelMm = -0.1))).success).toBe(false);
  });

  it("rejects a missing prediction key", () => {  // 예측 시점이 빠진 응답을 거부하는지 검사
    // B 구역 30초 예측이 없으면 거부필요
    expect(stateSchema.safeParse(variant((b) => delete b.predictions.B["30"])).success).toBe(false);
    // C 구역 예측이 통째로 없으면 거부필요
    expect(stateSchema.safeParse(variant((b) => delete b.predictions.C)).success).toBe(false);
  });

  // 범위를 벗어난 증가량·예측을 거부하는지 검사
  it("rejects out-of-range rate and prediction", () => {
    // 증가량 20.5 는 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.zones.B.rateMmSec = 20.5))).success).toBe(false);
    // 증가량 -20 은 받아야 한다(음수 허용)
    expect(stateSchema.safeParse(variant((b) => (b.zones.B.rateMmSec = -20))).success).toBe(true);
    // 예측 500.1 mm 는 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.predictions.A["10"] = 500.1))).success).toBe(false);
  });

  it("rejects numbers sent as strings", () => {  // 숫자를 글자로 보낸 응답을 거부하는지 검사
    // 글자로 된 수위는 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.zones.A.levelMm = "31.2"))).success).toBe(false);
  });

  // 서울 시각(+09:00)이 아닌 시각을 거부하는지 검사
  it("rejects a timestamp that is not +09:00", () => {
    // UTC(Z) 표기는 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.timestamp = "2026-10-22T01:00:00Z"))).success).toBe(false);
    // 오프셋이 없으면 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.timestamp = "2026-10-22T10:00:00"))).success).toBe(false);
    // 밀리초가 붙은 서울 시각은 받아야 함
    expect(stateSchema.safeParse(variant((b) => (b.timestamp = "2026-10-22T10:00:00.000+09:00"))).success).toBe(true);
  });

  it("rejects values outside the enums", () => {  // 허용 목록 밖의 값을 거부하는지 검사
    // 출처에 화면 글자를 넣으면 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.zones.A.source = "가상 실측"))).success).toBe(false);
    // 품질이 ok 면 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.quality = "ok"))).success).toBe(false);
    // 모드가 demo 면 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.mode = "demo"))).success).toBe(false);
    // 경보 단계가 danger 면 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.alerts[0].stage = "danger"))).success).toBe(false);
  });

  it("rejects outputsLocked false", () => {  // 출력 잠금이 풀린 응답을 거부하는지 검사
    // 잠금이 false 면 거부필요
    expect(stateSchema.safeParse(variant((b) => (b.outputsLocked = false))).success).toBe(false);
  });

  it("keeps extra fields", () => {  // 모르는 필드를 지우지 않는지 검사
    const body = variant((b) => {  // 새 필드를 둘 심은 사본을 만듦
      b.futureField = 1;  // 최상위에 새 필드를 넣음
      b.zones.A.note = "x";  // A 구역 안에도 새 필드를 넣음
    });
    const parsed = contract(body);  // 계약 검사를 통과시킨다
    expect(parsed.futureField).toBe(1);  // 최상위 새 필드가 남아야 함
    expect(parsed.zones.A.note).toBe("x");  // A 구역 새 필드가 남아야 함
  });

  // 잘못된 본문이면 계약 검사가 오류를 내는지 검사
  it("contract throws on an invalid body", () => {
    // 수위 501 본문은 오류를 내야 함
    expect(() => contract(variant((b) => (b.zones.A.levelMm = 501)))).toThrow();
  });
});

const CONFIG = {  // 설정 응답 예시. 서버는 config.yaml 전체를 주고 화면은 구역 한계만 기록
  model_version: "0.1-assumed",  // 모델 버전(가정값)
  zones: {  // 구역별 계수와 한계
    A: { S_m2: 0.1, z_m: 0, share: 0.4, threshold_mm: 45 },  // A 구역: 한계 45 mm
    B: { S_m2: 0.1, z_m: 0.02, share: 0.35, threshold_mm: 55 },  // B 구역: 한계 55 mm
    C: { S_m2: 0.08, z_m: 0.06, share: 0.25, threshold_mm: 65 },  // C 구역: 한계 65 mm
  },
  alerts: { release_ratio: 0.9, release_hold_s: 10 },  // 경보 해제 비율과 유지 시간
};

// 설정 예시를 복사해 고친 사본을 만드는 도우미
function version(mutate: (body: Json) => void): Json {
  const body = structuredClone(CONFIG) as Json;  // 설정 예시를 깊이 복사
  mutate(body);  // 받은 함수로 사본을 고친다
  return body;  // 고친 사본을 반환
}

describe("ceilings", () => {  // 한계 읽기 테스트 묶음
  // 서버 설정에서 구역 한계를 읽는지 검사
  it("reads the zone thresholds from the server config", () => {
    expect(ceilings(CONFIG)).toEqual({ A: 45, B: 55, C: 65 });  // 구역별 한계가 45·55·65 여야 함
  });

  // 쓸 수 있는 한계가 없는 설정을 거부하는지 검사
  it("rejects a config without usable thresholds", () => {
    // C 구역이 없으면 검사 오류여야 함
    expect(() => ceilings(version((b) => delete b.zones.C))).toThrow(ZodError);
    // A 한계가 없으면 검사 오류여야 함
    expect(() => ceilings(version((b) => delete b.zones.A.threshold_mm))).toThrow(ZodError);
    // 한계가 글자면 검사 오류여야 함
    expect(() => ceilings(version((b) => (b.zones.B.threshold_mm = "55")))).toThrow(ZodError);
    // 한계가 0 이면 검사 오류여야 함
    expect(() => ceilings(version((b) => (b.zones.B.threshold_mm = 0)))).toThrow(ZodError);
    // 한계가 500 을 넘으면 검사 오류여야 함
    expect(() => ceilings(version((b) => (b.zones.B.threshold_mm = 500.1)))).toThrow(ZodError);
    expect(() => ceilings(null)).toThrow(ZodError);  // 설정이 null 이면 검사 오류여야 함
  });
});
