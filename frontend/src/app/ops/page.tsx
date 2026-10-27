import type { Metadata } from "next";

export const metadata: Metadata = { title: "운영·설정" };  // 탭 제목(Next 가 읽는 고정 이름)

// 운영·설정 화면. S3 에서 제어와 구역 한계 수위 설정을 붙임
export default function Ops() {
  return (  // 화면에 그릴 내용을 반환
    // 본문 영역을 연다(폭은 최대 1800px)
    <main className="mx-auto w-full max-w-[1800px] px-4 py-6 md:px-8 md:py-8">
      {// 큰 제목
      }
      <h1 className="text-3xl font-black tracking-tight">운영·설정</h1>
      {// 다음 단계 안내 문구
      }
      <p className="mt-3 text-muted">제어와 구역 한계 수위 설정 화면은 다음 단계(S3)에서 붙습니다.</p>
    </main>
  );
}
