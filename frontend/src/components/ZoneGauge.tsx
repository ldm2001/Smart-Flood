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
import { Glyph } from "./Glyph";

// 카드가 받는 값. 단계와 eta 는 서버 alerts 의 status 만 씀
interface Props {
  zoneId: Zone;  // 구역 이름(A·B·C)
  zone: { levelMm: number; source: Source } | null;  // 현재 수위(mm)와 출처. 아직 없으면 null
  prediction: Prediction | null;  // +10·20·30초 예측 수위. 없으면 null
  thresholdMm: number | null;  // 한계 수위(mm). 설정을 받기 전에는 null
  status: Grade | null;  // 서버가 알린 경보 단계. 없으면 null
}

const width = (ratio: number) => `${Math.round(ratio * 10000) / 100}%`;  // 비율(0~1) → CSS 퍼센트
const STAFF = ["left-1/4", "left-1/2", "left-3/4"];  // 표척 눈금 자리. 한계의 1/4·1/2·3/4

// 구역 카드. 한계를 모르면 게이지 막대를 그리지 않음
export function Gauge({ zoneId, zone, prediction, thresholdMm, status }: Props) {
  const eta = status && phrase(status);  // 단계가 있으면 도달 문구를 만듦
  return (
    <article
      data-zone={zoneId}
      data-stage={status?.stage}
      className="panel border-(--alert,var(--line)) p-5"
    >
      <h3 className="flex flex-wrap items-center gap-2 text-lg font-medium">
        <span>{zoneId}</span>
        {ZONES[zoneId].name}
        {// 모델 추정 값이면 추정 표시 붙임
        }
        {zone?.source === "estimated" && <span className="chip text-base">추정</span>}
      </h3>
      <p className="text-muted">{zone ? SOURCE_LABELS[zone.source] : "—"}</p>

      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        {// 현재 수위 숫자(32px 큰 수치)
        }
        <p className="text-figure leading-none font-medium tabular-nums">
          {zone ? figure(zone.levelMm, thresholdMm) : "—"}
          {// 단위 mm
          }
          {zone && <small className="ml-1 text-base font-normal text-muted">mm</small>}
        </p>
        {// 단계가 있을 때만 단계 표시를 그림
        }
        {status && (
          <p className="chip border border-(--alert,transparent) bg-(--tint,var(--raised)) text-(--stage)">
            <Glyph name={STAGE_ICONS[status.stage]} />
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
        <span className="text-key leading-none font-medium text-ink">
          {// 퍼센트 값. 수위나 한계를 모르면 줄표
          }
          {zone && thresholdMm !== null ? share(zone.levelMm, thresholdMm) : "—"}
          {// 단위 %
          }
          <small className="ml-1 text-base font-normal text-muted">%</small>
        </span>
        <span>· {thresholdMm === null ? "한계 —" : `한계 ${thresholdMm} mm`}</span>
      </p>

      {// 수위와 한계를 알 때만 게이지 막대를 그림
      }
      {zone && thresholdMm !== null && (
        <div aria-hidden="true" className="relative mt-4 mb-3 h-2 rounded-full bg-raised">
          {// 채움: 현재 수위 비율. 한계를 넘는 값은 끝에 섬. 정상은 물 파란색
          }
          <div
            className="h-full rounded-full bg-(--alert,var(--brand))"
            style={{ width: width(fraction(zone.levelMm, thresholdMm)) }}
          />
          {// 표척 눈금. 막대 아래에 짧은 선
          }
          {STAFF.map((left) => (
            <span key={left} className={`absolute top-full mt-1 h-1.5 w-px -translate-x-1/2 bg-muted ${left}`} />
          ))}
          {prediction &&
            HORIZON_KEYS.map((key) => (
              <span
                key={key}
                className="absolute -top-1.5 h-5 w-0.5 -translate-x-1/2 rounded-full bg-ink"
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
            <dd className="text-xl font-medium tabular-nums">{prediction ? figure(prediction[key], thresholdMm) : "—"}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-lg font-medium">
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
