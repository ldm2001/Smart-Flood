import type { Stage } from "./derive";
import type { Input, Run, Zone, Source } from "./schema";

export const ZONES: Record<Zone, { name: string }> = {
  A: { name: "낮은 상가 도로" },  // A 구역: 낮은 상가 도로
  B: { name: "주택 골목" },  // B 구역: 주택 골목
  C: { name: "높은 광장" },  // C 구역: 높은 광장
};

export const SOURCE_LABELS: Record<Source, string> = {  // 추정 표시는 응답 source 를 따름
  measured: "실측",
  simulated: "가상 실측",
  estimated: "모델 추정",
  replay: "재생 입력",
};

export const STAGE_LABELS: Record<Stage, string> = {  // 4단계 이름표
  safe: "정상",
  caution: "주의",  // 주의 단계
  warning: "경계",
  evacuate: "침수(경보)",
};

export const STAGE_ICONS: Record<Stage, string> = {  // 색을 못 봐도 모양으로 구별(이름표와 함께)
  safe: "✓",  // 정상: 체크
  caution: "△",  // 주의: 빈 삼각형
  warning: "▲",  // 경계: 찬 삼각형
  evacuate: "≋",  // 침수: 물결
};

export const MODE_LABELS: Record<Input, string> = {
  sim: "가상",
  replay: "재생",
  live: "실측",
};

export const MODE_ICONS: Record<Input, string> = {
  sim: "◎",  // 시뮬레이션: 겹동그라미
  replay: "↺",  // 재생: 되감기 화살표
  live: "●",  // 실측: 채운 동그라미
};

export const RUN_STATE_LABELS: Record<Run, string> = {  // 위험 단계가 아니라 단계 색 미사용
  idle: "대기",
  running: "진행 중",
  stopped: "정지",
};

export const RUN_STATE_ICONS: Record<Run, string> = {
  idle: "◇",  // 대기: 빈 마름모
  running: "▶︎",  // 진행: 재생 삼각형
  stopped: "■",  // 정지: 네모
};
