import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {  // 탭 제목과 설명 정보(Next 가 읽는 고정 이름)
  // 탭 제목: 기본값과 하위 페이지용 양식
  title: { default: "SMART FLOOD | 도심 침수 예측 관제", template: "%s | SMART FLOOD" },
  // 검색·공유에 쓰이는 설명
  description: "A·B·C 구역 도시 침수 모형의 수위·예측·알림 이력을 보여 주는 시험용 관제 화면",
};

// 브라우저 테마 색(Next 가 읽는 고정 이름)
export const viewport: Viewport = { themeColor: "#07111f" };

const NAV = [  // 메뉴 목록. 정적 export 규칙에 따라 주소 끝에 /를 붙임
  { href: "/", icon: "▦", label: "종합 관제" },  // 종합 관제 메뉴
  { href: "/ops/", icon: "⚙", label: "운영·설정" },  // 운영·설정 메뉴
  { href: "/logs/", icon: "◷", label: "기록·재생" },  // 기록·재생 메뉴
];

// 모든 페이지를 감싸는 공통 틀
export default function Layout({ children }: Readonly<{ children: ReactNode }>) {
  return (  // 화면에 그릴 내용을 반환
    // 문서 최상위. 언어는 한국어다
    <html lang="ko">
      {// 본문 영역
      }
      <body>
        {// 전체 틀. 넓으면 옆 메뉴와 본문을 나란히 놓는다
        }
        <div className="min-h-screen md:flex">
          {// 옆 메뉴 영역. 좁으면 위에, 넓으면 왼쪽에 붙는다
          }
          <aside className="border-b border-line bg-sidebar p-3 md:sticky md:top-0 md:flex md:h-screen md:w-60 md:shrink-0 md:flex-col md:border-r md:border-b-0 md:px-4 md:py-7">
            {// 로고 링크. 누르면 첫 화면으로 간다
            }
            <Link href="/" className="mb-3 flex items-center gap-3 px-2 text-lg font-black md:mb-8">
              {// 로고 표시 상자를 연다
              }
              <span
                aria-hidden="true"  // 낭독기는 건너뛴다
                // 둥근 네모 바탕에 큰 글자
                className="grid size-10 place-items-center rounded-xl bg-brandmark text-3xl text-brandmark-ink"
              >
                {// 로고 기호
                }
                ≋
              </span>
              {// 로고 글자 칸
              }
              <span>
                {// 서비스 이름. FLOOD 만 강조 색이다
                }
                SMART <b className="text-brand">FLOOD</b>
              </span>
            </Link>
            {// 메뉴 목록 영역. 좁으면 옆으로 밀어 본다
            }
            <nav aria-label="메뉴" className="flex gap-1 overflow-x-auto md:grid">
              {// 메뉴마다 링크를 그린다
              }
              {NAV.map((item) => (
                <Link  // 메뉴 링크를 연다
                  key={item.href}  // 주소를 키로 기록
                  href={item.href}  // 이동할 주소
                  // 한 줄 메뉴 모양. 올리면 바탕이 바뀐다
                  className="flex items-center gap-3 rounded-lg px-4 py-3 font-bold whitespace-nowrap text-nav-ink hover:bg-nav-hover"
                >
                  {// 메뉴 아이콘(낭독기는 건너뛴다)
                  }
                  <span aria-hidden="true">{item.icon}</span>
                  {// 메뉴 이름
                  }
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          {// 본문과 바닥글 묶음. 남는 폭을 모두 쓴다
          }
          <div className="flex min-w-0 flex-1 flex-col">
            {// 각 페이지 내용이 들어가는 자리
            }
            <div className="flex-1">{children}</div>
            {// 바닥글 영역
            }
            <footer className="border-t border-line px-4 py-4 text-muted md:px-8">
              {// 시험용이라는 안내 문구
              }
              시험용 화면입니다. 실제 재난 판단·재난문자에 쓸 수 없습니다.
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
