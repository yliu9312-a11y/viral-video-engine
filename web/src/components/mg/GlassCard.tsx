import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { noiseOffset, SPRING } from '../../design-tokens/motion';
import { PALETTES, SPACING, RADIUS } from '../../design-tokens';

interface GlassCardProps {
  children: React.ReactNode;
  width?: number;
  height?: number;
  glowColor?: string;
  delay?: number;
  float?: boolean;
}

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  width = 280,
  height = 200,
  glowColor = PALETTES.promo.accentGlow,
  delay = 0,
  float = false,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: SPRING.heavy });
  const scale = interpolate(entry, [0, 1], [0.8, 1]);
  const opacity = interpolate(entry, [0, 1], [0, 1]);

  const floatOffset = float ? noiseOffset(42, frame, 0.02, 5) : { x: 0, y: 0 };

  return (
    <div
      style={{
        width,
        height,
        background: PALETTES.promo.bgGlass,
        border: `1px solid ${glowColor}`,
        borderRadius: RADIUS.md,
        // NOTE: backdrop-filter 在 headless Chrome 有边缘渲染差异 (Remotion #5126)
        // 改用 box-shadow 外发光模拟玻璃效果
        boxShadow: `0 0 30px ${glowColor}, 0 0 60px ${PALETTES.promo.accentGlowSubtle}, inset 0 1px 0 ${PALETTES.promo.highlight}`,
        padding: SPACING.md,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: 'center',
        opacity,
        transform: `scale(${scale}) translateY(${floatOffset.y}px)`,
        overflow: 'hidden',
      }}
    >
      {children}
    </div>
  );
};
