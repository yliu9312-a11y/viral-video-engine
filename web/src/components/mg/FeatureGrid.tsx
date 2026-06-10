import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING, STAGGER } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS, SPACING } from '../../design-tokens';
import { GlassCard } from './GlassCard';

interface Feature {
  label: string;
  icon?: string;
  description?: string;
}

interface FeatureGridProps {
  features: Feature[];
  columns?: number;
  delay?: number;
  cardWidth?: number;
  cardHeight?: number;
}

export const FeatureGrid: React.FC<FeatureGridProps> = ({
  features,
  columns = 2,
  delay = 0,
  cardWidth = 280,
  cardHeight = 180,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const gap = SPACING.md;
  const totalWidth = columns * cardWidth + (columns - 1) * gap;

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap,
        width: totalWidth,
      }}
    >
      {features.map((feature, i) => {
        const cellDelay = delay + i * STAGGER.card;
        const f = Math.max(0, frame - cellDelay);

        const entry = spring({
          frame: f,
          fps,
          config: SPRING.snappy,
        });
        const scale = interpolate(entry, [0, 1], [0.7, 1]);
        const opacity = interpolate(entry, [0, 1], [0, 1]);

        return (
          <div
            key={i}
            style={{
              opacity,
              transform: `scale(${scale})`,
            }}
          >
            <GlassCard
              width={cardWidth}
              height={cardHeight}
              delay={cellDelay}
            >
              {feature.icon && (
                <div style={{ fontSize: FONT_SIZES.body, marginBottom: SPACING.xs }}>
                  {feature.icon}
                </div>
              )}
              <div
                style={{
                  fontSize: FONT_SIZES.caption,
                  fontWeight: FONT_WEIGHTS.heavy,
                  fontFamily: '"SF Pro Display", "PingFang SC", sans-serif',
                  color: PALETTES.promo.secondary,
                  textAlign: 'center',
                  marginBottom: 4,
                }}
              >
                {feature.label}
              </div>
              {feature.description && (
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: FONT_WEIGHTS.regular,
                    color: PALETTES.promo.textMuted,
                    textAlign: 'center',
                  }}
                >
                  {feature.description}
                </div>
              )}
            </GlassCard>
          </div>
        );
      })}
    </div>
  );
};
