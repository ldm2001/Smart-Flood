import {
  command,
  question,
  reasons,
  wording,
  type Gate,
  type Hazard,
  type Press,
} from "@/lib/derive";
import { RUN_STATE_ICONS, RUN_STATE_LABELS } from "@/lib/layout-data";
import type { Command, Control, Snapshot } from "@/lib/schema";
import { Glyph } from "./Glyph";
import { Guard } from "./Guard";
import { Reasons, Trigger } from "./Trigger";

const RUNS = ["start", "stop", "reset"] as const;  // 회차 칸의 제어

// 회차 칸이 받는 값
interface Props {
  snapshot: Snapshot | null;  // 마지막 정상 상태. 받기 전 null
  gates: Record<Control, Gate>;  // 제어마다 켜짐
  open: Hazard | null;  // 열린 확인 줄
  onPress: (press: Press) => void;  // 확인 줄 누름
  onSend: (request: Command) => Promise<boolean>;  // 바로 보냄. 반영되면 true
}

// 회차 칸. 상태·실험 ID·경과와 시작·종료·초기화. 시작만 확인 없이 보냄
export function Round({ snapshot, gates, open, onPress, onSend }: Props) {
  const replay = snapshot?.dataSource === "replay";
  const run = snapshot?.runState ?? null;  // 회차 상태. 서버가 안 보냈으면 null
  const { lines, links } = reasons(RUNS.map((control) => [control, gates[control]] as const));
  return (
    <section aria-label="회차" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">회차</h2>
      <dl className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-muted">상태</dt>
          <dd className="flex items-center gap-2 font-medium">
            {run && <Glyph name={RUN_STATE_ICONS[run]} />}
            실험 {run ? RUN_STATE_LABELS[run] : "—"}
          </dd>
        </div>
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-muted">실험 ID</dt>
          <dd className="font-mono font-medium">{snapshot?.experimentId ?? "—"}</dd>
        </div>
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-muted">경과</dt>
          <dd className="font-medium tabular-nums">
            {snapshot ? `${Math.floor(snapshot.elapsedSec)}초` : "—"}
          </dd>
        </div>
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        {RUNS.map((control) => (
          <Trigger
            key={control}
            id={`ops-${control}`}
            gate={gates[control]}
            why={links[control]}
            onPress={
              control === "start"
                ? () => void onSend(command("start"))
                : () => onPress({ kind: "ask", control })
            }
          >
            {wording(control, replay)}
          </Trigger>
        ))}
      </div>
      {snapshot && (open === "stop" || open === "reset") && (
        <Guard
          key={open}
          control={open}
          name={wording(open, replay)}
          question={question(open, snapshot)}
          onYes={() => onPress({ kind: "yes" })}
          onNo={() => onPress({ kind: "no" })}
        />
      )}
      <Reasons lines={lines} />
    </section>
  );
}
