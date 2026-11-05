import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// 린트 설정(지시서 9장 2번)
const eslintConfig = defineConfig([
  ...nextVitals,  // 넥스트 기본 웹 성능 규칙
  ...nextTs,  // 넥스트 타입스크립트 규칙
  {  // 훅 권장 규칙 위에 여섯 규칙을 오류로 올림. 플러그인은 이미 등록됨
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],  // 스크립트와 타입스크립트 파일 전부
    rules: {
      "react-hooks/exhaustive-deps": "error",  // 효과 훅 의존 목록 빠짐 검사
      "react-hooks/set-state-in-effect": "error",  // 효과 안에서 상태를 바로 바꾸는 것 금지
      "react-hooks/set-state-in-render": "error",  // 렌더 중에 상태를 바꾸는 것 금지
      "react-hooks/purity": "error",  // 렌더 중 순수하지 않은 호출 금지
      "react-hooks/refs": "error",  // 렌더 중 참조 객체 읽기·쓰기 금지
      "react-hooks/immutability": "error",  // props·상태 값을 직접 고치는 것 금지
    },
  },
  globalIgnores([  // 린트 제외. 넥스트 기본 제외 목록을 이 목록으로 바꿈
    ".next/**",  // 개발 서버가 만드는 작업 폴더(넥스트 기본 제외)
    "out/**",  // 정적 export 결과 폴더
    "build/**",  // 빌드 결과 폴더
    "next-env.d.ts",  // 넥스트가 자동으로 만드는 타입 선언 파일
  ]),
]);

export default eslintConfig;
