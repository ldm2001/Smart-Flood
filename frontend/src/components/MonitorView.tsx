"use client";
import {
  entry,
  caption,
  clock,
  expiry,
  roster,
  scope,
  ZONE_IDS,
  type Sample,
  type Thresholds,
} from "@/lib/derive";
import { RUN_STATE_ICONS, RUN_STATE_LABELS } from "@/lib/layout-data";
import { trail, demo, diary } from "@/lib/mock";
import type { Snapshot } from "@/lib/schema";
import { useEvents, type Events } from "@/lib/useEvents";
import { useNow } from "@/lib/useNow";
import { useSettings } from "@/lib/useSettings";
import { useSnapshot, type Feed } from "@/lib/useSnapshot";
import { Timeline } from "./AlertTimeline";
import { Plan } from "./CityPlan";
import { Signal } from "./ConnectionBadge";
import { Devices } from "./DeviceStatus";
import { Journal } from "./EventLog";
import { Glyph } from "./Glyph";
import { Chart } from "./LevelChart";
import { Mode } from "./ModeBadge";
import { Headline } from "./StatusBanner";
import { Gauge } from "./ZoneGauge";

// 보여 줄 장면 타입. 연결 중이거나 값이 있는 장면
export type Scene =
  | { view: "connecting" }  // 연결 중: 시계나 첫 응답이 아직이라 값 자리는 줄표
  | {
      view: "mock" | "server";  // mock 은 가짜 값, server 는 실제 서버 값
      now: number;  // 지금 시각(ms)
      snapshot: Snapshot;
      samples: readonly Sample[];
      thresholds: Readonly<Thresholds> | null;
      receivedAt: number | null;  // 마지막으로 받은 시각(ms). mock 이면 null
      failed: boolean;  // 마지막 폴링이 실패했는가. mock 은 늘 참
    };

// 장면을 고르는 순수 함수. 시각은 인자로 받음
export function scene(now: number | null, polled: Feed, mockThresholds: Readonly<Thresholds>): Scene {
  const { latest } = polled;
  if (now === null || (latest === null && !polled.failed)) return { view: "connecting" };
  if (latest === null) {  // 응답 없이 첫 시도가 실패했으면
    return {  // mock 장면을 반환
      view: "mock",
      now,
      snapshot: demo(now, mockThresholds),  // 가짜 상태. 경보는 계산 도구와 같은 규칙으로 만듦
      samples: trail(now),
      thresholds: mockThresholds,
      receivedAt: null,
      failed: true,
    };
  }
  return {  // 한 번이라도 답했으면 끊겨도 마지막 정상 값을 보임
    view: "server",
    now,
    snapshot: latest.snapshot,  // 마지막 정상 상태. 단계·eta 는 서버 alerts 만 따름
    samples: entry(polled.history, latest.snapshot).samples,  // 차트 끝과 게이지 일치용 현재값 추가
    thresholds: polled.thresholds,  // 서버 설정의 한계 수위. 받기 전에는 null
    receivedAt: latest.receivedAt,
    failed: polled.failed,
  };
}

// 관제 화면. 서버 상태와 사건을 읽어 Panel 에 넘김
export function Monitor() {
  const now = useNow();
  const polled = useSnapshot();
  const { thresholds } = useSettings();  // 가짜 화면용 한계 수위를 설정에서 읽음
  const events = useEvents(polled.latest?.snapshot ?? null);  // 서버 상태가 있을 때만 사건을 읽음
  return <Panel {...scene(now, polled, thresholds)} events={events} />;
}

// 장면을 받아 화면을 그리는 컴포넌트. 사건은 Monitor 가 넘김
export function Panel(props: Scene & { events?: Events }) {
  const data = props.view === "connecting" ? null : props;
  const snapshot = data?.snapshot ?? null;
  const statuses = snapshot ? roster(snapshot.alerts) : null;  // 서버 alerts 로 구역별 단계를 구함
  const banner = snapshot && statuses ? caption(statuses, snapshot.zones) : null;
  const meta = snapshot?.predictionMeta;  // 예측 기준 정보(기준 시각·유효 초)
  const expired = data !== null && meta ? expiry(data.now, Date.parse(meta.basisTime), meta.validForSec) : false;
  const runState = snapshot?.runState;
  const events =  // mock 은 가짜 사건, server 는 읽은 사건
    data === null
      ? null
      : data.view === "mock"
        ? data.thresholds
          ? { list: diary(data.now, data.thresholds), failed: false }
          : null
        : (props.events ?? null);
  const log = events && snapshot  // 재생 중이면 지금 경과 초까지만
    ? { failed: events.failed, list: events.list && scope(events.list, snapshot) }
    : null;

  return (
    <main className="mx-auto w-full max-w-[1600px] px-4 py-6 md:px-8 md:py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-soft">A·B·C 구역 침수 모형</p>
          <h1 className="mt-1 text-3xl font-semibold">종합 관제</h1>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {// 입력원 표시(mock 이면 가짜 표시)
          }
          <Mode dataSource={snapshot?.dataSource ?? null} mock={props.view === "mock"} />
          <Signal
            view={props.view}
            now={data?.now ?? null}
            receivedAt={data?.receivedAt ?? null}
            failed={data?.failed ?? false}
          />
          {runState && (
            <span className="chip">
              <Glyph name={RUN_STATE_ICONS[runState]} />
              실험 {RUN_STATE_LABELS[runState]}
            </span>
          )}
          <span className="font-mono text-muted">{snapshot?.experimentId ?? "—"}</span>
          <span className="text-muted">
            {// 서버 상태의 기준 시각. 없으면 줄표
            }
            기준 시각{" "}
            <span className="font-mono text-soft tabular-nums">
              {snapshot ? clock(Date.parse(snapshot.timestamp)) : "—"}
            </span>
          </span>
          {expired && (
            <span className="chip border border-amber bg-transparent text-amber">
              <Glyph name="clock" />
              예측 만료
            </span>
          )}
        </div>
      </header>

      <Headline banner={banner} />

      {// 구역별 수위 카드 묶음(넓으면 3칸)
      }
      <section aria-label="구역별 현재 수위" className="mb-6 grid gap-4 md:grid-cols-3">
        {ZONE_IDS.map((id) => (
          <Gauge
            key={id}
            zoneId={id}
            zone={snapshot?.zones[id] ?? null}
            prediction={snapshot?.predictions[id] ?? null}  // +10·20·30초 예측 수위
            thresholdMm={data?.thresholds?.[id] ?? null}  // 한계 수위(mm)
            status={statuses?.[id] ?? null}
          />
        ))}
      </section>

      <Chart
        samples={data?.samples ?? []}
        predictions={snapshot?.predictions ?? null}
        thresholds={data?.thresholds ?? null}
      />
      <div className="mt-6 grid gap-4 md:grid-cols-[7fr_5fr] md:items-start">
        <Plan snapshot={snapshot} statuses={statuses} thresholds={data?.thresholds ?? null} />
        <Devices snapshot={snapshot} />
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Timeline
          log={log}
          notifier={snapshot?.notifier ?? null}
          past={snapshot?.dataSource === "replay"}
        />
        <Journal log={log} />
      </div>
    </main>
  );
}
