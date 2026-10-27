import { Monitor } from "@/components/MonitorView";

// 종합 관제 첫 화면. 정적 export 라서 값은 모두 브라우저에서 그린다
export default function Home() {
  return <Monitor />;  // 종합 관제 컴포넌트를 그린다
}
