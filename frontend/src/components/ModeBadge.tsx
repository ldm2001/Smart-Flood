import { MODE_ICONS, MODE_LABELS } from "@/lib/layout-data";
import type { Input } from "@/lib/schema";

// 배지가 받는 값
interface Props {
  dataSource: Input | null;  // 서버가 알린 입력원. 아직 없으면 null
  mock: boolean;  // 서버 없이 mock 을 보여 주는 중인지
}

// 데이터 모드 배지(가상·재생·실측)
export function Mode({ dataSource, mock }: Props) {
  return (  // 화면에 그릴 내용을 반환
    // 배지 둘을 한 묶음으로 기록
    <>
      {// 모드 알약
      }
      <span className="pill">
        {// 모드 아이콘. 없으면 빈 동그라미
        }
        <span aria-hidden="true">{dataSource ? MODE_ICONS[dataSource] : "○"}</span>
        {// 모드 이름. 없으면 줄표
        }
        모드 {dataSource ? MODE_LABELS[dataSource] : "—"}
      </span>
      {// mock 일 때만 크게 경고를 단다
      }
      {mock && (
        // 경고 알약
        <strong className="pill border-2 border-amber bg-transparent text-lg text-amber">
          {// 경고 아이콘
          }
          <span aria-hidden="true">{"⚠︎"}</span>
          {// 서버 없이 가상 값을 보여 준다는 안내
          }
          가상 데이터(서버 미연결)
        </strong>
      )}
    </>
  );
}
