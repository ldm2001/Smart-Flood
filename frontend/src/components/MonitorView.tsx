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

// 보여 줄 장면 타입. 연결 중이거나 값이 있는 장면이다
export type Scene =
  | { view: "connecting" }  // 연결 중: 시계나 첫 응답이 아직이라 값 자리는 줄표다
  | {  // 값이 있는 장면을 연다
      view: "mock" | "server";  // mock 은 가짜 값, server 는 실제 서버 값이다
      now: number;  // 지금 시각(ms)
      snapshot: Snapshot;  // 보여 줄 서버 상태
      samples: readonly Sample[];  // 차트에 그릴 표본 이력
      thresholds: Readonly<Thresholds> | null;  // 구역별 한계 수위. 모르면 null
      receivedAt: number | null;  // 마지막으로 받은 시각(ms). mock 이면 null
    };

// 장면을 고르는 순수 함수. 시각은 인자로 받음
export function scene(now: number | null, polled: Feed, mockThresholds: Readonly<Thresholds>): Scene {
  const { latest } = polled;  // 마지막 정상 응답을 꺼냄
  // 시계나 첫 응답이 아직이면 연결 중으로 둔다
  if (now === null || (latest === null && !polled.failed)) return { view: "connecting" };
  if (latest === null) {  // 응답 없이 첫 시도가 실패했으면
    return {  // mock 장면을 반환
      view: "mock",  // 가짜 값 장면 표시
      now,  // 지금 시각을 담는다
      snapshot: demo(now, mockThresholds),  // 가짜 상태. 경보는 계산 도구와 같은 규칙으로 만듦
      samples: trail(now),  // 가짜 표본 이력
      thresholds: mockThresholds,  // 가짜 화면용 한계 수위
      receivedAt: null,  // 받은 적이 없으니 비워 둔다
    };
  }
  return {  // 한 번이라도 답했으면 끊겨도 마지막 정상 값을 보인다
    view: "server",  // 서버 값 장면 표시
    now,  // 지금 시각을 담는다
    snapshot: latest.snapshot,  // 마지막 정상 상태. 단계·eta 는 서버 alerts 만 따름
    // 지금 응답을 이력에 한 번 더 넣어 차트 끝을 게이지와 맞춤
    samples: entry(polled.history, latest.snapshot).samples,
    thresholds: polled.thresholds,  // 서버 설정의 한계 수위. 받기 전에는 null
    receivedAt: latest.receivedAt,  // 마지막으로 받은 시각
  };
}

// 관제 화면. 서버 상태를 읽어 Panel 에 넘긴다
export function Monitor() {
  const now = useNow();  // 현재 시각을 구독
  const polled = useSnapshot();  // 서버 상태 읽기 결과를 구독
  const { thresholds } = useSettings();  // 가짜 화면용 한계 수위를 설정에서 읽음
  return <Panel {...scene(now, polled, thresholds)} />;  // 장면을 골라 Panel 로 그린다
}

// 장면을 받아 화면을 그리는 컴포넌트
export function Panel(props: Scene) {
  const data = props.view === "connecting" ? null : props;  // 연결 중이면 값이 없다
  const snapshot = data?.snapshot ?? null;  // 보여 줄 상태. 없으면 null
  const statuses = snapshot ? roster(snapshot.alerts) : null;  // 서버 alerts 로 구역별 단계를 구
  // 구역별 단계로 맨 위 문구를 만듦
  const banner = snapshot && statuses ? caption(statuses, snapshot.zones) : null;
  const meta = snapshot?.predictionMeta;  // 예측 기준 정보(기준 시각·유효 초)
  // 예측 유효 시간이 지났는지 렌더 중에 구
  const expired = data !== null && meta ? expiry(data.now, Date.parse(meta.basisTime), meta.validForSec) : false;
  const runState = snapshot?.runState;  // 실험 진행 상태

  return (  // 화면에 그릴 내용을 반환
    // 본문 영역을 연다(폭은 최대 1800px)
    <main className="mx-auto w-full max-w-[1800px] px-4 py-6 md:px-8 md:py-8">
      {// 머리 영역을 연다
      }
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        {// 제목 묶음
        }
        <div>
          {// 작은 위 제목
          }
          <p className="eyebrow">A·B·C 구역 침수 모형</p>
          {// 큰 제목
          }
          <h1 className="mt-1 text-3xl font-black tracking-tight">종합 관제</h1>
        </div>
        {// 상태 표시 묶음
        }
        <div className="flex flex-wrap items-center gap-2">
          {// 입력원 표시(mock 이면 가짜 표시)
          }
          <Mode dataSource={snapshot?.dataSource ?? null} mock={props.view === "mock"} />
          {// 연결 상태 표시
          }
          <Signal view={props.view} now={data?.now ?? null} receivedAt={data?.receivedAt ?? null} />
          {// 실험 상태가 있을 때만
          }
          {runState && (
            // 실험 상태 알약
            <span className="pill">
              {// 상태 아이콘(낭독기는 건너뛴다)
              }
              <span aria-hidden="true">{RUN_STATE_ICONS[runState]}</span>
              {// 실험 상태 이름
              }
              실험 {RUN_STATE_LABELS[runState]}
            </span>
          )}
          {// 실험 번호. 없으면 줄표
          }
          <span className="pill">{snapshot?.experimentId ?? "—"}</span>
          {// 기준 시각 글자 칸
          }
          <span className="text-muted tabular-nums">
            {// 서버 상태의 기준 시각. 없으면 줄표
            }
            기준 시각 {snapshot ? clock(Date.parse(snapshot.timestamp)) : "—"}
          </span>
          {// 예측이 만료됐을 때만
          }
          {expired && (
            // 만료 알약
            <span className="pill border border-amber bg-transparent text-amber">
              {// 경고 아이콘(낭독기는 건너뛴다)
              }
              <span aria-hidden="true">{"⚠︎"}</span>
              {// 만료 문구
              }
              예측 만료
            </span>
          )}
        </div>
      </header>

      {// 가장 높은 경보 단계 머리글
      }
      <Headline banner={banner} />

      {// 구역별 수위 카드 묶음(넓으면 3칸)
      }
      <section aria-label="구역별 현재 수위" className="mb-6 grid gap-4 md:grid-cols-3">
        {// 구역마다 카드를 그린다
        }
        {ZONE_IDS.map((id) => (
          <Gauge  // 구역 카드를 연다
            key={id}  // 구역 이름을 키로 기록
            zoneId={id}  // 구역 이름
            zone={snapshot?.zones[id] ?? null}  // 현재 수위와 출처
            prediction={snapshot?.predictions[id] ?? null}  // +10·20·30초 예측 수위
            thresholdMm={data?.thresholds?.[id] ?? null}  // 한계 수위(mm)
            status={statuses?.[id] ?? null}  // 서버가 알린 경보 단계
          />
        ))}
      </section>

      {// 수위 차트
      }
      <Chart
        samples={data?.samples ?? []}  // 그릴 표본 이력
        predictions={snapshot?.predictions ?? null}  // 구역별 예측 수위
        thresholds={data?.thresholds ?? null}  // 구역별 한계 수위
      />
    </main>
  );
}
