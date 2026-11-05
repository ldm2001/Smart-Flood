import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const text = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
// 검사 스크립트의 절대 경로
const SCRIPT = fileURLToPath(new URL("../scripts/check-state.mjs", import.meta.url));

// 계약 문서 'GET /api/state' 아래 첫 json 블록(응답 예시)을 읽는 도우미
function sample(): Record<string, unknown> {
  const md = text("../../docs/api-contract.md");  // 계약 문서를 읽음
  const json = md.slice(md.indexOf("## GET /api/state")).match(/```json\n([\s\S]*?)\n```/)?.[1];
  if (!json) throw new Error("api-contract.md 에서 예시 json 블록을 찾지 못했다");
  return JSON.parse(json);
}

const outcome = (input: string) => spawnSync(process.execPath, [SCRIPT], { input, encoding: "utf8" });

describe("check:state", () => {
  it("passes the backend's example response with nothing on stderr", () => {
    const result = outcome(JSON.stringify(sample()));
    expect(result.stderr).toBe("");
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("계약 통과");  // '계약 통과' 가 출력돼야 함
    expect(result.stdout).toContain("EXP-20261022-001");
  });

  // 계약을 어긴 응답은 실패하고 어긋난 필드를 알리는지 검사
  it("fails on a response that breaks the contract and names the field", () => {
    const example = sample();
    const zones = { ...(example.zones as object), A: { levelMm: 501, rateMmSec: 0, source: "simulated" } };
    const result = outcome(JSON.stringify({ ...example, zones }));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("계약 위반");  // '계약 위반' 이 출력돼야 함
    expect(result.stderr).toContain("zones.A.levelMm");
  });

  it("fails on a body that is not JSON", () => {
    const result = outcome("<html>502 Bad Gateway</html>");
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("JSON 이 아니다");  // JSON 이 아니라는 안내가 나와야 함
  });

  it("fails on empty input, which is what curl -f leaves when the backend is down", () => {
    const result = outcome("");
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("응답이 비었다");
  });

  it("is what npm run check:state feeds with the local backend's /api/state", () => {
    const command: string = JSON.parse(text("../package.json")).scripts["check:state"];
    expect(command).toBe("curl -fsS --max-time 5 http://localhost:8000/api/state | node scripts/check-state.mjs");
  });
});
