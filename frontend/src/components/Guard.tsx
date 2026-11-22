import type { Hazard } from "@/lib/derive";
import { LOOK } from "./Trigger";

// 확인 줄이 붙을 때 취소에 초점. 떨어질 때 줄 안에 초점이 있었으면 연 단추로 돌림
function guard(node: HTMLDivElement) {
  node.querySelector<HTMLElement>("[data-cancel]")?.focus();
  return () => {
    if (node.contains(document.activeElement)) {
      document.getElementById(node.dataset.opener ?? "")?.focus();
    }
  };
}

// 확인 줄이 받는 값
interface Props {
  control: Hazard;  // 이 줄을 연 제어
  name: string;  // 제어 이름. 줄 이름에 씀
  question: string;  // 물음 글
  onYes: () => void;
  onNo: () => void;
}

// 칸 안의 확인 줄. 초점이 취소에 있어 Enter 로는 보내지 않음, Esc 는 취소
export function Guard({ control, name, question, onYes, onNo }: Props) {
  return (
    <div
      ref={guard}
      role="group"
      aria-label={`${name} 확인`}
      data-opener={`ops-${control}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") onNo();
      }}
      className="mt-3 rounded-lg border border-line p-3"
    >
      <p className="leading-normal">{question}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className={LOOK} onClick={onYes}>
          예
        </button>
        <button type="button" data-cancel className={LOOK} onClick={onNo}>
          취소
        </button>
      </div>
    </div>
  );
}
