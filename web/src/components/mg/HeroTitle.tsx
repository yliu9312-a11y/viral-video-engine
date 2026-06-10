import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING, EASE } from '../../design-tokens/motion';
import { PALETTES, TYPOGRAPHY_PROMO, FONTS } from '../../design-tokens';
import { GradientText } from './GradientText';

interface HeroTitleProps {
  text: string;
  variant?: 'hero' | 'h1' | 'h2';
  gradient?: boolean;
  align?: 'left' | 'center' | 'right';
  enterDelay?: number;
  zIndex?: number;
}

export const HeroTitle: React.FC<HeroTitleProps> = ({
  text,
  variant = 'hero',
  gradient = true,
  align = 'center',
  enterDelay = 0,
  zIndex = 1,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - enterDelay);

  const typo = TYPOGRAPHY_PROMO[variant];

  const entry = spring({ frame: f, fps, config: SPRING.gentle });
  const opacity = interpolate(entry, [0, 1], [0, 1]);
  const translateY = interpolate(entry, [0, 1], [40, 0], { extrapolateRight: 'clamp' });

  if (gradient) {
    return (
      <div
        style={{
          position: 'relative',
          zIndex,
          textAlign: align,
          opacity,
          transform: `translateY(${translateY}px)`,
        }}
      >
        <GradientText
          text={text}
          fontSize={typo.fontSize}
          fontWeight={typo.fontWeight as 400 | 500 | 700 | 800 | 900}
          delay={enterDelay}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'relative',
        zIndex,
        textAlign: align,
        opacity,
        transform: `translateY(${translateY}px)`,
      }}
    >
      <span
        style={{
          fontSize: typo.fontSize,
          fontWeight: typo.fontWeight,
          letterSpacing: typo.letterSpacing,
          lineHeight: typo.lineHeight,
          fontFamily: FONTS.display,
          color: PALETTES.promo.secondary,
        }}
      >
        {text}
      </span>
    </div>
  );
};
