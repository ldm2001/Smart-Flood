import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const text = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const dev: string = JSON.parse(text("../package.json")).scripts.dev;
const option = (name: string) => dev.match(new RegExp(`--${name}[ =](\\S+)`))?.[1];

describe("dev server", () => {
  it("listens on localhost only", () => {  // 이 컴퓨터(localhost)에서만 여는지 검사
    expect(option("hostname")).toBe("localhost");
  });

  // 백엔드 CORS 가 허용하는 출처로 여는지 검사. 127.0.0.1 로 열면 막힘
  it("serves from an origin the backend CORS allows", () => {
    const origins = text("../../backend/config.yaml").match(/cors_origins:\s*\[([^\]]*)\]/)?.[1] ?? "";
    const allowed = origins.split(",").map((origin) => origin.trim().replace(/^["']|["']$/g, ""));
    expect(allowed).toContain(`http://${option("hostname")}:${option("port")}`);
  });
});
