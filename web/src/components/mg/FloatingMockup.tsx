import React from 'react';
import { useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { staggeredEntrance, noiseOffset } from '../../design-tokens/motion';
import { RADIUS } from '../../design-tokens';

interface FloatingMockupProps {
  children: React.ReactNode;
  width?: number;
  height?: number;
  floatSpeed?: number;
  perspective?: number;
  rotateY?: number;
  delay?: number;
}

export const FloatingMockup: React.FC<FloatingMockupProps> = ({
  children,
  width = 300,
  height = 200,
  floatSpeed = 0.02,
  perspective = 1000,
  rotateY = 5,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entrance = staggeredEntrance(frame, fps, delay, 'gentle');

  const floatY = noiseOffset(77, frame, floatSpeed, 20);
  const rotateNoise = noiseOffset(88, frame, floatSpeed * 0.7, 1);
  const currentRotateY = interpolate(
    rotateNoise.x,
    [-1, 1],
    [-rotateY, rotateY],
  );

  const shadowBlur = interpolate(floatY.y, [-20, 20], [15, 35]);
  const shadowOpacity = interpolate(floatY.y, [-20, 20], [0.3, 0.15]);

  return (
    <div
      style={{
        perspective,
        width,
        height,
        opacity: entrance.opacity,
        transform: `scale(${entrance.scale}) translateY(${floatY.y}px)`,
      }}
    >
      <div
        style={{
          width: '100%',
          height: '100%',
          transform: `rotateY(${currentRotateY}deg)`,
          borderRadius: RADIUS.sm,
          overflow: 'hidden',
          boxShadow: `0 ${shadowBlur}px ${shadowBlur * 2}px rgba(0,0,0,${shadowOpacity})`,
        }}
      >
        {children}
      </div>
    </div>
  );
};
