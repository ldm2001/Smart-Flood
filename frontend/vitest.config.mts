import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// 테스트 실행 설정
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },  // 화면 코드와 같은 별칭
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    environment: "node",  // 브라우저 없이 노드에서 돌림
  },
});
