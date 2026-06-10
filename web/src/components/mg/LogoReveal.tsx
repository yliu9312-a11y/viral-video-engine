import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { pulse } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS, SPACING } from '../../design-tokens';

interface LogoRevealProps {
  logoText: string;
  logoIcon?: string;
  glowColor?: string;
  delay?: number;
}

const LOGO_SPRING = { damping: 8, stiffness: 150 };

export const LogoReveal: React.FC<LogoRevealProps> = ({
  logoText,
  logoIcon,
  glowColor = PALETTES.promo.accent,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({
    frame: f,
    fps,
    config: LOGO_SPRING,
  });
  const scale = interpolate(entry, [0, 1], [0, 1]);
  const opacity = interpolate(entry, [0, 0.3], [0, 1], {
    extrapolateRight: 'clamp',
  });

  const glowPulse = f > 10 ? pulse(f, 0.15, 20) : 0;
  const glowBlur = 60 + glowPulse;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      {logoIcon && (
        <div
          style={{
            fontSize: FONT_SIZES.display,
            marginBottom: SPACING.sm,
            filter: `drop-shadow(0 0 ${glowBlur}px ${glowColor})`,
          }}
        >
          {logoIcon}
        </div>
      )}
      <div
        style={{
          fontSize: FONT_SIZES.display,
          fontWeight: FONT_WEIGHTS.heavy,
          fontFamily: '"SF Pro Display", "PingFang SC", sans-serif',
          color: PALETTES.promo.secondary,
          textShadow: `0 0 ${glowBlur}px ${glowColor}`,
          letterSpacing: -1,
        }}
      >
        {logoText}
      </div>
    </div>
  );
};
