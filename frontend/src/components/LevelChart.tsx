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

// 차트 크기, 시간 창(지난 2분), 여백
export const CHART_OPTIONS = { width: 720, height: 300, windowSec: 120, pad: { l: 0, r: 0, t: 12, b: 12 } };

const { width: W, height: H } = CHART_OPTIONS;  // 그림 좌표계의 가로와 세로 크기
// 좌표를 상자 대비 퍼센트 글자로 변환
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
  // 표본을 그림 좌표의 선으로 변환
  const chart = plot(samples, predictions, thresholds, CHART_OPTIONS);
  const { thresholdY, nowX, endY } = chart;  // 한계선 높이, 기준 시각 위치, 선 끝 높이를 꺼냄
  // 가까운 한계 라벨은 옆 칸으로 나눈다
  const labelColumn = thresholdY && columns(thresholdY, LABEL_HEIGHT);
  const endColumn = endY && columns(endY, END_HEIGHT);  // 가까운 선 끝 글자도 옆 칸으로 나눈다

  return (  // 화면에 그릴 내용을 반환
    // 차트 구획
    <section aria-label="수위 변화" className="panel p-5">
      {// 제목
      }
      <h2 className="mb-4 text-xl font-bold">수위 변화</h2>
      {// 눈금 열과 그림 열, 두 칸으로 나눈다
      }
      <div className="grid grid-cols-[3rem_1fr] gap-x-3">
        {// 왼쪽 눈금 열(낭독기는 건너뛴다)
        }
        <div aria-hidden="true" className="relative h-72 md:h-80">
          {// 눈금 값마다 글자 하나를 그린다
          }
          {chart.gridlines.map(({ value, y }) => (
            // 눈금 글자를 해당 높이에 놓는다
            <span key={value} className="absolute right-0 -translate-y-1/2 text-muted tabular-nums" style={{ top: percent(y, H) }}>
              {// 눈금 값
              }
              {value}
            </span>
          ))}
        </div>

        {// 오른쪽 그림 열
        }
        <div className="relative h-72 md:h-80">
          {// 그림 틀을 연다
          }
          <svg
            viewBox={`0 0 ${W} ${H}`}  // 좌표계 크기
            preserveAspectRatio="none"  // 상자에 맞춰 늘인다
            role="img"  // 그림으로 읽히게
            aria-label="구역별 수위 변화와 30초 예측"  // 낭독용 설명
            className="absolute inset-0 size-full overflow-visible"  // 상자를 꽉 채운다
          >
            {// 가로 눈금선 묶음
            }
            <g className="stroke-line">
              {// 눈금 값마다 가로선 하나를 그린다
              }
              {chart.gridlines.map(({ value, y }) => (
                // 가로선. 늘려도 굵기는 화면 픽셀로 고결정
                <line key={value} x1={0} y1={y} x2={W} y2={y} strokeWidth={1} vectorEffect="non-scaling-stroke" />
              ))}
            </g>
            {// 한계선 높이를 알면
            }
            {thresholdY &&
              ZONE_IDS.map((id) => (  // 구역마다 한계선을 그린다
                <line  // 한계선 하나를 연다
                  key={id}  // 구역을 키로 기록
                  data-zone={id}  // 구역 속성
                  x1={0}  // 왼쪽 끝에서 시작해
                  y1={thresholdY[id]}  // 한계 높이에서
                  x2={W}  // 오른쪽 끝까지
                  y2={thresholdY[id]}  // 같은 높이로 긋는다
                  className="stroke-(--zone)"  // 구역 색
                  strokeWidth={1.5}  // 선 굵기
                  strokeDasharray="2 6"  // 가는 점선
                  vectorEffect="non-scaling-stroke"  // 늘려도 굵기를 유지
                />
              ))}
            {// 기준 시각이 있으면
            }
            {nowX !== null && (
              // 기준 시각 세로선
              <line x1={nowX} y1={0} x2={nowX} y2={H} className="stroke-muted" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            )}
            {// 구역마다 수위 선 묶음을 그린다
            }
            {ZONE_IDS.map((id) => (
              // 구역 색 선 묶음
              <g key={id} data-zone={id} className="fill-none stroke-(--zone)">
                {// 실측 선이 있으면
                }
                {chart.measured[id] && (
                  // 지난 수위 실선
                  <path d={chart.measured[id]} strokeWidth={3} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                )}
                {// 이어지지 않는 외톨이 표본마다
                }
                {chart.isolated[id].map(({ x, y }) => (
                  // 점 하나(길이 0 선에 둥근 끝)
                  <path key={x} d={`M ${x} ${y} h 0`} strokeWidth={6} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                ))}
                {// 예측 선이 있으면
                }
                {chart.predicted[id] && (
                  // +30초 예측 점선
                  <path d={chart.predicted[id]} strokeWidth={2.5} strokeDasharray="8 6" vectorEffect="non-scaling-stroke" />
                )}
              </g>
            ))}
          </svg>

          {// 한계를 알면
          }
          {thresholds &&
            thresholdY &&  // 한계선 높이도 알면
            labelColumn &&  // 라벨 칸도 정해졌으면
            ZONE_IDS.map((id) => (  // 한계 라벨은 왼쪽 끝에 모으고, 가까운 것만 옆 칸으로 옮긴다
              <span  // 한계 라벨 하나를 연다
                key={id}  // 구역을 키로 기록
                data-zone={id}  // 구역 속성
                // 한계선 위에 놓이는 라벨 모양
                className="absolute -translate-y-full whitespace-nowrap rounded bg-panel/80 px-1 text-(--zone) tabular-nums"
                // 한계선 높이와 옆 칸 위치에 놓는다
                style={{ top: percent(thresholdY[id], H), left: `${labelColumn[id] * LABEL_STEP_REM}rem` }}
              >
                {// 라벨 글자
                }
                {id} 한계 {thresholds[id]}
              </span>
            ))}

          {// 기준 시각이 있고
          }
          {nowX !== null &&
            endY &&  // 선 끝 높이를 알고
            endColumn &&  // 글자 칸이 정해졌으면
            ZONE_IDS.map((id) => (  // 선 끝 글자는 기준 시각 세로선 바로 왼쪽에 둔다
              <span  // 선 끝 글자 하나를 연다
                key={id}  // 구역을 키로 기록
                data-zone={id}  // 구역 속성
                data-end=""  // 선 끝 글자 표시
                aria-hidden="true"  // 낭독기는 건너뛴다
                // 구역 색 테두리 글자 모양
                className="absolute -translate-x-full -translate-y-1/2 rounded border-2 border-(--zone) bg-panel px-1 font-bold leading-tight text-(--zone)"
                // 선 끝 높이와 세로선 왼쪽 위치에 놓는다
                style={{ top: percent(endY[id], H), left: `calc(${percent(nowX, W)} - ${0.25 + endColumn[id] * END_STEP_REM}rem)` }}
              >
                {// 구역 글자
                }
                {id}
              </span>
            ))}

          {// 기준 시각이 없으면
          }
          {nowX === null && (
            // 가운데에 대기 안내를 보여 반환
            <p className="absolute inset-0 grid place-items-center text-lg text-muted">수위 자료 대기</p>
          )}
        </div>

        {// 눈금 열 아래 빈칸
        }
        <div />
        {// 시간 눈금 줄(낭독기는 건너뛴다)
        }
        <div aria-hidden="true" className="relative mt-1 h-7 whitespace-nowrap text-muted">
          {// 기준 시각이 있으면
          }
          {nowX !== null && (
            // 시간 눈금 셋을 한 묶음으로 기록
            <>
              {// 왼쪽 끝은 2분 전
              }
              <span className="absolute left-0">−{CHART_OPTIONS.windowSec / 60}분</span>
              {// 기준 시각 라벨은 세로선 왼쪽에 붙여 +30초와 겹치지 않게 한다
              }
              <span className="absolute -translate-x-full pr-1" style={{ left: percent(nowX, W) }}>
                {// 라벨 글자
                }
                기준 시각
              </span>
              {// 오른쪽 끝은 +30초
              }
              <span className="absolute right-0">+30초</span>
            </>
          )}
        </div>
      </div>

      {// 범례 목록
      }
      <ul className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        {// 구역마다 범례 한 칸을 그린다
        }
        {ZONE_IDS.map((id) => (
          // 범례 한 칸
          <li key={id} data-zone={id} className="flex items-center gap-2">
            {// 구역 색 짧은 선
            }
            <span aria-hidden="true" className="h-1 w-6 rounded-full bg-(--zone)" />
            {// 구역 글자와 이름
            }
            {id} {ZONES[id].name}
          </li>
        ))}
        {// 선 모양 설명
        }
        <li className="text-muted">실선 지난 수위 · 점선 예측 · 가는 점선 한계</li>
        {// 단위 설명
        }
        <li className="text-muted">단위 mm</li>
      </ul>
    </section>
  );
}
