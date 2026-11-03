import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

type Rgb = [number, number, number];

// 저장소 안 파일을 글자로 읽음
const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const tokens = read("../src/styles/tokens.css").replace(/\/\*[\s\S]*?\*\//g, "");  // 주석 뺌
const globals = read("../src/app/globals.css").replace(/\/\*[\s\S]*?\*\//g, "");
const root = tokens.match(/:root\s*\{([^}]*)\}/)?.[1] ?? "";
const theme = tokens.match(/@theme\s+inline\s*\{([^}]*)\}/)?.[1] ?? "";
const entries = [...root.matchAll(/--([a-z-]+):\s*([^;]+);/g)];  // :root 의 --이름: 값; 짝
const vars = new Map(entries.map((m) => [m[1], m[2]?.trim()]));
const mixed = tokens.match(/--tint:\s*color-mix\(in oklab, var\(--stage\) (\d+)%/)?.[1];
const share = Number(mixed) / 100;  // 옅은 바탕(--tint)에 섞는 단계 색 비율

// grep 으로 확인한 글자·바탕 짝. 바탕 토큰 → 그 위 글자 토큰
const PAIRS: Record<string, string[]> = {
  sidebar: ["ink", "soft", "brand"],  // 로고 글·메뉴 글·로고 아이콘
  bg: ["ink", "soft", "muted", "amber"],  // 머리글·입력칸·바닥글·모의 자료 칩(투명)
  panel: ["ink", "soft", "muted", "green", "amber", "orange", "red"],  // 카드 글·단계 글
  raised: ["ink", "soft", "muted", "green", "amber", "red"],  // 칩·지금 메뉴·연결 아이콘
  amber: ["bg"],  // 모의 자료 배지(bg-amber text-bg)
};
const STAGES = ["caution", "warning", "evacuate"];  // 옅은 바탕(--tint)을 켜는 단계

// var(--이름) 을 따라가 #rrggbb 값을 찾음
function hex(name: string): string {
  const value = vars.get(name) ?? "";
  const link = value.match(/^var\(--([a-z-]+)\)$/)?.[1];
  return link ? hex(link) : value;
}

// #rrggbb 를 선형 RGB(0~1)로 바꿈
function linear(name: string): Rgb {
  const digits = hex(name).match(/^#([0-9a-f]{6})$/i)?.[1];
  if (!digits) throw new Error(`hex 색 아님: --${name}`);
  const channel = (at: number) => {
    const c = parseInt(digits.slice(at, at + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return [channel(0), channel(2), channel(4)];
}

// 선형 RGB 를 oklab 으로 바꿈
function oklab([r, g, b]: Rgb): Rgb {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

// color-mix(in oklab, 앞 share, 뒤) 결과를 선형 RGB 로 되돌림(0~1 밖은 자름)
function mix(front: Rgb, back: Rgb): Rgb {
  const [x, y] = [oklab(front), oklab(back)];
  const blend = (i: 0 | 1 | 2) => x[i] * share + y[i] * (1 - share);
  const [light, a, b] = [blend(0), blend(1), blend(2)];
  const l = (light + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (light - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (light - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return [
    clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

// 두 색의 WCAG 대비 비율
function ratio(text: Rgb, back: Rgb): number {
  const [one, two] = [text, back].map(([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b);
  const [hi, lo] = [Math.max(one ?? 0, two ?? 0), Math.min(one ?? 0, two ?? 0)];
  return (hi + 0.05) / (lo + 0.05);
}

// 블록의 font-size 를 px 로 바꿈. 없으면 물려받는 값(base)
function px(block: string, base: number): number {
  const [, value = "", unit = ""] = block.match(/font-size:\s*([\d.]+)(rem|px|%)/) ?? [];
  if (!value) return base;
  if (unit === "px") return Number(value);
  return unit === "%" ? (Number(value) / 100) * base : Number(value) * base;  // rem 은 html 기준
}

const CASES = Object.entries(PAIRS).flatMap(([back, inks]) => inks.map((ink) => [ink, back]));

describe("text contrast", () => {
  it.each(CASES)("keeps %s on %s at 4.5:1 or more", (ink = "", back = "") => {
    expect(ratio(linear(ink), linear(back))).toBeGreaterThanOrEqual(4.5);  // 본문 16px 이상
  });

  it.each(STAGES)("keeps stage and ink text on the %s tint at 4.5:1 or more", (stage) => {
    expect(share).toBeGreaterThan(0);  // tokens.css 의 --tint 식을 읽었는지
    const tint = mix(linear(`stage-${stage}`), linear("panel"));
    expect(ratio(linear(`stage-${stage}`), tint)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(linear("ink"), tint)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("type size", () => {
  it("keeps body text at 16 px or more", () => {
    const html = px(globals.match(/html\s*\{([^}]*)\}/)?.[1] ?? "", 16);  // 브라우저 기본 16px
    expect(html).toBeGreaterThanOrEqual(16);
    expect(px(globals.match(/body\s*\{([^}]*)\}/)?.[1] ?? "", html)).toBeGreaterThanOrEqual(16);
  });

  it.each(["key", "figure"])("keeps text-%s at 28 px or more", (name) => {
    const size = theme.match(new RegExp(`--text-${name}:\\s*([\\d.]+)rem;`))?.[1];
    expect(Number(size) * 16).toBeGreaterThanOrEqual(28);  // 1.75rem 이상
  });
});
