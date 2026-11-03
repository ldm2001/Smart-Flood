"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { address } from "@/lib/derive";

const NAV = [  // 메뉴 목록. 정적 export 규칙에 따라 주소 끝에 / 를 붙임
  { href: "/", label: "종합 관제" },
  { href: "/ops/", label: "운영·설정" },
  { href: "/logs/", label: "기록·재생" },
];

// 옆 메뉴. 지금 페이지 줄은 한 단 밝은 바탕과 가는 선
export function Menu() {
  const here = address(usePathname());
  return (
    <nav aria-label="메뉴" className="flex gap-1 overflow-x-auto md:grid">
      {NAV.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={here === item.href ? "page" : undefined}
          className="flex h-10 items-center rounded-lg border border-transparent px-3 whitespace-nowrap text-soft transition-colors hover:bg-panel hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand aria-[current=page]:border-line aria-[current=page]:bg-raised aria-[current=page]:text-ink"
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
