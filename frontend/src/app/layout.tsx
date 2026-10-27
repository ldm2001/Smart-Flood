import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {  // 탭 제목과 설명 정보(Next 가 읽는 고정 이름)
  title: { default: "SMART FLOOD | 도심 침수 예측 관제", template: "%s | SMART FLOOD" },
  description: "A·B·C 구역 도시 침수 모형의 수위·예측·알림 이력을 보여 주는 시험용 관제 화면",
};

export const viewport: Viewport = { themeColor: "#07111f" };  // 브라우저 테마 색(Next 고정 이름)

const NAV = [  // 메뉴 목록. 정적 export 규칙에 따라 주소 끝에 /를 붙임
  { href: "/", icon: "▦", label: "종합 관제" },
  { href: "/ops/", icon: "⚙", label: "운영·설정" },
  { href: "/logs/", icon: "◷", label: "기록·재생" },
];

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
            <Link href="/" className="mb-3 flex items-center gap-3 px-2 text-lg font-black md:mb-8">
              <span
                aria-hidden="true"
                className="grid size-10 place-items-center rounded-xl bg-brandmark text-3xl text-brandmark-ink"
              >
                ≋
              </span>
              <span>
                {// 서비스 이름. FLOOD 만 강조 색
                }
                SMART <b className="text-brand">FLOOD</b>
              </span>
            </Link>
            {// 메뉴 목록 영역. 좁으면 옆으로 밀어 봄
            }
            <nav aria-label="메뉴" className="flex gap-1 overflow-x-auto md:grid">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 rounded-lg px-4 py-3 font-bold whitespace-nowrap text-nav-ink hover:bg-nav-hover"
                >
                  {// 메뉴 아이콘(낭독기는 건너뜀)
                  }
                  <span aria-hidden="true">{item.icon}</span>
                  {item.label}
                </Link>
              ))}
            </nav>
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
