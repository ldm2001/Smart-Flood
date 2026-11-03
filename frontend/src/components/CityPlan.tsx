import {
  figure,
  fraction,
  obstruction,
  pool,
  spot,
  ZONE_IDS,
  type Grade,
  type Thresholds,
} from "@/lib/derive";
import {
  BLOCKAGE_ICONS,
  BLOCKAGE_LABELS,
  BLOCKAGE_TONES,
  INLETS,
  PLAN_METER,
  PLAN_PIPE,
  PLAN_VIEW,
  PLAN_ZONES,
  SOURCE_LABELS,
  STAGE_ICONS,
  STAGE_LABELS,
  ZONES,
} from "@/lib/layout-data";
import type { Blockage, Snapshot, Zone } from "@/lib/schema";
import { Glyph } from "./Glyph";

// 평면도가 받는 값. 단계는 서버 alerts 로 구한 값만 씀
interface Props {
  snapshot: Snapshot | null;  // 서버 상태. 연결 중 null
  statuses: Record<Zone, Grade> | null;  // 서버 alerts 로 구한 구역별 단계
  thresholds: Readonly<Thresholds> | null;  // 한계 수위. 받기 전에는 null
}

const RINGS: Record<Blockage, string> = {  // 빗물받이 테두리 색
  none: "stroke-muted",
  partial: "stroke-amber",
  full: "stroke-(--red)",
};

const MARKS: Record<Blockage, string> = {  // 빗물받이 번호 글자. 막혔으면 막힘 색에 한 단 굵게
  none: "text-muted",
  partial: "font-medium text-amber",
  full: "font-medium text-(--red)",
};

const METERS = [  // 배수 계량 두 값: 이름, drain 칸, 단위
  { name: "누적 배수량", key: "volumeL", unit: "L" },
  { name: "유량", key: "flowLMin", unit: "L/min" },
] as const;

const CENTER = "absolute -translate-x-1/2 -translate-y-1/2";  // 좌표를 글자 가운데에 맞춤
const LABEL_Y = 22;  // 구역 ID 글자의 평면도 높이
const INLET_R = 5;  // 빗물받이 원 반지름
const MARK_GAP = 10;  // 빗물받이 번호를 원 위로 올리는 거리

// 도시 모형 평면도와 막힘·배수 계량
export function Plan({ snapshot, statuses, thresholds }: Props) {
  // 빗물받이의 막힘 종류. 연결 중 null
  const blocked = (id: string) => (snapshot ? obstruction(snapshot.blockage, id) : null);
  return (
    <section aria-label="도시 모형 상태" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">도시 모형 상태</h2>
      {// 15/8 은 viewBox 300/160 과 같은 비율이라 겹친 글자와 그림이 맞음
      }
      <div role="img" aria-label="도시 모형 평면도" className="relative aspect-[15/8] w-full">
        <svg
          viewBox={`0 0 ${PLAN_VIEW.width} ${PLAN_VIEW.height}`}
          preserveAspectRatio="none"
          aria-hidden="true"
          className="absolute inset-0 h-full w-full"
        >
          {// 물 높이. 수위와 한계를 다 알 때만
          }
          {snapshot &&
            thresholds &&
            ZONE_IDS.map((id) => {
              const rect = PLAN_ZONES[id];
              const water = pool(rect, fraction(snapshot.zones[id].levelMm, thresholds[id]));
              return (
                <rect
                  key={id}
                  className="fill-brand/35"
                  x={rect.x}
                  y={water.y}
                  width={rect.width}
                  height={water.height}
                />
              );
            })}
          {// 구역 칸. 테두리는 주의 이상만 서버 단계 색, 그 밖에는 보조 글자색
          }
          {ZONE_IDS.map((id) => (
            <rect
              key={id}
              data-stage={statuses?.[id].stage}
              className="fill-none stroke-(--alert,var(--muted)) stroke-2"
              vectorEffect="non-scaling-stroke"
              {...PLAN_ZONES[id]}
            />
          ))}
          {// 하부 배수관, 빗물받이에서 내려가는 관, 계량 상자
          }
          <line
            className="stroke-muted stroke-2"
            vectorEffect="non-scaling-stroke"
            x1={PLAN_PIPE.from}
            y1={PLAN_PIPE.y}
            x2={PLAN_PIPE.to}
            y2={PLAN_PIPE.y}
          />
          {INLETS.map((inlet) => (
            <line
              key={inlet.id}
              className="stroke-muted stroke-2"
              vectorEffect="non-scaling-stroke"
              x1={inlet.x}
              y1={inlet.y + INLET_R}
              x2={inlet.x}
              y2={PLAN_PIPE.y}
            />
          ))}
          <rect
            className="fill-none stroke-muted stroke-2"
            vectorEffect="non-scaling-stroke"
            {...PLAN_METER}
          />
          {// 빗물받이. 테두리는 막힘 종류의 색
          }
          {INLETS.map((inlet) => (
            <circle
              key={inlet.id}
              className={`fill-panel ${RINGS[blocked(inlet.id) ?? "none"]} stroke-2`}
              vectorEffect="non-scaling-stroke"
              cx={inlet.x}
              cy={inlet.y}
              r={INLET_R}
            />
          ))}
        </svg>
        {// 구역 ID. 모델 추정 값이면 추정 표시 붙임
        }
        {ZONE_IDS.map((id) => (
          <span
            key={id}
            data-zone={id}
            className={`${CENTER} flex items-center gap-1 font-medium`}
            style={spot(PLAN_ZONES[id].x + PLAN_ZONES[id].width / 2, LABEL_Y)}
          >
            {id}
            {snapshot?.zones[id].source === "estimated" && (
              <span className="chip">추정</span>
            )}
          </span>
        ))}
        {INLETS.map((inlet) => (
          <span
            key={inlet.id}
            className={`${CENTER} ${MARKS[blocked(inlet.id) ?? "none"]}`}
            style={spot(inlet.x, inlet.y - MARK_GAP)}
          >
            {inlet.mark}
          </span>
        ))}
      </div>

      {// 막힘 칩. 글은 서버가 준 막힘 이름
      }
      {snapshot && (
        <div className="mt-4">
          <p className={`chip border ${BLOCKAGE_TONES[snapshot.blockage.type]}`}>
            <Glyph name={BLOCKAGE_ICONS[snapshot.blockage.type]} />
            {snapshot.blockage.label}
          </p>
        </div>
      )}
      <ul className="mt-3 space-y-1">
        {INLETS.map((inlet) => {
          const kind = blocked(inlet.id);
          return (
            <li key={inlet.id}>
              {`${inlet.mark} ${inlet.id} · ${inlet.zone} 구역 · `}
              {kind === null ? (
                "—"
              ) : (
                <>
                  <Glyph name={BLOCKAGE_ICONS[kind]} />
                  {` ${BLOCKAGE_LABELS[kind]}`}
                </>
              )}
            </li>
          );
        })}
      </ul>
      <ul className="mt-3 space-y-1">
        {ZONE_IDS.map((id) => {
          const zone = snapshot?.zones[id];
          const grade = statuses?.[id];
          return (
            <li key={id}>
              {`${id} ${ZONES[id].name} · `}
              {zone && grade ? (
                <>
                  {`${figure(zone.levelMm, thresholds?.[id] ?? null)} mm · `}
                  {// 단계 아이콘만 단계 색
                  }
                  <span data-stage={grade.stage} className="text-(--stage)">
                    <Glyph name={STAGE_ICONS[grade.stage]} />
                  </span>
                  {` ${STAGE_LABELS[grade.stage]} · ${SOURCE_LABELS[zone.source]}`}
                </>
              ) : (
                "—"
              )}
            </li>
          );
        })}
      </ul>

      <h3 className="mt-4 font-medium">하부 배수 계량</h3>
      <dl className="mt-2 grid grid-cols-2 gap-2">
        {METERS.map(({ name, key, unit }) => (
          <div key={key} className="rounded-lg border border-line px-3 py-2">
            <dt className="text-muted">{name}</dt>
            <dd>
              <span className="text-key font-medium tabular-nums">
                {snapshot ? snapshot.drain[key].toFixed(2) : "—"}
              </span>
              {snapshot && <small className="ml-1 text-base text-muted">{unit}</small>}
            </dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 text-base text-muted">
        C 구역은 수위 센서가 없어 늘 모델로 추정합니다. A·B 도 최근 관측이 없는 동안은 추정값입니다.
      </p>
      <p className="mt-1 text-base text-muted">
        위험 단계는 서버가 보정된 모델 수위로 판정합니다. 관측 수위가 한계를 넘어도 단계가 낮을 수
        있습니다.
      </p>
    </section>
  );
}
