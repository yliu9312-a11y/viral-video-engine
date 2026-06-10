import React from 'react';
import { useCurrentFrame, useVideoConfig } from 'remotion';
import { fadeInOut } from '../../design-tokens/motion';
import { PALETTES, FONT_WEIGHTS } from '../../design-tokens';

interface MarqueeTextProps {
  text: string;
  speed?: number;
  fontSize?: number;
  color?: string;
  direction?: 'left' | 'right';
}

export const MarqueeText: React.FC<MarqueeTextProps> = ({
  text,
  speed = 3.3,
  fontSize = 32,
  color = PALETTES.promo.textSubtle,
  direction = 'left',
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const opacity = fadeInOut(frame, durationInFrames, 15, 0, 15);

  const dir = direction === 'left' ? -1 : 1;
  const translateX = frame * speed * dir;

  const repeatedText = `${text}   •   ${text}   •   ${text}   •   `;

  return (
    <div
      style={{
        width: '100%',
        overflow: 'hidden',
        opacity,
        maskImage: 'linear-gradient(90deg, transparent 0%, black 10%, black 90%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(90deg, transparent 0%, black 10%, black 90%, transparent 100%)',
      }}
    >
      <div
        style={{
          display: 'flex',
          whiteSpace: 'nowrap',
          transform: `translateX(${translateX}px)`,
          fontSize,
          fontWeight: FONT_WEIGHTS.medium,
          fontFamily: '"SF Pro Display", "PingFang SC", sans-serif',
          color,
          letterSpacing: 2,
        }}
      >
        {repeatedText}
      </div>
    </div>
  );
};
