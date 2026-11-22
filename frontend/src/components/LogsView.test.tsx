import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Logs from "@/app/logs/page";
import { gates, halt, linkage, pass, rerun, stamp, type Stage } from "@/lib/derive";
import { demo } from "@/lib/mock";
import type { Log, Notifier, Snapshot, StageEvent, Zone } from "@/lib/schema";
import { Timeline } from "./AlertTimeline";
import { Shelf, type Stack } from "./LogsView";

// 아이콘 SVG 를 [이름] 글로 바꾸고 태그를 빼 공백을 하나로 줄여 글만 남기는 도우미
const content = (html: string) =>
  html
    .replace(/<svg[^>]*data-icon="([^"]+)"[^>]*>[\s\S]*?<\/svg>/g, " [$1] ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
const T0 = Date.UTC(2026, 9, 22, 1, 0, 0);  // 회차 시작 시각(2026-10-22 10:00 KST)
const ID = "EXP-20261022-001";
const LOGS: Log[] = [  // 기록 목록 두 줄
  {
    experimentId: ID,
    startTime: "2026-10-22T10:00:00.000+09:00",
    dataSource: "sim",
    modelVersion: "0.1-assumed",
    configHash: "abc123",
  },
  {
    experimentId: "EXP-20261022-002",
    startTime: "2026-10-22T11:30:05.000+09:00",
    dataSource: "sim",
    modelVersion: "0.1-assumed",
    configHash: "abc123",
  },
];

// 경과 e 초에 구역이 previous 에서 stage 로 바뀐 사건
function shift(e: number, zone: Zone, previous: Stage, stage: Stage, etaSec: number | null) {
  return {
    type: "event",
    kind: "stage",
    elapsedSec: e,
    time: stamp(T0 + e * 1000),
    message: `${zone} 구역 ${stage} (이전 ${previous})`,
    zone,
    stage,
    previous,
    etaSec,
  } as const satisfies StageEvent;
}

const EVENTS = [shift(100, "B", "safe", "warning", 10), shift(113, "B", "warning", "evacuate", 0)];

// 연결된 화면의 몸통 값. extra 로 바꿀 칸만 줌
function stack(extra: Partial<Stack> = {}): Stack {
  const snapshot: Snapshot = { ...demo(T0, { A: 45, B: 55, C: 65 }), runState: "idle" };
  const link = linkage(T0, T0, false);
  const replay = pass(gates(link, T0, snapshot, null).replay, rerun(snapshot, ID));
  return {
    now: T0,
    link,
    halt: halt(link, T0),
    receivedAt: T0,
    failed: false,
    snapshot,
    logs: LOGS,
    missing: false,
    id: ID,
    events: EVENTS,
    lost: false,
    gate: replay,
    open: false,
    sending: null,
    delivery: null,
    onPress: () => undefined,
    ...extra,
  };
}

describe("Shelf", () => {
  it("lists the records with links by query and marks the chosen one", () => {
    const html = renderToStaticMarkup(<Shelf {...stack()} />);
    // 시험에서는 trailingSlash 설정이 없어 Link 가 끝의 / 를 뺌. 빌드에서는 /logs/?id= 꼴
    expect(html).toMatch(new RegExp(`href="/logs/?\\?id=${ID}"`));
    expect(html).toMatch(/href="\/logs\/?\?id=EXP-20261022-002"/);
    expect(html.match(/aria-current="true"/g)).toHaveLength(1);
    expect(content(html)).toContain(`${ID} 10:00:00 입력원 가상`);
  });

  it("shows the record head, the replay button, the comparison and the timeline", () => {
    const text = content(renderToStaticMarkup(<Shelf {...stack()} />));
    expect(text).toContain(`실험 번호 ${ID} 시작 시각 10:00:00 입력원 가상 모델 버전 0.1-assumed`);
    expect(text).toContain("[play] 이 기록 재생");
    expect(text).toContain("구역 위험 판단 예측 도달 실제 도달 선행 시간 오차");
    expect(text).toContain("B 주택 골목 10:01:40 10:01:50 10:01:53 13초 +3초");
    expect(text).toContain("A 낮은 상가 도로 — — — — —");
    expect(text).toContain("위험 판단·시험용 문자");
    expect(text).not.toContain("주의보");
  });

  it("says when there are no records and asks to pick one", () => {
    const text = content(renderToStaticMarkup(<Shelf {...stack({ logs: [], id: null })} />));
    expect(text).toContain("저장된 실험 기록이 없습니다.");
    expect(text).toContain("목록에서 기록을 고르면 비교 표와 재생 단추가 나옵니다.");
    expect(text).not.toContain("이 기록 재생");
  });

  it("shows the read error line and an unknown record", () => {
    const broken = stack({ logs: null, missing: true });  // 목록 읽기 실패
    const failed = content(renderToStaticMarkup(<Shelf {...broken} />));
    expect(failed).toContain("[error] 실험 기록을 읽지 못했습니다");
    const gone = content(renderToStaticMarkup(<Shelf {...stack({ id: "EXP-20261022-009" })} />));
    expect(gone).toContain("고른 실험 기록이 목록에 없습니다.");
    expect(gone).not.toContain("이 기록 재생");
  });

  it("keeps the button reachable but off with the halt line in mock", () => {
    const link = linkage(T0, null, true);
    const gate = gates(link, null, null, null).replay;
    const html = renderToStaticMarkup(
      <Shelf
        {...stack({ link, halt: halt(link, null), receivedAt: null, snapshot: null, gate })}
      />,
    );
    expect(html).toContain('aria-describedby="ops-halt"');
    expect(html).toContain('aria-disabled="true"');
    expect(content(html)).toContain("가상 데이터에는 보내지 않습니다");
  });

  it("opens the in-panel check and links to the monitor after a replay is applied", () => {
    const open = content(renderToStaticMarkup(<Shelf {...stack({ open: true })} />));
    expect(open).toContain("이 기록을 처음부터 재생할까요?");
    expect(open).toContain("예 취소");
    const played = { ...demo(T0, { A: 45, B: 55, C: 65 }), dataSource: "replay" as const };
    const receipt = { snapshot: { ...played, experimentId: ID }, receivedAt: T0 };
    const answer = { ok: true as const, receipt };  // 반영된 응답
    const delivery = { control: "replay" as const, answer, replay: false };
    const html = renderToStaticMarkup(<Shelf {...stack({ delivery })} />);
    expect(content(html)).toContain(
      `[check] 반영 · 재생 시작 · ${ID} · 10:00:00 수신 종합 관제에서 보기`,
    );
    expect(html).toContain('href="/"');
  });

  it("prerenders the page as connecting with the replay button off", () => {
    const text = content(renderToStaticMarkup(<Logs />));
    expect(text).toContain("기록·재생");
    expect(text).toContain("서버에 연결하는 중이라 제어를 끕니다");
  });
});

describe("Timeline notifier", () => {
  it("names real sending only for an armed sms notifier", () => {
    const log = { list: EVENTS, failed: false };
    const plain = content(renderToStaticMarkup(<Timeline log={log} />));
    expect(plain).toContain("기록만, 실제 발송 차단");
    const view = (notifier: Notifier) =>
      content(renderToStaticMarkup(<Timeline log={log} notifier={notifier} />));
    const stub = view({ mode: "stub", armed: true });
    expect(stub).toContain("기록만, 실제 발송 차단");
    const armed = view({ mode: "sms", armed: true });
    expect(armed).toContain("실제 발송 켜짐, 허용 번호만");
    expect(armed).not.toContain("실제 발송 차단");
    const past = content(
      renderToStaticMarkup(<Timeline log={log} notifier={{ mode: "sms", armed: true }} past />),
    );
    expect(past).toContain("발송 결과는 서버 로그에만 남음");
    expect(past).not.toContain("실제 발송 켜짐");
  });
});
