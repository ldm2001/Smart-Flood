"use client";
import {
  entry,
  caption,
  clock,
  expiry,
  roster,
  ZONE_IDS,
  type Sample,
  type Thresholds,
} from "@/lib/derive";
import { RUN_STATE_ICONS, RUN_STATE_LABELS } from "@/lib/layout-data";
import { trail, demo } from "@/lib/mock";
import type { Snapshot } from "@/lib/schema";
import { useNow } from "@/lib/useNow";
import { useSettings } from "@/lib/useSettings";
import { useSnapshot, type Feed } from "@/lib/useSnapshot";
import { Signal } from "./ConnectionBadge";
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
    };
  }
  return {  // 한 번이라도 답했으면 끊겨도 마지막 정상 값을 보임
    view: "server",
    now,
    snapshot: latest.snapshot,  // 마지막 정상 상태. 단계·eta 는 서버 alerts 만 따름
    samples: entry(polled.history, latest.snapshot).samples,  // 차트 끝과 게이지 일치용 현재값 추가
    thresholds: polled.thresholds,  // 서버 설정의 한계 수위. 받기 전에는 null
    receivedAt: latest.receivedAt,
  };
}

// 관제 화면. 서버 상태를 읽어 Panel 에 넘김
export function Monitor() {
  const now = useNow();
  const polled = useSnapshot();
  const { thresholds } = useSettings();  // 가짜 화면용 한계 수위를 설정에서 읽음
  return <Panel {...scene(now, polled, thresholds)} />;
}

// 장면을 받아 화면을 그리는 컴포넌트
export function Panel(props: Scene) {
  const data = props.view === "connecting" ? null : props;
  const snapshot = data?.snapshot ?? null;
  const statuses = snapshot ? roster(snapshot.alerts) : null;  // 서버 alerts 로 구역별 단계를 구
  const banner = snapshot && statuses ? caption(statuses, snapshot.zones) : null;
  const meta = snapshot?.predictionMeta;  // 예측 기준 정보(기준 시각·유효 초)
  const expired = data !== null && meta ? expiry(data.now, Date.parse(meta.basisTime), meta.validForSec) : false;
  const runState = snapshot?.runState;

  return (
    <main className="mx-auto w-full max-w-[1800px] px-4 py-6 md:px-8 md:py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">A·B·C 구역 침수 모형</p>
          <h1 className="mt-1 text-3xl font-black tracking-tight">종합 관제</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {// 입력원 표시(mock 이면 가짜 표시)
          }
          <Mode dataSource={snapshot?.dataSource ?? null} mock={props.view === "mock"} />
          <Signal view={props.view} now={data?.now ?? null} receivedAt={data?.receivedAt ?? null} />
          {runState && (
            <span className="pill">
              {// 상태 아이콘(낭독기는 건너뜀)
              }
              <span aria-hidden="true">{RUN_STATE_ICONS[runState]}</span>
              실험 {RUN_STATE_LABELS[runState]}
            </span>
          )}
          <span className="pill">{snapshot?.experimentId ?? "—"}</span>
          <span className="text-muted tabular-nums">
            {// 서버 상태의 기준 시각. 없으면 줄표
            }
            기준 시각 {snapshot ? clock(Date.parse(snapshot.timestamp)) : "—"}
          </span>
          {expired && (
            <span className="pill border border-amber bg-transparent text-amber">
              {// 경고 아이콘(낭독기는 건너뜀)
              }
              <span aria-hidden="true">{"⚠︎"}</span>
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
    </main>
  );
}
