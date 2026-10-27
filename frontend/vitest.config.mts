// 테스트 실행 설정. 주소를 경로로 바꾸는 도구를 가져온다
import { fileURLToPath } from "node:url";
// 설정 도우미를 가져온다
import { defineConfig } from "vitest/config";

// 테스트 설정을 내보낸다
export default defineConfig({
  // 경로 해석 설정
  resolve: {
    // 별칭 '@' 가 src 폴더를 가리킨다(화면 코드와 같다)
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  // 테스트 실행 옵션
  test: {
    // src 와 tests 폴더의 테스트 파일만 돌린다
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    // 브라우저 없이 노드에서 돌린다
    environment: "node",
  },
});
