import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Home from "@/app/page";
import { Panel, scene } from "@/components/MonitorView";
import { entry, EMPTY_HISTORY } from "@/lib/derive";
import { trail, demo, diary } from "@/lib/mock";
import type { Snapshot } from "@/lib/schema";
import { DEFAULT_SETTINGS } from "@/lib/useSettings";
import type { Feed } from "@/lib/useSnapshot";

const THRESHOLDS = DEFAULT_SETTINGS.thresholds;  // 저장 설정의 기본 한계
const CONFIG = { A: 45, B: 55, C: 65 };  // 서버 설정이 준 구역별 한계
const BASE = Date.UTC(2026, 9, 23, 1, 0, 0);  // 기준 시각 10:00:00 서울, 예시 주기 0초
const AT = BASE + 70_000;  // 10:01:10. 예시의 A 가 44.9 mm 라 10초 예측이 한계를 넘음
// 평면도·장치·타임라인·기록 칸의 제목
const TITLES = ["도시 모형 상태", "현장 장치 상태", "위험 판단·시험용 문자", "이벤트 기록"];
// 사건 없는 구역의 타임라인 칸
const BLANK = "위험 판단 — 문자 요청(SMS 예정) — 실제 도달(경보) — 선행 시간 —";

// 마크업에서 태그를 빼고 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
// 통신 결과와 시각으로 패널을 그려 글만 돌려주는 도우미
const display = (polled: Feed, now: number | null) =>
  // 화면 고르기 결과를 패널에 넣어 그린 글
  content(renderToStaticMarkup(<Panel {...scene(now, polled, THRESHOLDS)} />));

// 서버 응답 흉내. 위험 판정 전이라 경보 목록이 빔
const answer = (patch: Partial<Snapshot> = {}): Snapshot => ({
  ...demo(AT, THRESHOLDS),  // 예시 응답 바탕
  experimentId: "EXP-20261023-001",  // 실험 번호 고정
  alerts: [],  // 경보 없음
  ...patch,  // 넘겨받은 값으로 덮어씀
});

// 아직 아무 응답도 실패도 없는 상태
const WAITING: Feed = { latest: null, failed: false, history: EMPTY_HISTORY, thresholds: null };
const DOWN: Feed = { ...WAITING, failed: true };  // 한 번도 응답을 못 받고 실패한 상태
// 응답과 받은 시각으로 통신 결과를 만드는 도우미
const feed = (snapshot: Snapshot, receivedAt: number, extra: Partial<Feed> = {}): Feed => ({
  latest: { snapshot, receivedAt },  // 마지막 응답과 받은 시각
  failed: false,  // 실패 없음
  history: entry(EMPTY_HISTORY, snapshot),  // 빈 이력에 이 응답을 더한 이력
  thresholds: CONFIG,  // 서버가 준 한계
  ...extra,  // 추가로 받은 값으로 덮어씀
});

// 어느 화면을 보일지 고르는 테스트 묶음
describe("which screen to show", () => {
  // 시계가 준비되고 첫 응답이나 실패가 있을 때까지 기다리는지 검사
  it("waits until the clock is ready and until the first answer or failure", () => {
    // 시각이 없으면 연결 중
    expect(scene(null, feed(answer(), AT), THRESHOLDS)).toEqual({ view: "connecting" });
    // 응답도 실패도 없으면 연결 중
    expect(scene(AT, WAITING, THRESHOLDS)).toEqual({ view: "connecting" });
  });

  // 서버가 한 번도 답하지 않으면 저장 한계로 예시를 보이는지 검사
  it("shows the mock with the stored thresholds when the server has never answered", () => {
    const now = BASE + 42_400;  // 기준 시각에서 42.4초 뒤
    expect(scene(now, DOWN, THRESHOLDS)).toEqual({  // 예시 화면 정보
      view: "mock",  // 화면 종류는 예시
      now,  // 지금 시각
      snapshot: demo(now, THRESHOLDS),  // 예시 응답
      samples: trail(now),  // 예시 이력
      thresholds: THRESHOLDS,  // 저장 설정의 한계
      receivedAt: null,  // 받은 시각 없음
    });
  });

  // 나중에 읽기가 실패해도 마지막 좋은 응답과 서버 한계를 유지하는지 검사
  it("keeps the last good answer with the server thresholds after later polls fail", () => {
    const body = answer();  // 서버 응답
    const polled = feed(body, AT + 300, { failed: true });  // 0.3초에 받고 이후 실패한 통신 결과
    expect(scene(AT + 9000, polled, THRESHOLDS)).toEqual({  // 9초 뒤에도 서버 화면 정보
      view: "server",  // 화면 종류는 서버
      now: AT + 9000,  // 지금 시각
      snapshot: body,  // 마지막 좋은 응답
      samples: polled.history.samples,  // 쌓인 이력
      thresholds: CONFIG,  // 서버가 준 한계
      receivedAt: AT + 300,  // 마지막 수신 시각
    });
  });

  // 읽기 콜백이 더하기 전에도 보이는 응답을 그래프에 넣는지 검사
  it("charts the shown answer even before the poll callback has added it", () => {
    const body = answer();  // 서버 응답
    // 이력이 비었어도 화면 정보를 구함
    const props = scene(AT, feed(body, AT, { history: EMPTY_HISTORY }), THRESHOLDS);
    // 이력이 지금 응답 하나로 채워짐
    expect(props.view === "server" && props.samples).toEqual([{ t: AT, A: 44.9, B: 31.8, C: 18.7 }]);
  });
});

// 검사 9번과 화면 테스트 묶음
describe("check 9 and the screens", () => {
  // 자료·예시 안내·시각 없는 중립 대기 화면을 미리 그리는지 검사
  it("prerenders a neutral waiting screen with no data, no mock notice and no time", () => {
    const text = content(renderToStaticMarkup(<Home />));  // 첫 화면을 그린 글
    for (const part of ["연결 중", "자료 대기", "—"]) expect(text).toContain(part);  // 대기 문구
    for (const title of TITLES) expect(text).toContain(title);  // 연결 중에도 칸 넷을 그림
    expect(text).not.toContain("가상 데이터");  // 예시 안내 문구 없음
    expect(text).not.toContain("EXP-");  // 실험 번호 없음
    expect(text).not.toContain("가상 실측");  // 출처 문구 없음
    expect(text).not.toMatch(/\d{2}:\d{2}:\d{2}/);  // 시각 모양 글자 없음
  });

  // 서버가 답한 적 없으면 가상 데이터라고 알리는지 검사(검사 9번)
  it("says it is mock data when the server never answered", () => {
    const text = display(DOWN, AT);  // 응답 없는 상태를 그린 글
    expect(text).toContain("가상 데이터(서버 미연결)");  // 가상 데이터 안내
    expect(text).toContain("연결 끊김 · 마지막 수신 —");  // 연결 끊김과 마지막 수신 없음
    expect(text).toContain("A 낮은 상가 도로 · 약 10초 후 침수 예상");  // A 침수 예상 문구
    expect(text).toContain("10:01:10");  // 서울 시각
    expect(text).toContain(demo(AT, THRESHOLDS).experimentId);  // 예시 실험 번호
    // 세 구역 수위 숫자
    for (const value of ["44.9", "31.8", "18.7"]) expect(text).toContain(value);
    // 단계 이름과 출처 문구
    for (const part of ["경계", "가상 실측", "모델 추정"]) expect(text).toContain(part);
  });

  // 서버가 답한 적 없으면 가짜 사건 둘로 타임라인 A 칸과 기록을 채우는지 검사
  it("fills the A timeline and the log with the two mock events", () => {
    const text = display(DOWN, AT);  // 10:01:10 의 mock 장면
    expect(text).toContain(
      "A 낮은 상가 도로 위험 판단 10:00:41 · △ 주의 문자 요청(SMS 예정) 10:01:01 · " +
        "기록만, 실제 발송 차단 실제 도달(경보) — 선행 시간 —",
    );
    expect(text).toContain(
      "이벤트 기록 10:01:01 ▲ A 구역 경계 (이전 주의, 한계까지 10 초) " +
        "10:00:41 △ A 구역 주의 (이전 정상, 한계까지 30 초)",
    );
    expect(text.split(BLANK).length - 1).toBe(2);  // B·C 는 사건 없음
  });

  // 화면 자체 판단이 아닌 서버의 값과 단계를 보이는지 검사
  it("shows the server's values and stages, not the front's own judgement", () => {
    // 0.3초에 받은 응답을 1초 시점에 그린 글
    const text = display(feed(answer(), AT + 300), AT + 1000);
    expect(text).not.toContain("서버 미연결");  // 미연결 안내 없음
    expect(text).toContain("모드 가상");  // 가상 모드 표시
    expect(text).toContain("연결 정상 · 마지막 수신 10:01:10");  // 연결 정상과 마지막 수신 시각
    expect(text).toContain("EXP-20261023-001");  // 서버 실험 번호
    expect(text).toContain("진행 중");  // 진행 중 표시
    expect(text).toContain("44.9");  // A 수위 숫자
    expect(text).toContain("한계 45 mm");  // A 한계
    // A 의 10초 예측이 한계를 넘어도 서버 경보가 비어 있어 정상
    expect(text).toContain("전 구역 정상 · 30초 안에 한계 도달 예상 없음");
    expect(text).not.toMatch(/경계|주의|침수\(경보\)/);  // 화면이 만든 단계 이름 없음
  });

  // 사건을 넘기지 않은 서버 장면은 평면도·장치만 채우고 타임라인·기록은 줄표인지 검사
  it("fills the plan and the devices but leaves the event panels blank without events", () => {
    const text = display(feed(answer(), AT + 300), AT + 1000);
    // 평면도 구역 목록은 서버 alerts 의 단계
    expect(text).toContain("A 낮은 상가 도로 · 44.9 mm · ✓ 정상 · 가상 실측");
    expect(text).toContain("✓ 보호 입력 정상");  // 장치 칸도 서버 상태
    expect(text.split(BLANK).length - 1).toBe(3);  // 세 구역 모두 빈 칸
    expect(text).toContain("이벤트 기록 —");
  });

  // 서버 사건을 넘기면 재생은 지금 경과 초까지만 보이고 live 는 거르지 않는지 검사
  it("hides later events while replaying and keeps all of them in live", () => {
    const events = { list: diary(BASE + 179_000, THRESHOLDS), failed: false };  // 179초까지 여섯
    // 응답을 사건과 함께 그린 글. 이 시험만 Panel 에 events 를 넘김
    const page = (snapshot: Snapshot) => {
      const props = scene(AT + 1000, feed(snapshot, AT + 300), THRESHOLDS);
      return content(renderToStaticMarkup(<Panel {...props} events={events} />));
    };
    const replay = page(answer({ mode: "replay", dataSource: "replay", elapsedSec: 61 }));
    expect(replay).toContain("A 구역 경계 (이전 주의, 한계까지 10 초)");  // 같은 초는 남음
    expect(replay).not.toMatch(/A 구역 침수|B 구역 (주의|경계|침수)/);  // 61초 뒤 사건은 숨김
    const live = page(answer());
    expect(live).toContain("실제 도달(경보) 10:01:11 선행 시간 30초");  // A 판단 41초, 도달 71초
    expect(live).toContain("B 구역 침수 (이전 경계, 한계 도달)");
  });

  // 서버 경보를 보이는지 검사
  it("shows a server alert", () => {
    // B 구역 주의 30초 경보가 든 응답
    const body = answer({ alerts: [{ zone: "B", stage: "caution", etaSec: 30 }] });
    const text = display(feed(body, AT + 300), AT + 1000);  // 그 응답을 그린 글
    expect(text).toContain("B 주택 골목 · 약 30초 후 침수 예상");  // B 침수 예상 문구
    expect(text).toContain("△ 주의");  // 주의 단계 표시
  });

  // 4초 뒤 마지막 값을 두고 연결 끊김을 알리는지 검사
  it("keeps the last values and says the connection is lost after 4 s", () => {
    // 0.3초에 받고 이후 실패한 상태를 4.301초 시점에 그린 글
    const text = display(feed(answer(), AT + 300, { failed: true }), AT + 4301);
    expect(text).toContain("연결 끊김 · 마지막 수신 10:01:10");  // 연결 끊김과 마지막 수신 시각
    expect(text).toContain("44.9");  // 마지막 수위 숫자 유지
    expect(text).not.toContain("서버 미연결");  // 미연결 안내 없음
  });

  // 예측이 유효 기간보다 오래되면 만료로 표시하는지 검사
  it("marks the prediction expired once it is older than its validity", () => {
    const polled = feed(answer(), AT + 300);  // 0.3초에 받은 응답의 통신 결과
    expect(display(polled, AT + 5000)).not.toContain("예측 만료");  // 5초 시점에는 만료 표시 없음
    expect(display(polled, AT + 5001)).toContain("예측 만료");  // 5.001초 시점에는 만료 표시
  });

  // 서버 설정이 오기 전에는 한계를 줄표로 보이는지 검사
  it("shows dashes for the thresholds until the server config arrives", () => {
    // 한계를 모르는 상태를 그린 글
    const text = display(feed(answer(), AT + 300, { thresholds: null }), AT + 1000);
    expect(text.match(/한계 —/g)).toHaveLength(3);  // 세 구역 모두 한계 줄표
    expect(text).not.toContain("한계 45 mm");  // 숫자 한계 없음
  });

  // 실행 상태를 보이는지 검사
  it("shows the run state", () => {
    // 실행 상태만 바꾼 응답을 그린 글
    const state = (runState: Snapshot["runState"]) =>
      display(feed(answer({ runState }), AT + 300), AT + 1000);
    expect(state("idle")).toContain("실험 대기");
    expect(state("stopped")).toContain("실험 정지");  // 비상정지 글에도 정지가 있어 정확한 글로 봄
  });
});
