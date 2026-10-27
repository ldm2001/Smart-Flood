import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

// 프런트 폴더 경로(지시서 9장 2번: 훅 규칙 여섯 개가 오류 등급인지 본다)
const ROOT = fileURLToPath(new URL("..", import.meta.url));
// 오류 등급으로 올린 훅 규칙 여섯 개
const RAISED = ["exhaustive-deps", "set-state-in-effect", "set-state-in-render", "purity", "refs", "immutability"];

// 규칙 설정에서 등급 숫자를 구하는 도우미
const severity = (entry: unknown) => {
  const level = Array.isArray(entry) ? entry[0] : entry;  // 배열이면 첫 칸이 등급이다
  // off·warn·error 를 0·1·2 로 바꿔 반환
  return ({ off: 0, warn: 1, error: 2 } as Record<string, number>)[String(level)] ?? level;
};

const PROBE = `"use client";  // 일부러 규칙을 어긴 컴포넌트 글자(파일 없이 글자로만 검사한다)
import { useEffect, useState } from "react";

export function Probe({ value }: { value: number }) {
  const [copy, setCopy] = useState(0);
  useEffect(() => {
    setCopy(value);
  }, [value]);
  useEffect(() => {
    console.log(value);
  }, []);
  return <p>{copy}</p>;
}
`;

describe("check 2: eslint config", () => {  // 린트 설정 검사 테스트 묶음(검사 2번)
  const eslint = new ESLint({ cwd: ROOT });  // 프런트 폴더 기준 린트 검사기를 만듦

  // 훅 규칙 여섯 개가 오류 등급으로 올랐는지 검사(느려서 30초까지 기다린다)
  it("raises the six react-hooks rules to error", { timeout: 30_000 }, async () => {
    // 첫 화면 파일에 적용되는 설정을 구
    const config = await eslint.calculateConfigForFile(join(ROOT, "src/app/page.tsx"));
    for (const rule of [...RAISED, "rules-of-hooks"]) {  // 여섯 규칙과 훅 호출 규칙을 하나씩 확인
      expect(severity(config.rules[`react-hooks/${rule}`]), rule).toBe(2);  // 등급이 오류(2)여야 함
    }
  });

  // 효과 안에서 props 를 복사하는 코드가 오류로 잡히는지 검사
  it("reports a probe that copies props in an effect as errors", { timeout: 30_000 }, async () => {
    // 컴포넌트 폴더의 가짜 파일 이름으로 그 글자를 검사
    const [result] = await eslint.lintText(PROBE, { filePath: join(ROOT, "src/components/Probe.tsx") });
    const hooks = result.messages  // 검사 결과 메시지에서
      // 훅 규칙에서 나온 것만 거른다
      .filter((message) => message.ruleId?.startsWith("react-hooks/"))
      .map((message) => [message.ruleId, message.severity]);  // 규칙 이름과 등급 쌍으로 변환
    // 효과 안 상태 설정이 오류(2)로 잡혀야 함
    expect(hooks).toContainEqual(["react-hooks/set-state-in-effect", 2]);
    // 의존성 배열 누락이 오류(2)로 잡혀야 함
    expect(hooks).toContainEqual(["react-hooks/exhaustive-deps", 2]);
  });
});
