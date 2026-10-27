import { ceilings, contract, type Snapshot, type Zone } from "./schema";
import { wall } from "./useNow";

// 서버 주소 앞부분. 운영은 빈 값(같은 출처), 개발은 환경 파일 값이다
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
export const DEFAULT_TIMEOUT_MS = 5000;  // 기본 제한 시간(ms)
export const POLL_TIMEOUT_MS = 3000;  // 상태 읽기 제한 시간(ms)

// HTTP 실패를 나타내는 오류
export class Failure extends Error {
  readonly status: number;  // HTTP 상태 번호

  constructor(status: number) {  // 상태 번호를 받아 만듦
    super(`HTTP ${status}`);  // 오류 메시지는 HTTP 번호만 담는다
    this.name = "Failure";  // 오류 이름
    this.status = status;  // 상태 번호를 저장
  }
}

// GET 으로 JSON 을 받는다. 시간 안에 못 받거나 2xx 가 아니면 던진다
export async function reply(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<unknown> {
  const controller = new AbortController();  // 요청을 끊을 수 있는 제어기
  // 제한 시간이 지나면 요청을 끊는다
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {  // 본문까지 받는 동안
    // 캐시 없이 서버에 요청
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Failure(response.status);  // 2xx 가 아니면 오류를 던진다
    return await response.json();  // 본문을 JSON 으로 읽어 반환
  } finally {  // 끝나면 항상
    clearTimeout(timer);  // 타이머를 치운다
  }
}

// 계약을 통과한 응답과 받은 시각
export interface Receipt {
  snapshot: Snapshot;  // 검사를 통과한 서버 상태
  receivedAt: number;  // 브라우저가 받은 시각(ms). 연결 끊김 판정에 기록
}

// 상태를 읽는다. 계약을 통과한 응답만 돌려주고 다른 실패는 모두 연결 오류다
export async function poll(): Promise<Receipt> {
  // 상태 주소를 읽어 계약 검사를
  const snapshot = contract(await reply("/api/state", POLL_TIMEOUT_MS));
  return { snapshot, receivedAt: wall() };  // 받은 시각을 붙여 반환
}

// 서버 설정의 구역별 한계 수위를 읽음
export async function limits(): Promise<Record<Zone, number>> {
  return ceilings(await reply("/api/config"));  // 설정 주소를 읽어 한계 수위만 추출
}
