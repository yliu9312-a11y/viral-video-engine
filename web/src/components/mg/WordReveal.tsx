import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS, SPACING } from '../../design-tokens';

interface WordRevealProps {
  text: string;
  fontSize?: number;
  color?: string;
  gradient?: string;
  staggerFrames?: number;
  delay?: number;
}

export const WordReveal: React.FC<WordRevealProps> = ({
  text,
  fontSize = FONT_SIZES.display,
  color = PALETTES.promo.secondary,
  gradient,
  staggerFrames = 3,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(' ');

  // Auto-reduce fontSize if too many words (prevent excessive wrapping)
  const maxWidth = 900; // safe zone
  const avgWordWidth = words.reduce((sum, w) => sum + w.length, 0) / words.length * fontSize * 0.6;
  const wordsPerLine = Math.floor(maxWidth / (avgWordWidth + SPACING.xs));
  const totalLines = Math.ceil(words.length / Math.max(1, wordsPerLine));
  const autoFontSize = totalLines > 3
    ? Math.max(28, Math.floor(fontSize * 3 / totalLines))
    : fontSize;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: `0 ${SPACING.xs}px`,
        lineHeight: 1.3,
        maxWidth,
      }}
    >
      {words.map((word, i) => {
        const wordDelay = delay + i * staggerFrames;
        const f = Math.max(0, frame - wordDelay);

        const entry = spring({
          frame: f,
          fps,
          config: SPRING.snappy,
        });
        const opacity = interpolate(entry, [0, 1], [0, 1]);
        const translateY = interpolate(entry, [0, 1], [20, 0]);

        const textStyle: React.CSSProperties = {
          display: 'inline-block',
          fontSize: autoFontSize,
          fontWeight: FONT_WEIGHTS.bold,
          fontFamily: '"SF Pro Display", "PingFang SC", sans-serif',
          opacity,
          transform: `translateY(${translateY}px)`,
          lineHeight: 1.3,
        };

        if (gradient) {
          return (
            <span
              key={i}
              style={{
                ...textStyle,
                background: gradient,
                backgroundSize: '200% 100%',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              {word}
            </span>
          );
        }

        return (
          <span key={i} style={{ ...textStyle, color }}>
            {word}
          </span>
        );
      })}
    </div>
  );
};
