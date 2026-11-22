import type { Metadata } from "next";
import { Desk } from "@/components/OpsView";

export const metadata: Metadata = { title: "운영·설정" };  // 탭 제목(Next 가 읽는 고정 이름)

// 운영·설정 화면. 정적 export 라서 제어와 값은 모두 브라우저에서 그림
export default function Ops() {
  return <Desk />;
}
