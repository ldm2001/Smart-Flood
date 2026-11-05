import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

// 프런트 폴더 경로(지시서 9장 2번: 훅 규칙 여섯 개가 오류 등급인지 봄)
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const RAISED = ["exhaustive-deps", "set-state-in-effect", "set-state-in-render", "purity", "refs", "immutability"];

// 규칙 설정에서 등급 숫자를 구하는 도우미
const severity = (entry: unknown) => {
  const level = Array.isArray(entry) ? entry[0] : entry;
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

describe("check 2: eslint config", () => {
  const eslint = new ESLint({ cwd: ROOT });

  it("raises the six react-hooks rules to error", { timeout: 30_000 }, async () => {
    const config = await eslint.calculateConfigForFile(join(ROOT, "src/app/page.tsx"));
    for (const rule of [...RAISED, "rules-of-hooks"]) {
      expect(severity(config.rules[`react-hooks/${rule}`]), rule).toBe(2);
    }
  });

  it("reports a probe that copies props in an effect as errors", { timeout: 30_000 }, async () => {
    const [result] = await eslint.lintText(PROBE, { filePath: join(ROOT, "src/components/Probe.tsx") });
    const hooks = result.messages
      .filter((message) => message.ruleId?.startsWith("react-hooks/"))
      .map((message) => [message.ruleId, message.severity]);
    expect(hooks).toContainEqual(["react-hooks/set-state-in-effect", 2]);
    expect(hooks).toContainEqual(["react-hooks/exhaustive-deps", 2]);
  });
});
