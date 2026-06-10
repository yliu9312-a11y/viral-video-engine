/**
 * Motion Primitives — pure animation functions
 *
 * Each primitive takes (frame, fps, params) → CSSProperties or scalar.
 * Components are thin shells; all animation logic lives here.
 * Driven by recipe.json.motion definitions.
 */

import { spring, interpolate, SpringConfig } from 'remotion';
import { SPRING, EASE } from '../design-tokens/motion';

// ═══════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════

type LooseSpringConfig = Partial<SpringConfig> & { damping: number; stiffness: number };

export interface WordRevealParams {
  staggerFrames: number;
  durationFrames: number;
  translateYFrom: number;
  springConfig: LooseSpringConfig;
}

export interface TypewriterParams {
  charIntervalFrames: number;
  cursorBlinkInterval: number;
  typingStartFrame: number;
}

export interface GlassCardParams {
  springConfig: LooseSpringConfig;
  scaleFrom: number;
}

export interface FloatingParams {
  springPreset: keyof typeof SPRING;
  noiseSpeed: number;
  noiseAmplitude: number;
}

export interface MarqueeParams {
  speed: number;
  direction: 1 | -1;
}

export interface GradientShimmerParams {
  speed: number;
  rangeStart: number;
  rangeEnd: number;
}

export interface LogoRevealParams {
  springConfig: LooseSpringConfig;
  glowPulseSpeed: number;
  glowPulseAmplitude: number;
  glowBlurBase: number;
}

export interface GlowTrailParams {
  durationFrames: number;
  easing: (t: number) => number;
}

// ═══════════════════════════════════════════════════════
// Default params (from recipe.json motion definitions)
// ═══════════════════════════════════════════════════════

export const WORD_REVEAL_DEFAULTS: WordRevealParams = {
  staggerFrames: 4,
  durationFrames: 12,
  translateYFrom: 20,
  springConfig: SPRING.snappy,
};

export const TYPEWRITER_DEFAULTS: TypewriterParams = {
  charIntervalFrames: 1,
  cursorBlinkInterval: 15,
  typingStartFrame: 15,
};

export const GLASS_CARD_DEFAULTS: GlassCardParams = {
  springConfig: { damping: 15, stiffness: 100 },
  scaleFrom: 0.8,
};

export const FLOATING_DEFAULTS: FloatingParams = {
  springPreset: 'snappy',
  noiseSpeed: 0.005,
  noiseAmplitude: 5,
};

export const MARQUEE_DEFAULTS: MarqueeParams = {
  speed: 2.5,
  direction: -1,
};

export const GRADIENT_SHIMMER_DEFAULTS: GradientShimmerParams = {
  speed: 0.02,
  rangeStart: -50,
  rangeEnd: 150,
};

export const LOGO_REVEAL_DEFAULTS: LogoRevealParams = {
  springConfig: { damping: 8, stiffness: 150 },
  glowPulseSpeed: 0.15,
  glowPulseAmplitude: 0.1,
  glowBlurBase: 60,
};

export const GLOW_TRAIL_DEFAULTS: GlowTrailParams = {
  durationFrames: 90,
  easing: EASE.smooth,
};

// ═══════════════════════════════════════════════════════
// Primitive: Word Reveal
// Per-word fade + slide with staggered timing
// ═══════════════════════════════════════════════════════

export function wordRevealStyle(
  frame: number,
  fps: number,
  wordIndex: number,
  params: Partial<WordRevealParams> = {},
): { opacity: number; transform: string } {
  const p = { ...WORD_REVEAL_DEFAULTS, ...params };
  const delay = wordIndex * p.staggerFrames;
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: p.springConfig });
  const opacity = interpolate(entry, [0, 1], [0, 1]);
  const translateY = interpolate(entry, [0, 1], [p.translateYFrom, 0]);

  return { opacity, transform: `translateY(${translateY}px)` };
}

// ═══════════════════════════════════════════════════════
// Primitive: Typewriter
// Character count + cursor blink state
// ═══════════════════════════════════════════════════════

export function typewriterState(
  frame: number,
  textLength: number,
  params: Partial<TypewriterParams> = {},
): { charsVisible: number; cursorVisible: boolean; isTypingDone: boolean } {
  const p = { ...TYPEWRITER_DEFAULTS, ...params };
  const f = Math.max(0, frame - p.typingStartFrame);
  const charsVisible = Math.min(Math.floor(f / p.charIntervalFrames), textLength);
  const isTypingDone = charsVisible >= textLength;

  const cursorFrame = Math.max(0, frame - p.typingStartFrame);
  const cursorVisible = cursorFrame > 0 && Math.floor(cursorFrame / p.cursorBlinkInterval) % 2 === 0;

  return { charsVisible, cursorVisible, isTypingDone };
}

// ═══════════════════════════════════════════════════════
// Primitive: Glass Card Entry
// Scale + opacity spring entrance
// ═══════════════════════════════════════════════════════

export function glassCardStyle(
  frame: number,
  fps: number,
  params: Partial<GlassCardParams> = {},
): { opacity: number; transform: string } {
  const p = { ...GLASS_CARD_DEFAULTS, ...params };
  const entry = spring({ frame, fps, config: p.springConfig });
  const opacity = interpolate(entry, [0, 1], [0, 1]);
  const scale = interpolate(entry, [0, 1], [p.scaleFrom, 1]);

  return { opacity, transform: `scale(${scale})` };
}

// ═══════════════════════════════════════════════════════
// Primitive: Floating Mockup Entry
// Staggered multi-property entrance (opacity, scale, translateY, rotate)
// ═══════════════════════════════════════════════════════

export function floatingEntryStyle(
  frame: number,
  fps: number,
  delay: number = 0,
  preset: keyof typeof SPRING = 'snappy',
) {
  const f = Math.max(0, frame - delay);
  const cfg = SPRING[preset];

  const opacity = spring({ frame: f, fps, config: { ...cfg, damping: cfg.damping + 8 } });
  const scaleVal = spring({ frame: f - 2, fps, config: cfg });
  const translateYVal = spring({ frame: f - 4, fps, config: { ...cfg, stiffness: cfg.stiffness * 0.8 } });
  const rotateVal = spring({ frame: f - 6, fps, config: { ...cfg, damping: cfg.damping - 2 } });

  return {
    opacity,
    scale: interpolate(scaleVal, [0, 1], [0.7, 1]),
    translateY: interpolate(translateYVal, [0, 1], [40, 0]),
    rotate: interpolate(rotateVal, [0, 1], [-8, 0]),
  };
}

// ═══════════════════════════════════════════════════════
// Primitive: Marquee Offset
// Linear horizontal scroll
// ═══════════════════════════════════════════════════════

export function marqueeOffset(
  frame: number,
  _textWidth: number,
  params: Partial<MarqueeParams> = {},
): number {
  const p = { ...MARQUEE_DEFAULTS, ...params };
  return frame * p.speed * p.direction;
}

// ═══════════════════════════════════════════════════════
// Primitive: Gradient Shimmer
// Background position animation for text gradient
// ═══════════════════════════════════════════════════════

export function gradientShimmerPosition(
  frame: number,
  params: Partial<GradientShimmerParams> = {},
): string {
  const p = { ...GRADIENT_SHIMMER_DEFAULTS, ...params };
  const pos = p.rangeStart + ((frame * p.speed * 100) % (p.rangeEnd - p.rangeStart));
  return `${pos}% 0`;
}

// ═══════════════════════════════════════════════════════
// Primitive: Logo Reveal
// Spring bounce entry + glow pulse
// ═══════════════════════════════════════════════════════

export function logoRevealStyle(
  frame: number,
  fps: number,
  params: Partial<LogoRevealParams> = {},
): { scale: number; glowBlur: number } {
  const p = { ...LOGO_REVEAL_DEFAULTS, ...params };
  const entry = spring({ frame, fps, config: p.springConfig });
  const scale = interpolate(entry, [0, 0.3], [0, 1]);

  const glowPulse = 1 + Math.sin(frame * p.glowPulseSpeed) * p.glowPulseAmplitude;
  const glowBlur = p.glowBlurBase * glowPulse;

  return { scale, glowBlur };
}

// ═══════════════════════════════════════════════════════
// Primitive: Glow Trail Position
// Progress along an SVG path with easing
// ═══════════════════════════════════════════════════════

export function glowTrailProgress(
  frame: number,
  delay: number = 0,
  params: Partial<GlowTrailParams> = {},
): number {
  const p = { ...GLOW_TRAIL_DEFAULTS, ...params };
  const f = Math.max(0, frame - delay);
  return interpolate(f, [0, p.durationFrames], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: p.easing,
  });
}

// ═══════════════════════════════════════════════════════
// Primitive: Perspective Tilt
// 3D transform for mockup screenshots
// ═══════════════════════════════════════════════════════

export function perspectiveTiltStyle(
  frame: number,
  fps: number,
  delay: number = 0,
): { scale: number; rotateY: number } {
  const entry = spring({
    frame: Math.max(0, frame - delay),
    fps,
    config: SPRING.gentle,
  });
  return {
    scale: interpolate(entry, [0, 1], [0.85, 1]),
    rotateY: interpolate(entry, [0, 1], [0, 5]),
  };
}

// ═══════════════════════════════════════════════════════
// Re-exports for convenience
// ═══════════════════════════════════════════════════════

export { fadeInOut, SPRING, EASE } from '../design-tokens/motion';
