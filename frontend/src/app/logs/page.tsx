import type { Metadata } from "next";
import { Suspense } from "react";
import { Archive, Waiting } from "@/components/LogsView";

export const metadata: Metadata = { title: "기록·재생" };  // 탭 제목(Next 가 읽는 고정 이름)

// 기록·재생 화면. 주소의 ?id= 는 브라우저에서만 읽어 Suspense 로 감쌈
export default function Logs() {
  return (
    <Suspense fallback={<Waiting />}>
      <Archive />
    </Suspense>
  );
}
