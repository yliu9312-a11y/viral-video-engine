import React from 'react';
import { useCurrentFrame, useVideoConfig, interpolate } from 'remotion';
import { EASE } from '../../design-tokens/motion';

interface SectionProps {
  enter?: 'fadeIn' | 'slideUp' | 'scaleIn' | 'none';
  exit?: 'fadeOut' | 'slideDown' | 'scaleOut' | 'none';
  enterDuration?: number;
  exitDuration?: number;
  zIndex?: number;
  children: React.ReactNode;
}

export const Section: React.FC<SectionProps> = ({
  enter = 'fadeIn',
  exit = 'fadeOut',
  enterDuration = 20,
  exitDuration = 15,
  zIndex = 0,
  children,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Enter animation
  const enterProgress = interpolate(frame, [0, enterDuration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  // Exit animation
  const exitStart = durationInFrames - exitDuration;
  const exitProgress = interpolate(frame, [exitStart, durationInFrames], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const isEntering = frame < enterDuration;
  const isExiting = frame > exitStart;
  const progress = isExiting ? exitProgress : isEntering ? enterProgress : 1;

  let opacity = 1;
  let translateY = 0;
  let scale = 1;

  // Enter effects
  if (isEntering) {
    switch (enter) {
      case 'fadeIn':
        opacity = progress;
        break;
      case 'slideUp':
        translateY = interpolate(progress, [0, 1], [60, 0]);
        opacity = progress;
        break;
      case 'scaleIn':
        scale = interpolate(progress, [0, 1], [0.85, 1]);
        opacity = progress;
        break;
      case 'none':
        break;
    }
  }

  // Exit effects
  if (isExiting) {
    switch (exit) {
      case 'fadeOut':
        opacity = progress;
        break;
      case 'slideDown':
        translateY = interpolate(progress, [1, 0], [0, 60]);
        opacity = progress;
        break;
      case 'scaleOut':
        scale = interpolate(progress, [1, 0], [1, 0.85]);
        opacity = progress;
        break;
      case 'none':
        break;
    }
  }

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex,
        opacity,
        transform: `translateY(${translateY}px) scale(${scale})`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {children}
    </div>
  );
};
