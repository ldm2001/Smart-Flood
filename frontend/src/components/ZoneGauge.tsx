import {
  phrase,
  figure,
  fraction,
  HORIZON_KEYS,
  share,
  type Prediction,
  type Grade,
} from "@/lib/derive";
import { SOURCE_LABELS, STAGE_ICONS, STAGE_LABELS, ZONES } from "@/lib/layout-data";
import type { Zone, Source } from "@/lib/schema";

// 카드가 받는 값. 단계와 eta 는 서버 alerts 의 status 만 기록
interface Props {
  zoneId: Zone;  // 구역 이름(A·B·C)
  zone: { levelMm: number; source: Source } | null;  // 현재 수위(mm)와 출처. 아직 없으면 null
  prediction: Prediction | null;  // +10·20·30초 예측 수위. 없으면 null
  thresholdMm: number | null;  // 한계 수위(mm). 설정을 받기 전에는 null
  status: Grade | null;  // 서버가 알린 경보 단계. 없으면 null
}

// 비율(0~1)을 CSS 퍼센트 글자로 변환
const width = (ratio: number) => `${Math.round(ratio * 10000) / 100}%`;

// 구역 카드. 한계를 모르면 게이지 막대를 그리지 않음
export function Gauge({ zoneId, zone, prediction, thresholdMm, status }: Props) {
  const eta = status && phrase(status);  // 단계가 있으면 도달 문구를 만듦
  return (  // 화면에 그릴 내용을 반환
    <article  // 구역 카드를 연다
      data-zone={zoneId}  // 구역 이름을 data 속성에 단다
      data-stage={status?.stage}  // 단계 값을 data 속성에 단다
      className="panel border-t-4 border-t-(--stage,var(--line)) p-5"  // 위쪽 띠에 단계 색을 기록
    >
      {// 구역 제목 줄
      }
      <h3 className="flex flex-wrap items-center gap-2 text-xl font-bold">
        {// 구역 글자는 구역 색으로 쓴다
        }
        <span className="text-(--zone)">{zoneId}</span>
        {// 구역 이름
        }
        {ZONES[zoneId].name}
        {// 모델 추정 값이면 추정 표시를 단다
        }
        {zone?.source === "estimated" && <span className="pill text-base">추정</span>}
      </h3>
      {// 데이터 출처 문구
      }
      <p className="text-muted">{zone ? SOURCE_LABELS[zone.source] : "—"}</p>

      {// 수위와 단계 표시 줄
      }
      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        {// 현재 수위 숫자(48px 큰 수치)
        }
        <p className="text-5xl font-bold tabular-nums">
          {// 수위 숫자. 없으면 줄표
          }
          {zone ? figure(zone.levelMm, thresholdMm) : "—"}
          {// 단위 mm
          }
          {zone && <small className="ml-1 text-xl font-medium text-muted">mm</small>}
        </p>
        {// 단계가 있을 때만 단계 표시를 그린다
        }
        {status && (
          // 단계 알약
          <p className="pill border border-(--stage) bg-transparent text-lg text-(--stage)">
            {// 단계 아이콘
            }
            <span aria-hidden="true">{STAGE_ICONS[status.stage]}</span>
            {// 단계 이름
            }
            {STAGE_LABELS[status.stage]}
          </p>
        )}
      </div>

      {// 한계 대비 줄. 좁으면 한계 문구가 통째로 다음 줄로 간다
      }
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2 text-muted tabular-nums">
        {// 항목 이름
        }
        <span>한계 대비</span>
        {// 한계 대비 퍼센트(28px 큰 수치)
        }
        <span className="text-key font-bold leading-none text-ink">
          {// 퍼센트 값. 수위나 한계를 모르면 줄표
          }
          {zone && thresholdMm !== null ? share(zone.levelMm, thresholdMm) : "—"}
          {// 단위 %
          }
          <small className="ml-0.5 text-base font-medium text-muted">%</small>
        </span>
        {// 한계 수위 값. 모르면 줄표
        }
        <span>· {thresholdMm === null ? "한계 —" : `한계 ${thresholdMm} mm`}</span>
      </p>

      {// 수위와 한계를 알 때만 게이지 막대를 그린다
      }
      {zone && thresholdMm !== null && (
        // 막대 바탕(낭독기는 건너뛴다)
        <div aria-hidden="true" className="relative mt-3 h-4 rounded-full bg-line">
          {// 채움: 현재 수위 비율. 한계를 넘는 값은 끝에 선다
          }
          <div className="h-full rounded-full bg-(--stage,var(--zone))" style={{ width: width(fraction(zone.levelMm, thresholdMm)) }} />
          {// 예측이 있으면
          }
          {prediction &&
            HORIZON_KEYS.map((key) => (  // 시점마다 눈금을 그린다
              <span  // 눈금 하나를 연다
                key={key}  // 시점을 키로 기록
                // 세로 눈금 모양
                className="absolute -top-1 h-6 w-1 -translate-x-1/2 rounded-full bg-ink"
                // 예측 수위 비율 위치에 놓는다
                style={{ left: width(fraction(prediction[key], thresholdMm)) }}
              />
            ))}
        </div>
      )}

      {// +10·20·30초 예측 수위 목록
      }
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        {// 시점마다 한 칸을 그린다
        }
        {HORIZON_KEYS.map((key) => (
          // 한 칸 상자
          <div key={key} className="rounded-lg border border-line py-2">
            {// 시점 이름
            }
            <dt className="text-muted">+{key}초</dt>
            {// 예측 수위. 없으면 줄표
            }
            <dd className="text-xl font-bold tabular-nums">{prediction ? figure(prediction[key], thresholdMm) : "—"}</dd>
          </div>
        ))}
      </dl>

      {// 도달 시간 문구 줄
      }
      <p className="mt-3 text-lg font-bold">
        {// 남은 초가 있을 때만
        }
        {eta?.value && (
          // 숫자와 문구를 한 묶음으로 기록
          <>
            {// 남은 초 숫자(28px 큰 수치)와 띄어쓰기
            }
            <span className="text-key leading-none tabular-nums">{eta.value}</span>{" "}
          </>
        )}
        {// 나머지 문구. 없으면 줄표
        }
        {eta ? eta.rest : "—"}
      </p>
    </article>
  );
}
