import React from 'react';
import { AbsoluteFill } from 'remotion';

interface StageProps {
  background?: React.ReactNode;
  children: React.ReactNode;
  foreground?: React.ReactNode;
}

export const Stage: React.FC<StageProps> = ({
  background,
  children,
  foreground,
}) => {
  return (
    <AbsoluteFill>
      {/* Layer 0: Background */}
      {background && (
        <AbsoluteFill style={{ zIndex: 0 }}>
          {background}
        </AbsoluteFill>
      )}

      {/* Layer 1: Content */}
      <AbsoluteFill style={{ zIndex: 1 }}>
        {children}
      </AbsoluteFill>

      {/* Layer 2: Foreground (optional) */}
      {foreground && (
        <AbsoluteFill style={{ zIndex: 2, pointerEvents: 'none' }}>
          {foreground}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
