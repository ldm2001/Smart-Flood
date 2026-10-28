import { clock, outage } from "@/lib/derive";

// 연결 상태: 대기·정상·끊김
type Connection = "wait" | "ok" | "lost";

const ICONS: Record<Connection, string> = { wait: "◌", ok: "◉", lost: "✕" };  // 색 없이도 모양 구별

// 배지가 받는 값
interface Props {
  view: "connecting" | "mock" | "server";  // 화면 종류(연결 중·mock·서버)
  now: number | null;  // 지금 시각(ms). 시계가 준비되기 전에는 null
  receivedAt: number | null;  // 마지막 정상 수신 시각(ms). 아직 없으면 null
}

// 연결 배지. 마지막 정상 수신 뒤 4초가 넘으면 끊김
export function Signal({ view, now, receivedAt }: Props) {
  const connection: Connection =
    view === "connecting" || now === null ? "wait" : outage(now, receivedAt) ? "lost" : "ok";
  const received = receivedAt === null ? "—" : clock(receivedAt);
  return (
    <span data-conn={connection} className="pill border border-(--conn) bg-transparent text-(--conn)">
      {// 상태 아이콘(낭독기는 건너뜀)
      }
      <span aria-hidden="true">{ICONS[connection]}</span>
      {connection === "wait"
        ? "연결 중"
        : `${connection === "ok" ? "연결 정상" : "연결 끊김"} · 마지막 수신 ${received}`}
    </span>
  );
}
