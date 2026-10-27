// 응답 계약 검사 스크립트(지시서 9장 10번). 검증 도구를 가져온다
import { z } from "zod";
// 화면과 같은 응답 계약을 가져온다. 노드가 타입만 지우고 그대로 읽는다
import { stateSchema } from "../src/lib/schema.ts";

// 표준 입력 조각을 모을 목록. npm run check:state 가 curl 응답을 넘긴다
const chunks = [];
// 표준 입력을 끝까지 읽어 조각을 담는다
for await (const chunk of process.stdin) chunks.push(chunk);
// 조각을 이어 글로 만든다
const body = Buffer.concat(chunks).toString("utf8");

// 응답 글이 계약을 지키는지 판정하는 함수
function verdict(text) {
  // 빈 입력이면 문제다. curl 은 서버 오류에서 아무것도 넘기지 않는다
  if (text.trim() === "") return { problem: "응답이 비었다(백엔드가 꺼져 있거나 오류 응답을 냈다)" };
  // 해석한 JSON 을 담을 자리
  let json;
  // JSON 으로 해석해 본다
  try {
    // 글을 JSON 으로 바꾼다
    json = JSON.parse(text);
  // 해석이 실패하면
  } catch (error) {
    // JSON 이 아니라는 문제를 돌려준다
    return { problem: `JSON 이 아니다 (${error.message})` };
  }
  // 계약에 맞는지 검사한다
  const result = stateSchema.safeParse(json);
  // 통과하면 응답을, 아니면 어긋난 곳을 돌려준다
  return result.success ? { snapshot: result.data } : { problem: `계약 위반\n${z.prettifyError(result.error)}` };
}

// 받은 글을 판정한다
const { problem, snapshot } = verdict(body);
// 문제가 있으면
if (problem) {
  // 실패 이유를 오류로 찍는다
  console.error(`/api/state 검사 실패: ${problem}`);
  // 실패 코드 1 로 끝낸다
  process.exitCode = 1;
// 문제가 없으면
} else {
  // 응답에서 핵심 값 네 개를 꺼낸다
  const { experimentId, dataSource, runState, timestamp } = snapshot;
  // 통과 메시지에 핵심 값을 담아 찍는다
  console.log(`/api/state 계약 통과: 실험 ${experimentId} · 입력원 ${dataSource} · 상태 ${runState ?? "—"} · 기준 ${timestamp}`);
}
