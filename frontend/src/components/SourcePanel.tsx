import { question, reasons, wording, type Gate, type Hazard, type Press } from "@/lib/derive";
import { MODE_ICONS, MODE_LABELS } from "@/lib/layout-data";
import type { Control, Snapshot } from "@/lib/schema";
import { Glyph } from "./Glyph";
import { Guard } from "./Guard";
import { Reasons, Trigger } from "./Trigger";

const SOURCES = ["sim", "live"] as const;  // 입력원 칸의 제어

// 입력원 칸이 받는 값
interface Props {
  snapshot: Snapshot | null;  // 마지막 정상 상태. 받기 전 null
  gates: Record<Control, Gate>;  // 제어마다 켜짐
  open: Hazard | null;  // 열린 확인 줄
  onPress: (press: Press) => void;  // 단추와 확인 줄 누름
}

// 입력원 칸. 지금 입력원과 시뮬레이션·실측 전환. 둘 다 확인 줄을 거침
export function Origin({ snapshot, gates, open, onPress }: Props) {
  const source = snapshot?.dataSource ?? null;  // 지금 입력원. 받기 전 null
  const replay = source === "replay";
  const { lines, links } = reasons(SOURCES.map((control) => [control, gates[control]] as const));
  return (
    <section aria-label="입력원" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">입력원</h2>
      <p className="chip">
        {// 입력원 아이콘. 없으면 빈 원
        }
        <Glyph name={source ? MODE_ICONS[source] : "circle"} />
        입력원 {source ? MODE_LABELS[source] : "—"}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {SOURCES.map((control) => (
          <Trigger
            key={control}
            id={`ops-${control}`}
            gate={gates[control]}
            why={links[control]}
            onPress={() => onPress({ kind: "ask", control })}
          >
            {wording(control, replay)}
          </Trigger>
        ))}
      </div>
      {snapshot && (open === "sim" || open === "live") && (
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
      <p className="mt-3 text-base text-muted">재생 시작은 기록·재생 화면에서 합니다.</p>
    </section>
  );
}
