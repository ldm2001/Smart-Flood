import { notices, verdicts, stamp, type Prediction, type Sample, type Thresholds } from "./derive";
import type { Snapshot, Zone, Source } from "./schema";

export const MOCK_CYCLE_SEC = 180;  // 가짜 데이터 반복 주기(초). 같은 초면 같은 값이다

const RAIN_FACTOR = 0.7;  // 보통 강우 계수(옛 RAIN.medium 값)
const DRAIN_FACTOR = 0.45;  // 부분 막힘 배수 계수(옛 BLOCKAGE.partial 값)
const DRAIN_FLOW_L_MIN = 0.65;  // 부분 막힘 배수 유량 L/min(옛 BLOCKAGE.partial.drainFlow 값)
const START_MM: Record<Zone, number> = { A: 12, B: 8, C: 4 };  // 구역별 시작 수위(mm)
const MAX_MM = 150;  // 수위 상한(mm)

// 음수는 0 으로 올리고 소수 둘째 자리로 맞춤
const amount = (value: number) => Number(Math.max(0, value).toFixed(2));

const RATES: Record<Zone, number> = {  // 구역별 수위 상승 속도(mm/s). 옛 계산식과 같다
  A: amount(0.82 * RAIN_FACTOR - 0.24 * DRAIN_FACTOR),  // A 구역: 강우 유입에서 배수를 뺀 값
  B: amount(0.62 * RAIN_FACTOR - 0.2 * DRAIN_FACTOR),  // B 구역: 같은 식
  C: amount(0.38 * RAIN_FACTOR - 0.13 * DRAIN_FACTOR),  // C 구역: 같은 식
};

// 구역별 출처. C 는 센서가 없어 추정이다
const SOURCES: Record<Zone, Source> = { A: "simulated", B: "simulated", C: "estimated" };

// e 초째 수위. 속도가 일정해 옛 1초 단계 계산과 같다
const level = (id: Zone, e: number) => amount(Math.min(MAX_MM, START_MM[id] + RATES[id] * e));

// 현재 수위에서 +10·20·30초 예측을 만듦
const forecast = (id: Zone, levelMm: number): Prediction => ({
  "10": amount(levelMm + RATES[id] * 10),  // +10초 예측
  "20": amount(levelMm + RATES[id] * 20),  // +20초 예측
  "30": amount(levelMm + RATES[id] * 30),  // +30초 예측
});

// 시각만으로 정해지는 가짜 서버 상태를 만듦
export function demo(nowMs: number, thresholds: Thresholds): Snapshot {
  const epochSec = Math.floor(nowMs / 1000);  // 초 단위 시각
  const e = epochSec % MOCK_CYCLE_SEC;  // 주기 안에서 흐른 초
  const cycle = Math.floor(epochSec / MOCK_CYCLE_SEC);  // 몇 번째 주기인지
  const timestamp = stamp(epochSec * 1000);  // 한국 시각 글자로 바꾼 기준 시각

  // 구역 하나의 수위·속도·출처
  const zone = (id: Zone) => ({ levelMm: level(id, e), rateMmSec: RATES[id], source: SOURCES[id] });
  const zones = { A: zone("A"), B: zone("B"), C: zone("C") };  // 세 구역을 모음
  const predictions = {  // 구역별 예측을 모음
    A: forecast("A", zones.A.levelMm),  // A 구역 예측
    B: forecast("B", zones.B.levelMm),  // B 구역 예측
    C: forecast("C", zones.C.levelMm),  // C 구역 예측
  };

  return {  // 서버 응답과 같은 모양으로 반환
    // 가짜 실험 번호(주기마다 바뀐다)
    experimentId: `EXP-DEMO-${String(cycle % 1000).padStart(3, "0")}`,
    mode: "live",  // 실험 모드
    timestamp,  // 기준 시각
    elapsedSec: e,  // 주기 안에서 흐른 초
    zones,  // 구역별 현재 상태
    predictions,  // 구역별 예측
    // 배수 누적량(L)과 유량(L/min)
    drain: { volumeL: amount((DRAIN_FLOW_L_MIN * e) / 60), flowLMin: DRAIN_FLOW_L_MIN },
    rain: { state: "ON", intensity: "보통 강우", mmPerHour: 60 },  // 보통 강우 상태
    // 빗물받이 ② 부분 막힘
    blockage: { location: "INLET-02", type: "partial", label: "빗물받이 ② 부분 막힘" },
    // 장치는 모두 정상
    devices: { esp32_1: "online", esp32_2: "online", floatSwitch: "normal", emergencyStop: "normal" },
    quality: "valid",  // 자료 품질
    outputsLocked: true,  // 출력은 늘 잠금(표시만)
    dataSource: "sim",  // 입력원은 시뮬레이션
    // 경보는 계산 도구와 같은 규칙으로 만듦
    alerts: notices(verdicts({ zones, predictions }, thresholds)),
    runState: "running",  // 실험 진행 중
    predictionMeta: {  // 예측 기준 정보
      basisTime: timestamp,  // 예측 기준 시각
      basisElapsedSec: e,  // 예측 기준 경과 초
      validForSec: 5,  // 예측이 유효한 초
      modelVersion: "mock-legacy-sim",  // 모델 이름(가짜 표시)
      assumptions: {  // 예측 가정
        rule: "현재 강우와 막힘이 예측 구간 동안 유지된다",  // 가정 문구
        rainMmPerHour: 60,  // 가정한 강우(mm/h)
        blockage: { "INLET-02": "partial" },  // 가정한 막힘
      },
    },
  };
}

// 주기 시작(0초)부터 지금까지 1초 간격 수위 이력. 서버가 없을 때 차트가 기록
export function trail(nowMs: number): Sample[] {
  const epochSec = Math.floor(nowMs / 1000);  // 초 단위 시각
  const startSec = epochSec - (epochSec % MOCK_CYCLE_SEC);  // 이번 주기가 시작한 초
  // 시작부터 지금까지 1초마다 표본을 만듦
  return Array.from({ length: epochSec - startSec + 1 }, (_, e) => ({
    t: (startSec + e) * 1000,  // 표본 시각(ms)
    A: level("A", e),  // A 수위
    B: level("B", e),  // B 수위
    C: level("C", e),  // C 수위
  }));
}
