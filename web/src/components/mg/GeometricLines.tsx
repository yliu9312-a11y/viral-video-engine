import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING } from '../../design-tokens/motion';

interface GeometricLinesProps {
  shape?: 'triangle' | 'x' | 'diamond' | 'expanding';
  color?: string;
  size?: number;
  delay?: number;
  strokeWidth?: number;
}

export const GeometricLines: React.FC<GeometricLinesProps> = ({
  shape = 'expanding',
  color = '#E91E63',
  size = 400,
  delay = 0,
  strokeWidth = 2,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: SPRING.gentle });
  const progress = interpolate(f, [0, 60], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const expand = interpolate(f, [0, 90], [0.2, 1.5], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = interpolate(entry, [0, 1], [0, 0.8]);

  const paths: Record<string, string> = {
    triangle: `M ${size / 2},${size * 0.15} L ${size * 0.85},${size * 0.85} L ${size * 0.15},${size * 0.85} Z`,
    x: `M ${size * 0.2},${size * 0.2} L ${size * 0.8},${size * 0.8} M ${size * 0.8},${size * 0.2} L ${size * 0.2},${size * 0.8}`,
    diamond: `M ${size / 2},${size * 0.1} L ${size * 0.9},${size / 2} L ${size / 2},${size * 0.9} L ${size * 0.1},${size / 2} Z`,
    expanding: `M ${size * 0.3},${size * 0.1} L ${size * 0.7},${size * 0.1} L ${size * 0.9},${size * 0.5} L ${size * 0.7},${size * 0.9} L ${size * 0.3},${size * 0.9} L ${size * 0.1},${size * 0.5} Z`,
  };

  const pathD = paths[shape] || paths.expanding;
  const pathLength = size * 4;
  const dashOffset = interpolate(progress, [0, 1], [pathLength, 0]);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{
        position: 'absolute',
        left: '50%',
        top: '50%',
        transform: `translate(-50%, -50%) scale(${expand})`,
        opacity,
        pointerEvents: 'none',
      }}
    >
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeDasharray={pathLength}
        strokeDashoffset={dashOffset}
        filter="url(#geoGlow)"
      />
      <defs>
        <filter id="geoGlow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
    </svg>
  );
};
