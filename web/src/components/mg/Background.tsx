import React from 'react';
import { AbsoluteFill } from 'remotion';
import { PALETTES } from '../../design-tokens';
import { ParticleBg } from './ParticleBg';

interface BackgroundProps {
  variant?: 'gradient' | 'particles' | 'both';
  gradient?: string;
  particleColor?: string;
  particleCount?: number;
  children?: React.ReactNode;
}

export const Background: React.FC<BackgroundProps> = ({
  variant = 'both',
  gradient = `radial-gradient(ellipse at 50% 50%, #0a0a2e 0%, ${PALETTES.promo.primary} 70%)`,
  particleColor = PALETTES.promo.accent,
  particleCount = 30,
  children,
}) => {
  return (
    <AbsoluteFill>
      {/* Gradient layer */}
      {(variant === 'gradient' || variant === 'both') && (
        <AbsoluteFill style={{ background: gradient }} />
      )}

      {/* Particle layer */}
      {(variant === 'particles' || variant === 'both') && (
        <AbsoluteFill>
          <ParticleBg
            count={particleCount}
            color={particleColor}
            speed={0.5}
            size={[2, 6]}
            opacity={0.3}
            style="float"
          />
        </AbsoluteFill>
      )}

      {/* Content overlay */}
      {children && (
        <AbsoluteFill>
          {children}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
