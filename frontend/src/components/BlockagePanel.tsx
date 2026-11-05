import { useState } from "react";
import { pass, plug, reasons, type Gate } from "@/lib/derive";
import { BLOCKAGE_ICONS, BLOCKAGE_LABELS, BLOCKAGE_TONES, INLETS } from "@/lib/layout-data";
import { blockageTypeSchema, type Blockage, type Command, type Snapshot } from "@/lib/schema";
import { Glyph } from "./Glyph";
import { Reasons, Trigger } from "./Trigger";

// 라디오 한 칸
const CHOICE = "inline-flex h-10 items-center gap-2 rounded-lg border border-line px-3";

// 막힘 칸이 받는 값
interface Props {
  snapshot: Snapshot | null;  // 마지막 정상 상태. 받기 전 null
  gate: Gate;  // 막힘 제어의 켜짐
  onSend: (request: Command) => Promise<boolean>;  // 보냄. 반영되면 true
  kind: Blockage | null;  // 고른 종류. 안 골랐으면 null
  inlet: string | null;  // 고른 빗물받이 id. 안 골랐으면 null
  onKind: (kind: Blockage | null) => void;
  onInlet: (inlet: string | null) => void;
}

// 막힘 칸. 고른 종류·빗물받이만 상태로 두고 그리기는 BlockagePanel 에 맡김
export function Clog(props: Omit<Props, "kind" | "inlet" | "onKind" | "onInlet">) {
  const [kind, setKind] = useState<Blockage | null>(null);  // 고른 종류
  const [inlet, setInlet] = useState<string | null>(null);  // 고른 빗물받이
  return (
    <BlockagePanel {...props} kind={kind} inlet={inlet} onKind={setKind} onInlet={setInlet} />
  );
}

// 막힘 칸 몸통. 지금 막힘, 종류·빗물받이 고르기와 적용
export function BlockagePanel({ snapshot, gate, onSend, kind, inlet, onKind, onInlet }: Props) {
  const chosen = kind ?? snapshot?.blockage.type ?? "none";  // 안 골랐으면 서버 값
  const place = inlet ?? snapshot?.blockage.location ?? null;  // 안 골랐으면 서버 자리
  const check = plug(chosen, place);
  const apply = pass(gate, check);  // 적용 단추의 판정
  const { lines, links } = reasons([["blockage", apply]]);
  // 고른 막힘을 보냄. 반영되면 고른 값을 비워 서버 값을 따름
  const submission = async () => {
    if (!check.ok) return;
    if (await onSend(check.value)) {
      onKind(null);
      onInlet(null);
    }
  };
  return (
    <section aria-label="막힘" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">막힘</h2>
      {// 막힘 칩. 글은 서버가 준 막힘 이름
      }
      {snapshot ? (
        <p className={`chip border ${BLOCKAGE_TONES[snapshot.blockage.type]}`}>
          <Glyph name={BLOCKAGE_ICONS[snapshot.blockage.type]} />
          {snapshot.blockage.label}
        </p>
      ) : (
        <p className="chip border border-line">—</p>
      )}
      <fieldset className="mt-4">
        <legend className="text-muted">종류</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {blockageTypeSchema.options.map((type) => (
            <label key={type} className={CHOICE}>
              <input
                type="radio"
                name="ops-kind"
                value={type}
                checked={chosen === type}
                onChange={() => onKind(type)}
                className="accent-brand"
              />
              <Glyph name={BLOCKAGE_ICONS[type]} />
              {BLOCKAGE_LABELS[type]}
            </label>
          ))}
        </div>
      </fieldset>
      {// 막힘 없음이면 빗물받이를 고를 일이 없어 막음
      }
      <fieldset className="mt-4 disabled:text-muted" disabled={chosen === "none"}>
        <legend className="text-muted">빗물받이</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {INLETS.map((item) => (
            <label key={item.id} className={CHOICE}>
              <input
                type="radio"
                name="ops-inlet"
                value={item.id}
                checked={chosen !== "none" && place === item.id}
                onChange={() => onInlet(item.id)}
                className="accent-brand"
              />
              {`${item.mark} ${item.id}`}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="mt-4">
        <Trigger id="ops-blockage" gate={apply} why={links.blockage} onPress={() => void submission()}>
          적용
        </Trigger>
      </div>
      <Reasons lines={lines} />
    </section>
  );
}
