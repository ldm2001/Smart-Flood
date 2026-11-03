"use client";
import { useState } from "react";
import { order } from "@/lib/api";
import {
  command,
  gates,
  halt,
  linkage,
  outcome,
  step,
  wording,
  type Delivery,
  type Gate,
  type Hazard,
  type Linkage,
  type Press,
  type Thresholds,
} from "@/lib/derive";
import { OUTCOME_ICONS } from "@/lib/layout-data";
import type { Command, Control, Rainfall, Snapshot } from "@/lib/schema";
import { useNow } from "@/lib/useNow";
import { useSettings } from "@/lib/useSettings";
import { handover, useSnapshot } from "@/lib/useSnapshot";
import { Clog } from "./BlockagePanel";
import { Signal } from "./ConnectionBadge";
import { Glyph } from "./Glyph";
import { Limits } from "./LimitPanel";
import { Mode } from "./ModeBadge";
import { Rain } from "./RainPanel";
import { Round } from "./RunPanel";
import { Origin } from "./SourcePanel";

// 운영 화면. 서버 상태를 읽고 제어를 보냄
export function Desk() {
  const now = useNow();
  const polled = useSnapshot();
  const { thresholds } = useSettings();  // 가상 데이터용 한계 수위
  const [open, setOpen] = useState<Hazard | null>(null);  // 열린 확인 줄
  const [sending, setSending] = useState<Control | null>(null);  // 보내는 중인 제어
  const [delivery, setDelivery] = useState<Delivery | null>(null);  // 마지막 결과
  const receivedAt = polled.latest?.receivedAt ?? null;  // 마지막 정상 수신 시각. 받기 전 null
  const snapshot = polled.latest?.snapshot ?? null;
  const link = linkage(now, receivedAt, polled.failed);
  const switches = gates(link, receivedAt, snapshot, sending);  // 제어마다 켜짐
  if (open !== null && !switches[open].on) setOpen(null);  // 판정이 꺼진 확인 줄은 닫음
  // 제어 하나를 보냄. 반영되면 응답 상태를 캐시에 넣고 true
  const send = async (request: Command) => {
    if (sending !== null || !switches[request.control].on) return false;  // 두 번 누름과 꺼진 제어를 막음
    const replay = snapshot?.dataSource === "replay";  // 결과 글은 보낼 때 기준
    setSending(request.control);
    setOpen(null);
    const answer = await order(request);
    if (answer.ok) await handover(answer.receipt);
    setDelivery({ control: request.control, answer, replay });
    setSending(null);
    return answer.ok;
  };
  // 단추와 확인 줄 누름. 예면 열린 줄의 제어를 보냄
  const press = (input: Press) => {
    const next = step(open, input);
    setOpen(next.open);
    if (next.send !== null) void send(command(next.send));
  };
  return (
    <Sheet
      now={now}
      link={link}
      halt={halt(link, receivedAt)}
      receivedAt={receivedAt}
      failed={polled.failed}
      snapshot={snapshot}
      rain={polled.rain}
      limits={polled.thresholds}
      saved={thresholds}
      gates={switches}
      open={open}
      sending={sending}
      delivery={delivery}
      onPress={press}
      onSend={send}
    />
  );
}

// 운영 화면 몸통이 받는 값. Desk 가 렌더 중에 구해 넘김
export interface Board {
  now: number | null;  // 지금 시각(ms). 시계가 준비되기 전 null
  link: Linkage;  // 연결 상태
  halt: string | null;  // 제어를 모두 끈 이유. online 이면 null
  receivedAt: number | null;  // 마지막 정상 수신 시각(ms). 받기 전 null
  failed: boolean;  // 마지막 폴링이 실패했는가
  snapshot: Snapshot | null;  // 마지막 정상 상태. 받기 전 null
  rain: Rainfall | null;  // 서버 설정의 강우 단계값과 상한. 받기 전이나 틀리면 null
  limits: Readonly<Thresholds> | null;  // 서버 설정의 한계 수위. 받기 전 null
  saved: Readonly<Thresholds>;  // 이 브라우저에 저장된 가상 데이터용 값
  gates: Record<Control, Gate>;  // 제어마다 켜짐
  open: Hazard | null;  // 열린 확인 줄
  sending: Control | null;  // 보내는 중인 제어
  delivery: Delivery | null;  // 마지막 결과. 보낸 적 없으면 null
  onPress: (press: Press) => void;  // 단추와 확인 줄 누름
  onSend: (request: Command) => Promise<boolean>;  // 바로 보냄. 반영되면 true
}

// 운영 화면 몸통. 머리, 멈춤 줄, 결과 줄과 칸 다섯
export function Sheet(props: Board) {
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
          <h1 className="mt-1 text-3xl font-semibold">운영·설정</h1>
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
      <p id="ops-note" aria-live="polite" className="mt-1 flex min-h-7 items-center gap-2">
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
          </>
        )}
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Round
          snapshot={props.snapshot}
          gates={props.gates}
          open={props.open}
          onPress={props.onPress}
          onSend={props.onSend}
        />
        <Origin
          snapshot={props.snapshot}
          gates={props.gates}
          open={props.open}
          onPress={props.onPress}
        />
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Rain
          snapshot={props.snapshot}
          rain={props.rain}
          gate={props.gates.rain}
          onSend={props.onSend}
        />
        <Clog snapshot={props.snapshot} gate={props.gates.blockage} onSend={props.onSend} />
      </div>
      <div className="mt-6">
        <Limits limits={props.limits} saved={props.saved} />
      </div>
    </main>
  );
}
