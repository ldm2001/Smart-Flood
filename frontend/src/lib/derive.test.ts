import { describe, expect, it } from "vitest";
import {
  notices,
  entry,
  caption,
  plot,
  EMPTY_HISTORY,
  leader,
  phrase,
  verdict,
  verdicts,
  figure,
  clock,
  fraction,
  HISTORY_LIMIT,
  outage,
  expiry,
  columns,
  lead,
  share,
  roster,
  stamp,
  peak,
  type Grade,
} from "./derive";
import type { Alert, Zone, Source } from "./schema";

// 세 시점 예측이 모두 v 인 평평한 예측을 만드는 도우미
const plateau = (v: number) => ({ "10": v, "20": v, "30": v });
const THRESHOLDS = { A: 45, B: 55, C: 65 };  // 구역별 한계 수위(mm)
// 구역 등급 하나를 만드는 도우미
const status = (zoneId: Zone, stage: Grade["stage"], etaSec: number | null): Grade => ({
  zoneId,  // 구역 이름
  stage,  // 경보 단계
  etaSec,  // 남은 초
});
// 세 구역 등급을 묶는 도우미
const trio = (a: Grade, b: Grade, c: Grade) => ({ A: a, B: b, C: c });
// 세 구역 출처를 묶는 도우미
const sources = (a: Source, b: Source, c: Source) => ({ A: { source: a }, B: { source: b }, C: { source: c } });
// 시뮬레이션 출처: A·B 는 가상 실측, C 는 모델 추정
const SIM_SOURCES = sources("simulated", "simulated", "estimated");
// 세 구역이 모두 정상인 등급
const ALL_SAFE = trio(status("A", "safe", null), status("B", "safe", null), status("C", "safe", null));

describe("verdict", () => {  // 구역 등급 판정 테스트 묶음
  // 한계 바로 아래와 한계 위치의 판정이 갈리는지 검사
  it("44.9 mm is below a 45 mm threshold, 45.0 mm is at it", () => {
    // 44.9 mm 는 정상이어야 함
    expect(verdict("A", 44.9, plateau(44.9), 45)).toEqual(status("A", "safe", null));
    // 45.0 mm 는 침수(0초)여야 함
    expect(verdict("A", 45.0, plateau(45.0), 45)).toEqual(status("A", "evacuate", 0));
  });

  // 10초 뒤 한계에 닿으면 경고(10초)인지 검사
  it("a +10 s prediction at the threshold is warning with eta 10", () => {
    // 10초 뒤 45 mm 면 경고 10초여야 함
    expect(verdict("A", 40, { "10": 45, "20": 50, "30": 55 }, 45)).toEqual(status("A", "warning", 10));
    // 10초 뒤 44.9 mm 면 20초 때 닿아 주의여야 함
    expect(verdict("A", 40, { "10": 44.9, "20": 50, "30": 55 }, 45)).toEqual(status("A", "caution", 20));
  });

  // 30초 뒤 한계면 주의(30초), 바로 아래면 정상인지 검사
  it("a +30 s prediction at the threshold is caution with eta 30, just below is safe", () => {
    // 30초 뒤 45 mm 면 주의 30초여야 함
    expect(verdict("A", 40, { "10": 44.9, "20": 44.9, "30": 45 }, 45)).toEqual(status("A", "caution", 30));
    // 30초 뒤 44.9 mm 면 정상이어야 함
    expect(verdict("A", 40, { "10": 44.9, "20": 44.9, "30": 44.9 }, 45)).toEqual(status("A", "safe", null));
  });

  it("the current level wins over predictions", () => {  // 현재 수위가 예측보다 앞서는지 검사
    // 현재 60 mm 면 예측이 0 이어도 침수여야 함
    expect(verdict("B", 60, plateau(0), 55)).toEqual(status("B", "evacuate", 0));
  });
});

describe("verdicts", () => {  // 세 구역 판정 테스트 묶음
  it("uses each zone's own threshold", () => {  // 구역마다 자기 한계를 쓰는지 검사
    const snapshot = {  // 구역별 수위와 예측을 담은 스냅샷
      zones: {  // 구역별 현재 수위
        A: { levelMm: 45, rateMmSec: 0, source: "simulated" as const },  // A 는 45 mm(한계 45)
        // B 는 45 mm(한계 55 라서 아직 정상)
        B: { levelMm: 45, rateMmSec: 0, source: "simulated" as const },
        C: { levelMm: 60, rateMmSec: 0, source: "estimated" as const },  // C 는 60 mm(한계 65)
      },
      // 구역별 예측: A·B 는 평평, C 는 30초 뒤 한계
      predictions: { A: plateau(45), B: plateau(45), C: { "10": 61, "20": 63, "30": 65 } },
    };
    expect(verdicts(snapshot, THRESHOLDS)).toEqual(  // A 침수, B 정상, C 주의 30초여야 함
      // 기대하는 세 구역 등급
      trio(status("A", "evacuate", 0), status("B", "safe", null), status("C", "caution", 30)),
    );
  });
});

describe("stage priority", () => {  // 단계 우선순위 테스트 묶음
  // 구역 순서와 상관없이 높은 단계가 최악인지 검사
  it("the higher stage is worst regardless of zone order", () => {
    // A 주의, B 경고, C 정상 등급
    const zones = trio(status("A", "caution", 20), status("B", "warning", 10), status("C", "safe", null));
    expect(peak(zones).zoneId).toBe("B");  // 가장 위험한 구역은 B 여야 함
    // 경고보다 침수인 C 가 더 위험필요
    expect(peak(trio(status("A", "safe", null), status("B", "warning", 10), status("C", "evacuate", 0))).zoneId).toBe("C");
  });

  // 같은 단계면 빨리 닿는 쪽, 그다음 구역 순서인지 검사
  it("within one stage the earlier eta is worst, then zone order", () => {
    // 주의끼리면 20초인 B 가 먼저여야 함
    expect(peak(trio(status("A", "caution", 30), status("B", "caution", 20), status("C", "safe", null))).zoneId).toBe("B");
    // 모두 같으면 A 가 먼저여야 함
    expect(peak(trio(status("A", "caution", 20), status("B", "caution", 20), status("C", "caution", 20))).zoneId).toBe("A");
  });

  // 모두 정상이면 최악도 정상이고 먼저 닿는 구역은 없는지 검사
  it("all safe gives a safe worst zone and no earliest zone", () => {
    // 세 구역이 모두 정상인 등급
    const zones = trio(status("A", "safe", null), status("B", "safe", null), status("C", "safe", null));
    expect(peak(zones).stage).toBe("safe");  // 가장 위험한 구역의 단계는 정상이어야 함
    expect(leader(zones)).toBeNull();  // 먼저 닿는 구역은 없어야 한다(null)
  });

  it("earliest picks the smallest eta", () => {  // 가장 작은 남은 초를 고르는지 검사
    // A 30초, B 정상, C 20초 등급
    const zones = trio(status("A", "caution", 30), status("B", "safe", null), status("C", "caution", 20));
    expect(leader(zones)?.zoneId).toBe("C");  // 먼저 닿는 구역은 C 여야 함
  });

  // 경보 목록에 정상이 아닌 구역만 A·B·C 순으로 담기는지 검사
  it("alerts list only non-safe zones in A, B, C order", () => {
    // A 경고, B 정상, C 주의 등급
    const zones = trio(status("A", "warning", 10), status("B", "safe", null), status("C", "caution", 30));
    expect(notices(zones)).toEqual([  // B 는 빠지고 A, C 만 순서대로 나와야 함
      { zone: "A", stage: "warning", etaSec: 10 },  // A 경고 10초
      { zone: "C", stage: "caution", etaSec: 30 },  // C 주의 30초
    ]);
  });
});

describe("roster", () => {  // 서버 경보를 등급으로 바꾸는 테스트 묶음
  // 서버 경보에서 단계와 남은 초를 읽고 나머지는 정상으로 두는지 검사
  it("reads stage and eta from the server alerts and leaves the other zones safe", () => {
    // A 경고 경보 하나면 A 만 경고여야 함
    expect(roster([{ zone: "A", stage: "warning", etaSec: 10 }])).toEqual(
      // 기대하는 등급: A 경고 10초, B·C 정상
      trio(status("A", "warning", 10), status("B", "safe", null), status("C", "safe", null)),
    );
    expect(roster([])).toEqual(ALL_SAFE);  // 경보가 없으면 모두 정상이어야 함
  });

  it("treats a missing eta as unknown", () => {  // 남은 초가 없으면 모름(null)으로 보는지 검사
    // etaSec 가 아예 없어도 null 이어야 함
    expect(roster([{ zone: "B", stage: "caution" }]).B).toEqual(status("B", "caution", null));
    // etaSec 가 null 이어도 null 이어야 함
    expect(roster([{ zone: "B", stage: "caution", etaSec: null }]).B).toEqual(status("B", "caution", null));
  });

  // 같은 구역이 반복되면 높은 단계를 남기는지 검사
  it("keeps the higher stage when the server repeats a zone", () => {
    const alerts: Alert[] = [  // A 구역 경보가 세 번 온 목록
      { zone: "A", stage: "caution", etaSec: 20 },  // 주의 20초
      { zone: "A", stage: "evacuate", etaSec: 0 },  // 침수 0초(가장 높다)
      { zone: "A", stage: "warning", etaSec: 10 },  // 경고 10초(침수보다 낮다)
    ];
    expect(roster(alerts).A).toEqual(status("A", "evacuate", 0));  // A 는 침수 0초만 남아야 함
  });

  // mock 이 경보로 바꾼 등급이 그대로 돌아오는지 검사
  it("gives back the statuses the mock made its alerts from", () => {
    // A 경고, B 정상, C 주의 등급
    const zones = trio(status("A", "warning", 10), status("B", "safe", null), status("C", "caution", 30));
    expect(roster(notices(zones))).toEqual(zones);  // 경보로 바꿨다가 되돌려도 같아야 함
  });
});

describe("caption", () => {  // 배너 문구 테스트 묶음
  it("all safe", () => {  // 모두 정상일 때 문구를 검사
    const banner = caption(ALL_SAFE, SIM_SOURCES);  // 모두 정상인 배너를 만듦
    // 정상 문구에 구역은 없어야 함
    expect(banner).toEqual({ stage: "safe", zoneId: null, message: "전 구역 정상 · 30초 안에 한계 도달 예상 없음" });
  });

  it("names the worst zone with its eta", () => {  // 가장 위험한 구역 이름과 남은 초를 넣는지 검사
    // A 가 주의 20초인 배너를 만듦
    const banner = caption(trio(status("A", "caution", 20), status("B", "safe", null), status("C", "safe", null)), SIM_SOURCES);
    // A 구역 이름과 약 20초 문구여야 함
    expect(banner).toEqual({ stage: "caution", zoneId: "A", message: "A 낮은 상가 도로 · 약 20초 후 침수 예상" });
  });

  it("marks zone C as a model estimate", () => {  // C 구역에 모델 추정 표시가 붙는지 검사
    // C 가 경고 10초인 배너를 만듦
    const banner = caption(trio(status("A", "safe", null), status("B", "safe", null), status("C", "warning", 10)), SIM_SOURCES);
    // 문구 끝에 모델 추정이 붙어야 함
    expect(banner.message).toBe("C 높은 광장 · 약 10초 후 침수 예상 (모델 추정)");
  });

  // 추정 표시는 구역 고정표가 아니라 구역의 출처를 따르는지 검사
  it("takes the estimate mark from the zone's source, not from a fixed zone list", () => {
    // A 만 위험한 등급
    const aAtRisk = trio(status("A", "warning", 10), status("B", "safe", null), status("C", "safe", null));
    // C 만 위험한 등급
    const cAtRisk = trio(status("A", "safe", null), status("B", "safe", null), status("C", "warning", 10));
    // A 출처가 추정이면 A 문구에 표시가 붙어야 함
    expect(caption(aAtRisk, sources("estimated", "measured", "estimated")).message).toBe(
      "A 낮은 상가 도로 · 약 10초 후 침수 예상 (모델 추정)",  // 기대하는 문구(모델 추정 포함)
    );
    // C 출처가 실측이면 C 문구에 표시가 없어야 함
    expect(caption(cAtRisk, sources("measured", "measured", "measured")).message).toBe("C 높은 광장 · 약 10초 후 침수 예상");
  });

  it("evacuate says flooding has happened", () => {  // 침수 단계는 침수 발생 문구인지 검사
    // A 가 침수인 배너를 만듦
    const banner = caption(trio(status("A", "evacuate", 0), status("B", "warning", 10), status("C", "safe", null)), SIM_SOURCES);
    // 남은 초 없이 침수 발생이어야 함
    expect(banner).toEqual({ stage: "evacuate", zoneId: "A", message: "A 낮은 상가 도로 · 침수 발생" });
  });

  // 남은 초가 없어도 구역 이름은 나오는지 검사
  it("a non-safe stage without eta still names the zone", () => {
    // B 가 남은 초 모름인 주의 배너를 만듦
    const banner = caption(trio(status("A", "safe", null), status("B", "caution", null), status("C", "safe", null)), SIM_SOURCES);
    expect(banner.message).toBe("B 주택 골목 · 침수 위험");  // B 구역 이름과 침수 위험 문구여야 함
  });
});

describe("phrase", () => {  // 도달 문구 테스트 묶음
  // 단계별 도달 문구를 남은 초와 나눠 내는지 검사
  it("says when each stage reaches the threshold, with the seconds apart so the card can show them large", () => {
    // 정상은 값 없이 도달 예상 없음 문구여야 함
    expect(phrase(status("A", "safe", null))).toEqual({ value: null, rest: "30초 안에 한계 도달 예상 없음" });
    // 주의 20초는 약 20초와 뒷 문구로 나뉘어야 함
    expect(phrase(status("A", "caution", 20))).toEqual({ value: "약 20초", rest: "후 한계 도달 예상" });
    // 경고 10초는 약 10초와 뒷 문구로 나뉘어야 함
    expect(phrase(status("A", "warning", 10))).toEqual({ value: "약 10초", rest: "후 한계 도달 예상" });
    // 침수는 값 없이 한계 도달 문구여야 함
    expect(phrase(status("A", "evacuate", 0))).toEqual({ value: null, rest: "한계 도달" });
  });

  // 서버가 안 보낸 시각을 지어내지 않는지 검사
  it("does not invent a time the server did not send", () => {
    // 주의인데 남은 초를 모르면 시각 미상이어야 함
    expect(phrase(status("B", "caution", null))).toEqual({ value: null, rest: "한계 도달 예상 · 시각 미상" });
    // 경고인데 남은 초를 모르면 시각 미상이어야 함
    expect(phrase(status("B", "warning", null))).toEqual({ value: null, rest: "한계 도달 예상 · 시각 미상" });
  });
});

describe("gauge", () => {  // 게이지 비율·퍼센트 테스트 묶음
  // 비율이 수위 나누기 한계이고 0~1 로 잘리는지 검사
  it("ratio is level over threshold, clamped to 0..1", () => {
    expect(fraction(22.5, 45)).toBe(0.5);  // 22.5 나누기 45 는 0.5 여야 함
    expect(fraction(45, 45)).toBe(1);  // 한계에 닿으면 1 이어야 함
    expect(fraction(60, 45)).toBe(1);  // 한계를 넘어도 1 로 잘려야 함
    expect(fraction(0, 45)).toBe(0);  // 수위 0 이면 0 이어야 함
    expect(fraction(10, 0)).toBe(0);  // 한계가 0 이면 0 이어야 함
  });

  // 퍼센트를 내려서 100 % 가 한계 도달을 뜻하는지 검사
  it("percent rounds down so 100 % means the threshold is reached", () => {
    expect(share(44.9, 45)).toBe(99);  // 44.9 는 99 % 여야 함
    expect(share(45, 45)).toBe(100);  // 45 는 100 % 여야 함
    expect(share(60, 45)).toBe(133);  // 60 은 133 % 여야 한다(한계를 넘는 값은 그대로)
    expect(share(25.65, 45)).toBe(57);  // 25.65 나누기 45 는 소수 오차를 보정해 57 % 여야 함
  });

  // 한계 아래에서는 100 % 가 안 나오고 침수 경계와 같은지 검사
  it("never shows 100 % below the threshold, the same boundary as the evacuate stage", () => {
    expect(share(44.9999999999, 45)).toBe(99);  // 44.9999999999 는 99 % 여야 함
    expect(share(54.99999999999, 55)).toBe(99);  // 54.99999999999 는 한계 55 아래라 99 % 여야 함
    // 같은 값은 침수 단계가 아니어야 함
    expect(verdict("A", 44.9999999999, plateau(0), 45).stage).not.toBe("evacuate");
  });
});

describe("figure", () => {  // 수위 표시 글자 테스트 묶음
  // 반올림 대신 0.1 mm 로 내려서 한계 아래 값이 한계로 안 읽히는지 검사
  it("cuts to 0.1 mm instead of rounding, so a level below the threshold never reads as the threshold", () => {
    expect(figure(44.96, 45)).toBe("44.9");  // 44.96 은 44.9 여야 함
    expect(figure(44.9999999999, 45)).toBe("44.9");  // 44.9999999999 는 44.9 여야 함
    expect(figure(45, 45)).toBe("45.0");  // 45 는 45.0 이어야 함
    expect(figure(45.37, 45)).toBe("45.3");  // 45.37 은 45.3 이어야 한다(내림)
  });

  // 부동소수가 조금 어긋나게 저장한 값도 맞게 보이는지 검사
  it("keeps decimals that floats store a hair off", () => {
    // 0.1 곱하기 3 은 0.30000000000000004 로 저장돼도 0.3 이어야 함
    expect(figure(0.1 * 3, 45)).toBe("0.3");
    // 0.7 곱하기 3 은 2.0999999999999996 으로 저장돼도 2.1 이어야 함
    expect(figure(0.7 * 3, 45)).toBe("2.1");
    expect(figure(31.8, 55)).toBe("31.8");  // 31.8 은 31.8 그대로여야 함
  });

  it("works before the threshold is known", () => {  // 한계를 알기 전에도 동작하는지 검사
    expect(figure(44.96, null)).toBe("44.9");  // 한계가 없어도 44.96 은 44.9 여야 함
    expect(figure(0, null)).toBe("0.0");  // 한계가 없어도 0 은 0.0 이어야 함
  });
});

describe("level history", () => {  // 수위 이력 테스트 묶음
  const T = Date.UTC(2026, 9, 25, 1, 0, 0);  // 기준 시각(2026-10-25 01:00 UTC)
  // 실험 번호와 입력원(sim)을 묶은 기본 실행
  const RUN = { experimentId: "EXP-20261025-001", dataSource: "sim" as const };
  // 기준 시각에서 sec 초 뒤의 스냅샷을 만드는 도우미
  const frame = (sec: number, A = 10, run: { experimentId: string; dataSource: "sim" | "replay" | "live" } = RUN) => ({
    ...run,  // 실험 번호와 입력원을 그대로 기록
    timestamp: stamp(T + sec * 1000),  // 서울 시각 글자로 바꾼 서버 시각
    // 구역별 수위: A 는 인자, B 는 8, C 는 4
    zones: { A: { levelMm: A }, B: { levelMm: 8 }, C: { levelMm: 4 } },
  });

  // 새 서버 시각마다 표본이 하나씩 늘어나는지 검사
  it("adds one sample per new server timestamp", () => {
    // 0초와 1초 스냅샷을 차례로 합산
    const history = entry(entry(EMPTY_HISTORY, frame(0, 10)), frame(1, 11));
    expect(history.samples).toEqual([  // 표본 두 개가 시간순으로 있어야 함
      { t: T, A: 10, B: 8, C: 4 },  // 0초 표본
      { t: T + 1000, A: 11, B: 8, C: 4 },  // 1초 표본
    ]);
  });

  // 같은 시각이 또 오면 이력이 그대로인지 검사(정지·대기 중인 서버)
  it("keeps the same history for a repeated timestamp (stopped or idle server)", () => {
    const history = entry(EMPTY_HISTORY, frame(0));  // 0초 표본 하나를 합산
    // 같은 시각이면 값이 달라도 같은 이력 객체여야 함
    expect(entry(history, frame(0, 99))).toBe(history);
  });

  // 시간이 거꾸로 가거나 실행이 바뀌면 새로 시작하는지 검사
  it("starts over when time goes backwards or the run changes", () => {
    const history = entry(entry(EMPTY_HISTORY, frame(0)), frame(1));  // 0초와 1초 표본이 있는 이력
    // 5초 전 시각이 오면 그 표본 하나로 새로 시작
    expect(entry(history, frame(-5)).samples).toEqual([{ t: T - 5000, A: 10, B: 8, C: 4 }]);
    // 실험 번호가 바뀌면 표본 하나로 새로 시작
    expect(entry(history, frame(2, 10, { ...RUN, experimentId: "EXP-20261025-002" })).samples).toHaveLength(1);
    // 입력원이 바뀌면 표본 하나로 새로 시작
    expect(entry(history, frame(2, 10, { ...RUN, dataSource: "replay" })).samples).toHaveLength(1);
  });

  it("keeps the latest 600 samples", () => {  // 최근 600개 표본만 남기는지 검사
    let history = EMPTY_HISTORY;  // 빈 이력에서 시작
    // 605초 동안 한 표본씩 합산
    for (let sec = 0; sec < 605; sec += 1) history = entry(history, frame(sec));
    expect(HISTORY_LIMIT).toBe(600);  // 최대 개수는 600 이어야 함
    expect(history.samples).toHaveLength(600);  // 표본은 600개여야 함
    expect(history.samples[0].t).toBe(T + 5000);  // 가장 오래된 표본은 5초 뒤 것이어야 함
    expect(history.samples.at(-1)?.t).toBe(T + 604_000);  // 가장 최근 표본은 604초 뒤 것이어야 함
  });
});

describe("expiry and disconnection", () => {  // 만료·끊김 테스트 묶음
  const T = Date.UTC(2026, 9, 23, 1, 0, 0);  // 기준 시각(2026-10-23 01:00 UTC)

  // 지금에서 기준을 뺀 값이 유효 기간을 넘어야 만료인지 검사
  it("a prediction is stale only when now - basis exceeds validity", () => {
    expect(expiry(T + 5000, T, 5)).toBe(false);  // 딱 5초면 아직 만료가 아니다
    expect(expiry(T + 5001, T, 5)).toBe(true);  // 5.001초면 만료다
    expect(expiry(T - 1000, T, 5)).toBe(false);  // 기준보다 과거 시각이면 만료가 아니다
  });

  // 마지막 정상 응답 뒤 4초를 넘어야 끊김인지 검사
  it("disconnected only when more than 4 s passed since the last good response", () => {
    expect(outage(T + 4000, T)).toBe(false);  // 딱 4초면 아직 연결이다
    expect(outage(T + 4001, T)).toBe(true);  // 4.001초면 끊김이다
    expect(outage(T, null)).toBe(true);  // 한 번도 못 받았으면 끊김이다
  });

  // 선행 시간이 도달 시각에서 주의보 시각을 뺀 초인지 검사
  it("lead time is arrival minus caution, in seconds", () => {
    expect(lead(T, T + 20_000)).toBe(20);  // 주의보 20초 뒤 도달이면 20 이어야 함
    expect(lead(null, T)).toBeNull();  // 주의보가 없으면 null 이어야 함
    expect(lead(T, null)).toBeNull();  // 도달이 없으면 null 이어야 함
  });
});

describe("Seoul time", () => {  // 서울 시각 테스트 묶음
  // 한 시점을 밀리초 포함 서울 시각 글자로 바꾸는지 검사
  it("formats an instant as KST ISO with milliseconds", () => {
    // UTC 01:00:42 는 서울 10:00:42 여야 함
    expect(stamp(Date.UTC(2026, 9, 22, 1, 0, 42))).toBe("2026-10-22T10:00:42.000+09:00");
    // UTC 15:30:05.123 은 다음 날 서울 00:30:05.123 이어야 함
    expect(stamp(Date.UTC(2026, 9, 22, 15, 30, 5, 123))).toBe("2026-10-23T00:30:05.123+09:00");
  });

  it("formats the clock as HH:MM:SS in KST", () => {  // 서울 시각을 시:분:초 글자로 바꾸는지 검사
    // UTC 01:00:42 는 10:00:42 여야 함
    expect(clock(Date.UTC(2026, 9, 22, 1, 0, 42))).toBe("10:00:42");
    // UTC 15:30:05 는 00:30:05 여야 함
    expect(clock(Date.UTC(2026, 9, 22, 15, 30, 5, 999))).toBe("00:30:05");
  });
});

describe("plot", () => {  // 차트 경로 테스트 묶음
  // 그림 크기. 안쪽 300px 가 150초(지난 120 + 예측 30)라 1초당 2px
  const options = { width: 354, height: 248 };
  const END = Date.UTC(2026, 9, 23, 1, 2, 0);  // 그래프 끝 시각(2026-10-23 01:02 UTC)
  const samples = [  // 1초 간격 표본 세 개
    { t: END - 2000, A: 10, B: 8, C: 4 },  // 2초 전 표본
    { t: END - 1000, A: 12, B: 8, C: 4.5 },  // 1초 전 표본
    { t: END, A: 14, B: 8, C: 5 },  // 현재 표본
  ];
  // 예측: A 는 오르고 B·C 는 평평하다
  const predictions = { A: { "10": 16, "20": 18, "30": 20 }, B: plateau(8), C: plateau(5) };

  // 지난 120초 실측 선을 그리고 세로 최대값이 한계에서 나오는지 검사
  it("draws measured lines over the last 120 s with yMax from thresholds", () => {
    const chart = plot(samples, predictions, THRESHOLDS, options);  // 차트 경로를 만듦
    // 세로 최대값은 65 곱하기 1.15 = 74.75 를 10 단위로 올린 80 이어야 함
    expect(chart.yMax).toBe(80);
    // A 실측 선은 세 점을 이어야 함
    expect(chart.measured.A).toBe("M 276 195 L 278 190 L 280 185");
    expect(chart.measured.B).toBe("M 276 200 L 278 200 L 280 200");  // B 실측 선은 수평이어야 함
    expect(chart.nowX).toBe(280);  // 현재 시각 위치는 280 이어야 함
  });

  // 예측 선이 마지막 점에서 +30초까지 이어지는지 검사
  it("draws predictions from the last point to +30 s", () => {
    const chart = plot(samples, predictions, THRESHOLDS, options);  // 차트 경로를 만듦
    // A 예측 선은 현재 점에서 10·20·30초 점으로 이어져야 함
    expect(chart.predicted.A).toBe("M 280 185 L 300 180 L 320 175 L 340 170");
  });

  // 선 끝 점의 세로 위치(구역 글자 자리)를 주는지 검사
  it("gives the y of each line's last point, where the zone letter goes", () => {
    // A 185, B 200, C 207.5 여야 함
    expect(plot(samples, predictions, THRESHOLDS, options).endY).toEqual({ A: 185, B: 200, C: 207.5 });
  });

  // 한계선과 가로 눈금이 같은 눈금자를 쓰는지 검사
  it("puts threshold lines and gridlines on the same scale", () => {
    const chart = plot(samples, predictions, THRESHOLDS, options);  // 차트 경로를 만듦
    // 한계선 세로 위치는 A 107.5, B 82.5, C 57.5 여야 함
    expect(chart.thresholdY).toEqual({ A: 107.5, B: 82.5, C: 57.5 });
    expect(chart.gridlines).toEqual([  // 가로 눈금은 0 부터 80 까지 16 간격이어야 함
      { value: 0, y: 220 },  // 0 눈금
      { value: 16, y: 180 },  // 16 눈금
      { value: 32, y: 140 },  // 32 눈금
      { value: 48, y: 100 },  // 48 눈금
      { value: 64, y: 60 },  // 64 눈금
      { value: 80, y: 20 },  // 80 눈금
    ]);
  });

  // 한계를 넘는 값이 있으면 세로 최대값을 올리는지 검사
  it("raises yMax to fit values above the thresholds", () => {
    const high = [{ t: END, A: 150, B: 8, C: 4 }];  // 150 mm 표본 하나
    // 150 곱하기 1.15 = 172.5 를 10 단위로 올린 180 이어야 함
    expect(plot(high, null, THRESHOLDS, options).yMax).toBe(180);
    // 표본이 없으면 예측 값은 쓰지 않아 한계로만 80 이어야 함
    expect(plot([], { A: plateau(100), B: plateau(0), C: plateau(0) }, THRESHOLDS, options).yMax).toBe(80);
  });

  // 범위 밖 표본을 버리고 벌어진 곳에서 선을 끊는지 검사
  it("drops samples older than the window and breaks lines at gaps", () => {
    const chart = plot(  // 표본 네 개로 차트 경로를 만듦
      [  // 수위 표본 목록
        { t: END - 121_000, A: 40, B: 8, C: 4 },  // 121초 전 표본(범위 밖이라 버려진다)
        { t: END - 120_000, A: 10, B: 8, C: 4 },  // 120초 전 표본(범위 안 가장자리)
        { t: END - 10_000, A: 12, B: 8, C: 4 },  // 10초 전 표본
        { t: END, A: 14, B: 8, C: 4 },  // 현재 표본
      ],
      null,  // 예측 없음
      THRESHOLDS,  // 구역별 한계
      options,  // 그림 크기
    );
    // 벌어진 표본마다 새로 시작(M)해 선이 이어지지 않아야 함
    expect(chart.measured.A).toBe("M 40 195 M 260 190 M 280 185");
    expect(chart.predicted.A).toBe("");  // 예측이 없으면 빈 경로여야 함
  });

  // 이웃이 없는 표본을 점으로 표시하는지 검사(혼자 이동은 안 그려진다)
  it("marks samples with no neighbour inside the gap, since a lone move draws nothing", () => {
    const apart = [  // 서로 멀리 떨어진 표본 세 개
      { t: END - 120_000, A: 10, B: 8, C: 4 },  // 120초 전 표본
      { t: END - 10_000, A: 12, B: 8, C: 4 },  // 10초 전 표본
      { t: END, A: 14, B: 8, C: 4 },  // 현재 표본
    ];
    // A 의 외톨이 점 세 개가 나와야 함
    expect(plot(apart, null, THRESHOLDS, options).isolated.A).toEqual([
      { x: 40, y: 195 },  // 120초 전 점
      { x: 260, y: 190 },  // 10초 전 점
      { x: 280, y: 185 },  // 현재 점
    ]);
    // 이어진 표본에는 외톨이 점이 없어야 함
    expect(plot(samples, predictions, THRESHOLDS, options).isolated).toEqual({ A: [], B: [], C: [] });
  });

  // 한계를 모르는 동안 한계선을 빼는지 검사
  it("leaves out threshold lines while the thresholds are unknown", () => {
    const chart = plot(samples, predictions, null, options);  // 한계 없이 차트 경로를 만듦
    expect(chart.thresholdY).toBeNull();  // 한계선은 없어야 한다(null)
    expect(chart.yMax).toBe(30);  // 값만으로 20 곱하기 1.15 = 23 을 올린 30 이어야 함
    // 눈금자가 달라져 A 선의 y 값도 달라져야 함
    expect(chart.measured.A).toBe("M 276 153.33 L 278 140 L 280 126.67");
  });

  it("is empty without samples", () => {  // 표본이 없으면 비어 있는지 검사
    const chart = plot([], predictions, THRESHOLDS, options);  // 표본 없이 차트 경로를 만듦
    expect(chart.measured).toEqual({ A: "", B: "", C: "" });  // 실측 선은 모두 비어야 함
    expect(chart.predicted).toEqual({ A: "", B: "", C: "" });  // 예측 선은 모두 비어야 함
    expect(chart.nowX).toBeNull();  // 현재 시각 위치는 null 이어야 함
    expect(chart.endY).toBeNull();  // 선 끝 위치는 null 이어야 함
    expect(chart.yMax).toBe(80);  // 세로 최대값은 한계에서 나온 80 이어야 함
    expect(chart.isolated).toEqual({ A: [], B: [], C: [] });  // 외톨이 점은 없어야 함
  });
});

describe("columns", () => {  // 라벨 칸 배치 테스트 묶음
  // 라벨이 선 위에 얹혀 겹치지 않도록, 멀면 모두 첫 칸인지 검사
  it("keeps every label in the first column while the lines are far apart", () => {
    // 실제 차트(높이 300, 여백 12, 최대 80)에서 45·55·65 mm 의 y 값이면 모두 0 칸
    expect(columns({ A: 132.75, B: 98.25, C: 63.75 }, 28)).toEqual({ A: 0, B: 0, C: 0 });
  });

  // 같은 칸에서 다른 라벨을 가릴 때만 옆 칸으로 옮기는지 검사
  it("moves a label aside only while it would cover another in the same column", () => {
    // A 와 B 가 가까우면 B 만 1 칸으로 옮겨야 함
    expect(columns({ A: 150, B: 140, C: 110 }, 28)).toEqual({ A: 0, B: 1, C: 0 });
    // 세 라벨이 모두 가까우면 0·1·2 칸으로 펼쳐야 함
    expect(columns({ A: 150, B: 140, C: 130 }, 28)).toEqual({ A: 0, B: 1, C: 2 });
  });

  // 라벨 높이만큼 정확히 떨어지면 같은 칸을 쓰는지 검사
  it("lets labels exactly one label height apart share a column", () => {
    // 28 간격이면 겹치지 않아 모두 0 칸이어야 함
    expect(columns({ A: 150, B: 122, C: 94 }, 28)).toEqual({ A: 0, B: 0, C: 0 });
  });
});
