import type { Icon } from "@/lib/layout-data";

const CIRCLE = "M21 12a9 9 0 1 1-18 0a9 9 0 0 1 18 0";  // 바깥 원
// (x, y) 자리의 작은 점. 반지름 r 원에 선 1.5 를 둘러 꽉 찬 점으로 보임
const dot = (x: number, y: number, r = 0.75) =>
  `M${x + r} ${y}a${r} ${r} 0 1 1-${2 * r} 0a${r} ${r} 0 0 1 ${2 * r} 0`;
const WAVE = "q2.25-2.5 4.5 0t4.5 0 4.5 0 4.5 0";  // 왼쪽에서 오른쪽까지 물결 넷
const WIFI = [  // 아래 점을 중심으로 한 호 셋
  "M8.5 15.5a5 5 0 0 1 7 0",
  "M5 12a10 10 0 0 1 14 0",
  "M2 8.5a15 15 0 0 1 20 0",
  dot(12, 19),
];

const SHAPES: Record<Icon, readonly string[]> = {  // 아이콘별 선 경로(24 칸 좌표)
  check: [CIRCLE, "m8.5 12.5 2.5 2.5 5-5"],
  alert: [CIRCLE, "M12 7.5v5", dot(12, 16)],
  triangle: ["M12 3.5 21.5 20h-19z", "M12 9v4", dot(12, 16.25)],
  waves: [`M3 7.5${WAVE}`, `M3 12${WAVE}`, `M3 16.5${WAVE}`],
  wave: [`M3 12${WAVE}`],
  target: [CIRCLE, "M16 12a4 4 0 1 1-8 0a4 4 0 0 1 8 0", dot(12, 12)],
  rotate: ["M4.5 12a7.5 7.5 0 1 0 2.2-5.3", "M6.7 3.2v3.5h3.5"],  // 반시계 화살표
  radio: [
    "M13.5 12a1.5 1.5 0 1 1-3 0a1.5 1.5 0 0 1 3 0",
    "M8.5 8.5a5 5 0 0 0 0 7",
    "M15.5 8.5a5 5 0 0 1 0 7",
    "M5.6 5.6a9 9 0 0 0 0 12.8",
    "M18.4 5.6a9 9 0 0 1 0 12.8",
  ],
  circle: [CIRCLE],
  pause: ["M9 6.5v11", "M15 6.5v11"],
  play: ["M7 4.5v15l12-7.5z"],
  stop: ["M7 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"],
  dots: [dot(6, 12, 1), dot(12, 12, 1), dot(18, 12, 1)],
  wifi: WIFI,
  nowifi: [...WIFI, "m3 3 18 18"],
  half: [CIRCLE],
  ban: [CIRCLE, "m5.6 5.6 12.8 12.8"],
  clock: [CIRCLE, "M12 7v5l3 2"],
  info: [CIRCLE, "M12 16v-4.5", dot(12, 8)],
  error: [CIRCLE, "m9 9 6 6", "m15 9-6 6"],
};

// 선 밑에 칠하는 면. 부분 막힘은 왼쪽 반원
const FILLED: Partial<Record<Icon, string>> = { half: "M12 3a9 9 0 0 0 0 18z" };

const BASE = "inline-block shrink-0 align-[-0.2em]";  // 글줄 안에서 글자 가운데에 맞춤

// 한 벌 선 아이콘. 18px·선 1.5, 색은 글자색을 따름. 낭독기는 건너뜀
export function Glyph({ name, className }: { name: Icon; className?: string }) {
  const fill = FILLED[name];
  return (
    <svg aria-hidden="true" data-icon={name} width="18" height="18" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"
      className={className ? `${BASE} ${className}` : BASE}>
      {fill && <path d={fill} fill="currentColor" stroke="none" />}
      {SHAPES[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}
