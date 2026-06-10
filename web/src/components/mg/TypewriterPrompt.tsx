import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING, pulse } from '../../design-tokens/motion';
import { PALETTES, SPACING, RADIUS, FONT_SIZES } from '../../design-tokens';

interface TypewriterPromptProps {
  text: string;
  placeholder?: string;
  charInterval?: number;
  showCursor?: boolean;
  glowColor?: string;
  delay?: number;
}

export const TypewriterPrompt: React.FC<TypewriterPromptProps> = ({
  text,
  placeholder: _placeholder = '',
  charInterval = 1,
  showCursor = true,
  glowColor: _glowColor = PALETTES.promo.accent,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const containerEntry = spring({
    frame: f,
    fps,
    config: SPRING.heavy,
  });
  const containerScale = interpolate(containerEntry, [0, 1], [0.8, 1]);
  const containerOpacity = interpolate(containerEntry, [0, 1], [0, 1]);

  const typingStart = 15;
  const typingFrame = Math.max(0, f - typingStart);
  const charsVisible = Math.min(
    Math.floor(typingFrame / charInterval),
    text.length,
  );
  const displayText = text.slice(0, charsVisible);
  const isTypingDone = charsVisible >= text.length;

  const cursorOpacity =
    showCursor && f > typingStart
      ? Math.floor(f / 15) % 2 === 0
        ? 1
        : 0
      : 0;

  const glowPulse = f > 5 ? pulse(f, 0.1, 15) : 0;
  const glowBlur = 25 + glowPulse;

  const barWidth = interpolate(containerEntry, [0, 1], [200, 700]);

  // Auto-reduce fontSize if text is too long for the bar
  const avgCharWidth = FONT_SIZES.body * 0.6; // monospace approximation
  const padding = SPACING.lg * 2;
  const textWidth = text.length * avgCharWidth;
  const availableWidth = 700 - padding; // max barWidth - padding
  const autoFontSize = textWidth > availableWidth
    ? Math.max(16, Math.floor(FONT_SIZES.body * availableWidth / textWidth))
    : FONT_SIZES.body;

  return (
    <div
      style={{
        opacity: containerOpacity,
        transform: `scale(${containerScale})`,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          width: barWidth,
          height: 64,
          background: PALETTES.promo.bgGlassHeavy,
          border: `1.5px solid ${PALETTES.promo.borderGlassStrong}`,
          borderRadius: RADIUS.pill,
          boxShadow: `0 0 ${glowBlur}px ${PALETTES.promo.accentGlowSubtle}, inset 0 1px 0 ${PALETTES.promo.highlight}`,
          display: 'flex',
          alignItems: 'center',
          padding: `0 ${SPACING.lg}px`,
          overflow: 'hidden',
        }}
      >
        <span
          style={{
            fontSize: autoFontSize,
            fontWeight: 500,
            fontFamily: '"SF Mono", "Fira Code", monospace',
            color: isTypingDone ? PALETTES.promo.secondary : PALETTES.promo.textBright,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {displayText}
        </span>
        {showCursor && (
          <span
            style={{
              fontSize: autoFontSize,
              fontWeight: 300,
              color: PALETTES.promo.secondary,
              opacity: cursorOpacity,
              marginLeft: 1,
            }}
          >
            |
          </span>
        )}
      </div>
    </div>
  );
};
