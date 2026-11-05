import { clock, mark, score, span, tally } from "@/lib/derive";
import { ZONES } from "@/lib/layout-data";
import type { LogEvent } from "@/lib/schema";

// 표 머리 글
const HEADS = ["구역", "위험 판단", "예측 도달", "실제 도달", "선행 시간", "오차", "판정"];
const time = (ms: number | null) => (ms === null ? "—" : clock(ms));  // 시각 칸 글(HH:MM:SS)

// 기록의 구역별 예측 도달과 실제 도달 비교 표. 사건 전에는 모두 줄표
// ended 는 실험이 끝났는지. 끝난 기록에서만 도달 없는 판단을 오경보로 셈
export function Compare({ events, ended = false }: { events: readonly LogEvent[] | null; ended?: boolean }) {
  const lines = tally(events ?? []);
  return (
    <section aria-label="예측과 실제 비교" className="panel p-5">
      <h2 className="mb-4 text-lg font-medium">예측과 실제 비교</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left whitespace-nowrap">
          <thead>
            <tr className="text-muted">
              {HEADS.map((head) => (
                <th key={head} scope="col" className="py-2 pr-4 font-normal">
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.zone} className="border-t border-line">
                <th scope="row" data-zone={line.zone} className="py-2 pr-4 font-medium">
                  {`${line.zone} ${ZONES[line.zone].name}`}
                </th>
                <td className="py-2 pr-4 font-mono tabular-nums">{time(line.judgement)}</td>
                <td className="py-2 pr-4 font-mono tabular-nums">{time(line.forecast)}</td>
                <td className="py-2 pr-4 font-mono tabular-nums">{time(line.arrival)}</td>
                <td className="py-2 pr-4 text-key font-medium tabular-nums">{span(line.lead)}</td>
                <td className="py-2 pr-4 tabular-nums">{span(line.error, true)}</td>
                <td className="py-2 pr-4 tabular-nums">{mark(line, ended)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-base leading-normal text-muted">
        예측 도달은 위험 판단 시각에 그때 남은 초를 더한 값이고,
        오차는 실제 도달에서 예측 도달을 뺀 초입니다.
      </p>
      <p className="mt-1 text-base leading-normal text-muted">
        현재 수위 경보는 한계에 닿을 때 울립니다. 선행 시간은 그보다 먼저 알린 초입니다.
      </p>
      <p className="mt-1 text-base leading-normal text-muted">{score(lines, ended)}</p>
    </section>
  );
}
