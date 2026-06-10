import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';
import { FONT_SIZES, FONTS, FONT_WEIGHTS, SPACING, RADIUS, SAFE_ZONE } from '../../design-tokens';

interface PriceRevealProps {
  originalPrice: string;
  currentPrice: string;
  badge?: string;
  color?: string;
  delay?: number;
}

export const PriceReveal: React.FC<PriceRevealProps> = ({
  originalPrice,
  currentPrice,
  badge = '限时特价',
  color = '#FF416C',
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  // Safe zone center
  const centerX = SAFE_ZONE.left + (1080 - SAFE_ZONE.left - SAFE_ZONE.right) / 2;
  const centerY = SAFE_ZONE.top + (1920 - SAFE_ZONE.top - SAFE_ZONE.bottom) / 2;

  // Badge slides in from top
  const badgeY = interpolate(f, [0, 12], [-40, 0], { extrapolateRight: 'clamp' });
  const badgeOpacity = interpolate(f, [0, 10], [0, 1], { extrapolateRight: 'clamp' });

  // Original price appears then gets slashed
  const origOpacity = interpolate(f, [8, 14], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const slashWidth = interpolate(f, [18, 28], [0, 100], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  // Current price bounces in
  const priceScale = spring({ frame: f, fps, config: { damping: 8, stiffness: 200, mass: 0.8 }, delay: 20 });
  const priceOpacity = interpolate(f, [20, 26], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  // Glow pulse
  const glowIntensity = interpolate(f % 30, [0, 15, 30], [0.3, 0.8, 0.3], { extrapolateRight: 'clamp' });

  // Component dimensions (from component_proportions.md)
  const componentWidth = 500; // 46% of canvas
  const priceGap = SPACING.lg; // 32px between elements

  return (
    <AbsoluteFill>
      {/* Outer container - centered in safe zone */}
      <div
        style={{
          position: 'absolute',
          top: centerY - 150, // offset up slightly
          left: centerX - componentWidth / 2,
          width: componentWidth,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: priceGap,
        }}
      >
        {/* Badge */}
        <div
          style={{
            transform: `translateY(${badgeY}px)`,
            opacity: badgeOpacity,
            background: `linear-gradient(135deg, ${color}, ${color}CC)`,
            borderRadius: RADIUS.md,
            padding: `${SPACING.xs}px ${SPACING.lg}px`,
            boxShadow: `0 4px 20px ${color}66`,
          }}
        >
          <div style={{ fontSize: FONT_SIZES.caption, fontWeight: FONT_WEIGHTS.bold, color: '#fff', fontFamily: FONTS.primary }}>
            {badge}
          </div>
        </div>

        {/* Original price with slash */}
        <div style={{ opacity: origOpacity, position: 'relative' }}>
          <div
            style={{
              fontSize: FONT_SIZES.body, // 40px
              fontWeight: FONT_WEIGHTS.medium,
              color: 'rgba(255,255,255,0.5)',
              fontFamily: FONTS.primary,
              textDecoration: 'line-through',
              textDecorationColor: '#FF416C',
              textDecorationThickness: `${Math.min(slashWidth, 100)}%`,
            }}
          >
            {originalPrice}
          </div>
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: 0,
              width: `${slashWidth}%`,
              height: 3,
              background: '#FF416C',
              transform: 'translateY(-50%) rotate(-8deg)',
              borderRadius: 2,
              boxShadow: '0 0 8px rgba(255,65,108,0.6)',
            }}
          />
        </div>

        {/* Current price with bounce */}
        <div style={{ transform: `scale(${priceScale})`, opacity: priceOpacity }}>
          <div
            style={{
              fontSize: FONT_SIZES.display, // 96px
              fontWeight: FONT_WEIGHTS.black,
              color: '#FFD700',
              fontFamily: FONTS.display,
              textShadow: `0 0 ${20 * glowIntensity}px rgba(255,215,0,0.8), 0 0 ${40 * glowIntensity}px rgba(255,215,0,0.4), -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000`,
              letterSpacing: 2,
            }}
          >
            {currentPrice}
          </div>
        </div>

        {/* Decorative particles - smaller, tighter radius */}
        {[...Array(6)].map((_, i) => {
          const angle = (i / 6) * Math.PI * 2;
          const radius = interpolate(f, [25, 45], [0, 60], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          const particleOpacity = interpolate(f, [25, 35, 45], [0, 0.8, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          const x = Math.cos(angle) * radius;
          const y = Math.sin(angle) * radius;
          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                bottom: -20,
                left: '50%',
                width: 5,
                height: 5,
                borderRadius: '50%',
                background: '#FFD700',
                opacity: particleOpacity,
                transform: `translate(${x}px, ${y}px)`,
                boxShadow: '0 0 6px rgba(255,215,0,0.8)',
              }}
            />
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
