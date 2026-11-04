"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { logbook, order, records } from "@/lib/api";
import {
  clock,
  closure,
  gates,
  halt,
  linkage,
  outcome,
  pass,
  playback,
  question,
  reasons,
  rerun,
  step,
  wording,
  RECORD_ID,
  type Delivery,
  type Gate,
  type Hazard,
  type Linkage,
  type Press,
} from "@/lib/derive";
import { MODE_LABELS, OUTCOME_ICONS } from "@/lib/layout-data";
import type { Command, Control, Log, LogEvent, Snapshot } from "@/lib/schema";
import { EVENTS_SWR_OPTIONS } from "@/lib/useEvents";
import { useNow } from "@/lib/useNow";
import { handover, useSnapshot } from "@/lib/useSnapshot";
import { Timeline } from "./AlertTimeline";
import { Compare } from "./Compare";
import { Signal } from "./ConnectionBadge";
import { Glyph } from "./Glyph";
import { Guard } from "./Guard";
import { Mode } from "./ModeBadge";
import { Reasons, Trigger } from "./Trigger";

const ROW = [  // 기록 목록 줄 모양. 제어 단추의 토큰에 고른 줄 변형만 씀
  "flex flex-wrap items-center gap-x-3 rounded-lg border border-transparent px-3 py-2 text-soft",
  "transition-colors hover:bg-raised hover:text-ink",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
  "aria-[current=true]:border-line aria-[current=true]:bg-raised aria-[current=true]:text-ink",
].join(" ");

// 기록 화면. 주소의 id 마다 확인 줄과 결과 줄을 새로 둠
export function Archive() {
  const id = useSearchParams()?.get("id") ?? null;  // 고른 기록 번호. 없으면 null
  return <Desk key={id ?? ""} id={id} />;
}

// 주소를 읽기 전의 기록 화면. 연결 중이라 제어는 모두 꺼짐
export function Waiting() {
  return (
    <Shelf
      now={null}
      link="connecting"
      halt={halt("connecting", null)}
      receivedAt={null}
      failed={false}
      snapshot={null}
      logs={null}
      missing={false}
      id={null}
      events={null}
      lost={false}
      gate={gates("connecting", null, null, null).replay}
      open={false}
      sending={null}
      delivery={null}
      onPress={() => undefined}
    />
  );
}

// 기록 화면의 읽기와 재생 시작. 서버 상태·목록·사건을 읽어 Shelf 에 넘김
function Desk({ id }: { id: string | null }) {
  const now = useNow();
  const polled = useSnapshot();
  const chosen = id !== null && RECORD_ID.test(id) ? id : null;  // 꼴이 맞는 번호만 읽고 보냄
  const shelf = useSWR("/api/logs", records, EVENTS_SWR_OPTIONS);
  const book = useSWR(
    chosen === null ? null : (["log", chosen] as const),
    ([, key]: readonly [string, string]) => logbook(key),
    EVENTS_SWR_OPTIONS,
  );
  const [open, setOpen] = useState<Hazard | null>(null);  // 열린 확인 줄
  const [sending, setSending] = useState<Control | null>(null);  // 보내는 중인 제어
  const [delivery, setDelivery] = useState<Delivery | null>(null);  // 마지막 결과
  const receivedAt = polled.latest?.receivedAt ?? null;  // 마지막 정상 수신 시각. 받기 전 null
  const snapshot = polled.latest?.snapshot ?? null;
  const link = linkage(now, receivedAt, polled.failed);
  const own = gates(link, receivedAt, snapshot, sending).replay;  // 다른 제어와 같은 규칙의 판정
  const gate = pass(own, rerun(snapshot, chosen ?? ""));
  if (open !== null && !gate.on) setOpen(null);  // 판정이 꺼진 확인 줄은 닫음
  // 재생 시작을 보냄. 반영되면 응답 상태를 캐시에 넣음
  const send = async (request: Command) => {
    if (sending !== null || !gate.on) return;  // 두 번 누름과 꺼진 제어를 막음
    const replay = snapshot?.dataSource === "replay";  // 결과 글은 보낼 때 기준
    setSending(request.control);
    setOpen(null);
    const answer = await order(request);
    if (answer.ok) await handover(answer.receipt);
    setDelivery({ control: request.control, answer, replay });
    setSending(null);
  };
  // 단추와 확인 줄 누름. 예면 고른 기록의 재생 시작을 보냄
  const press = (input: Press) => {
    const next = step(open, input);
    setOpen(next.open);
    if (next.send === "replay" && chosen !== null) void send(playback(chosen));
  };
  return (
    <Shelf
      now={now}
      link={link}
      halt={halt(link, receivedAt)}
      receivedAt={receivedAt}
      failed={polled.failed}
      snapshot={snapshot}
      logs={shelf.data ?? null}
      missing={shelf.error !== undefined}
      id={id}
      events={chosen === null ? null : (book.data ?? null)}
      lost={book.error !== undefined}
      gate={gate}
      open={open === "replay"}
      sending={sending}
      delivery={delivery}
      onPress={press}
    />
  );
}

// 기록 화면 몸통이 받는 값. Desk 가 렌더 중에 구해 넘김
export interface Stack {
  now: number | null;  // 지금 시각(ms). 시계가 준비되기 전 null
  link: Linkage;  // 연결 상태
  halt: string | null;  // 제어를 모두 끈 이유. online 이면 null
  receivedAt: number | null;  // 마지막 정상 수신 시각(ms). 받기 전 null
  failed: boolean;  // 마지막 폴링이 실패했는가
  snapshot: Snapshot | null;  // 마지막 정상 상태. 받기 전 null
  logs: readonly Log[] | null;  // 기록 목록. 받기 전이나 못 읽었으면 null
  missing: boolean;  // 목록 읽기의 실패 여부
  id: string | null;  // 주소의 기록 번호. 고르지 않았으면 null
  events: readonly LogEvent[] | null;  // 고른 기록의 사건. 받기 전 null
  lost: boolean;  // 사건 읽기의 실패 여부
  gate: Gate;  // 재생 시작의 켜짐
  open: boolean;  // 재생 확인 줄이 열렸는가
  sending: Control | null;  // 보내는 중인 제어
  delivery: Delivery | null;  // 마지막 결과. 보낸 적 없으면 null
  onPress: (press: Press) => void;  // 단추와 확인 줄 누름
}

// 기록 화면 몸통. 머리, 멈춤 줄, 결과 줄, 목록과 상세
export function Shelf(props: Stack) {
  const replay = props.snapshot?.dataSource === "replay";
  // 결과 줄의 종류와 글. 보내는 중이면 지난 결과를 가림
  const result = props.sending === null && props.delivery ? outcome(props.delivery) : null;
  // 연결 배지의 화면 종류. 연결 중과 mock 밖은 서버 값 화면
  const view = props.link === "online" || props.link === "lost" ? "server" : props.link;
  return (
    <main className="mx-auto w-full max-w-[1600px] px-4 py-6 md:px-8 md:py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-soft">A·B·C 구역 침수 모형</p>
          <h1 className="mt-1 text-3xl font-semibold">기록·재생</h1>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Mode dataSource={props.snapshot?.dataSource ?? null} mock={props.link === "mock"} />
          <Signal
            view={view}
            now={props.now}
            receivedAt={props.receivedAt}
            failed={props.failed}
          />
        </div>
      </header>

      {props.halt !== null && (
        <p id="ops-halt" className="flex items-center gap-2 font-medium">
          <Glyph name="info" />
          {props.halt}
        </p>
      )}
      {// 결과 줄. 바뀐 글을 낭독기가 읽도록 비어도 자리를 둠
      }
      <p
        id="ops-note"
        aria-live="polite"
        className="mt-1 flex min-h-7 flex-wrap items-center gap-2"
      >
        {props.sending !== null && (
          <>
            <Glyph name="dots" />
            {`${wording(props.sending, replay)} 보내는 중입니다`}
          </>
        )}
        {result && (
          <>
            <Glyph name={OUTCOME_ICONS[result.tone]} />
            {result.text}
            {result.tone === "ok" && (
              <Link href="/" className="underline underline-offset-4">
                종합 관제에서 보기
              </Link>
            )}
          </>
        )}
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-[5fr_7fr] md:items-start">
        <Records logs={props.logs} missing={props.missing} id={props.id} />
        <Detail {...props} />
      </div>
    </main>
  );
}

// 기록 목록 칸. 줄을 누르면 ?id= 로 감
function Records({ logs, missing, id }: Pick<Stack, "logs" | "missing" | "id">) {
  return (
    <section aria-label="실험 기록" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">실험 기록</h2>
      {missing && (
        <p className="mb-3 flex items-center gap-2 text-(--red)">
          <Glyph name="error" />
          실험 기록을 읽지 못했습니다
        </p>
      )}
      {logs !== null && logs.length === 0 && (
        <p className="text-muted">저장된 실험 기록이 없습니다.</p>
      )}
      {logs !== null && logs.length > 0 && (
        <ul className="space-y-1">
          {logs.map((log) => (
            <li key={log.experimentId}>
              <Link
                href={`/logs/?id=${encodeURIComponent(log.experimentId)}`}
                aria-current={log.experimentId === id ? "true" : undefined}
                className={ROW}
              >
                <span className="font-mono">{log.experimentId}</span>
                <span className="font-mono text-muted tabular-nums">
                  {clock(Date.parse(log.startTime))}
                </span>
                <span>{`입력원 ${MODE_LABELS[log.dataSource]}`}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// 고른 기록의 머리 정보, 재생 시작, 비교 표, 타임라인
function Detail(props: Stack) {
  if (props.id === null) {
    return (
      <section aria-label="기록 상세" className="panel p-5">
        <h2 className="mb-4 text-lg font-medium">기록 상세</h2>
        <p className="text-muted">목록에서 기록을 고르면 비교 표와 재생 단추가 나옵니다.</p>
      </section>
    );
  }
  const log = props.logs?.find((each) => each.experimentId === props.id) ?? null;
  const gone = props.logs !== null && log === null;  // 목록을 받았는데 그 번호가 없음
  const replay = props.snapshot?.dataSource === "replay";
  const { lines, links } = reasons([["replay", props.gate]]);
  return (
    <div className="space-y-4">
      <section aria-label="기록 상세" className="panel p-5">
        <h2 className="mb-4 text-lg font-medium">기록 상세</h2>
        {gone ? (
          <p className="text-muted">고른 실험 기록이 목록에 없습니다.</p>
        ) : (
          <>
            <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-4 gap-y-1">
              <dt className="text-muted">실험 번호</dt>
              <dd className="font-mono">{log?.experimentId ?? "—"}</dd>
              <dt className="text-muted">시작 시각</dt>
              <dd className="font-mono tabular-nums">
                {log ? clock(Date.parse(log.startTime)) : "—"}
              </dd>
              <dt className="text-muted">입력원</dt>
              <dd>{log ? MODE_LABELS[log.dataSource] : "—"}</dd>
              <dt className="text-muted">모델 버전</dt>
              <dd className="font-mono">{log?.modelVersion ?? "—"}</dd>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <Trigger
                id="ops-replay"
                gate={props.gate}
                why={links.replay}
                onPress={() => props.onPress({ kind: "ask", control: "replay" })}
              >
                <Glyph name="play" />
                이 기록 재생
              </Trigger>
            </div>
            {props.snapshot && props.open && (
              <Guard
                control="replay"
                name={wording("replay", replay)}
                question={question("replay", props.snapshot)}
                onYes={() => props.onPress({ kind: "yes" })}
                onNo={() => props.onPress({ kind: "no" })}
              />
            )}
            <Reasons lines={lines} />
          </>
        )}
      </section>
      {!gone && (
        <>
          <Compare events={props.events} ended={closure(props.snapshot, props.id)} />
          <Timeline log={{ list: props.events, failed: props.lost }} past />
        </>
      )}
    </div>
  );
}
