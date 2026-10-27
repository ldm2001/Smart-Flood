import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// 파일 내용을 글자로 읽는 도우미(이 파일 기준 상대 경로)
const text = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
// 검사 스크립트의 절대 경로
const SCRIPT = fileURLToPath(new URL("../scripts/check-state.mjs", import.meta.url));

// 계약 문서 'GET /api/state' 아래 첫 json 블록(응답 예시)을 읽는 도우미
function sample(): Record<string, unknown> {
  const md = text("../../docs/api-contract.md");  // 계약 문서를 읽음
  // 상태 항목 아래 첫 json 블록 글을 찾음
  const json = md.slice(md.indexOf("## GET /api/state")).match(/```json\n([\s\S]*?)\n```/)?.[1];
  // 블록이 없으면 오류를 냄
  if (!json) throw new Error("api-contract.md 에서 예시 json 블록을 찾지 못했다");
  return JSON.parse(json);  // 블록 글을 객체로 바꿔 반환
}

// 입력을 넣어 검사 스크립트를 돌리고 결과를 돌려주는 도우미
const outcome = (input: string) => spawnSync(process.execPath, [SCRIPT], { input, encoding: "utf8" });

describe("check:state", () => {  // 상태 응답 검사 스크립트 테스트 묶음
  // 백엔드 예시 응답이 오류 출력 없이 통과하는지 검사
  it("passes the backend's example response with nothing on stderr", () => {
    const result = outcome(JSON.stringify(sample()));  // 예시 응답을 스크립트에 넣어 돌린다
    expect(result.stderr).toBe("");  // 오류 출력이 비어 있어야 함
    expect(result.status).toBe(0);  // 종료 코드는 0 이어야 함
    expect(result.stdout).toContain("계약 통과");  // '계약 통과' 가 출력돼야 함
    expect(result.stdout).toContain("EXP-20261022-001");  // 실험 번호가 출력돼야 함
  });

  // 계약을 어긴 응답은 실패하고 어긋난 필드를 알리는지 검사
  it("fails on a response that breaks the contract and names the field", () => {
    const example = sample();  // 예시 응답을 읽음
    // A 구역 수위를 501 로 망가뜨린 구역 묶음을 만듦
    const zones = { ...(example.zones as object), A: { levelMm: 501, rateMmSec: 0, source: "simulated" } };
    // 망가진 응답을 스크립트에 넣어 돌린다
    const result = outcome(JSON.stringify({ ...example, zones }));
    expect(result.status).toBe(1);  // 종료 코드는 1 이어야 함
    expect(result.stderr).toContain("계약 위반");  // '계약 위반' 이 출력돼야 함
    expect(result.stderr).toContain("zones.A.levelMm");  // 어긋난 필드 이름이 출력돼야 함
  });

  it("fails on a body that is not JSON", () => {  // JSON 이 아닌 본문은 실패하는지 검사
    const result = outcome("<html>502 Bad Gateway</html>");  // 게이트웨이 오류 페이지를 넣어 돌린다
    expect(result.status).toBe(1);  // 종료 코드는 1 이어야 함
    expect(result.stderr).toContain("JSON 이 아니다");  // JSON 이 아니라는 안내가 나와야 함
  });

  // 빈 입력은 실패하는지 검사(백엔드가 꺼지면 curl 이 이렇게 남긴다)
  it("fails on empty input, which is what curl -f leaves when the backend is down", () => {
    const result = outcome("");  // 빈 입력을 넣어 돌린다
    expect(result.status).toBe(1);  // 종료 코드는 1 이어야 함
    expect(result.stderr).toContain("응답이 비었다");  // 비었다는 안내가 나와야 함
  });

  // npm 명령이 로컬 백엔드 응답을 스크립트에 넘기는지 검사
  it("is what npm run check:state feeds with the local backend's /api/state", () => {
    // 패키지 파일에서 check:state 명령을 꺼냄
    const command: string = JSON.parse(text("../package.json")).scripts["check:state"];
    // curl 로 받은 응답을 스크립트에 넘기는 명령이어야 함
    expect(command).toBe("curl -fsS --max-time 5 http://localhost:8000/api/state | node scripts/check-state.mjs");
  });
});
