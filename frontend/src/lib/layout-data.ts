import type { Stage } from "./derive";
import type { Input, Run, Zone, Source } from "./schema";

// 구역 이름 표. 백엔드에 묻지 않는 값만 둔다
export const ZONES: Record<Zone, { name: string }> = {
  A: { name: "낮은 상가 도로" },  // A 구역: 낮은 상가 도로
  B: { name: "주택 골목" },  // B 구역: 주택 골목
  C: { name: "높은 광장" },  // C 구역: 높은 광장
};

// 출처 이름표. 모델 추정 표시는 응답의 source 를 따른다(C 는 늘 추정)
export const SOURCE_LABELS: Record<Source, string> = {
  measured: "실측",  // 실제 센서 값
  simulated: "가상 실측",  // 시뮬레이션 값
  estimated: "모델 추정",  // 모델이 추정한 값
  replay: "재생 입력",  // 기록을 재생한 값
};

// 4단계 이름표. 색은 스타일의 --stage 토큰을 기록
export const STAGE_LABELS: Record<Stage, string> = {
  safe: "정상",  // 정상 단계
  caution: "주의",  // 주의 단계
  warning: "경계",  // 경계 단계
  evacuate: "침수(경보)",  // 침수 경보 단계
};

// 단계 아이콘. 색을 못 봐도 모양으로 구별되고 이름표와 함께 기록
export const STAGE_ICONS: Record<Stage, string> = {
  safe: "✓",  // 정상: 체크
  caution: "△",  // 주의: 빈 삼각형
  warning: "▲",  // 경계: 찬 삼각형
  evacuate: "≋",  // 침수: 물결
};

export const MODE_LABELS: Record<Input, string> = {  // 입력원 이름표
  sim: "가상",  // 시뮬레이션 입력
  replay: "재생",  // 기록 재생 입력
  live: "실측",  // 실제 센서 입력
};

export const MODE_ICONS: Record<Input, string> = {  // 입력원 아이콘
  sim: "◎",  // 시뮬레이션: 겹동그라미
  replay: "↺",  // 재생: 되감기 화살표
  live: "●",  // 실측: 채운 동그라미
};

// 실험 상태 이름표. 위험 단계가 아니라서 단계 색을 쓰지 않음
export const RUN_STATE_LABELS: Record<Run, string> = {
  idle: "대기",  // 대기 중
  running: "진행 중",  // 돌고 있음
  stopped: "정지",  // 멈춤
};

export const RUN_STATE_ICONS: Record<Run, string> = {  // 실험 상태 아이콘
  idle: "◇",  // 대기: 빈 마름모
  running: "▶︎",  // 진행: 재생 삼각형
  stopped: "■",  // 정지: 네모
};
