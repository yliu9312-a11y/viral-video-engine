import React, { useMemo } from 'react';
import { AbsoluteFill, useCurrentFrame, interpolate } from 'remotion';

interface ParticleBgProps {
  count?: number;
  color?: string;
  secondaryColor?: string;
  speed?: number;
  size?: [number, number]; // [min, max]
  opacity?: number;
  style?: 'float' | 'burst' | 'drift' | 'stars';
}

interface Particle {
  x: number;
  y: number;
  size: number;
  speed: number;
  angle: number;
  delay: number;
  opacity: number;
  color: string;
}

export const ParticleBg: React.FC<ParticleBgProps> = ({
  count = 40,
  color = '#FFD700',
  secondaryColor = '#FF416C',
  speed = 1,
  size = [2, 6],
  opacity = 0.6,
  style = 'float',
}) => {
  const frame = useCurrentFrame();

  // Generate particles deterministically
  const particles: Particle[] = useMemo(() => {
    const result: Particle[] = [];
    for (let i = 0; i < count; i++) {
      const seed = i * 7919; // prime for distribution
      const x = ((seed * 13) % 1000) / 10;
      const y = ((seed * 17) % 1000) / 10;
      const s = size[0] + ((seed * 23) % (size[1] - size[0]));
      const sp = 0.3 + ((seed * 29) % 100) / 100;
      const angle = ((seed * 31) % 360) * (Math.PI / 180);
      const delay = ((seed * 37) % 100) / 10;
      const op = 0.2 + ((seed * 41) % 100) / 200;
      const c = i % 3 === 0 ? secondaryColor : color;
      result.push({ x, y, size: s, speed: sp, angle, delay, opacity: op, color: c });
    }
    return result;
  }, [count, color, secondaryColor, size]);

  return (
    <AbsoluteFill>
      {particles.map((p, i) => {
        const t = (frame + p.delay * 10) * p.speed * speed;

        let px: number, py: number, particleOpacity: number;

        switch (style) {
          case 'burst': {
            // Burst from center
            const radius = (t * 0.5) % 600;
            const fadeOut = radius > 400 ? interpolate(radius, [400, 600], [1, 0], { extrapolateRight: 'clamp' }) : 1;
            px = 50 + Math.cos(p.angle + t * 0.01) * radius * 0.1;
            py = 50 + Math.sin(p.angle + t * 0.01) * radius * 0.1;
            particleOpacity = p.opacity * opacity * fadeOut;
            break;
          }
          case 'drift': {
            // Gentle diagonal drift
            px = (p.x + t * 0.1) % 120 - 10;
            py = (p.y + t * 0.05) % 120 - 10;
            particleOpacity = p.opacity * opacity;
            break;
          }
          case 'stars': {
            // Twinkling stars
            px = p.x;
            py = p.y;
            const twinkle = Math.sin(t * 0.1 + p.delay) * 0.5 + 0.5;
            particleOpacity = p.opacity * opacity * twinkle;
            break;
          }
          default: {
            // Float upward
            px = p.x + Math.sin(t * 0.02 + p.delay) * 3;
            py = ((p.y - t * 0.05) % 120 + 120) % 120 - 10;
            particleOpacity = p.opacity * opacity * (py > 0 && py < 100 ? 1 : 0.3);
            break;
          }
        }

        const scale = style === 'stars'
          ? 0.5 + Math.sin(t * 0.08 + p.delay) * 0.5
          : 1;

        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${px}%`,
              top: `${py}%`,
              width: p.size * scale,
              height: p.size * scale,
              borderRadius: '50%',
              background: p.color,
              opacity: particleOpacity,
              boxShadow: `0 0 ${p.size * 2}px ${p.color}80`,
              transform: `scale(${scale})`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
