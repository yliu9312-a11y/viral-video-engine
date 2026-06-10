import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING } from '../../design-tokens/motion';

interface ImageOrbitProps {
  items: Array<{ color: string; label?: string }>;
  centerText?: string;
  radius?: number;
  orbitSpeed?: number;
  delay?: number;
}

export const ImageOrbit: React.FC<ImageOrbitProps> = ({
  items,
  centerText = '',
  radius = 200,
  orbitSpeed = 0.02,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const f = Math.max(0, frame - delay);

  const entry = spring({ frame: f, fps, config: SPRING.snappy });
  const containerOpacity = interpolate(entry, [0, 1], [0, 1]);

  return (
    <div style={{
      position: 'relative',
      width: radius * 2 + 120,
      height: radius * 2 + 120,
      opacity: containerOpacity,
    }}>
      {items.map((item, i) => {
        const angle = (i / items.length) * Math.PI * 2 + f * orbitSpeed;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius * 0.6;
        const itemDelay = delay + i * 3;
        const itemEntry = spring({ frame: Math.max(0, frame - itemDelay), fps, config: SPRING.snappy });
        const itemScale = interpolate(itemEntry, [0, 1], [0, 1]);
        const z = Math.sin(angle) * 0.3 + 0.7;

        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: '50%',
              top: '50%',
              transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px)) scale(${itemScale * z})`,
              width: 90,
              height: 120,
              borderRadius: 8,
              background: item.color,
              boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
              zIndex: Math.round(z * 10),
              opacity: interpolate(z, [0.4, 1], [0.5, 1]),
            }}
          >
            {item.label && (
              <div style={{
                position: 'absolute',
                bottom: 4,
                left: 4,
                right: 4,
                fontSize: 8,
                color: '#fff',
                textAlign: 'center',
                textShadow: '0 1px 3px rgba(0,0,0,0.8)',
              }}>
                {item.label}
              </div>
            )}
          </div>
        );
      })}
      {centerText && (
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 20,
        }}>
          <span style={{
            fontSize: 36,
            fontWeight: 700,
            color: '#FFFFFF',
            fontFamily: '"SF Pro Display", sans-serif',
            textShadow: '0 0 30px rgba(0,0,0,0.8)',
          }}>
            {centerText}
          </span>
        </div>
      )}
    </div>
  );
};
