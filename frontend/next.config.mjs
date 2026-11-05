// 넥스트 설정 객체
const nextConfig = {
  output: "export",  // 정적 export. 전시 때 FastAPI 가 out 폴더를 그대로 냄. 서버 기능 미사용
  trailingSlash: true,  // 주소 끝에 슬래시를 붙여 폴더별 index.html 로 내보냄
  agentRules: false,  // 개발 서버가 에이전트를 감지해 AGENTS.md 를 만들거나 고치는 것 막음
  turbopack: {  // 빠른 번들러 설정
    rules: {  // 파일 종류별 처리 규칙
      "*.css": {  // 스타일시트 파일 규칙
        loaders: ["@tailwindcss/turbopack"],  // 테일윈드 로더로 처리
        as: "*.css",  // 처리 뒤에도 스타일시트 파일로 다룸
      },
    },
  },
};

export default nextConfig;
