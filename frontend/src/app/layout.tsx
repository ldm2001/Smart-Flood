import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { Glyph } from "@/components/Glyph";
import { Menu } from "@/components/Menu";
import "./globals.css";

export const metadata: Metadata = {  // 탭 제목과 설명 정보(Next 가 읽는 고정 이름)
  title: { default: "SMART FLOOD | 도심 침수 예측 관제", template: "%s | SMART FLOOD" },
  description: "A·B·C 구역 도시 침수 모형의 수위·예측·알림 이력을 보여 주는 시험용 관제 화면",
};

export const viewport: Viewport = { themeColor: "#0b0d14" };  // 브라우저 테마 색(Next 고정 이름)

// 모든 페이지를 감싸는 공통 틀
export default function Layout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        {// 전체 틀. 넓으면 옆 메뉴와 본문을 나란히 놓음
        }
        <div className="min-h-screen md:flex">
          {// 옆 메뉴 영역. 좁으면 위에, 넓으면 왼쪽에 붙음
          }
          <aside className="border-b border-line bg-sidebar p-3 md:sticky md:top-0 md:flex md:h-screen md:w-60 md:shrink-0 md:flex-col md:border-r md:border-b-0 md:px-4 md:py-7">
            {// 로고 링크. 누르면 첫 화면으로 감
            }
            <Link href="/" className="mb-3 flex h-10 items-center gap-2 px-3 text-lg font-semibold md:mb-6">
              <Glyph name="wave" className="size-6 text-brand" />
              SMART FLOOD
            </Link>
            {// 메뉴 목록 영역. 좁으면 옆으로 밀어 봄
            }
            <Menu />
          </aside>
          {// 본문과 바닥글 묶음. 남는 폭을 모두 씀
          }
          <div className="flex min-w-0 flex-1 flex-col">
            {// 각 페이지 내용이 들어가는 자리
            }
            <div className="flex-1">{children}</div>
            <footer className="border-t border-line px-4 py-4 text-muted md:px-8">
              시험용 화면입니다. 실제 재난 판단·재난문자에 쓸 수 없습니다.
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
