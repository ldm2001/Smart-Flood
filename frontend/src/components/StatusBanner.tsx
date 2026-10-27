import type { Banner } from "@/lib/derive";
import { STAGE_ICONS, STAGE_LABELS } from "@/lib/layout-data";

// 머리글 컴포넌트. 문구는 caption 이 서버 alerts 로 만든 값이다
export function Headline({ banner }: { banner: Banner | null }) {
  return (  // 화면에 그릴 내용을 반환
    <section  // 경보 구획을 연다
      aria-live="polite"  // 바뀐 내용을 화면 낭독기가 읽게
      data-stage={banner?.stage}  // 단계 값을 data 속성에 단다
      // 왼쪽 굵은 띠에 단계 색을 기록
      className="panel mb-6 flex items-center gap-5 border-l-8 border-l-(--stage,var(--line)) p-5"
    >
      {// 단계 아이콘 칸(낭독기는 건너뛴다)
      }
      <span aria-hidden="true" className="text-5xl leading-none text-(--stage,var(--muted))">
        {// 배너가 있으면 그 단계의 아이콘, 없으면 줄임표
        }
        {banner ? STAGE_ICONS[banner.stage] : "…"}
      </span>
      {// 글 묶음 상자
      }
      <div>
        {// 단계 이름. 배너가 없으면 자료 대기
        }
        <p className="text-lg font-bold text-(--stage,var(--muted))">{banner ? STAGE_LABELS[banner.stage] : "자료 대기"}</p>
        {// 경보 문구. 배너가 없으면 기다리는 중 안내
        }
        <h2 className="text-3xl font-bold">{banner?.message ?? "수위 자료를 기다리는 중입니다"}</h2>
      </div>
    </section>
  );
}
