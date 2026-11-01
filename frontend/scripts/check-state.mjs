import { z } from "zod";
import { stateSchema } from "../src/lib/schema.ts";

// /api/state 응답 계약 검사(지시서 9장 10번). 화면과 같은 스키마를 노드가 타입만 지우고 읽음
const chunks = [];  // npm run check:state 가 넘긴 curl 응답 조각
for await (const chunk of process.stdin) chunks.push(chunk);
const body = Buffer.concat(chunks).toString("utf8");

// 응답 글이 계약을 지키는지 판정하는 함수
function verdict(text) {
  // 빈 입력은 문제. curl 은 서버 오류에서 아무것도 넘기지 않음
  if (text.trim() === "") return { problem: "응답이 비었다(백엔드가 꺼져 있거나 오류 응답을 냈다)" };
  let json;
  try {
    json = JSON.parse(text);
  } catch (error) {
    return { problem: `JSON 이 아니다 (${error.message})` };
  }
  const result = stateSchema.safeParse(json);
  return result.success ? { snapshot: result.data } : { problem: `계약 위반\n${z.prettifyError(result.error)}` };
}

const { problem, snapshot } = verdict(body);
if (problem) {
  console.error(`/api/state 검사 실패: ${problem}`);
  process.exitCode = 1;
} else {
  const { experimentId, dataSource, runState, timestamp } = snapshot;
  console.log(`/api/state 계약 통과: 실험 ${experimentId} · 입력원 ${dataSource} · 상태 ${runState ?? "—"} · 기준 ${timestamp}`);
}
