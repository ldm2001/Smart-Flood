// 넥스트 설정 객체
const nextConfig = {
  // 정적 export. 전시 때 FastAPI 가 out 폴더를 그대로 낸다. 서버 기능은 쓰지 않는다
  output: "export",
  // 주소 끝에 슬래시를 붙여 폴더별 index.html 로 내보낸다
  trailingSlash: true,
  // 개발 서버가 에이전트를 감지해 AGENTS.md 를 만들거나 고치는 것을 막는다
  agentRules: false,
  // 빠른 번들러 설정
  turbopack: {
    // 파일 종류별 처리 규칙
    rules: {
      // 스타일시트 파일 규칙
      "*.css": {
        // 테일윈드 로더로 처리한다
        loaders: ["@tailwindcss/turbopack"],
        // 처리 뒤에도 스타일시트 파일로 다룬다
        as: "*.css",
      },
    },
  },
};

// 설정을 내보낸다
export default nextConfig;
