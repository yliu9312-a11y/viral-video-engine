import React from 'react';
import { useCurrentFrame, interpolate } from 'remotion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS } from '../../design-tokens';

interface FeatureScrollerProps {
  features: string[];
  highlightIndex?: number;
  speed?: number;
  delay?: number;
}

export const FeatureScroller: React.FC<FeatureScrollerProps> = ({
  features,
  highlightIndex = 0,
  speed = 2,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const f = Math.max(0, frame - delay);

  const lineHeight = 36;
  const scrollY = -highlightIndex * lineHeight + f * speed;

  const opacity = interpolate(f, [0, 8], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      height: 200,
      overflow: 'hidden',
      opacity,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{
        transform: `translateY(${scrollY}px)`,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
      }}>
        {features.concat(features).concat(features).map((feat, i) => {
          const normalizedIndex = i % features.length;
          const isHighlighted = normalizedIndex === highlightIndex && i >= features.length;
          const distFromCenter = Math.abs(i - features.length - highlightIndex);
          const itemOpacity = interpolate(distFromCenter, [0, 3, 6], [1, 0.3, 0.1], {
            extrapolateRight: 'clamp',
          });

          return (
            <div
              key={i}
              style={{
                height: lineHeight,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: itemOpacity,
                fontSize: isHighlighted ? FONT_SIZES.body : FONT_SIZES.caption,
                fontWeight: isHighlighted ? FONT_WEIGHTS.bold : FONT_WEIGHTS.regular,
                color: isHighlighted ? '#FFFFFF' : 'rgba(255,255,255,0.4)',
                fontFamily: '"SF Pro Display", sans-serif',
                whiteSpace: 'nowrap',
              }}
            >
              {isHighlighted && <span style={{ color: PALETTES.promo.accent, marginRight: 8 }}>▶</span>}
              {feat}
            </div>
          );
        })}
      </div>
    </div>
  );
};
