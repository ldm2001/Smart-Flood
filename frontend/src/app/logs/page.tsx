import type { Metadata } from "next";

export const metadata: Metadata = { title: "기록·재생" };  // 탭 제목(Next 가 읽는 고정 이름)

// 기록·재생 화면. S4 에서 기록 목록·상세·재생 시작을 붙임
export default function Logs() {
  return (  // 화면에 그릴 내용을 반환
    // 본문 영역을 연다(폭은 최대 1800px)
    <main className="mx-auto w-full max-w-[1800px] px-4 py-6 md:px-8 md:py-8">
      {// 큰 제목
      }
      <h1 className="text-3xl font-black tracking-tight">기록·재생</h1>
      {// 다음 단계 안내 문구
      }
      <p className="mt-3 text-muted">실험 기록 목록과 재생 화면은 다음 단계(S4)에서 붙습니다.</p>
    </main>
  );
}
