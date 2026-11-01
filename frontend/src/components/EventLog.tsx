import { clock, rows } from "@/lib/derive";
import { STAGE_ICONS } from "@/lib/layout-data";
import type { Events } from "@/lib/useEvents";

// 사건 기록. 최신이 위로 30개까지
export function Journal({ log }: { log: Events | null }) {
  return (
    <section aria-label="이벤트 기록" className="panel p-5">
      <h2 className="mb-4 text-xl font-bold">이벤트 기록</h2>
      <div aria-live="polite">
        {// 읽기 실패 줄. 받아 둔 줄이 있으면 그 위
        }
        {log?.failed && <p className="text-(--red)">! 이벤트를 읽지 못했습니다.</p>}
        <Entries log={log} />
      </div>
    </section>
  );
}

// 상태별 기록 본문. 읽기 실패면 읽는 중 글은 뺌
function Entries({ log }: { log: Events | null }) {
  if (log === null) return <p>—</p>;
  if (log.list === null) {
    return log.failed ? null : <p className="text-muted">이벤트를 읽는 중입니다.</p>;
  }
  if (log.list.length === 0) return <p className="text-muted">표시할 이벤트가 없습니다.</p>;
  return (
    <ol className="space-y-2">
      {rows(log.list).map((event) => (
        <li
          key={`${event.elapsedSec}:${event.kind === "stage" ? event.zone : "error"}`}
          className="flex flex-wrap gap-x-2"
        >
          <time dateTime={event.time} className="tabular-nums text-muted">
            {clock(Date.parse(event.time))}
          </time>
          {// 단계 사건은 단계 아이콘, 계산 오류는 오류 표시
          }
          {event.kind === "stage" ? (
            <span aria-hidden="true" data-stage={event.stage} className="text-(--stage)">
              {STAGE_ICONS[event.stage]}
            </span>
          ) : (
            <span className="text-(--red)">! 계산 오류</span>
          )}
          <span>{event.message}</span>
        </li>
      ))}
    </ol>
  );
}
