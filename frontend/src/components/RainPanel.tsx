import { useState } from "react";
import { pass, rate, reasons, shower, type Gate } from "@/lib/derive";
import { PRESET_LABELS, RAIN_ICONS, RAIN_STATE_LABELS } from "@/lib/layout-data";
import { presetSchema, type Command, type Rainfall, type Snapshot } from "@/lib/schema";
import { Glyph } from "./Glyph";
import { FIELD, Reasons, Trigger } from "./Trigger";

// 강우 칸이 받는 값
interface Props {
  snapshot: Snapshot | null;  // 마지막 정상 상태. 받기 전 null
  rain: Rainfall | null;  // 서버 설정의 단계값과 상한. 받기 전이나 틀리면 null
  gate: Gate;  // 강우 제어의 켜짐
  onSend: (request: Command) => Promise<boolean>;  // 보냄. 반영되면 true
  draft: string;  // 직접 입력 칸의 글
  onDraft: (text: string) => void;
}

// 강우 칸. 입력 중인 글만 상태로 두고 그리기는 RainPanel 에 맡김
export function Rain(props: Omit<Props, "draft" | "onDraft">) {
  const [draft, setDraft] = useState("");  // 직접 입력 칸의 글
  return <RainPanel {...props} draft={draft} onDraft={setDraft} />;
}

// 강우 칸 몸통. 지금 강우, 단계 단추 셋, 직접 입력과 적용
export function RainPanel({ snapshot, rain, gate, onSend, draft, onDraft }: Props) {
  const max = rain?.maxMmPerHour ?? null;  // 직접 입력 상한. 설정을 받기 전 null
  const check = rate(draft, max);
  const apply = pass(gate, check);  // 적용 단추의 판정
  const { lines, links } = reasons([
    ...presetSchema.options.map((preset) => [`rain-${preset}`, gate] as const),
    ["rain", apply],
    ["rain-mm", check],
  ]);
  // 직접 입력을 보냄. 반영되면 칸을 비움
  const submit = async () => {
    if (!check.ok) return;
    if (await onSend(shower(check.value))) onDraft("");
  };
  return (
    <section aria-label="강우" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">강우</h2>
      <dl className="grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-muted">단계</dt>
          <dd className="font-medium">{snapshot?.rain.intensity ?? "—"}</dd>
        </div>
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-muted">세기</dt>
          <dd className="font-medium tabular-nums">
            {snapshot ? `${snapshot.rain.mmPerHour} mm/h` : "—"}
          </dd>
        </div>
        <div className="rounded-lg border border-line px-3 py-2">
          <dt className="text-muted">상태</dt>
          <dd className="flex items-center gap-2 font-medium">
            {snapshot ? (
              <>
                <Glyph name={RAIN_ICONS[snapshot.rain.state]} />
                {RAIN_STATE_LABELS[snapshot.rain.state]}
              </>
            ) : (
              "—"
            )}
          </dd>
        </div>
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        {presetSchema.options.map((preset) => (
          <Trigger
            key={preset}
            id={`ops-rain-${preset}`}
            gate={gate}
            why={links[`rain-${preset}`]}
            current={snapshot?.rain.intensity === PRESET_LABELS[preset]}
            onPress={() => void onSend(shower(preset))}
          >
            {`${PRESET_LABELS[preset]} ${rain ? rain.presets[preset] : "—"} mm/h`}
          </Trigger>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label htmlFor="ops-rain-mm">직접 입력(mm/h)</label>
        <input
          id="ops-rain-mm"
          type="number"
          min={0}
          max={max ?? undefined}
          step="any"
          disabled={max === null}
          value={draft}
          aria-invalid={!check.ok && max !== null && draft.trim() !== "" ? true : undefined}
          aria-describedby={links["rain-mm"]}
          onChange={(event) => onDraft(event.target.value)}
          className={FIELD}
        />
        <Trigger id="ops-rain" gate={apply} why={links.rain} onPress={() => void submit()}>
          적용
        </Trigger>
      </div>
      <Reasons lines={lines} />
    </section>
  );
}
