import { clock, linkage } from "@/lib/derive";
import type { Icon } from "@/lib/layout-data";
import { Glyph } from "./Glyph";

// 연결 상태: 대기·정상·끊김
type Connection = "wait" | "ok" | "lost";

// 연결 상태별 아이콘. 색 없이도 모양 구별
const ICONS: Record<Connection, Icon> = { wait: "dots", ok: "wifi", lost: "nowifi" };

// 배지가 받는 값
interface Props {
  view: "connecting" | "mock" | "server";  // 화면 종류(연결 중·mock·서버)
  now: number | null;  // 지금 시각(ms). 시계가 준비되기 전에는 null
  receivedAt: number | null;  // 마지막 정상 수신 시각(ms). 아직 없으면 null
  failed: boolean;  // 마지막 폴링이 실패했는가. 실패 없이 4초가 지나면 아직 연결 중
}

// 연결 배지. 마지막 정상 수신 뒤 4초가 넘고 폴링이 실패했으면 끊김
export function Signal({ view, now, receivedAt, failed }: Props) {
  const link = view === "connecting" ? "connecting" : linkage(now, receivedAt, failed);
  const connection: Connection =
    link === "connecting" ? "wait" : link === "online" ? "ok" : "lost";  // mock 도 끊김
  const received = receivedAt === null ? "—" : clock(receivedAt);
  return (
    <span
      data-conn={connection}
      className={`chip border ${connection === "lost" ? "border-(--conn) text-ink" : "border-line"}`}
    >
      {// 상태 아이콘만 연결 색. 끊기면 테두리도 켬
      }
      <Glyph name={ICONS[connection]} className="text-(--conn)" />
      {connection === "wait"
        ? "연결 중"
        : `${connection === "ok" ? "연결 정상" : "연결 끊김"} · 마지막 수신 ${received}`}
    </span>
  );
}
