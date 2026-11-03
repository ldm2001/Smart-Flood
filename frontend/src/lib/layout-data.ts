import type { Stage } from "./derive";
import type { Blockage, Control, Input, Preset, Run, Snapshot, Zone, Source } from "./schema";

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

// 한 벌 선 아이콘 이름. 뜻이 아니라 모양으로 붙임(Glyph 가 그림)
export type Icon =
  | "check"
  | "alert"
  | "triangle"
  | "waves"
  | "wave"
  | "target"
  | "rotate"
  | "radio"
  | "circle"
  | "pause"
  | "play"
  | "stop"
  | "dots"
  | "wifi"
  | "nowifi"
  | "half"
  | "ban"
  | "clock"
  | "info"
  | "error";

export const STAGE_ICONS: Record<Stage, Icon> = {  // 색을 못 봐도 모양으로 구별(이름표와 함께)
  safe: "check",  // 정상: 원 안 체크
  caution: "alert",  // 주의: 원 안 느낌표
  warning: "triangle",  // 경계: 삼각형 느낌표
  evacuate: "waves",  // 침수: 물결 셋
};

export const MODE_LABELS: Record<Input, string> = {
  sim: "가상",
  replay: "재생",
  live: "실측",
};

export const MODE_ICONS: Record<Input, Icon> = {
  sim: "target",  // 시뮬레이션: 과녁
  replay: "rotate",  // 재생: 되감기 화살표
  live: "radio",  // 실측: 퍼지는 전파
};

export const RUN_STATE_LABELS: Record<Run, string> = {  // 위험 단계가 아니라 단계 색 미사용
  idle: "대기",
  running: "진행 중",
  stopped: "정지",
};

export const RUN_STATE_ICONS: Record<Run, Icon> = {
  idle: "pause",  // 대기: 세로 두 줄
  running: "play",  // 진행: 재생 삼각형
  stopped: "stop",  // 정지: 네모
};

export const PLAN_VIEW = { width: 300, height: 160 };  // 평면도 viewBox 크기

// 평면도의 구역 칸(viewBox 좌표)
export const PLAN_ZONES: Record<Zone, { x: number; y: number; width: number; height: number }> = {
  A: { x: 10, y: 10, width: 90, height: 100 },
  B: { x: 105, y: 10, width: 90, height: 100 },
  C: { x: 200, y: 10, width: 90, height: 100 },
};

export const INLETS = [  // 빗물받이 셋. 번호 글자, 맡은 구역, 평면도 자리
  { id: "INLET-01", mark: "①", zone: "A", x: 35, y: 110 },
  { id: "INLET-02", mark: "②", zone: "A", x: 75, y: 110 },
  { id: "INLET-03", mark: "③", zone: "B", x: 150, y: 110 },
] as const;

export const PLAN_PIPE = { y: 135, from: 35, to: 230 };  // 하부 배수관

export const PLAN_METER = { x: 230, y: 125, width: 60, height: 25 };  // 배수 계량 상자

// 보호 입력 넷(장치 둘, 플로트, 비상정지)
export const DEVICE_KEYS = ["esp32_1", "esp32_2", "floatSwitch", "emergencyStop"] as const;

// 장치 이름 타입
export type Device = (typeof DEVICE_KEYS)[number];

export const DEVICE_NAMES: Record<Device, string> = {  // 장치 표시 이름
  esp32_1: "ESP32 #1",
  esp32_2: "ESP32 #2",
  floatSwitch: "플로트 스위치",
  emergencyStop: "비상정지",
};

export const DEVICE_LABELS = {  // 장치 값 표시 글. 목록에 없는 값은 그대로 보임
  online: "정상",
  normal: "정상",
  offline: "끊김",
  unknown: "미상",
} as const;

export const QUALITY_LABELS: Record<Snapshot["quality"], string> = {  // 입력 품질 표시 글
  valid: "정상",
  degraded: "확인 필요",
  invalid: "사용 중지",
};

export const QUALITY_TONES: Record<Snapshot["quality"], string> = {  // 입력 품질 글자색
  valid: "text-(--green)",
  degraded: "text-amber",
  invalid: "text-(--red)",
};

export const BLOCKAGE_LABELS: Record<Blockage, string> = {  // 막힘 종류 표시 글
  none: "막힘 없음",
  partial: "부분 막힘",
  full: "완전 막힘",
};

export const BLOCKAGE_ICONS: Record<Blockage, Icon> = {  // 막힘 종류 아이콘
  none: "circle",  // 빈 원
  partial: "half",  // 반 찬 원
  full: "ban",  // 사선 그은 원
};

export const HEALTH_ICONS = { ok: "check", check: "alert" } as const;  // 정상·확인 아이콘

export const CONTROL_NAMES: Record<Control, string> = {  // 제어 단추와 결과 줄의 이름
  start: "시작",
  stop: "종료",
  reset: "초기화",
  rain: "강우 적용",
  blockage: "막힘 적용",
  sim: "시뮬레이션으로 바꾸기",
  live: "실측으로 바꾸기",
  replay: "재생 시작",
};

export const REPLAY_NAMES = { stop: "재생 멈춤", sim: "시뮬레이션으로 돌아가기" } as const;  // 재생 중 이름

export const PRESET_LABELS: Record<Preset, string> = {  // 서버 강우 단계 이름과 같음
  light: "약한 강우",
  medium: "보통 강우",
  heavy: "강한 강우",
};

export const RAIN_STATE_LABELS = { ON: "켜짐", OFF: "꺼짐" } as const;  // 강우 켜짐 표시 글
export const RAIN_ICONS = { ON: "wave", OFF: "pause" } as const;  // 강우 켜짐 아이콘
// 결과 줄 아이콘
export const OUTCOME_ICONS = { ok: "check", fail: "error", unsure: "triangle" } as const;

export const BLOCKAGE_TONES: Record<Blockage, string> = {  // 막힘 칩의 테두리와 글자 색. 막힘 없으면 칩 기본색
  none: "border-line",
  partial: "border-amber text-amber",
  full: "border-(--red) text-(--red)",
};
