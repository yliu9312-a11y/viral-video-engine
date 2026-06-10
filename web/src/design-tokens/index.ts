/**
 * VST Design Tokens — 视觉美感工程化
 *
 * 所有 Remotion 组件必须 import 此文件，禁止使用魔法数字。
 * 基于 vst_aesthetic_engineering_guide.md 的 8 条铁律。
 */

// ─── 画布 ───
export const CANVAS = {
  width: 1080,
  height: 1920,
  fps: 30,
} as const;

// ─── 安全区（铁律 1）───
export const SAFE_ZONE = {
  top: 200,
  bottom: 320,
  left: 60,
  right: 120,
  centerWidth: 900,
  centerHeight: 1400,
} as const;

// ─── 字号 4 档制（铁律 2 + 3，按 1080×1920 画布校准）───
export const FONT_SIZES = {
  display: 96,    // 屏中央巨字，1 视频最多 2 次 (占画布 8.9%)
  headline: 64,   // 主标题、卖点大字 (占画布 5.9%)
  body: 40,       // 字幕、说明文字 (占画布 3.7%)
  caption: 28,    // 数据小字、品牌名、价格单位 (占画布 2.6%)
} as const;
export type FontSize = keyof typeof FONT_SIZES;

// ─── 字重（铁律 4）───
export const FONT_WEIGHTS = {
  black: 900,
  heavy: 800,
  bold: 700,
  medium: 500,
  regular: 400,
} as const;

// ─── 字体（铁律 4，最多 2 种）───
export const FONTS = {
  primary: '"PingFang SC", "Source Han Sans CN", "Alibaba PuHuiTi 3.0", sans-serif',
  display: '"Alibaba PuHuiTi 3.0 115 Black", "PingFang SC", sans-serif',
} as const;

// ─── 调色板 60-30-10（铁律 5）───
export const PALETTES = {
  beauty: {
    primary: '#F5E6E0',    // 60% 米白背景
    secondary: '#1F1B1A',  // 30% 近黑文字
    accent: '#E8746B',     // 10% 珊瑚红强调
  },
  digital: {
    primary: '#0A0E1A',
    secondary: '#FFFFFF',
    accent: '#3DE0FF',
  },
  food: {
    primary: '#FAF5E8',
    secondary: '#2C1A0E',
    accent: '#E8B04D',
  },
  viral: {
    primary: '#000000',
    secondary: '#FFFFFF',
    accent: '#FFD60A',
  },
  promo: {
    primary: '#050510',
    secondary: '#FFFFFF',
    accent: '#3B82F6',
    accentLight: '#60A5FA',
    accentGlow: 'rgba(59, 130, 246, 0.3)',
    accentGlowSubtle: 'rgba(59, 130, 246, 0.15)',
    accentGlowBg: 'rgba(59, 130, 246, 0.08)',
    bgGlass: 'rgba(15, 23, 42, 0.6)',
    bgGlassHeavy: 'rgba(15, 23, 42, 0.7)',
    borderGlass: 'rgba(59, 130, 246, 0.3)',
    borderGlassStrong: 'rgba(59, 130, 246, 0.4)',
    highlight: 'rgba(255, 255, 255, 0.05)',
    textBright: 'rgba(255, 255, 255, 0.9)',
    textMuted: 'rgba(255, 255, 255, 0.5)',
    textSubtle: 'rgba(255, 255, 255, 0.35)',
    vignette: 'rgba(0, 0, 0, 0.6)',
  },
} as const;
export type PaletteName = keyof typeof PALETTES;

// ─── 间距 8 倍数制 ───
export const SPACING = {
  xs: 8,
  sm: 16,
  md: 24,
  lg: 32,
  xl: 48,
  '2xl': 64,
  '3xl': 96,
} as const;

// ─── 圆角 ───
export const RADIUS = {
  sm: 8,
  md: 16,
  lg: 24,
  pill: 9999,
} as const;

// ─── Easing（铁律 8，禁止 linear）───
export const EASING = {
  enter: [0.16, 1, 0.3, 1] as [number, number, number, number],     // ease-out-expo
  exit: [0.7, 0, 0.84, 0] as [number, number, number, number],      // ease-in-expo
  emphasize: [0.34, 1.56, 0.64, 1] as [number, number, number, number], // 略带回弹
} as const;

// ─── 字幕样式预设（铁律 6，3 种合格做法）───
export const CAPTION_STYLES = {
  black_pill: {
    background: 'rgba(0, 0, 0, 0.75)',
    color: '#FFFFFF',
    padding: `${SPACING.sm}px ${SPACING.lg}px`,
    borderRadius: RADIUS.md,
    fontWeight: FONT_WEIGHTS.bold,
    fontFamily: FONTS.primary,
  },
  outlined_white: {
    color: '#FFFFFF',
    WebkitTextStroke: '3px #000000',
    textShadow: '0 4px 12px rgba(0,0,0,0.5)',
    fontWeight: FONT_WEIGHTS.black,
    fontFamily: FONTS.primary,
  },
  highlight_keyword: {
    color: '#FFFFFF',
    fontWeight: FONT_WEIGHTS.black,
    fontFamily: FONTS.display,
  },
} as const;
export type CaptionStyle = keyof typeof CAPTION_STYLES;

// ─── ProductPromo 专用字体层级 ───
export const TYPOGRAPHY_PROMO = {
  hero: { fontSize: 72, fontWeight: 800, letterSpacing: -2, lineHeight: 1.1 },
  h1: { fontSize: 48, fontWeight: 700, letterSpacing: -1, lineHeight: 1.2 },
  h2: { fontSize: 32, fontWeight: 600, letterSpacing: 0, lineHeight: 1.3 },
  body: { fontSize: 18, fontWeight: 400, letterSpacing: 0.5, lineHeight: 1.6 },
  caption: { fontSize: 14, fontWeight: 400, letterSpacing: 1, lineHeight: 1.4 },
  label: { fontSize: 12, fontWeight: 600, letterSpacing: 2, lineHeight: 1.0 },
} as const;
export type TypographyPromo = keyof typeof TYPOGRAPHY_PROMO;

// ─── ProductPromo 专用间距 ───
export const SPACING_PROMO = {
  section: { padding: '60px 80px' },
  card: { padding: 24, gap: 16, borderRadius: 16 },
  grid: { columns: 4, gap: 20 },
  beatMargin: 0,
} as const;

// ─── 对比度校验（铁律 5 的 WCAG AA）───
function luminance(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const toLinear = (c: number) => c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

export function contrastRatio(fg: string, bg: string): number {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

export function assertContrast(fg: string, bg: string, fontSize: number): boolean {
  const ratio = contrastRatio(fg, bg);
  const required = fontSize >= FONT_SIZES.headline ? 3 : 4.5;
  return ratio >= required;
}
