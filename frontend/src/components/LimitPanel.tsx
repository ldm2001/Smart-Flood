import { useState } from "react";
import {
  amendment,
  pass,
  reasons,
  MAX_THRESHOLD_MM,
  ZONE_IDS,
  type Gate,
  type Thresholds,
} from "@/lib/derive";
import { ZONES } from "@/lib/layout-data";
import type { Zone } from "@/lib/schema";
import { defaults, revision } from "@/lib/useSettings";
import { FIELD, Reasons, Trigger } from "./Trigger";

const ON: Gate = { on: true };  // 늘 켜진 판정. 이 칸은 서버로 보내지 않음

// 한계 수위 칸이 받는 값
interface Props {
  limits: Readonly<Thresholds> | null;  // 서버 설정의 한계 수위. 받기 전 null
  saved: Readonly<Thresholds>;  // 이 브라우저에 저장된 가상 데이터용 값
  draft: Partial<Record<Zone, string>>;  // 고치는 중인 글. 없는 칸은 저장값
  onDraft: (draft: Partial<Record<Zone, string>>) => void;
}

// 한계 수위 칸. 고치는 중인 글만 상태로 두고 그리기는 LimitPanel 에 맡김
export function Limits(props: Omit<Props, "draft" | "onDraft">) {
  const [draft, setDraft] = useState<Partial<Record<Zone, string>>>({});  // 고치는 중인 글
  return <LimitPanel {...props} draft={draft} onDraft={setDraft} />;
}

// 한계 수위 칸 몸통. 서버 값은 읽기만, 가상 데이터용 값은 고쳐 저장
export function LimitPanel({ limits, saved, draft, onDraft }: Props) {
  const { texts, checks, save } = amendment(draft, saved);
  const keep = pass(ON, save);  // 저장 단추의 판정
  const { lines, links } = reasons([
    ["save", keep],
    ...ZONE_IDS.map((id) => [`limit-${id}`, checks[id]] as const),
  ]);
  return (
    <section aria-label="구역 한계 수위" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">구역 한계 수위</h2>
      <h3 className="font-medium">서버 설정(config.yaml) · 읽기 전용</h3>
      <dl className="mt-2 grid gap-2 md:grid-cols-3">
        {ZONE_IDS.map((id) => (
          <div key={id} className="rounded-lg border border-line px-3 py-2">
            <dt className="text-muted">{`${id} ${ZONES[id].name}`}</dt>
            <dd className="font-medium tabular-nums">{limits ? `${limits[id]} mm` : "—"}</dd>
          </div>
        ))}
      </dl>
      <h3 className="mt-4 font-medium">가상 데이터용(이 브라우저)</h3>
      <div className="mt-2 grid gap-2 md:grid-cols-3">
        {ZONE_IDS.map((id) => (
          <div key={id} className="rounded-lg border border-line px-3 py-2">
            <label htmlFor={`ops-limit-${id}`} className="block text-muted">
              {`${id} ${ZONES[id].name}`}
            </label>
            <div className="mt-1 flex items-center gap-2">
              <input
                id={`ops-limit-${id}`}
                type="number"
                min={0}
                max={MAX_THRESHOLD_MM}
                step="any"
                value={texts[id]}
                aria-invalid={checks[id].ok ? undefined : true}
                aria-describedby={links[`limit-${id}`]}
                onChange={(event) => onDraft({ ...draft, [id]: event.target.value })}
                className={FIELD}
              />
              <span className="text-muted">mm</span>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Trigger
          id="ops-save"
          gate={keep}
          why={links.save}
          onPress={() => {
            if (!save.ok) return;
            revision({ thresholds: save.value });
            onDraft({});
          }}
        >
          저장
        </Trigger>
        {// 저장값이 이미 기본값이면 다시 그리지 않으므로 고치던 글도 비움
        }
        <Trigger
          id="ops-defaults"
          gate={ON}
          onPress={() => {
            defaults();
            onDraft({});
          }}
        >
          기본값으로 되돌리기
        </Trigger>
      </div>
      <Reasons lines={lines} />
      <p className="mt-4 text-base leading-normal text-muted">
        가상 데이터용 값은 서버에 연결되지 않은 <span className="font-mono">/</span> 화면에만 쓰입니다.
      </p>
    </section>
  );
}
