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
  WordReveal,
  TypewriterPrompt,
  GlassCard,
  FloatingMockup,
  MarqueeText,
  GradientText,
  FeatureGrid,
  LogoReveal,
  GlowTrail,
  ParticleBg,
  Stage,
  Background,
} from '../../components/mg';
import { fadeInOut, SPRING, noiseOffset } from '../../design-tokens/motion';
import { PALETTES, FONT_SIZES, FONT_WEIGHTS, SPACING, RADIUS } from '../../design-tokens';

// ═══════════════════════════════════════════════════════
// Config Interface — change this to generate a different video
// ═══════════════════════════════════════════════════════

interface FeatureItem {
  label: string;
  icon: string;
  description: string;
}

export interface ProductPromoConfig {
  brand: string;
  tagline: string;
  taglineDetail: string;
  buttons: string[];
  hookText: string;
  promptText: string;
  payoffText: string;
  closingText: string;
  featuresPhase1: FeatureItem[];
  featuresPhase2: FeatureItem[];
  gridFeatures: FeatureItem[];
  marquee1: string;
  marquee2: string;
  logoIcon: string;
}

export const DEFAULT_PROMO_CONFIG: ProductPromoConfig = {
  brand: 'WriteFlow',
  tagline: 'AI-Powered Content Studio',
  taglineDetail: 'Write • Edit • Publish • Analyze',
  buttons: ['Draft', 'Edit', 'Publish'],
  hookText: 'What if one prompt could build your content strategy?',
  promptText: 'Write a compelling product launch email for a new AI-powered writing tool',
  payoffText: 'From idea to published content',
  closingText: 'Stop writing, start publishing',
  featuresPhase1: [
    { label: 'Email', icon: '✉️', description: 'AI-powered drafts' },
    { label: 'Blog', icon: '📝', description: 'Long-form content' },
    { label: 'Social', icon: '📱', description: 'Multi-platform posts' },
  ],
  featuresPhase2: [
    { label: 'Analytics', icon: '📊', description: 'Content performance' },
    { label: 'SEO', icon: '🔍', description: 'Keyword optimization' },
    { label: 'Schedule', icon: '⏰', description: 'Auto-publishing' },
  ],
  gridFeatures: [
    { label: 'Templates', icon: '📄', description: '100+ proven formats' },
    { label: 'SEO', icon: '🔍', description: 'Keyword research built-in' },
    { label: 'Analytics', icon: '📈', description: 'Track content performance' },
    { label: 'Scheduling', icon: '📅', description: 'Auto-publish anywhere' },
  ],
  marquee1: 'Email  •  Blog  •  Social  •  Analytics  •  SEO  •  Scheduling  •  Templates  •  AI Writing',
  marquee2: 'Templates  •  SEO  •  Analytics  •  Scheduling  •  AI Writing  •  Multi-platform',
  logoIcon: '✦',
};

// ═══════════════════════════════════════════════════════
// Beat Sheet — 7 beats, 1170 frames @30fps = 39s
// ═══════════════════════════════════════════════════════

const BEATS = [
  { id: 'hook', start: 0, duration: 180 },        // 0-6s
  { id: 'typewriter', start: 180, duration: 90 },   // 6-9s
  { id: 'features', start: 270, duration: 390 },    // 9-22s
  { id: 'payoff', start: 660, duration: 180 },       // 22-28s
  { id: 'grid', start: 840, duration: 120 },         // 28-32s
  { id: 'closing', start: 960, duration: 150 },      // 32-37s
  { id: 'logo', start: 1110, duration: 60 },         // 37-39s
] as const;

// ═══════════════════════════════════════════════════════
// Main Composition
// ═══════════════════════════════════════════════════════

interface ProductPromoProps {
  config?: ProductPromoConfig;
}

export const ProductPromo: React.FC<ProductPromoProps> = ({
  config = DEFAULT_PROMO_CONFIG,
}) => {
  const frame = useCurrentFrame();

  return (
    <Stage
      background={<Background variant="both" particleCount={15} />}
      foreground={
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: `radial-gradient(ellipse at center, transparent 40%, ${PALETTES.promo.vignette} 100%)`,
            pointerEvents: 'none',
          }}
        />
      }
    >
      <Sequence from={BEATS[0].start} durationInFrames={BEATS[0].duration}>
        <HookBeat hookText={config.hookText} />
      </Sequence>

      <Sequence from={BEATS[1].start} durationInFrames={BEATS[1].duration}>
        <TypewriterBeat promptText={config.promptText} />
      </Sequence>

      <Sequence from={BEATS[2].start} durationInFrames={BEATS[2].duration}>
        <FeaturesBeat
          phase1={config.featuresPhase1}
          phase2={config.featuresPhase2}
          marquee={config.marquee1}
        />
      </Sequence>

      <Sequence from={BEATS[3].start} durationInFrames={BEATS[3].duration}>
        <PayoffBeat
          headline={config.payoffText}
          brand={config.brand}
          tagline={config.tagline}
          taglineDetail={config.taglineDetail}
          buttons={config.buttons}
        />
      </Sequence>

      <Sequence from={BEATS[4].start} durationInFrames={BEATS[4].duration}>
        <GridBeat features={config.gridFeatures} />
      </Sequence>

      <Sequence from={BEATS[5].start} durationInFrames={BEATS[5].duration}>
        <ClosingBeat headline={config.closingText} marquee={config.marquee2} />
      </Sequence>

      <Sequence from={BEATS[6].start} durationInFrames={BEATS[6].duration}>
        <LogoBeat brand={config.brand} logoIcon={config.logoIcon} />
      </Sequence>
    </Stage>
  );
};

// ═══════════════════════════════════════════════════════
// Background Layer
// ═══════════════════════════════════════════════════════

const BackgroundLayer: React.FC<{ frame: number }> = ({ frame }) => {
  const noise1 = noiseOffset(1, frame, 0.005, 1);
  const noise2 = noiseOffset(2, frame, 0.004, 1);
  const glowX = interpolate(noise1.x, [-1, 1], [30, 70]);
  const glowY = interpolate(noise2.y, [-1, 1], [20, 60]);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(ellipse 60% 50% at ${glowX}% ${glowY}%, ${PALETTES.promo.accentGlowBg}, transparent 70%)`,
        }}
      />
      <ParticleBg count={15} color={PALETTES.promo.accent} secondaryColor={PALETTES.promo.accentLight} style="float" opacity={0.15} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 0: Hook
// ═══════════════════════════════════════════════════════

const HookBeat: React.FC<{ hookText: string }> = ({ hookText }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 15, 0, 15);

  return (
    <AbsoluteFill
      style={{
        opacity,
        justifyContent: 'center',
        alignItems: 'center',
        padding: `0 ${SPACING['2xl']}px`,
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 2,
          height: '100%',
          background:
            'linear-gradient(180deg, transparent 0%, rgba(255,255,255,0.08) 30%, rgba(255,255,255,0.12) 50%, rgba(255,255,255,0.08) 70%, transparent 100%)',
        }}
      />
      <GlowTrail pathD="M 100,320 Q 300,80 540,100" delay={30} />
      <div style={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
        <WordReveal
          text={hookText}
          fontSize={48}
          gradient={`linear-gradient(90deg, #9CA3AF, ${PALETTES.promo.secondary}, ${PALETTES.promo.accent})`}
          staggerFrames={4}
          delay={10}
        />
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 1: Typewriter
// ═══════════════════════════════════════════════════════

const TypewriterBeat: React.FC<{ promptText: string }> = ({ promptText }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 10, 0, 10);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <TypewriterPrompt text={promptText} charInterval={1} delay={10} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 2: Features
// ═══════════════════════════════════════════════════════

interface FeaturesBeatProps {
  phase1: FeatureItem[];
  phase2: FeatureItem[];
  marquee: string;
}

const FeaturesBeat: React.FC<FeaturesBeatProps> = ({ phase1, phase2, marquee }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 15, 0, 15);

  const phase1End = 150;
  const phase2Start = 130;

  const phase1Opacity = interpolate(frame, [0, 15, phase1End - 15, phase1End], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const phase2Opacity = interpolate(frame, [phase2Start, phase2Start + 15, durationInFrames - 15, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{ opacity }}>
      <AbsoluteFill style={{ opacity: phase1Opacity, justifyContent: 'center', alignItems: 'center' }}>
        <FeatureCards features={phase1} baseDelay={0} />
      </AbsoluteFill>

      <AbsoluteFill style={{ opacity: phase2Opacity, justifyContent: 'center', alignItems: 'center' }}>
        <FeatureCards features={phase2} baseDelay={phase2Start} />
      </AbsoluteFill>

      <div style={{ position: 'absolute', bottom: 40, left: 0, right: 0 }}>
        <MarqueeText text={marquee} speed={2.5} fontSize={24} color={PALETTES.promo.textSubtle} />
      </div>
    </AbsoluteFill>
  );
};

const FeatureCards: React.FC<{ features: FeatureItem[]; baseDelay: number }> = ({
  features,
  baseDelay,
}) => (
  <div style={{ display: 'flex', gap: SPACING.md }}>
    {features.map((feat, i) => (
      <FloatingMockup key={i} width={260} height={200} delay={baseDelay + i * 8}>
        <GlassCard width={260} height={200} delay={baseDelay + i * 8}>
          <div style={{ fontSize: FONT_SIZES.headline, marginBottom: SPACING.xs }}>{feat.icon}</div>
          <div
            style={{
              fontSize: FONT_SIZES.body,
              fontWeight: FONT_WEIGHTS.bold,
              color: PALETTES.promo.secondary,
              fontFamily: '"SF Pro Display", sans-serif',
              marginBottom: 4,
            }}
          >
            {feat.label}
          </div>
          <div style={{ fontSize: 13, color: PALETTES.promo.textMuted }}>
            {feat.description}
          </div>
        </GlassCard>
      </FloatingMockup>
    ))}
  </div>
);

// ═══════════════════════════════════════════════════════
// Beat 3: Payoff
// ═══════════════════════════════════════════════════════

interface PayoffBeatProps {
  headline: string;
  brand: string;
  tagline: string;
  taglineDetail: string;
  buttons: string[];
}

const PayoffBeat: React.FC<PayoffBeatProps> = ({
  headline,
  brand,
  tagline,
  taglineDetail,
  buttons,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 15, 0, 15);

  const perspectiveEntry = spring({
    frame: Math.max(0, frame - 30),
    fps,
    config: SPRING.gentle,
  });
  const mockupScale = interpolate(perspectiveEntry, [0, 1], [0.85, 1]);
  const mockupRotateY = interpolate(perspectiveEntry, [0, 1], [0, 5]);

  return (
    <AbsoluteFill
      style={{
        opacity,
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        gap: SPACING.xl,
      }}
    >
      <GradientText text={headline} fontSize={52} fontWeight={800} delay={5} />

      <div style={{ perspective: 1000, width: 600, height: 340 }}>
        <div
          style={{
            width: '100%',
            height: '100%',
            transform: `rotateY(${mockupRotateY}deg) scale(${mockupScale})`,
            borderRadius: RADIUS.sm,
            overflow: 'hidden',
            boxShadow: '0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(59, 130, 246, 0.15)',
          }}
        >
          <GlassCard width={600} height={340}>
            <div
              style={{
                fontSize: FONT_SIZES.headline,
                fontWeight: FONT_WEIGHTS.heavy,
                color: PALETTES.promo.secondary,
                fontFamily: '"SF Pro Display", sans-serif',
                marginBottom: 12,
              }}
            >
              {brand}
            </div>
            <div
              style={{
                fontSize: 14,
                color: PALETTES.promo.textMuted,
                textAlign: 'center',
                lineHeight: 1.6,
              }}
            >
              {tagline}
              <br />
              {taglineDetail}
            </div>
            <div style={{ display: 'flex', gap: SPACING.xs, marginTop: SPACING.sm }}>
              {buttons.map((label) => (
                <div
                  key={label}
                  style={{
                    padding: '6px 16px',
                    background: 'rgba(59, 130, 246, 0.2)',
                    border: `1px solid ${PALETTES.promo.borderGlassStrong}`,
                    borderRadius: 6,
                    fontSize: 12,
                    color: PALETTES.promo.accentLight,
                    fontWeight: FONT_WEIGHTS.medium,
                  }}
                >
                  {label}
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 4: Feature Grid
// ═══════════════════════════════════════════════════════

const GridBeat: React.FC<{ features: FeatureItem[] }> = ({ features }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 12, 0, 12);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <FeatureGrid features={features} columns={2} delay={5} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 5: Closing
// ═══════════════════════════════════════════════════════

const ClosingBeat: React.FC<{ headline: string; marquee: string }> = ({
  headline,
  marquee,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 12, 0, 12);

  return (
    <AbsoluteFill
      style={{
        opacity,
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        gap: SPACING.lg,
      }}
    >
      <GradientText
        text={headline}
        fontSize={48}
        fontWeight={800}
        delay={5}
        gradient={`linear-gradient(90deg, #6B7280, ${PALETTES.promo.secondary}, ${PALETTES.promo.accent})`}
      />
      <div style={{ width: '80%', marginTop: 20 }}>
        <MarqueeText text={marquee} speed={2} fontSize={20} color={PALETTES.promo.textSubtle} />
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Beat 6: Logo
// ═══════════════════════════════════════════════════════

const LogoBeat: React.FC<{ brand: string; logoIcon: string }> = ({ brand, logoIcon }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const opacity = fadeInOut(frame, durationInFrames, 8, 0, 8);

  return (
    <AbsoluteFill style={{ opacity, justifyContent: 'center', alignItems: 'center' }}>
      <LogoReveal logoText={brand} logoIcon={logoIcon} glowColor={PALETTES.promo.accent} />
    </AbsoluteFill>
  );
};
