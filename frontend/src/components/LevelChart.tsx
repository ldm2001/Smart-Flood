import {
  plot,
  columns,
  ZONE_IDS,
  type Prediction,
  type Sample,
  type Thresholds,
} from "@/lib/derive";
import { ZONES } from "@/lib/layout-data";
import type { Zone } from "@/lib/schema";

export const CHART_OPTIONS = { width: 720, height: 300, windowSec: 120, pad: { l: 0, r: 0, t: 12, b: 12 } };

const { width: W, height: H } = CHART_OPTIONS;  // 그림 좌표계의 가로와 세로 크기
const percent = (value: number, whole: number) => `${Math.round((value / whole) * 10000) / 100}%`;

const LABEL_HEIGHT = 28;  // 한계 라벨 한 줄의 좌표 높이(상자가 가장 낮을 때 27 단위라 28)
const LABEL_STEP_REM = 5;  // 라벨 옆 칸 간격(rem). 라벨 폭 약 4.4rem 보다 넓게
const END_HEIGHT = 26;  // 선 끝 글자 하나의 좌표 높이(약 24px)
const END_STEP_REM = 1.75;  // 선 끝 글자 옆 칸 간격(rem). 글자 폭 약 1.4rem 보다 넓게

// 차트가 받는 값
interface Props {
  samples: readonly Sample[];  // 지난 수위 표본들
  predictions: Record<Zone, Prediction> | null;  // 구역별 예측. 없으면 null
  thresholds: Readonly<Thresholds> | null;  // 구역별 한계. 설정을 받기 전에는 null
}

// 수위 변화 차트: 지난 수위는 실선, +30초 예측은 점선, 한계는 가는 점선
export function Chart({ samples, predictions, thresholds }: Props) {
  const chart = plot(samples, predictions, thresholds, CHART_OPTIONS);
  const { thresholdY, nowX, endY } = chart;  // 한계선 높이, 기준 시각 위치, 선 끝 높이를 꺼냄
  const labelColumn = thresholdY && columns(thresholdY, LABEL_HEIGHT);
  const endColumn = endY && columns(endY, END_HEIGHT);  // 가까운 선 끝 글자도 옆 칸으로 나눔

  return (
    <section aria-label="수위 변화" className="panel p-5">
      <h2 className="mb-4 text-xl font-bold">수위 변화</h2>
      {// 눈금 열과 그림 열, 두 칸으로 나눔
      }
      <div className="grid grid-cols-[3rem_1fr] gap-x-3">
        {// 왼쪽 눈금 열(낭독기는 건너뜀)
        }
        <div aria-hidden="true" className="relative h-72 md:h-80">
          {// 눈금 값마다 글자 하나를 그림
          }
          {chart.gridlines.map(({ value, y }) => (
            <span key={value} className="absolute right-0 -translate-y-1/2 text-muted tabular-nums" style={{ top: percent(y, H) }}>
              {value}
            </span>
          ))}
        </div>

        <div className="relative h-72 md:h-80">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            role="img"
            aria-label="구역별 수위 변화와 30초 예측"
            className="absolute inset-0 size-full overflow-visible"
          >
            <g className="stroke-line">
              {// 눈금 값마다 가로선 하나를 그림
              }
              {chart.gridlines.map(({ value, y }) => (
                <line key={value} x1={0} y1={y} x2={W} y2={y} strokeWidth={1} vectorEffect="non-scaling-stroke" />
              ))}
            </g>
            {thresholdY &&
              ZONE_IDS.map((id) => (
                <line
                  key={id}
                  data-zone={id}
                  x1={0}
                  y1={thresholdY[id]}
                  x2={W}
                  y2={thresholdY[id]}
                  className="stroke-(--zone)"
                  strokeWidth={1.5}
                  strokeDasharray="2 6"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
            {nowX !== null && (
              <line x1={nowX} y1={0} x2={nowX} y2={H} className="stroke-muted" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            )}
            {// 구역마다 수위 선 묶음을 그림
            }
            {ZONE_IDS.map((id) => (
              <g key={id} data-zone={id} className="fill-none stroke-(--zone)">
                {chart.measured[id] && (
                  <path d={chart.measured[id]} strokeWidth={3} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                )}
                {chart.isolated[id].map(({ x, y }) => (
                  <path key={x} d={`M ${x} ${y} h 0`} strokeWidth={6} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                ))}
                {chart.predicted[id] && (
                  // +30초 예측 점선
                  <path d={chart.predicted[id]} strokeWidth={2.5} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
                )}
              </g>
            ))}
          </svg>

          {thresholds &&
            thresholdY &&
            labelColumn &&
            ZONE_IDS.map((id) => (  // 한계 라벨은 왼쪽 끝에 모으고, 가까운 것만 옆 칸으로 옮김
              <span
                key={id}
                data-zone={id}
                className="absolute -translate-y-full whitespace-nowrap rounded bg-panel/80 px-1 text-(--zone) tabular-nums"
                style={{ top: percent(thresholdY[id], H), left: `${labelColumn[id] * LABEL_STEP_REM}rem` }}
              >
                {id} 한계 {thresholds[id]}
              </span>
            ))}

          {nowX !== null &&
            endY &&
            endColumn &&
            ZONE_IDS.map((id) => (  // 선 끝 글자는 기준 시각 세로선 바로 왼쪽에 둠
              <span
                key={id}
                data-zone={id}
                data-end=""
                aria-hidden="true"
                className="absolute -translate-x-full -translate-y-1/2 rounded border-2 border-(--zone) bg-panel px-1 font-bold leading-tight text-(--zone)"
                style={{ top: percent(endY[id], H), left: `calc(${percent(nowX, W)} - ${0.25 + endColumn[id] * END_STEP_REM}rem)` }}
              >
                {id}
              </span>
            ))}

          {nowX === null && (
            <p className="absolute inset-0 grid place-items-center text-lg text-muted">수위 자료 대기</p>
          )}
        </div>

        <div />
        {// 시간 눈금 줄(낭독기는 건너뜀)
        }
        <div aria-hidden="true" className="relative mt-1 h-7 whitespace-nowrap text-muted">
          {nowX !== null && (
            <>
              {// 왼쪽 끝은 2분 전
              }
              <span className="absolute left-0">−{CHART_OPTIONS.windowSec / 60}분</span>
              {// 기준 시각 라벨은 세로선 왼쪽에 붙여 +30초와 겹치지 않게 함
              }
              <span className="absolute -translate-x-full pr-1" style={{ left: percent(nowX, W) }}>
                기준 시각
              </span>
              <span className="absolute right-0">+30초</span>
            </>
          )}
        </div>
      </div>

      <ul className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        {ZONE_IDS.map((id) => (
          <li key={id} data-zone={id} className="flex items-center gap-2">
            <span aria-hidden="true" className="h-1 w-6 rounded-full bg-(--zone)" />
            {id} {ZONES[id].name}
          </li>
        ))}
        <li className="text-muted">실선 지난 수위 · 점선 예측 · 가는 점선 한계</li>
        {// 단위 설명
        }
        <li className="text-muted">단위 mm</li>
      </ul>
    </section>
  );
}
