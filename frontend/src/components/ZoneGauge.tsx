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

// 카드가 받는 값. 단계와 eta 는 서버 alerts 의 status 만 씀
interface Props {
  zoneId: Zone;  // 구역 이름(A·B·C)
  zone: { levelMm: number; source: Source } | null;  // 현재 수위(mm)와 출처. 아직 없으면 null
  prediction: Prediction | null;  // +10·20·30초 예측 수위. 없으면 null
  thresholdMm: number | null;  // 한계 수위(mm). 설정을 받기 전에는 null
  status: Grade | null;  // 서버가 알린 경보 단계. 없으면 null
}

const width = (ratio: number) => `${Math.round(ratio * 10000) / 100}%`;  // 비율(0~1) → CSS 퍼센트

// 구역 카드. 한계를 모르면 게이지 막대를 그리지 않음
export function Gauge({ zoneId, zone, prediction, thresholdMm, status }: Props) {
  const eta = status && phrase(status);  // 단계가 있으면 도달 문구를 만듦
  return (
    <article
      data-zone={zoneId}
      data-stage={status?.stage}
      className="panel border-t-4 border-t-(--stage,var(--line)) p-5"
    >
      <h3 className="flex flex-wrap items-center gap-2 text-xl font-bold">
        <span className="text-(--zone)">{zoneId}</span>
        {ZONES[zoneId].name}
        {// 모델 추정 값이면 추정 표시 붙임
        }
        {zone?.source === "estimated" && <span className="pill text-base">추정</span>}
      </h3>
      <p className="text-muted">{zone ? SOURCE_LABELS[zone.source] : "—"}</p>

      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        {// 현재 수위 숫자(48px 큰 수치)
        }
        <p className="text-5xl font-bold tabular-nums">
          {zone ? figure(zone.levelMm, thresholdMm) : "—"}
          {// 단위 mm
          }
          {zone && <small className="ml-1 text-xl font-medium text-muted">mm</small>}
        </p>
        {// 단계가 있을 때만 단계 표시를 그림
        }
        {status && (
          <p className="pill border border-(--stage) bg-transparent text-lg text-(--stage)">
            <span aria-hidden="true">{STAGE_ICONS[status.stage]}</span>
            {STAGE_LABELS[status.stage]}
          </p>
        )}
      </div>

      {// 한계 대비 줄. 좁으면 한계 문구가 통째로 다음 줄로 감
      }
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2 text-muted tabular-nums">
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
        <span>· {thresholdMm === null ? "한계 —" : `한계 ${thresholdMm} mm`}</span>
      </p>

      {// 수위와 한계를 알 때만 게이지 막대를 그림
      }
      {zone && thresholdMm !== null && (
        <div aria-hidden="true" className="relative mt-3 h-4 rounded-full bg-line">
          {// 채움: 현재 수위 비율. 한계를 넘는 값은 끝에 섬
          }
          <div className="h-full rounded-full bg-(--stage,var(--zone))" style={{ width: width(fraction(zone.levelMm, thresholdMm)) }} />
          {prediction &&
            HORIZON_KEYS.map((key) => (
              <span
                key={key}
                className="absolute -top-1 h-6 w-1 -translate-x-1/2 rounded-full bg-ink"
                style={{ left: width(fraction(prediction[key], thresholdMm)) }}
              />
            ))}
        </div>
      )}

      {// +10·20·30초 예측 수위 목록
      }
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        {HORIZON_KEYS.map((key) => (
          <div key={key} className="rounded-lg border border-line py-2">
            <dt className="text-muted">+{key}초</dt>
            <dd className="text-xl font-bold tabular-nums">{prediction ? figure(prediction[key], thresholdMm) : "—"}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-lg font-bold">
        {eta?.value && (
          <>
            {// 남은 초 숫자(28px 큰 수치)와 띄어쓰기
            }
            <span className="text-key leading-none tabular-nums">{eta.value}</span>{" "}
          </>
        )}
        {eta ? eta.rest : "—"}
      </p>
    </article>
  );
}
