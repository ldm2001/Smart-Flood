import { MODE_ICONS, MODE_LABELS } from "@/lib/layout-data";
import type { Input } from "@/lib/schema";
import { Glyph } from "./Glyph";

// 배지가 받는 값
interface Props {
  dataSource: Input | null;  // 서버가 알린 입력원. 아직 없으면 null
  mock: boolean;  // 서버 없이 mock 을 보여 주는 중인지
}

// 데이터 모드 배지(가상·재생·실측)
export function Mode({ dataSource, mock }: Props) {
  return (
    <>
      <span className="chip">
        {// 모드 아이콘. 없으면 빈 원
        }
        <Glyph name={dataSource ? MODE_ICONS[dataSource] : "circle"} />
        모드 {dataSource ? MODE_LABELS[dataSource] : "—"}
      </span>
      {mock && (
        <strong className="chip bg-amber font-medium text-bg">
          <Glyph name="info" />
          {// 서버 없이 가상 값을 보여 주는 안내. 화면에서 하나뿐인 채운 칩
          }
          가상 데이터(서버 미연결)
        </strong>
      )}
    </>
  );
}
