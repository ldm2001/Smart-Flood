import {
  cause,
  ceilings,
  chronicle,
  contract,
  rainfall,
  type Command,
  type Control,
  type LogEvent,
  type Rainfall,
  type Snapshot,
  type Zone,
} from "./schema";
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

// 서버 설정에서 쓰는 값
export interface Setup {
  thresholds: Record<Zone, number>;  // 구역 한계 수위. 틀리면 setup 이 실패
  rain: Rainfall | null;  // 강우 단계값과 상한. 틀리면 null
}

// 서버 설정을 읽음. 한계 수위가 틀리면 던짐
export async function setup(): Promise<Setup> {
  const body = await reply("/api/config");
  return { thresholds: ceilings(body), rain: rainfall(body) };
}

// 실험 기록의 사건을 읽음. 기록이 없으면 빈 목록
export async function logbook(id: string): Promise<LogEvent[]> {
  try {
    return chronicle(await reply(`/api/logs/${encodeURIComponent(id)}/events`));
  } catch (error) {
    if (error instanceof Failure && error.status === 404) return [];  // 기록 없음
    throw error;
  }
}

// 제어 실패의 모양
export type Fault =
  | { kind: "refused"; status: number; text: string }  // 서버가 이유를 붙여 거절
  | { kind: "status"; status: number }  // 이유 없는 HTTP 실패
  | { kind: "timeout" }  // 5 초 안에 답 없음
  | { kind: "network" }  // 서버에 닿지 못함
  | { kind: "format" };  // 200 인데 계약과 다름

// 제어 결과. 실패해도 던지지 않음
export type Answer = { ok: true; receipt: Receipt } | { ok: false; fault: Fault; at: number };

const ROUTES: Record<Control, string> = {  // 제어마다 POST 주소
  start: "/api/experiment/start",
  stop: "/api/experiment/stop",
  reset: "/api/experiment/reset",
  rain: "/api/rain",
  blockage: "/api/blockage",
  sim: "/api/source",
  live: "/api/source",
};

// 제어를 POST 로 보냄. 성공은 바뀐 뒤 상태, 실패는 그 모양과 시각. 던지지 않음
export async function order(command: Command): Promise<Answer> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  const fail = (fault: Fault): Answer => ({ ok: false, fault, at: wall() });  // 실패와 그 시각
  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${ROUTES[command.control]}`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(command.body),
        signal: controller.signal,
      });
    } catch {
      return fail(controller.signal.aborted ? { kind: "timeout" } : { kind: "network" });
    }
    let body: unknown = null;  // 본문을 못 읽으면 이유 없음으로 봄
    try {
      body = await response.json();
    } catch {
      if (controller.signal.aborted) return fail({ kind: "timeout" });  // 본문을 읽다 시간이 다 됨
    }
    if (response.ok) {
      try {
        return { ok: true, receipt: { snapshot: contract(body), receivedAt: wall() } };
      } catch {
        return fail({ kind: "format" });  // 200 인데 계약과 다름
      }
    }
    const text = cause(body);  // 서버가 붙인 이유 글
    return fail(
      text === null
        ? { kind: "status", status: response.status }
        : { kind: "refused", status: response.status, text },
    );
  } finally {  // 끝나면 항상
    clearTimeout(timer);
  }
}
