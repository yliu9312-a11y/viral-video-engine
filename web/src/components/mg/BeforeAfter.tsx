import React from 'react';
import { AbsoluteFill, Img, useCurrentFrame, interpolate, staticFile } from 'remotion';

interface BeforeAfterProps {
  beforeImage: string;
  afterImage: string;
  beforeLabel?: string;
  afterLabel?: string;
  direction?: 'left' | 'right' | 'up' | 'down';
  revealDelay?: number;
  duration?: number;
}

export const BeforeAfter: React.FC<BeforeAfterProps> = ({
  beforeImage,
  afterImage,
  beforeLabel = 'Before',
  afterLabel = 'After',
  direction = 'left',
  revealDelay = 15,
}) => {
  const frame = useCurrentFrame();

  // Reveal animation: wipe from left to right
  const revealProgress = interpolate(
    frame,
    [revealDelay, revealDelay + 30],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  // Divider line position
  const dividerPos = revealProgress * 100;

  // Labels fade in
  const labelOpacity = interpolate(
    frame,
    [revealDelay + 10, revealDelay + 20],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  // Arrow bounce
  const arrowBounce = Math.sin(frame * 0.2) * 5;

  // Vertical direction handling
  const isVertical = direction === 'up' || direction === 'down';

  const beforeClip = isVertical
    ? `inset(0 0 ${100 - dividerPos}% 0)`
    : `inset(0 ${100 - dividerPos}% 0 0)`;

  const afterClip = isVertical
    ? `inset(${dividerPos}% 0 0 0)`
    : `inset(0 0 0 ${dividerPos}%)`;

  return (
    <AbsoluteFill style={{ backgroundColor: '#111' }}>
      {/* Before image (full, clipped) */}
      <AbsoluteFill style={{ clipPath: beforeClip }}>
        <Img
          src={staticFile(`materials/${beforeImage}`)}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
        {/* Dark overlay for "before" feel */}
        <AbsoluteFill style={{ background: 'rgba(0,0,0,0.2)', filter: 'saturate(0.7)' }} />
      </AbsoluteFill>

      {/* After image (full, clipped) */}
      <AbsoluteFill style={{ clipPath: afterClip }}>
        <Img
          src={staticFile(`materials/${afterImage}`)}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
        {/* Bright overlay for "after" feel */}
        <AbsoluteFill style={{ background: 'rgba(255,255,255,0.05)' }} />
      </AbsoluteFill>

      {/* Divider line */}
      <div
        style={{
          position: 'absolute',
          ...(isVertical
            ? { top: `${dividerPos}%`, left: 0, right: 0, height: 4 }
            : { left: `${dividerPos}%`, top: 0, bottom: 0, width: 4 }),
          background: '#fff',
          boxShadow: '0 0 20px rgba(255,255,255,0.5)',
          zIndex: 10,
        }}
      />

      {/* Arrow indicator */}
      <div
        style={{
          position: 'absolute',
          ...(isVertical
            ? { top: `${dividerPos}%`, left: '50%', transform: `translate(-50%, -50%) translateY(${arrowBounce}px)` }
            : { left: `${dividerPos}%`, top: '50%', transform: `translate(-50%, -50%) translateX(${arrowBounce}px)` }),
          zIndex: 11,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: '50%',
            background: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            fontSize: 24,
          }}
        >
          ⇄
        </div>
      </div>

      {/* Before label */}
      <div
        style={{
          position: 'absolute',
          top: 60,
          left: 40,
          opacity: labelOpacity,
          zIndex: 12,
        }}
      >
        <div
          style={{
            background: 'rgba(0,0,0,0.7)',
            borderRadius: 12,
            padding: '8px 20px',
            fontSize: 24,
            fontWeight: 700,
            color: '#FF6B6B',
            fontFamily: 'PingFang SC, sans-serif',
            backdropFilter: 'blur(10px)',
          }}
        >
          {beforeLabel}
        </div>
      </div>

      {/* After label */}
      <div
        style={{
          position: 'absolute',
          top: 60,
          right: 40,
          opacity: labelOpacity,
          zIndex: 12,
        }}
      >
        <div
          style={{
            background: 'rgba(0,0,0,0.7)',
            borderRadius: 12,
            padding: '8px 20px',
            fontSize: 24,
            fontWeight: 700,
            color: '#4ECDC4',
            fontFamily: 'PingFang SC, sans-serif',
            backdropFilter: 'blur(10px)',
          }}
        >
          {afterLabel}
        </div>
      </div>
    </AbsoluteFill>
  );
};
