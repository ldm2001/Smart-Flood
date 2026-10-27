import { clock, outage } from "@/lib/derive";

// 연결 상태: 대기·정상·끊김
type Connection = "wait" | "ok" | "lost";

// 상태별 아이콘. 색을 못 봐도 모양으로 구별되고 모드 배지와 겹치지 않음
const ICONS: Record<Connection, string> = { wait: "◌", ok: "◉", lost: "✕" };

// 배지가 받는 값
interface Props {
  view: "connecting" | "mock" | "server";  // 화면 종류(연결 중·mock·서버)
  now: number | null;  // 지금 시각(ms). 시계가 준비되기 전에는 null
  receivedAt: number | null;  // 마지막 정상 수신 시각(ms). 아직 없으면 null
}

// 연결 배지. 마지막 정상 수신 뒤 4초가 넘으면 끊김이다
export function Signal({ view, now, receivedAt }: Props) {
  const connection: Connection =  // 연결 상태를 결정
    // 첫 응답 전이면 대기, 4초가 넘었으면 끊김, 아니면 정상
    view === "connecting" || now === null ? "wait" : outage(now, receivedAt) ? "lost" : "ok";
  // 마지막 수신 시각 글자. 없으면 줄표
  const received = receivedAt === null ? "—" : clock(receivedAt);
  return (  // 화면에 그릴 내용을 반환
    // 배지 알약. 상태 색은 data 속성으로 건넨다
    <span data-conn={connection} className="pill border border-(--conn) bg-transparent text-(--conn)">
      {// 상태 아이콘(낭독기는 건너뛴다)
      }
      <span aria-hidden="true">{ICONS[connection]}</span>
      {// 상태 문구를 고른다
      }
      {connection === "wait"
        ? "연결 중"  // 대기면 연결 중
        // 아니면 정상·끊김 문구와 마지막 수신 시각
        : `${connection === "ok" ? "연결 정상" : "연결 끊김"} · 마지막 수신 ${received}`}
    </span>
  );
}
