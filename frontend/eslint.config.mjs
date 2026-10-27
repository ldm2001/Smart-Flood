// 린트 설정 파일(지시서 9장 2번). 설정 도우미를 가져온다
import { defineConfig, globalIgnores } from "eslint/config";
// 넥스트 기본 웹 성능 규칙 묶음을 가져온다
import nextVitals from "eslint-config-next/core-web-vitals";
// 넥스트 타입스크립트 규칙 묶음을 가져온다
import nextTs from "eslint-config-next/typescript";

// 최종 설정 목록을 만든다
const eslintConfig = defineConfig([
  // 넥스트 기본 웹 성능 규칙을 펼쳐 넣는다
  ...nextVitals,
  // 넥스트 타입스크립트 규칙을 펼쳐 넣는다
  ...nextTs,
  // 훅 권장 규칙 위에 여섯 규칙을 오류로 올린다. 플러그인은 이미 등록됐다
  {
    // 스크립트와 타입스크립트 파일 전부에 적용한다
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    // 규칙 목록
    rules: {
      // 효과 훅 의존 목록 빠짐 검사
      "react-hooks/exhaustive-deps": "error",
      // 효과 안에서 상태를 바로 바꾸는 것 금지
      "react-hooks/set-state-in-effect": "error",
      // 렌더 중에 상태를 바꾸는 것 금지
      "react-hooks/set-state-in-render": "error",
      // 렌더 중 순수하지 않은 호출 금지
      "react-hooks/purity": "error",
      // 렌더 중 참조 객체 읽기·쓰기 금지
      "react-hooks/refs": "error",
      // props·상태 값을 직접 고치는 것 금지
      "react-hooks/immutability": "error",
    },
  },
  // 린트에서 제외할 곳. 넥스트 기본 제외 목록을 이 목록으로 바꾼다
  globalIgnores([
    // 개발 서버가 만드는 작업 폴더(넥스트 기본 제외)
    ".next/**",
    // 정적 export 결과 폴더
    "out/**",
    // 빌드 결과 폴더
    "build/**",
    // 넥스트가 자동으로 만드는 타입 선언 파일
    "next-env.d.ts",
  ]),
]);

// 최종 설정을 내보낸다
export default eslintConfig;
