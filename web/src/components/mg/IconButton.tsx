import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS, FONTS } from '../../design-tokens';

interface IconButtonProps {
  icon: string;
  label?: string;
  glowColor?: string;
  size?: number;
  delay?: number;
}

export const IconButton: React.FC<IconButtonProps> = ({
  icon,
  label,
  glowColor = PALETTES.promo.accentGlow,
  size = 48,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: SPRING.bouncy });
  const scale = interpolate(entry, [0, 1], [0, 1]);
  const opacity = interpolate(entry, [0, 1], [0, 1]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          width: size,
          height: size,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: size * 0.6,
          borderRadius: '50%',
          background: PALETTES.promo.bgGlass,
          border: `1px solid ${glowColor}`,
          boxShadow: `0 0 20px ${glowColor}`,
        }}
      >
        {icon}
      </div>
      {label && (
        <span
          style={{
            color: PALETTES.promo.textMuted,
            fontSize: FONT_SIZES.caption,
            fontWeight: FONT_WEIGHTS.medium,
            fontFamily: FONTS.primary,
          }}
        >
          {label}
        </span>
      )}
    </div>
  );
};
