import { describe, expect, it } from "vitest";
import { MOCK_CYCLE_SEC, trail, demo } from "./mock";
import { stateSchema, type Snapshot, type Zone } from "./schema";

const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
// 기준 시각(2026-10-23 01:00 UTC). 에포크 초가 180 의 배수라 주기 0초
const BASE = Date.UTC(2026, 9, 23, 1, 0, 0);
// 주기 e 초 지점의 예시 응답을 만드는 도우미
const frame = (e: number) => demo(BASE + e * 1000, THRESHOLDS);
// 스냅샷에서 한 구역의 경보를 찾는 도우미
const notice = (snapshot: Snapshot, zone: Zone) => snapshot.alerts.find((alert) => alert.zone === zone);

// 옛 시뮬레이션을 그대로 옮긴 비교 기준(보통 강우, 부분 막힘)
function legacy(seconds: number) {
  // 0 아래는 0 으로, 소수 둘째 자리까지 맞춤
  const amount = (value: number) => Number(Math.max(0, value).toFixed(2));
  const rain = 0.7;  // 보통 강우 세기
  const drain = 0.45;  // 부분 막힘일 때 배수 세기
  const rates = {  // 구역별 초당 증가량(mm)
    A: amount(0.82 * rain - 0.24 * drain),  // A 구역 증가량
    B: amount(0.62 * rain - 0.2 * drain),  // B 구역 증가량
    C: amount(0.38 * rain - 0.13 * drain),  // C 구역 증가량
  };
  let zones = { A: 12, B: 8, C: 4 };  // 시작 수위(mm)
  for (let i = 0; i < seconds; i += 1) {  // 초 수만큼 한 초씩 올림
    zones = {  // 새 수위를 만듦
      A: amount(Math.min(150, zones.A + rates.A)),  // A: 증가량을 더하고 150 에서 멈춘다
      B: amount(Math.min(150, zones.B + rates.B)),  // B: 증가량을 더하고 150 에서 멈춘다
      C: amount(Math.min(150, zones.C + rates.C)),  // C: 증가량을 더하고 150 에서 멈춘다
    };
  }
  return { zones, rates };  // 수위와 증가량을 반환
}

describe("demo", () => {  // 예시 응답 테스트 묶음
  // 주기의 모든 초에서 상태 검사 틀을 통과하는지 검사
  it("passes the /api/state schema at every second of the cycle", () => {
    for (let e = 0; e < MOCK_CYCLE_SEC; e += 1) {  // 주기의 모든 초를 확인
      const result = stateSchema.safeParse(frame(e));  // 그 초의 응답을 검사 틀로 확인
      expect(result.error?.issues, `e=${e}`).toBeUndefined();  // 검사 오류가 없어야 함
    }
  });

  it("matches the legacy step-by-step simulation", () => {  // 옛 시뮬레이션과 초마다 같은지 검사
    for (let e = 0; e < MOCK_CYCLE_SEC; e += 1) {  // 주기의 모든 초를 확인
      const { zones, rates } = legacy(e);  // 비교 기준의 수위와 증가량
      const snapshot = frame(e);  // 예시 응답
      for (const id of ["A", "B", "C"] as const) {  // 세 구역을 확인
        expect(snapshot.zones[id].levelMm, `${id} e=${e}`).toBe(zones[id]);  // 수위가 같아야 함
        expect(snapshot.zones[id].rateMmSec).toBe(rates[id]);  // 초당 증가량이 같아야 함
        // 30초 뒤 예측은 수위 더하기 증가량 곱하기 30 이어야 함
        expect(snapshot.predictions[id]["30"]).toBe(Number((zones[id] + rates[id] * 30).toFixed(2)));
      }
    }
  });

  it("depends only on the whole second", () => {  // 정수 초에만 달라지는지 검사
    expect(demo(BASE + 42_999, THRESHOLDS)).toEqual(frame(42));  // 42.999초는 42초와 같아야 함
    expect(frame(42)).toEqual(frame(42));  // 같은 시각을 두 번 만들어도 같아야 함
  });

  it("starts from the legacy levels", () => {  // 옛 시작 수위에서 출발하는지 검사
    const first = frame(0);  // 주기 시작 응답
    expect(first.elapsedSec).toBe(0);  // 경과 시간은 0초여야 함
    // 수위는 12·8·4 mm 여야 함
    expect([first.zones.A.levelMm, first.zones.B.levelMm, first.zones.C.levelMm]).toEqual([12, 8, 4]);
    // A·B 초당 증가량은 0.47·0.34 여야 함
    expect([first.zones.A.rateMmSec, first.zones.B.rateMmSec]).toEqual([0.47, 0.34]);
    // 배수는 0 L, 유량 0.65 L/min 이어야 함
    expect(first.drain).toEqual({ volumeL: 0, flowLMin: 0.65 });
    expect(frame(60).drain.volumeL).toBe(0.65);  // 60초 뒤 배수량은 0.65 L 여야 함
  });

  it("walks zone A through every stage", () => {  // A 구역이 모든 단계를 차례로 지나는지 검사
    expect(notice(frame(40), "A")).toBeUndefined();  // 40초에는 경보가 없어야 함
    // 41초에 주의 30초가 시작돼야 함
    expect(notice(frame(41), "A")).toEqual({ zone: "A", stage: "caution", etaSec: 30 });
    // 50초까지 주의 30초가 이어져야 함
    expect(notice(frame(50), "A")).toEqual({ zone: "A", stage: "caution", etaSec: 30 });
    // 51초에 주의 20초가 돼야 함
    expect(notice(frame(51), "A")).toEqual({ zone: "A", stage: "caution", etaSec: 20 });
    // 61초에 경고 10초가 돼야 함
    expect(notice(frame(61), "A")).toEqual({ zone: "A", stage: "warning", etaSec: 10 });
    expect(frame(70).zones.A.levelMm).toBe(44.9);  // 70초 수위는 44.9 mm(한계 바로 아래)여야 함
    // 그래도 경고 10초여야 함
    expect(notice(frame(70), "A")).toEqual({ zone: "A", stage: "warning", etaSec: 10 });
    expect(frame(71).zones.A.levelMm).toBe(45.37);  // 71초 수위는 45.37 mm(한계 넘음)여야 함
    // 침수 0초가 돼야 함
    expect(notice(frame(71), "A")).toEqual({ zone: "A", stage: "evacuate", etaSec: 0 });
  });

  // B 구역이 더 늦게 모든 단계를 지나는지 검사
  it("walks zone B through every stage later", () => {
    expect(notice(frame(108), "B")).toBeUndefined();  // 108초에는 경보가 없어야 함
    // 109초에 주의 30초가 시작돼야 함
    expect(notice(frame(109), "B")).toEqual({ zone: "B", stage: "caution", etaSec: 30 });
    // 119초에 주의 20초가 돼야 함
    expect(notice(frame(119), "B")).toEqual({ zone: "B", stage: "caution", etaSec: 20 });
    // 129초에 경고 10초가 돼야 함
    expect(notice(frame(129), "B")).toEqual({ zone: "B", stage: "warning", etaSec: 10 });
    expect(notice(frame(138), "B")?.stage).toBe("warning");  // 138초까지 경고여야 함
    // 139초에 침수 0초가 돼야 함
    expect(notice(frame(139), "B")).toEqual({ zone: "B", stage: "evacuate", etaSec: 0 });
  });

  // C 구역은 정상으로 두고 경보에는 정상이 아닌 구역만 담는지 검사
  it("keeps zone C safe and lists only non-safe zones", () => {
    // 주기 내내 C 경보가 없어야 함
    for (let e = 0; e < MOCK_CYCLE_SEC; e += 1) expect(notice(frame(e), "C")).toBeUndefined();
    expect(frame(0).alerts).toEqual([]);  // 시작에는 경보 목록이 비어야 함
    // 75초에는 A 침수만 있어야 함
    expect(frame(75).alerts).toEqual([{ zone: "A", stage: "evacuate", etaSec: 0 }]);
  });

  it("uses the thresholds it is given", () => {  // 받은 한계를 쓰는지 검사
    // A 한계를 10 으로 낮추면 시작부터 A 침수여야 함
    expect(demo(BASE, { A: 10, B: 55, C: 65 }).alerts).toEqual([{ zone: "A", stage: "evacuate", etaSec: 0 }]);
  });

  it("starts a new experiment every 180 s", () => {  // 180초마다 새 실험이 시작되는지 검사
    const last = frame(MOCK_CYCLE_SEC - 1);  // 주기의 마지막 초
    expect(last.elapsedSec).toBe(179);  // 경과 시간은 179초여야 함
    // A·B 수위는 96.13·68.86 mm 여야 함
    expect([last.zones.A.levelMm, last.zones.B.levelMm]).toEqual([96.13, 68.86]);
    expect(last.experimentId).toBe(frame(0).experimentId);  // 같은 주기라 실험 번호가 같아야 함

    const next = frame(MOCK_CYCLE_SEC);  // 다음 주기의 첫 초
    expect(next.elapsedSec).toBe(0);  // 경과 시간이 0초로 돌아가야 함
    expect(next.zones.A.levelMm).toBe(12);  // A 수위가 시작값 12 mm 로 돌아가야 함
    expect(next.experimentId).not.toBe(frame(0).experimentId);  // 실험 번호가 바뀌어야 함
    // 실험 번호는 EXP-DEMO-세 자리 모양이어야 함
    expect(frame(0).experimentId).toMatch(/^EXP-DEMO-\d{3}$/);
  });

  // 서울 시각 정수 초와 새 예측 기준 시각을 찍는지 검사
  it("stamps KST whole seconds and a fresh prediction basis", () => {
    const snapshot = frame(42);  // 42초 지점 응답
    // 시각은 서울 시각 정수 초여야 함
    expect(snapshot.timestamp).toBe("2026-10-23T10:00:42.000+09:00");
    // 예측 기준 시각이 지금 시각과 같아야 함
    expect(snapshot.predictionMeta?.basisTime).toBe(snapshot.timestamp);
    expect(snapshot.predictionMeta?.basisElapsedSec).toBe(42);  // 예측 기준 경과 시간이 42초여야 함
    expect(snapshot.predictionMeta?.validForSec).toBe(5);  // 예측 유효 기간이 5초여야 함
  });

  // 출력이 잠긴 서버 시뮬레이션처럼 보이는지 검사
  it("looks like the server sim with outputs locked", () => {
    const snapshot = frame(0);  // 시작 응답
    expect(snapshot.dataSource).toBe("sim");  // 입력원은 sim 이어야 함
    expect(snapshot.mode).toBe("live");  // 모드는 live 여야 함
    // 구역별 출처가 A·B 가상 실측, C 모델 추정이어야 함
    expect([snapshot.zones.A.source, snapshot.zones.B.source, snapshot.zones.C.source]).toEqual([
      "simulated",  // A: 가상 실측
      "simulated",  // B: 가상 실측
      "estimated",  // C: 모델 추정
    ]);
    // 막힘은 빗물받이 ② 부분 막힘이어야 함
    expect(snapshot.blockage).toEqual({ location: "INLET-02", type: "partial", label: "빗물받이 ② 부분 막힘" });
    expect(snapshot.outputsLocked).toBe(true);  // 출력은 늘 잠겨 있어야 함
  });

  // 예측 가정에 막힌 빗물받이만 담는지 검사(서버와 같게)
  it("lists only the blocked inlet in the prediction assumptions, like the server", () => {
    // 예측에 쓴 막힘만 담고(없으면 빈 객체), 서버도 막힌 곳만 넣음
    expect(frame(0).predictionMeta?.assumptions.blockage).toEqual({ "INLET-02": "partial" });
  });
});

describe("trail", () => {  // 이력 만들기 테스트 묶음
  // 주기 시작부터 초마다 표본 하나이고 수위가 예시 응답과 같은지 검사
  it("has one sample per second from the cycle start, the same levels as demo", () => {
    const history = trail(BASE + 42_400);  // 42.4초 지점까지의 이력을 만듦
    expect(history).toHaveLength(43);  // 0초부터 42초까지 43개여야 함
    for (const [e, sample] of history.entries()) {  // 표본마다 같은 초의 예시 응답과 견반환
      const { timestamp, zones } = frame(e);  // 그 초의 예시 응답에서 시각과 수위를 꺼냄
      // 표본이 응답의 시각과 수위와 같아야 함
      expect(sample, `e=${e}`).toEqual({ t: Date.parse(timestamp), A: zones.A.levelMm, B: zones.B.levelMm, C: zones.C.levelMm });
    }
  });

  it("starts over with each cycle", () => {  // 주기마다 새로 시작하는지 검사
    // 주기의 마지막 초에는 표본이 주기 길이만큼이어야 함
    expect(trail(BASE + (MOCK_CYCLE_SEC - 1) * 1000)).toHaveLength(MOCK_CYCLE_SEC);
    // 다음 주기의 첫 초에는 표본이 하나뿐이어야 함
    expect(trail(BASE + MOCK_CYCLE_SEC * 1000)).toEqual([{ t: BASE + MOCK_CYCLE_SEC * 1000, A: 12, B: 8, C: 4 }]);
  });
});
