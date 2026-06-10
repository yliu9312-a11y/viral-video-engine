import React from 'react';
import { useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';
import { SPRING } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS } from '../../design-tokens';

interface GradientTextProps {
  text: string;
  gradient?: string;
  fontSize?: number;
  fontWeight?: number;
  shimmerSpeed?: number;
  delay?: number;
}

const DEFAULT_GRADIENT = `linear-gradient(90deg, #9CA3AF, ${PALETTES.promo.secondary}, ${PALETTES.promo.accent})`;

export const GradientText: React.FC<GradientTextProps> = ({
  text,
  gradient = DEFAULT_GRADIENT,
  fontSize = FONT_SIZES.headline,
  fontWeight = FONT_WEIGHTS.heavy,
  shimmerSpeed: _shimmerSpeed = 0.02,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: SPRING.snappy });
  const opacity = interpolate(entry, [0, 1], [0, 1]);
  const translateY = interpolate(entry, [0, 1], [20, 0]);

  const shimmerX = interpolate(f, [0, 120], [-100, 200], {
    extrapolateRight: 'extend',
  });

  // Auto-reduce fontSize if text is too long for canvas (1080px - safe zone)
  const maxWidth = 900; // 1080 - 60 - 120 safe zone
  const avgCharWidth = fontSize * 0.55; // proportional font approximation
  const textWidth = text.length * avgCharWidth;
  const autoFontSize = textWidth > maxWidth
    ? Math.max(24, Math.floor(fontSize * maxWidth / textWidth))
    : fontSize;

  return (
    <span
      style={{
        display: 'inline-block',
        fontSize: autoFontSize,
        fontWeight,
        fontFamily: '"SF Pro Display", "PingFang SC", sans-serif',
        background: gradient,
        backgroundSize: '200% 100%',
        backgroundPosition: `${shimmerX}% 0`,
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        opacity,
        transform: `translateY(${translateY}px)`,
        lineHeight: 1.2,
        maxWidth,
        wordBreak: 'break-word',
        textAlign: 'center',
      }}
    >
      {text}
    </span>
  );
};
