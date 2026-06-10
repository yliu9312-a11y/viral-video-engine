/**
 * Motion Design Tokens — 专业级动画预设
 *
 * 基于 Disney 12 原则 + 短视频爆款动效研究。
 * 所有 Remotion 组件必须用这些预设，不要手写 spring config。
 */

import { spring, interpolate, Easing, useCurrentFrame, useVideoConfig } from 'remotion';

// ═══════════════════════════════════════════════════════
// Spring 预设 — 5 种物理特性
// ═══════════════════════════════════════════════════════

export const SPRING = {
  /** 快速弹入，轻微过冲，快速稳定 — 标题/产品入场 */
  snappy: { damping: 12, stiffness: 200, mass: 0.8 },
  /** 柔和浮动，无弹跳 — 背景/装饰元素 */
  gentle: { damping: 20, stiffness: 80, mass: 1 },
  /** 戏剧性弹跳，夸张过冲 — 促销/价格/强调 */
  bouncy: { damping: 6, stiffness: 180, mass: 0.6 },
  /** 沉稳厚重，缓慢到位 — 大字/品牌名 */
  heavy: { damping: 15, stiffness: 100, mass: 1.5 },
  /** 弹性回弹，高能量 — CTA/按钮/角标 */
  elastic: { damping: 4, stiffness: 250, mass: 0.5 },
} as const;

export type SpringPreset = keyof typeof SPRING;

// ═══════════════════════════════════════════════════════
// Easing 预设 — 专业曲线
// ═══════════════════════════════════════════════════════

export const EASE = {
  /** 指数出场 — 快起慢落，最常用的入场曲线 */
  expoOut: Easing.bezier(0.16, 1, 0.3, 1),
  /** 指数入场 — 慢起快落，适合出场 */
  expoIn: Easing.bezier(0.7, 0, 0.84, 0),
  /** 回弹出场 — 到位后轻微过冲 */
  backOut: Easing.out(Easing.back(1.4)),
  /** 弹性出场 — 多次弹跳衰减 */
  elasticOut: Easing.out(Easing.elastic(1.2)),
  /** 弹跳出场 — 真实物理弹跳 */
  bounceOut: Easing.out(Easing.bounce),
  /** 平滑过渡 — 无过冲 */
  smooth: Easing.bezier(0.25, 0.1, 0.25, 1),
  /** 戏剧性 — 强对比快慢 */
  dramatic: Easing.bezier(0.87, 0, 0.13, 1),
} as const;

// ═══════════════════════════════════════════════════════
// 时序预设 — 帧数偏移
// ═══════════════════════════════════════════════════════

export const STAGGER = {
  /** 文字逐字 — 每字间隔 2 帧 */
  char: 2,
  /** 元素逐个 — 每元素间隔 4 帧 */
  element: 4,
  /** 卡片逐张 — 每卡间隔 6 帧 */
  card: 6,
  /** 慢速序列 — 每项间隔 8 帧 */
  slow: 8,
} as const;

// ═══════════════════════════════════════════════════════
// 运动工具函数
// ═══════════════════════════════════════════════════════

/**
 * 多属性交错入场 — 每个属性用不同 spring + 不同延迟
 * 这是区分"玩具"和"专业"的核心差异
 */
export function staggeredEntrance(
  frame: number,
  fps: number,
  delay: number = 0,
  preset: SpringPreset = 'snappy',
) {
  const f = Math.max(0, frame - delay);
  const cfg = SPRING[preset];

  // 每个属性偏移 2 帧，用不同 spring
  const opacity = spring({ frame: f, fps, config: { ...cfg, damping: cfg.damping + 8 } });
  const scale = spring({ frame: f - 2, fps, config: cfg });
  const translateY = spring({ frame: f - 4, fps, config: { ...cfg, stiffness: cfg.stiffness * 0.8 } });
  const rotate = spring({ frame: f - 6, fps, config: { ...cfg, damping: cfg.damping - 2 } });

  return {
    opacity,
    scale: interpolate(scale, [0, 1], [0.7, 1]),
    translateY: interpolate(translateY, [0, 1], [40, 0]),
    rotate: interpolate(rotate, [0, 1], [-8, 0]),
  };
}

/**
 * 呼吸脉冲 — 用于 CTA 按钮持续吸引注意力
 */
export function pulse(frame: number, speed: number = 0.15, amplitude: number = 0.06) {
  return 1 + Math.sin(frame * speed) * amplitude;
}

/**
 * 噪声偏移 — 有机微动（替代粗糙的 Math.sin 抖动）
 * 需要 @remotion/noise
 */
export function noiseOffset(seed: number, frame: number, speed: number = 0.03, amplitude: number = 8) {
  try {
    const { noise2D } = require('@remotion/noise');
    return {
      x: noise2D(seed, frame * speed, 0) * amplitude,
      y: noise2D(seed + 50, 0, frame * speed) * amplitude,
    };
  } catch {
    // fallback to sin if noise package not available
    return {
      x: Math.sin(frame * speed * 2) * amplitude * 0.5,
      y: Math.cos(frame * speed * 3) * amplitude * 0.5,
    };
  }
}

/**
 * 淡入淡出 — 带缓入缓出的透明度控制
 */
export function fadeInOut(
  frame: number,
  totalFrames: number,
  fadeInFrames: number = 10,
  holdFrames: number = 0,
  fadeOutFrames: number = 10,
) {
  const fadeOutStart = totalFrames - fadeOutFrames;
  return interpolate(
    frame,
    [0, fadeInFrames, fadeOutStart, totalFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );
}
