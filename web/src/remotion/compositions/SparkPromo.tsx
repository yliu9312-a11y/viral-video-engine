import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from 'remotion';
import {
  ImageOrbit,
  FeatureScroller,
  GeometricLines,
  PhotoStack,
  ParticleBg,
} from '../../components/mg';
import { fadeInOut, SPRING, noiseOffset } from '../../design-tokens/motion';
import { FONT_WEIGHTS } from '../../design-tokens';

// ═══════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════

const BRAND = 'Spark';
const LOGO_ICON = '⚡';

const ORBIT_ITEMS = [
  { color: '#FF6B6B' }, { color: '#4ECDC4' }, { color: '#45B7D1' },
  { color: '#96CEB4' }, { color: '#FFEAA7' }, { color: '#DDA0DD' },
  { color: '#98D8C8' }, { color: '#F7DC6F' }, { color: '#BB8FCE' },
  { color: '#85C1E9' }, { color: '#F0B27A' }, { color: '#82E0AA' },
];

const FEATURES = [
  'AI Image Generator',
  'Video Upscaler',
  'Background Remover',
  'Skin Enhancer',
  'Style Transfer',
  'Cinematic Color',
  'Object Eraser',
  'AI Video Editor',
  'Lip Sync',
  'Text to Speech',
  'Voice Cloner',
  'Motion Blur',
];

const PHOTO_ITEMS = [
  { color: 'linear-gradient(135deg, #667eea, #764ba2)' },
  { color: 'linear-gradient(135deg, #f093fb, #f5576c)' },
  { color: 'linear-gradient(135deg, #4facfe, #00f2fe)' },
  { color: 'linear-gradient(135deg, #43e97b, #38f9d7)' },
  { color: 'linear-gradient(135deg, #fa709a, #fee140)' },
  { color: 'linear-gradient(135deg, #a18cd1, #fbc2eb)' },
  { color: 'linear-gradient(135deg, #ffecd2, #fcb69f)' },
  { color: 'linear-gradient(135deg, #ff9a9e, #fecfef)' },
];

// ═══════════════════════════════════════════════════════
// Beat Sheet — 12 beats, 1860 frames @60fps = 31s
// ═══════════════════════════════════════════════════════

const BEATS = [
  { id: 'intro',       start: 0,    duration: 120 },  // 0-2s
  { id: 'steppingUp',  start: 120,  duration: 120 },  // 2-4s
  { id: 'levelUp',     start: 240,  duration: 180 },  // 4-7s
  { id: 'proWorkflows',start: 420,  duration: 120 },  // 7-9s
  { id: 'photoWall',   start: 540,  duration: 120 },  // 9-11s
  { id: 'featureList', start: 660,  duration: 300 },  // 11-16s
  { id: 'geometric1',  start: 960,  duration: 120 },  // 16-18s
  { id: 'headline1',   start: 1080, duration: 120 },  // 18-20s
  { id: 'headline2',   start: 1200, duration: 120 },  // 20-22s
  { id: 'headline3',   start: 1320, duration: 180 },  // 22-25s
  { id: 'geometric2',  start: 1500, duration: 240 },  // 25-29s
  { id: 'logo',        start: 1740, duration: 120 },  // 29-31s
] as const;

const BG_DARK = '#0A0A0A';
const BG_RED = '#1A0508';
const ACCENT_PINK = '#E91E63';

// ═══════════════════════════════════════════════════════
// Main Composition
// ═══════════════════════════════════════════════════════

export const SparkPromo: React.FC = () => {
  const frame = useCurrentFrame();

  // Background transitions from black to dark red at beat 4 (9s)
  const bgBlend = interpolate(frame, [480, 540], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const bgColor = bgBlend < 0.5 ? BG_DARK : BG_RED;

  return (
    <AbsoluteFill style={{ backgroundColor: bgColor }}>
      {/* Ambient glow */}
      <BackgroundLayer frame={frame} />

      <Sequence from={BEATS[0].start} durationInFrames={BEATS[0].duration}>
        <IntroBeat />
      </Sequence>

      <Sequence from={BEATS[1].start} durationInFrames={BEATS[1].duration}>
        <SteppingUpBeat />
      </Sequence>

      <Sequence from={BEATS[2].start} durationInFrames={BEATS[2].duration}>
        <LevelUpBeat />
      </Sequence>

      <Sequence from={BEATS[3].start} durationInFrames={BEATS[3].duration}>
        <ProWorkflowsBeat />
      </Sequence>

      <Sequence from={BEATS[4].start} durationInFrames={BEATS[4].duration}>
        <PhotoWallBeat />
      </Sequence>

      <Sequence from={BEATS[5].start} durationInFrames={BEATS[5].duration}>
        <FeatureListBeat />
      </Sequence>

      <Sequence from={BEATS[6].start} durationInFrames={BEATS[6].duration}>
        <Geometric1Beat />
      </Sequence>

      <Sequence from={BEATS[7].start} durationInFrames={BEATS[7].duration}>
        <Headline1Beat />
      </Sequence>

      <Sequence from={BEATS[8].start} durationInFrames={BEATS[8].duration}>
        <Headline2Beat />
      </Sequence>

      <Sequence from={BEATS[9].start} durationInFrames={BEATS[9].duration}>
        <Headline3Beat />
      </Sequence>

      <Sequence from={BEATS[10].start} durationInFrames={BEATS[10].duration}>
        <Geometric2Beat />
      </Sequence>

      <Sequence from={BEATS[11].start} durationInFrames={BEATS[11].duration}>
        <LogoBeat />
      </Sequence>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Background
// ═══════════════════════════════════════════════════════

const BackgroundLayer: React.FC<{ frame: number }> = ({ frame }) => {
  const n1 = noiseOffset(1, frame, 0.003, 1);
  const glowX = interpolate(n1.x, [-1, 1], [30, 70]);
  const glowY = interpolate(n1.y, [-1, 1], [30, 70]);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        background: `radial-gradient(ellipse 50% 50% at ${glowX}% ${glowY}%, rgba(233, 30, 99, 0.06), transparent 70%)`,
      }} />
      <ParticleBg count={10} color="#E91E63" secondaryColor="#FF6B9D" style="float" opacity={0.1} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 0: Intro — black + fade in
// ═══════════════════════════════════════════════════════

const IntroBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 30, 0, 15);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <div style={{
        fontSize: 24,
        fontWeight: FONT_WEIGHTS.medium,
        color: 'rgba(255,255,255,0.3)',
        fontFamily: '"SF Pro Display", sans-serif',
        letterSpacing: 4,
      }}>
        {BRAND}
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 1: Stepping Up — photo stack
// ═══════════════════════════════════════════════════════

const SteppingUpBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 10, 0, 10);

  const textEntry = spring({ frame: Math.max(0, frame - 15), fps, config: SPRING.snappy });
  const textOpacity = interpolate(textEntry, [0, 1], [0, 1]);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <PhotoStack items={PHOTO_ITEMS} direction="vertical" delay={5} />
      <div style={{
        position: 'absolute',
        bottom: '30%',
        opacity: textOpacity,
        fontSize: 32,
        fontWeight: FONT_WEIGHTS.bold,
        color: '#FFFFFF',
        fontFamily: '"SF Pro Display", sans-serif',
      }}>
        stepping up
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 2: Level Up — image orbit
// ═══════════════════════════════════════════════════════

const LevelUpBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 10, 0, 10);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <ImageOrbit
        items={ORBIT_ITEMS}
        centerText="level up"
        radius={220}
        orbitSpeed={0.015}
        delay={5}
      />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 3: Pro Workflows — scattered photos
// ═══════════════════════════════════════════════════════

const ProWorkflowsBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 10, 0, 10);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <PhotoStack items={PHOTO_ITEMS} direction="grid" delay={5} />
      <div style={{
        position: 'absolute',
        fontSize: 36,
        fontWeight: FONT_WEIGHTS.bold,
        color: '#FFFFFF',
        fontFamily: '"SF Pro Display", sans-serif',
        textShadow: '0 0 40px rgba(0,0,0,0.8)',
      }}>
        pro workflows
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 4: Photo Wall — scattered on dark red
// ═══════════════════════════════════════════════════════

const PhotoWallBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 8, 0, 8);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <PhotoStack items={PHOTO_ITEMS} direction="grid" delay={0} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 5: Feature List — scrolling features
// ═══════════════════════════════════════════════════════

const FeatureListBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 10, 0, 10);

  const highlightIndex = Math.min(
    Math.floor(frame / 20),
    FEATURES.length - 1,
  );

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <FeatureScroller
        features={FEATURES}
        highlightIndex={highlightIndex}
        speed={0.5}
        delay={10}
      />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 6: Geometric 1 — triangle
// ═══════════════════════════════════════════════════════

const Geometric1Beat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 8, 0, 8);

  const textEntry = spring({ frame: Math.max(0, frame - 20), fps, config: SPRING.snappy });
  const textOpacity = interpolate(textEntry, [0, 1], [0, 1]);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <GeometricLines shape="triangle" color={ACCENT_PINK} size={500} delay={0} />
      <div style={{
        position: 'absolute',
        fontSize: 36,
        fontWeight: FONT_WEIGHTS.bold,
        color: '#FFFFFF',
        fontFamily: '"SF Pro Display", sans-serif',
        opacity: textOpacity,
      }}>
        that let you create
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 7: Headline 1 — "EXPAND YOUR REACH"
// ═══════════════════════════════════════════════════════

const Headline1Beat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 8, 0, 8);

  const entry = spring({ frame: Math.max(0, frame - 5), fps, config: SPRING.heavy });
  const scale = interpolate(entry, [0, 1], [0.8, 1]);
  const textOpacity = interpolate(entry, [0, 1], [0, 1]);

  return (
    <AbsoluteFill style={{
      opacity,
      justifyContent: 'center',
      alignItems: 'center',
      background: BG_RED,
    }}>
      <div style={{
        transform: `scale(${scale})`,
        opacity: textOpacity,
        textAlign: 'center',
      }}>
        <div style={{
          fontSize: 48,
          fontWeight: FONT_WEIGHTS.black,
          color: '#FFFFFF',
          fontFamily: '"SF Pro Display", sans-serif',
          lineHeight: 1.1,
        }}>
          EXPAND
        </div>
        <div style={{
          fontSize: 48,
          fontWeight: FONT_WEIGHTS.black,
          color: '#FFFFFF',
          fontFamily: '"SF Pro Display", sans-serif',
          lineHeight: 1.1,
        }}>
          YOUR REACH
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 8: Headline 2 — "MUCH BIGGER"
// ═══════════════════════════════════════════════════════

const Headline2Beat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 8, 0, 8);

  const entry = spring({ frame: Math.max(0, frame - 5), fps, config: SPRING.heavy });
  const scale = interpolate(entry, [0, 1], [0.8, 1]);

  return (
    <AbsoluteFill style={{
      opacity,
      justifyContent: 'center',
      alignItems: 'center',
    }}>
      {/* Abstract background image placeholder */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(180deg, #1a0508 0%, #2d1520 40%, #e8a0b0 70%, #f5d0d0 100%)',
      }} />
      <div style={{
        transform: `scale(${scale})`,
        textAlign: 'center',
        zIndex: 1,
      }}>
        <div style={{
          fontSize: 72,
          fontWeight: FONT_WEIGHTS.black,
          color: '#FFFFFF',
          fontFamily: '"SF Pro Display", sans-serif',
          lineHeight: 1,
          textShadow: '0 4px 30px rgba(0,0,0,0.5)',
        }}>
          MUCH
        </div>
        <div style={{
          fontSize: 72,
          fontWeight: FONT_WEIGHTS.black,
          color: '#FFFFFF',
          fontFamily: '"SF Pro Display", sans-serif',
          lineHeight: 1,
          textShadow: '0 4px 30px rgba(0,0,0,0.5)',
        }}>
          BIGGER
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 9: Headline 3 — "REWRITE THE RULES"
// ═══════════════════════════════════════════════════════

const Headline3Beat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 8, 0, 8);

  const entry = spring({ frame: Math.max(0, frame - 5), fps, config: SPRING.heavy });
  const scale = interpolate(entry, [0, 1], [0.85, 1]);

  return (
    <AbsoluteFill style={{
      opacity,
      justifyContent: 'center',
      alignItems: 'center',
    }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        background: 'linear-gradient(180deg, #2d1520 0%, #c08090 50%, #f0c0d0 100%)',
      }} />
      <div style={{
        transform: `scale(${scale})`,
        textAlign: 'center',
        zIndex: 1,
      }}>
        <div style={{
          fontSize: 64,
          fontWeight: FONT_WEIGHTS.black,
          color: '#FFFFFF',
          fontFamily: '"SF Pro Display", sans-serif',
          lineHeight: 1.1,
          textShadow: '0 4px 30px rgba(0,0,0,0.4)',
        }}>
          REWRITE
        </div>
        <div style={{
          fontSize: 64,
          fontWeight: FONT_WEIGHTS.black,
          color: '#FFFFFF',
          fontFamily: '"SF Pro Display", sans-serif',
          lineHeight: 1.1,
          textShadow: '0 4px 30px rgba(0,0,0,0.4)',
        }}>
          THE RULES
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 10: Geometric 2 — expanding lines + text
// ═══════════════════════════════════════════════════════

const Geometric2Beat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 10, 0, 10);

  // Two words appear sequentially
  const word1Opacity = interpolate(frame, [10, 20, 90, 110], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const word2Opacity = interpolate(frame, [100, 115, 200, 230], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <GeometricLines shape="expanding" color={ACCENT_PINK} size={600} delay={0} />
      <GeometricLines shape="x" color={ACCENT_PINK} size={400} delay={30} />
      <div style={{
        position: 'absolute',
        fontSize: 36,
        fontWeight: FONT_WEIGHTS.bold,
        color: '#FFFFFF',
        fontFamily: '"SF Pro Display", sans-serif',
        opacity: word1Opacity,
      }}>
        today
      </div>
      <div style={{
        position: 'absolute',
        fontSize: 36,
        fontWeight: FONT_WEIGHTS.bold,
        color: '#FFFFFF',
        fontFamily: '"SF Pro Display", sans-serif',
        opacity: word2Opacity,
      }}>
        into tomorrow
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 11: Logo — brand reveal on white
// ═══════════════════════════════════════════════════════

const LogoBeat: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 15, 0, 1);

  const entry = spring({ frame: Math.max(0, frame - 10), fps, config: SPRING.heavy });
  const scale = interpolate(entry, [0, 1], [0.8, 1]);
  const logoOpacity = interpolate(entry, [0, 1], [0, 1]);

  return (
    <AbsoluteFill style={{
      opacity,
      justifyContent: 'center',
      alignItems: 'center',
      backgroundColor: '#FFFFFF',
    }}>
      <div style={{
        transform: `scale(${scale})`,
        opacity: logoOpacity,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}>
        <span style={{ fontSize: 48 }}>{LOGO_ICON}</span>
        <span style={{
          fontSize: 48,
          fontWeight: FONT_WEIGHTS.bold,
          color: '#1A1A1A',
          fontFamily: '"SF Pro Display", sans-serif',
        }}>
          {BRAND}
        </span>
      </div>
    </AbsoluteFill>
  );
};
