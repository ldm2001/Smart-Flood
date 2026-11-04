import type { Banner } from "@/lib/derive";
import { STAGE_ICONS, STAGE_LABELS } from "@/lib/layout-data";
import { Glyph } from "./Glyph";

// 머리글 컴포넌트. 문구는 caption 이 서버 alerts 로 만든 값. 주의 이상만 바탕·테두리를 켬
export function Headline({ banner, guide = null }: { banner: Banner | null; guide?: string | null }) {
  return (
    <section
      aria-live="polite"  // 바뀐 내용을 화면 낭독기가 읽게
      data-stage={banner?.stage}
      className="panel mb-6 flex items-center gap-4 border-(--alert,var(--line)) bg-(--tint,var(--panel)) p-5"
    >
      {// 단계 아이콘. 배너가 없으면 점 셋
      }
      <Glyph name={banner ? STAGE_ICONS[banner.stage] : "dots"} className="size-6 text-(--stage,var(--muted))" />
      <div>
        {// 단계 이름. 배너가 없으면 자료 대기
        }
        <p className="font-medium text-(--stage,var(--muted))">{banner ? STAGE_LABELS[banner.stage] : "자료 대기"}</p>
        {// 경보 문구. 배너가 없으면 기다리는 중 안내
        }
        <h2 className="text-2xl leading-snug font-medium">{banner?.message ?? "수위 자료를 기다리는 중입니다"}</h2>
        {// 대피 안내. route 가 서버 alerts 로 만든 한 줄
        }
        {guide && <p className="mt-1 text-base text-muted">{guide}</p>}
      </div>
    </section>
  );
}
