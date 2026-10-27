import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// 파일 내용을 글자로 읽는 도우미(이 파일 기준 상대 경로)
const text = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
// 패키지 파일의 dev 명령 글자를 꺼냄
const dev: string = JSON.parse(text("../package.json")).scripts.dev;
// dev 명령에서 옵션(이름) 값을 찾는 도우미
const option = (name: string) => dev.match(new RegExp(`--${name}[ =](\\S+)`))?.[1];

describe("dev server", () => {  // 개발 서버 설정 테스트 묶음
  // 이 컴퓨터(localhost)에서만 여는지 검사. 다른 기기는 붙지 못
  it("listens on localhost only", () => {
    expect(option("hostname")).toBe("localhost");  // 호스트 옵션이 localhost 여야 함
  });

  // 백엔드 CORS 가 허용하는 출처로 여는지 검사. 127.0.0.1 로 열면 막힌다
  it("serves from an origin the backend CORS allows", () => {
    // 백엔드 설정에서 허용 출처 목록 글자를 꺼냄
    const origins = text("../../backend/config.yaml").match(/cors_origins:\s*\[([^\]]*)\]/)?.[1] ?? "";
    // 쉼표로 나누고 따옴표를 떼어 출처 배열로 만듦
    const allowed = origins.split(",").map((origin) => origin.trim().replace(/^["']|["']$/g, ""));
    // dev 명령의 호스트와 포트로 만든 주소가 허용 목록에 있어야 함
    expect(allowed).toContain(`http://${option("hostname")}:${option("port")}`);
  });
});
