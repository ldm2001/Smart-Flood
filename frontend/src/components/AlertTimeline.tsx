import { clock, lead, milestones, ZONE_IDS, type Milestones } from "@/lib/derive";
import { STAGE_ICONS, STAGE_LABELS, ZONES } from "@/lib/layout-data";
import type { StageEvent } from "@/lib/schema";
import type { Events } from "@/lib/useEvents";

const BLANK: Milestones = { judgement: null, request: null, arrival: null };  // 사건 전의 빈 칸
const moment = (event: StageEvent) => clock(Date.parse(event.time));  // 사건 시각(HH:MM:SS)
// 사건의 경과 밀리초. 없으면 null
const at = (event: StageEvent | null) => (event === null ? null : event.elapsedSec * 1000);

// 구역별 위험 판단·문자 요청·실제 도달과 선행 시간
export function Timeline({ log }: { log: Events | null }) {
  return (
    <section aria-label="위험 판단·시험용 문자" className="panel p-5">
      <h2 className="mb-4 text-xl font-bold">위험 판단·시험용 문자</h2>
      {log?.failed && <p className="mb-3 text-(--red)">! 이벤트를 읽지 못했습니다.</p>}
      <div className="space-y-4">
        {ZONE_IDS.map((id) => {
          const { judgement, request, arrival } = log?.list ? milestones(log.list, id) : BLANK;
          const gap = lead(at(judgement), at(arrival));  // 선행 시간(초)
          return (
            <div key={id}>
              <h3 data-zone={id} className="text-lg font-bold text-(--zone)">
                {`${id} ${ZONES[id].name}`}
              </h3>
              <dl className="mt-1 grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-1">
                <dt className="text-muted">위험 판단</dt>
                <dd>
                  {judgement ? (
                    <>
                      {`${moment(judgement)} · `}
                      <span aria-hidden="true">{STAGE_ICONS[judgement.stage]}</span>
                      {` ${STAGE_LABELS[judgement.stage]}`}
                    </>
                  ) : (
                    "—"
                  )}
                </dd>
                <dt className="text-muted">문자 요청(SMS 예정)</dt>
                <dd>{request ? `${moment(request)} · 기록만, 실제 발송 차단` : "—"}</dd>
                <dt className="text-muted">실제 도달(경보)</dt>
                <dd>{arrival ? moment(arrival) : "—"}</dd>
                <dt className="text-muted">선행 시간</dt>
                <dd className="text-key font-bold tabular-nums">
                  {gap === null ? "—" : `${Math.round(gap)}초`}
                </dd>
              </dl>
            </div>
          );
        })}
      </div>
      {// S2 는 문자를 보내지 않아 도착 확인은 늘 불가
      }
      <p className="mt-4 text-base text-muted">휴대전화 도착 확인 · 확인 불가(시험 번호 미연결)</p>
    </section>
  );
}
