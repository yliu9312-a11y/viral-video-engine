import React from 'react';
import { useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { EASE } from '../../design-tokens/motion';

interface TransitionFXProps {
  type?: 'fade' | 'wipe' | 'cut' | 'zoom';
  duration?: number;
  direction?: 'left' | 'right' | 'up' | 'down';
  children: React.ReactNode;
}

export const TransitionFX: React.FC<TransitionFXProps> = ({
  type = 'fade',
  duration = 15,
  direction = 'left',
  children,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Entrance: first `duration` frames
  const enterProgress = interpolate(frame, [0, duration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Exit: last `duration` frames
  const exitStart = durationInFrames - duration;
  const exitProgress = interpolate(frame, [exitStart, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const isEntering = frame < duration;
  const isExiting = frame > exitStart;
  const progress = isExiting ? exitProgress : isEntering ? enterProgress : 1;

  let style: React.CSSProperties = {};
  let childOpacity = 1;

  switch (type) {
    case 'fade': {
      childOpacity = progress;
      break;
    }
    case 'wipe': {
      const dirMap = {
        left: `inset(0 ${(1 - progress) * 100}% 0 0)`,
        right: `inset(0 0 0 ${(1 - progress) * 100}%)`,
        up: `inset(0 0 ${(1 - progress) * 100}% 0)`,
        down: `inset(${(1 - progress) * 100}% 0 0 0)`,
      };
      style = { clipPath: dirMap[direction] };
      break;
    }
    case 'zoom': {
      const scale = interpolate(progress, [0, 1], [0.8, 1]);
      childOpacity = progress;
      style = { transform: `scale(${scale})` };
      break;
    }
    case 'cut': {
      // Instant cut at midpoint
      childOpacity = frame >= duration / 2 ? 1 : 0;
      break;
    }
  }

  return (
    <div style={{ opacity: childOpacity, ...style }}>
      {children}
    </div>
  );
};
