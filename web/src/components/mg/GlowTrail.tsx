import React from 'react';
import { useCurrentFrame, useVideoConfig, interpolate, spring } from 'remotion';
import { SPRING, EASE } from '../../design-tokens/motion';
import { PALETTES } from '../../design-tokens';

interface GlowTrailProps {
  pathD: string;
  color?: string;
  trailLength?: number;
  dotSize?: number;
  delay?: number;
}

export const GlowTrail: React.FC<GlowTrailProps> = ({
  pathD,
  color = PALETTES.promo.accent,
  trailLength = 5,
  dotSize = 6,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: SPRING.gentle });
  const opacity = interpolate(entry, [0, 1], [0, 1]);

  const progress = interpolate(f, [0, 90], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE.smooth,
  });

  const points: Array<{ x: number; y: number; opacity: number; scale: number }> = [];
  for (let i = 0; i < trailLength; i++) {
    const trailProgress = Math.max(0, progress - i * 0.04);
    const px = interpolate(trailProgress, [0, 1], [100, width * 0.5]);
    const py = interpolate(trailProgress, [0, 0.5, 1], [height * 0.5, height * 0.15, height * 0.15]);
    points.push({
      x: px,
      y: py,
      opacity: interpolate(i, [0, trailLength - 1], [1, 0.15]),
      scale: interpolate(i, [0, trailLength - 1], [1, 0.4]),
    });
  }

  return (
    <svg
      width={width}
      height={height}
      style={{ position: 'absolute', top: 0, left: 0, opacity, pointerEvents: 'none' }}
    >
      <defs>
        <filter id="glow">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path
        d={pathD}
        fill="none"
        stroke={PALETTES.promo.accentGlowSubtle}
        strokeWidth="2"
      />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={dotSize * p.scale}
          fill={i === 0 ? '#FFFFFF' : color}
          opacity={p.opacity}
          filter="url(#glow)"
        />
      ))}
    </svg>
  );
};
