import type { ReactNode } from "react";
import type { Gate, Reason } from "@/lib/derive";

// 꺼진 판정의 이유 글 자리
type Cue = Extract<Gate, { on: false }>["cue"];

// 칸 밖 이유 줄 id
const CUES: Partial<Record<Cue, string>> = { halt: "ops-halt", note: "ops-note" };

export const LOOK = [  // 제어 단추 모양. Menu 링크의 토큰에 꺼짐·지금 변형만 더함
  "inline-flex h-10 items-center gap-2 rounded-lg border border-line px-3 whitespace-nowrap",
  "text-soft transition-colors not-aria-disabled:hover:bg-raised not-aria-disabled:hover:text-ink",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
  "aria-disabled:cursor-not-allowed aria-disabled:text-muted",
  "aria-[current=true]:border-line aria-[current=true]:bg-raised aria-[current=true]:text-ink",
  "motion-safe:not-aria-disabled:active:translate-y-px",  // 누르는 동안 1px 내려감. 꺼짐이면 그대로
].join(" ");

export const FIELD = [  // 숫자 입력 칸 모양. 단추와 같은 높이·외곽선. 테두리는 대비 3:1 이상인 muted 색
  "h-10 min-w-0 rounded-lg border border-muted bg-bg px-3 text-ink",  // 좁은 칸에서는 줄어듦
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
  "disabled:cursor-not-allowed disabled:border-line disabled:text-muted",
].join(" ");

// 제어 단추가 받는 값
interface Props {
  id: string;  // 단추 id. 확인 줄이 닫힐 때 초점이 돌아올 자리
  gate: Gate;  // 켜짐과 꺼진 이유
  why?: string;  // 칸 이유 줄의 id. 그 칸 이유로 꺼질 때 가리킴
  current?: boolean;  // 지금 단계인가(강우 단계 단추만)
  onPress: () => void;
  children: ReactNode;
}

// 제어 단추. 꺼져도 Tab 으로 닿고 이유가 읽힘. 누름은 켜졌을 때만 받음
export function Trigger({ id, gate, why, current, onPress, children }: Props) {
  return (
    <button
      type="button"
      id={id}
      aria-disabled={gate.on ? undefined : true}
      aria-describedby={gate.on ? undefined : (CUES[gate.cue] ?? why)}
      aria-current={current ? "true" : undefined}
      onClick={gate.on ? onPress : undefined}
      className={LOOK}
    >
      {children}
    </button>
  );
}

// 칸의 꺼진 이유 목록. 같은 글은 한 줄
export function Reasons({ lines }: { lines: readonly Reason[] }) {
  if (lines.length === 0) return null;
  return (
    <ul className="mt-3 text-soft">
      {lines.map((line) => (
        <li key={line.id} id={line.id}>
          {line.text}
        </li>
      ))}
    </ul>
  );
}
