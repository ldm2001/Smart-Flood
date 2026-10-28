import { ceilings, contract, type Snapshot, type Zone } from "./schema";
import { wall } from "./useNow";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";  // 운영은 빈 값(같은 출처)
export const DEFAULT_TIMEOUT_MS = 5000;  // 기본 제한 시간(ms)
export const POLL_TIMEOUT_MS = 3000;  // 상태 읽기 제한 시간(ms)

// HTTP 실패를 나타내는 오류
export class Failure extends Error {
  readonly status: number;  // HTTP 상태 번호

  constructor(status: number) {
    super(`HTTP ${status}`);  // 오류 메시지는 HTTP 번호만 담음
    this.name = "Failure";
    this.status = status;
  }
}

// GET 으로 JSON 을 받음. 시간 안에 못 받거나 2xx 가 아니면 던짐
export async function reply(path: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Failure(response.status);  // 2xx 가 아니면 오류를 던짐
    return await response.json();
  } finally {  // 끝나면 항상
    clearTimeout(timer);
  }
}

// 계약을 통과한 응답과 받은 시각
export interface Receipt {
  snapshot: Snapshot;  // 검사를 통과한 서버 상태
  receivedAt: number;  // 브라우저가 받은 시각(ms). 연결 끊김 판정에 씀
}

// 상태를 읽음. 계약을 통과한 응답만 돌려주고 다른 실패는 모두 연결 오류
export async function poll(): Promise<Receipt> {
  const snapshot = contract(await reply("/api/state", POLL_TIMEOUT_MS));
  return { snapshot, receivedAt: wall() };
}

// 서버 설정의 구역별 한계 수위를 읽음
export async function limits(): Promise<Record<Zone, number>> {
  return ceilings(await reply("/api/config"));  // 설정 주소를 읽어 한계 수위만 추출
}
