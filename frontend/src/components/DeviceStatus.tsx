import { condition, readiness } from "@/lib/derive";
import {
  DEVICE_KEYS,
  DEVICE_NAMES,
  HEALTH_ICONS,
  QUALITY_LABELS,
  QUALITY_TONES,
} from "@/lib/layout-data";
import type { Snapshot } from "@/lib/schema";

const mark = (ok: boolean) => `${ok ? HEALTH_ICONS.ok : HEALTH_ICONS.check} `;  // 아이콘과 띄어쓰기

// 보호 입력과 입력 품질, 출력 잠금
export function Devices({ snapshot }: { snapshot: Snapshot | null }) {
  const ready = snapshot && readiness(snapshot.devices);  // 보호 입력 넷의 정상 여부. 연결 중 null
  return (
    <section aria-label="현장 장치 상태" className="panel p-5">
      <h2 className="mb-4 text-xl font-bold">현장 장치 상태</h2>
      {snapshot === null ? (
        <p className="text-lg font-bold">—</p>
      ) : (
        <p className={`text-lg font-bold ${ready ? "text-(--green)" : "text-amber"}`}>
          <span aria-hidden="true">{mark(ready === true)}</span>
          {ready ? "보호 입력 정상" : "보호 상태 확인"}
        </p>
      )}
      <ul className="mt-3 space-y-1">
        {DEVICE_KEYS.map((key) => {
          const health = snapshot && condition(snapshot.devices[key]);  // 표시 글과 정상 여부
          return (
            <li key={key}>
              {health && <span aria-hidden="true">{mark(health.ok)}</span>}
              {`${DEVICE_NAMES[key]} · ${health ? health.label : "—"}`}
            </li>
          );
        })}
      </ul>
      <p className={snapshot ? `mt-3 ${QUALITY_TONES[snapshot.quality]}` : "mt-3"}>
        {snapshot && <span aria-hidden="true">{mark(snapshot.quality === "valid")}</span>}
        {`입력 품질 · ${snapshot ? QUALITY_LABELS[snapshot.quality] : "—"}`}
      </p>
      {// 계약의 outputsLocked 는 늘 true 라 보이기만 함
      }
      <p className="mt-3 flex flex-wrap items-center gap-2">
        제어 출력
        <span className="pill border border-line bg-transparent text-muted">출력 잠금</span>
      </p>
      {// 5초는 backend/config.yaml 의 offline_after_s 와 같음
      }
      <p className="mt-4 text-base text-muted">
        가상·재생 입력에서는 장치 값이 늘 정상으로 나옵니다. 실측 입력에서는 마지막 메시지 뒤
        5초 안의 장치만 정상이고, 한 번도 오지 않은 장치는 끊김, 플로트 스위치·비상정지는
        메시지에 없어 미상으로 보입니다.
      </p>
      <p className="mt-1 text-base text-muted">웹 화면은 안전 차단을 대신하지 않습니다.</p>
    </section>
  );
}
