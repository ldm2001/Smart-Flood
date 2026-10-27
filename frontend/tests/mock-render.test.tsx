// 관제 화면 렌더 테스트 파일. 마크업 글자로 그리는 도구를 가져온다
import { renderToStaticMarkup } from "react-dom/server";
// 테스트 도구를 가져온다
import { describe, expect, it } from "vitest";
// 첫 화면 컴포넌트를 가져온다
import Home from "@/app/page";
// 관제 패널과 화면 고르기 함수를 가져온다
import { Panel, scene } from "@/components/MonitorView";
// 이력 더하기 함수와 빈 이력을 가져온다
import { entry, EMPTY_HISTORY } from "@/lib/derive";
// 예시 이력·예시 응답 만들기를 가져온다
import { trail, demo } from "@/lib/mock";
// 응답 스냅샷 타입을 가져온다
import type { Snapshot } from "@/lib/schema";
// 기본 설정을 가져온다
import { DEFAULT_SETTINGS } from "@/lib/useSettings";
// 통신 결과 타입을 가져온다
import type { Feed } from "@/lib/useSnapshot";

// 저장 설정의 기본 한계
const THRESHOLDS = DEFAULT_SETTINGS.thresholds;
// 서버 설정이 준 구역별 한계
const CONFIG = { A: 45, B: 55, C: 65 };
// 기준 시각 10:00:00 서울, 예시 주기 0초
const BASE = Date.UTC(2026, 9, 23, 1, 0, 0);
// 10:01:10. 예시의 A 가 44.9 mm 라 10초 예측이 한계를 넘는다
const AT = BASE + 70_000;

// 마크업에서 태그를 빼고 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
// 통신 결과와 시각으로 패널을 그려 글만 돌려주는 도우미
const display = (polled: Feed, now: number | null) =>
  // 화면 고르기 결과를 패널에 넣어 그린 글이다
  content(renderToStaticMarkup(<Panel {...scene(now, polled, THRESHOLDS)} />));

// 서버 응답 흉내. 위험 판정 전이라 경보 목록이 비어 있다
const answer = (patch: Partial<Snapshot> = {}): Snapshot => ({
  // 예시 응답을 바탕으로 한다
  ...demo(AT, THRESHOLDS),
  // 실험 번호를 고정한다
  experimentId: "EXP-20261023-001",
  // 경보는 없다
  alerts: [],
  // 넘겨받은 값으로 덮어쓴다
  ...patch,
});

// 아직 아무 응답도 실패도 없는 상태
const WAITING: Feed = { latest: null, failed: false, history: EMPTY_HISTORY, thresholds: null };
// 한 번도 응답을 못 받고 실패한 상태
const DOWN: Feed = { ...WAITING, failed: true };
// 응답과 받은 시각으로 통신 결과를 만드는 도우미
const feed = (snapshot: Snapshot, receivedAt: number, extra: Partial<Feed> = {}): Feed => ({
  // 마지막 응답과 받은 시각
  latest: { snapshot, receivedAt },
  // 실패하지 않았다
  failed: false,
  // 빈 이력에 이 응답을 더한 이력
  history: entry(EMPTY_HISTORY, snapshot),
  // 서버가 준 한계
  thresholds: CONFIG,
  // 추가로 받은 값으로 덮어쓴다
  ...extra,
});

// 어느 화면을 보일지 고르는 테스트 묶음
describe("which screen to show", () => {
  // 시계가 준비되고 첫 응답이나 실패가 있을 때까지 기다리는지 검사
  it("waits until the clock is ready and until the first answer or failure", () => {
    // 시각이 없으면 연결 중이어야 한다
    expect(scene(null, feed(answer(), AT), THRESHOLDS)).toEqual({ view: "connecting" });
    // 응답도 실패도 없으면 연결 중이어야 한다
    expect(scene(AT, WAITING, THRESHOLDS)).toEqual({ view: "connecting" });
  });

  // 서버가 한 번도 답하지 않으면 저장 한계로 예시를 보이는지 검사
  it("shows the mock with the stored thresholds when the server has never answered", () => {
    // 기준 시각에서 42.4초 뒤
    const now = BASE + 42_400;
    // 예시 화면 정보여야 한다
    expect(scene(now, DOWN, THRESHOLDS)).toEqual({
      // 화면 종류는 예시
      view: "mock",
      // 지금 시각
      now,
      // 예시 응답
      snapshot: demo(now, THRESHOLDS),
      // 예시 이력
      samples: trail(now),
      // 저장 설정의 한계
      thresholds: THRESHOLDS,
      // 받은 시각은 없다
      receivedAt: null,
    });
  });

  // 나중에 읽기가 실패해도 마지막 좋은 응답과 서버 한계를 유지하는지 검사
  it("keeps the last good answer with the server thresholds after later polls fail", () => {
    // 서버 응답을 만든다
    const body = answer();
    // 0.3초에 받고 이후 실패한 통신 결과
    const polled = feed(body, AT + 300, { failed: true });
    // 9초 뒤에도 서버 화면 정보여야 한다
    expect(scene(AT + 9000, polled, THRESHOLDS)).toEqual({
      // 화면 종류는 서버
      view: "server",
      // 지금 시각
      now: AT + 9000,
      // 마지막 좋은 응답
      snapshot: body,
      // 쌓인 이력
      samples: polled.history.samples,
      // 서버가 준 한계
      thresholds: CONFIG,
      // 마지막 수신 시각
      receivedAt: AT + 300,
    });
  });

  // 읽기 콜백이 더하기 전에도 보이는 응답을 그래프에 넣는지 검사
  it("charts the shown answer even before the poll callback has added it", () => {
    // 서버 응답을 만든다
    const body = answer();
    // 이력이 비었어도 화면 정보를 구한다
    const props = scene(AT, feed(body, AT, { history: EMPTY_HISTORY }), THRESHOLDS);
    // 이력이 지금 응답 하나로 채워져야 한다
    expect(props.view === "server" && props.samples).toEqual([{ t: AT, A: 44.9, B: 31.8, C: 18.7 }]);
  });
});

// 검사 9번과 화면 테스트 묶음
describe("check 9 and the screens", () => {
  // 자료·예시 안내·시각 없는 중립 대기 화면을 미리 그리는지 검사
  it("prerenders a neutral waiting screen with no data, no mock notice and no time", () => {
    // 첫 화면을 그려 글만 뽑는다
    const text = content(renderToStaticMarkup(<Home />));
    // 대기 문구가 모두 있어야 한다
    for (const part of ["연결 중", "자료 대기", "—"]) expect(text).toContain(part);
    // 예시 안내 문구는 없어야 한다
    expect(text).not.toContain("가상 데이터");
    // 실험 번호는 없어야 한다
    expect(text).not.toContain("EXP-");
    // 출처 문구는 없어야 한다
    expect(text).not.toContain("가상 실측");
    // 시각 모양 글자는 없어야 한다
    expect(text).not.toMatch(/\d{2}:\d{2}:\d{2}/);
  });

  // 서버가 답한 적 없으면 가상 데이터라고 알리는지 검사(검사 9번)
  it("says it is mock data when the server never answered", () => {
    // 응답 없는 상태를 그려 글만 뽑는다
    const text = display(DOWN, AT);
    // 가상 데이터 안내가 있어야 한다
    expect(text).toContain("가상 데이터(서버 미연결)");
    // 연결 끊김과 마지막 수신 없음이 보여야 한다
    expect(text).toContain("연결 끊김 · 마지막 수신 —");
    // A 구역 10초 뒤 침수 예상 문구가 있어야 한다
    expect(text).toContain("A 낮은 상가 도로 · 약 10초 후 침수 예상");
    // 서울 시각이 보여야 한다
    expect(text).toContain("10:01:10");
    // 예시 실험 번호가 보여야 한다
    expect(text).toContain(demo(AT, THRESHOLDS).experimentId);
    // 세 구역 수위 숫자가 보여야 한다
    for (const value of ["44.9", "31.8", "18.7"]) expect(text).toContain(value);
    // 단계 이름과 출처 문구가 보여야 한다
    for (const part of ["경계", "가상 실측", "모델 추정"]) expect(text).toContain(part);
  });

  // 화면 자체 판단이 아닌 서버의 값과 단계를 보이는지 검사
  it("shows the server's values and stages, not the front's own judgement", () => {
    // 0.3초에 받은 응답을 1초 시점에 그려 글만 뽑는다
    const text = display(feed(answer(), AT + 300), AT + 1000);
    // 미연결 안내는 없어야 한다
    expect(text).not.toContain("서버 미연결");
    // 가상 모드 표시가 있어야 한다
    expect(text).toContain("모드 가상");
    // 연결 정상과 마지막 수신 시각이 보여야 한다
    expect(text).toContain("연결 정상 · 마지막 수신 10:01:10");
    // 서버 실험 번호가 보여야 한다
    expect(text).toContain("EXP-20261023-001");
    // 진행 중 표시가 있어야 한다
    expect(text).toContain("진행 중");
    // A 수위 숫자가 보여야 한다
    expect(text).toContain("44.9");
    // A 한계가 보여야 한다
    expect(text).toContain("한계 45 mm");
    // A 의 10초 예측이 한계를 넘어도 서버 경보가 비어 있어 정상이다
    expect(text).toContain("전 구역 정상 · 30초 안에 한계 도달 예상 없음");
    // 화면이 만든 단계 이름은 없어야 한다
    expect(text).not.toMatch(/경계|주의|침수\(경보\)/);
  });

  // 서버 경보를 보이는지 검사
  it("shows a server alert", () => {
    // B 구역 주의 30초 경보가 든 응답을 만든다
    const body = answer({ alerts: [{ zone: "B", stage: "caution", etaSec: 30 }] });
    // 그 응답을 그려 글만 뽑는다
    const text = display(feed(body, AT + 300), AT + 1000);
    // B 구역 30초 뒤 침수 예상 문구가 있어야 한다
    expect(text).toContain("B 주택 골목 · 약 30초 후 침수 예상");
    // 주의 단계 표시가 있어야 한다
    expect(text).toContain("△ 주의");
  });

  // 4초 뒤 마지막 값을 두고 연결 끊김을 알리는지 검사
  it("keeps the last values and says the connection is lost after 4 s", () => {
    // 0.3초에 받고 이후 실패한 상태를 4.301초 시점에 그린다
    const text = display(feed(answer(), AT + 300, { failed: true }), AT + 4301);
    // 연결 끊김과 마지막 수신 시각이 보여야 한다
    expect(text).toContain("연결 끊김 · 마지막 수신 10:01:10");
    // 마지막 수위 숫자가 남아야 한다
    expect(text).toContain("44.9");
    // 미연결 안내는 없어야 한다
    expect(text).not.toContain("서버 미연결");
  });

  // 예측이 유효 기간보다 오래되면 만료로 표시하는지 검사
  it("marks the prediction expired once it is older than its validity", () => {
    // 0.3초에 받은 응답의 통신 결과
    const polled = feed(answer(), AT + 300);
    // 5초 시점에는 만료 표시가 없어야 한다
    expect(display(polled, AT + 5000)).not.toContain("예측 만료");
    // 5.001초 시점에는 만료 표시가 있어야 한다
    expect(display(polled, AT + 5001)).toContain("예측 만료");
  });

  // 서버 설정이 오기 전에는 한계를 줄표로 보이는지 검사
  it("shows dashes for the thresholds until the server config arrives", () => {
    // 한계를 모르는 상태를 그려 글만 뽑는다
    const text = display(feed(answer(), AT + 300, { thresholds: null }), AT + 1000);
    // 세 구역 모두 한계 줄표여야 한다
    expect(text.match(/한계 —/g)).toHaveLength(3);
    // 숫자 한계는 없어야 한다
    expect(text).not.toContain("한계 45 mm");
  });

  // 실행 상태를 보이는지 검사
  it("shows the run state", () => {
    // 대기 상태는 '대기' 로 보여야 한다
    expect(display(feed(answer({ runState: "idle" }), AT + 300), AT + 1000)).toContain("대기");
    // 정지 상태는 '정지' 로 보여야 한다
    expect(display(feed(answer({ runState: "stopped" }), AT + 300), AT + 1000)).toContain("정지");
  });
});
