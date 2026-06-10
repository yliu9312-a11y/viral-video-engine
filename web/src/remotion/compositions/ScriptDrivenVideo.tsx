import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  interpolate,
  Easing,
} from "remotion";
import { KineticText } from "../../components/mg/KineticText";
import { ProductShowcase } from "../../components/mg/ProductShowcase";
import { CountdownTimer } from "../../components/mg/CountdownTimer";
import { PriceReveal } from "../../components/mg/PriceReveal";
import { BeforeAfter } from "../../components/mg/BeforeAfter";
import { BarChart, NumberRoll, DonutChart } from "../../components/mg/DataChart";
import { ParticleBg } from "../../components/mg/ParticleBg";
import { GradientText } from "../../components/mg/GradientText";
import { WordReveal } from "../../components/mg/WordReveal";
import { TypewriterPrompt } from "../../components/mg/TypewriterPrompt";
import { GlassCard } from "../../components/mg/GlassCard";
import { FloatingMockup } from "../../components/mg/FloatingMockup";
import { MarqueeText } from "../../components/mg/MarqueeText";
import { FeatureGrid } from "../../components/mg/FeatureGrid";
import { LogoReveal } from "../../components/mg/LogoReveal";
import { GlowTrail } from "../../components/mg/GlowTrail";
import { SAFE_ZONE, FONT_SIZES, EASING } from "../../design-tokens";

// ── Video Spec types (shots[] 扁平格式) ──

interface ShotSpec {
  id: string;
  role: "hook" | "build" | "cta";
  component: string;
  props: Record<string, unknown>;
  start: number;  // frames
  duration: number;  // frames
  position?: "center" | "upper" | "lower";
  transition?: "none" | "crossfade";  // 转场类型
}

interface VideoSpec {
  shots: ShotSpec[];
  globalStyle?: {
    bgColor?: string;
    palette?: string;
  };
}

interface ScriptDrivenVideoProps {
  script: VideoSpec;
}

// ── Component registry ──

const COMPONENT_MAP: Record<string, React.FC<Record<string, unknown>>> = {
  KineticText: (props) => (
    <KineticText
      text={String(props.text || "")}
      mode={(props.mode as "bounce" | "slide" | "typewriter" | "shake") || "bounce"}
      fontSize={Number(props.fontSize) || FONT_SIZES.headline}
      color={String(props.color || "#FFFFFF")}
      strokeColor={String(props.strokeColor || "#000000")}
      strokeWidth={Number(props.strokeWidth) || 3}
      delay={Number(props.delay) || 0}
    />
  ),
  ProductShowcase: (props) => (
    <ProductShowcase
      productImage={String(props.productImage || "")}
      productName={String(props.productName || "")}
      price={String(props.price || "")}
      cta={String(props.cta || "")}
    />
  ),
  CountdownTimer: (props) => (
    <CountdownTimer
      from={Number(props.countdown) || 3}
      color={String(props.color || "#FF416C")}
      goText={String(props.goText || "GO!")}
    />
  ),
  PriceReveal: (props) => (
    <PriceReveal
      originalPrice={String(props.originalPrice || "¥199")}
      currentPrice={String(props.currentPrice || "¥39.9")}
      badge={String(props.badge || "限时特价")}
      color={String(props.color || "#FF416C")}
    />
  ),
  BeforeAfter: (props) => (
    <BeforeAfter
      beforeImage={String(props.beforeImage || "")}
      afterImage={String(props.afterImage || "")}
      beforeLabel={String(props.beforeLabel || "Before")}
      afterLabel={String(props.afterLabel || "After")}
    />
  ),
  BarChart: (props) => (
    <BarChart
      data={
        (props.data as { label: string; value: number; color?: string }[]) || [
          { label: "效果", value: 85 },
          { label: "性价比", value: 92 },
        ]
      }
    />
  ),
  NumberRoll: (props) => (
    <NumberRoll
      value={Number(props.value) || 10000}
      prefix={String(props.prefix || "")}
      suffix={String(props.suffix || "+")}
      color={String(props.color || "#FFD700")}
      fontSize={Number(props.fontSize) || FONT_SIZES.display}
    />
  ),
  DonutChart: (props) => (
    <DonutChart
      segments={
        ((props.data || props.segments) as { label: string; value: number; color?: string }[])?.map((s) => ({
          ...s,
          color: s.color || "#FFD60A",
        })) || [
          { label: "好评", value: 95, color: "#4ECDC4" },
          { label: "中评", value: 5, color: "#FF6B6B" },
        ]
      }
    />
  ),
  ParticleBg: (props) => (
    <ParticleBg
      count={Number(props.count) || 25}
      color={String(props.color || "#FFD60A")}
      secondaryColor={String(props.secondaryColor || "#FF416C")}
      style={(props.style as "float" | "burst" | "drift" | "stars") || "float"}
      opacity={Number(props.opacity) || 0.3}
    />
  ),
  GradientText: (props) => (
    <GradientText
      text={String(props.text || "")}
      gradient={props.gradient ? String(props.gradient) : undefined}
      fontSize={Number(props.fontSize) || FONT_SIZES.headline}
      fontWeight={Number(props.fontWeight) || 800}
      shimmerSpeed={Number(props.shimmerSpeed) || 0.02}
      delay={Number(props.delay) || 0}
    />
  ),
  WordReveal: (props) => (
    <WordReveal
      text={String(props.text || "")}
      fontSize={Number(props.fontSize) || FONT_SIZES.display}
      color={String(props.color || "#FFFFFF")}
      gradient={props.gradient ? String(props.gradient) : undefined}
      staggerFrames={Number(props.staggerFrames) || 3}
      delay={Number(props.delay) || 0}
    />
  ),
  TypewriterPrompt: (props) => (
    <TypewriterPrompt
      text={String(props.text || "")}
      placeholder={String(props.placeholder || "")}
      charInterval={Number(props.charInterval) || 1}
      showCursor={props.showCursor !== false}
      glowColor={String(props.glowColor || "#3B82F6")}
      delay={Number(props.delay) || 0}
    />
  ),
  GlassCard: (props) => {
    const children = props.children
      ? String(props.children)
      : String(props.text || "");
    return (
      <GlassCard
        width={Number(props.width) || 280}
        height={Number(props.height) || 200}
        glowColor={String(props.glowColor || "rgba(59, 130, 246, 0.3)")}
        delay={Number(props.delay) || 0}
        float={Boolean(props.float)}
      >
        <div style={{ color: "#FFFFFF", fontSize: 28, textAlign: "center" }}>
          {children}
        </div>
      </GlassCard>
    );
  },
  FloatingMockup: (props) => {
    const src = String(props.src || "");
    const hasImage = src && src.length > 0;
    return (
      <FloatingMockup
        width={Number(props.width) || 300}
        height={Number(props.height) || 200}
        floatSpeed={Number(props.floatSpeed) || 0.02}
        perspective={Number(props.perspective) || 1000}
        rotateY={Number(props.rotateY) || 5}
        delay={Number(props.delay) || 0}
      >
        {hasImage ? (
          <Img
            src={staticFile(`data/output/wuhan_test/${src}`)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <div style={{ color: "#FFFFFF", fontSize: 24, padding: 20, textAlign: "center" }}>
            {String(props.text || "")}
          </div>
        )}
      </FloatingMockup>
    );
  },
  MarqueeText: (props) => (
    <MarqueeText
      text={String(props.text || "")}
      speed={Number(props.speed) || 3.3}
      fontSize={Number(props.fontSize) || 32}
      color={String(props.color || "rgba(255, 255, 255, 0.35)")}
      direction={(props.direction as "left" | "right") || "left"}
    />
  ),
  FeatureGrid: (props) => {
    const features = Array.isArray(props.features)
      ? (props.features as Array<{ label: string; icon?: string; description?: string }>)
      : [{ label: String(props.text || "Feature"), icon: String(props.icon || "") }];
    return (
      <FeatureGrid
        features={features}
        columns={Number(props.columns) || 2}
        delay={Number(props.delay) || 0}
        cardWidth={Number(props.cardWidth) || 280}
        cardHeight={Number(props.cardHeight) || 180}
      />
    );
  },
  LogoReveal: (props) => (
    <LogoReveal
      logoText={String(props.logoText || props.text || "")}
      logoIcon={props.logoIcon ? String(props.logoIcon) : undefined}
      glowColor={String(props.glowColor || "#3B82F6")}
      delay={Number(props.delay) || 0}
    />
  ),
  GlowTrail: (props) => (
    <GlowTrail
      pathD={String(
        props.pathD || "M 100 960 Q 300 200 540 280 T 980 200"
      )}
      color={String(props.color || "#3B82F6")}
      trailLength={Number(props.trailLength) || 5}
      dotSize={Number(props.dotSize) || 6}
      delay={Number(props.delay) || 0}
    />
  ),
};

// ── Position styles ──

function getPositionStyle(position?: string): React.CSSProperties {
  switch (position) {
    case "upper":
      return {
        position: "absolute",
        top: SAFE_ZONE.top + 50,
        left: SAFE_ZONE.left,
        right: SAFE_ZONE.right,
        height: "40%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      };
    case "lower":
      return {
        position: "absolute",
        bottom: SAFE_ZONE.bottom + 50,
        left: SAFE_ZONE.left,
        right: SAFE_ZONE.right,
        height: "40%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      };
    default: // center
      return {
        position: "absolute",
        top: SAFE_ZONE.top + 200,
        bottom: SAFE_ZONE.bottom + 200,
        left: SAFE_ZONE.left,
        right: SAFE_ZONE.right,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      };
  }
}

// ── Crossfade constants ──

const CROSSFADE_FRAMES = 10; // 0.33s crossfade window

// ── Shot renderer (with crossfade support) ──

const ShotRenderer: React.FC<{ shot: ShotSpec; globalFrame: number }> = ({
  shot,
  globalFrame,
}) => {
  const Comp = COMPONENT_MAP[shot.component];

  if (!Comp) {
    return null;
  }

  // Calculate local frame (relative to shot start)
  const localFrame = globalFrame - shot.start;

  // Only render when within visible range (with crossfade overlap)
  const fadeInFrames = shot.transition === "crossfade" ? CROSSFADE_FRAMES : 9;
  const fadeOutFrames = shot.transition === "crossfade" ? CROSSFADE_FRAMES : 6;

  // Shot is visible from (start - crossfade) to (start + duration + crossfade)
  const visibleStart = shot.transition === "crossfade"
    ? -CROSSFADE_FRAMES
    : 0;
  const visibleEnd = shot.transition === "crossfade"
    ? shot.duration + CROSSFADE_FRAMES
    : shot.duration;

  if (localFrame < visibleStart || localFrame > visibleEnd) {
    return null;
  }

  const exitStart = Math.max(0, shot.duration - fadeOutFrames);

  const opacity = interpolate(
    localFrame,
    [visibleStart, fadeInFrames, exitStart, visibleEnd],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(...EASING.enter),
    }
  );

  const translateY = interpolate(
    localFrame,
    [visibleStart, fadeInFrames],
    [20, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(...EASING.enter),
    }
  );

  // All shots use positioned layout (BG handled by BeatRenderer)
  const posStyle = getPositionStyle(shot.position);

  return (
    <div style={{ ...posStyle, opacity, transform: `translateY(${translateY}px)` }}>
      <Comp {...shot.props} />
    </div>
  );
};

// ── Beat grouping: shots with same start → flex row ──

interface BeatGroup {
  start: number;
  shots: ShotSpec[];
}

function groupShotsByBeat(shots: ShotSpec[]): BeatGroup[] {
  const groups = new Map<number, ShotSpec[]>();
  for (const shot of shots) {
    const key = shot.start;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(shot);
  }
  return Array.from(groups.entries())
    .map(([start, shots]) => ({ start, shots }))
    .sort((a, b) => a.start - b.start);
}

// ── Global background layer ──

const BackgroundLayer: React.FC<{ bgColor: string }> = ({ bgColor }) => {
  const frame = useCurrentFrame();
  // Slow-moving radial gradient for visual depth
  const glowX = 50 + Math.sin(frame * 0.005) * 15;
  const glowY = 50 + Math.cos(frame * 0.004) * 10;

  return (
    <AbsoluteFill style={{ backgroundColor: bgColor }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(ellipse 60% 50% at ${glowX}% ${glowY}%, rgba(59,130,246,0.06), transparent 70%)`,
        }}
      />
    </AbsoluteFill>
  );
};

// ── Beat renderer: multiple shots in same time window ──

const BeatRenderer: React.FC<{ group: BeatGroup; globalFrame: number }> = ({
  group,
  globalFrame,
}) => {
  // Separate BG shots from content shots
  const bgShots = group.shots.filter((s) => s.component === "ParticleBg");
  const contentShots = group.shots.filter((s) => s.component !== "ParticleBg");

  // Group content shots by position for flex layout
  const byPosition = new Map<string, ShotSpec[]>();
  for (const shot of contentShots) {
    const pos = shot.position || "center";
    if (!byPosition.has(pos)) byPosition.set(pos, []);
    byPosition.get(pos)!.push(shot);
  }

  return (
    <>
      {/* BG shots: full frame */}
      {bgShots.map((shot) => (
        <AbsoluteFill key={shot.id}>
          <ShotRenderer shot={shot} globalFrame={globalFrame} />
        </AbsoluteFill>
      ))}

      {/* Content shots: grouped by position, flex row within group */}
      {Array.from(byPosition.entries()).map(([position, shots]) => {
        const posStyle = getPositionStyle(position);
        const isMultiShot = shots.length > 1;

        return (
          <div
            key={`${group.start}-${position}`}
            style={{
              ...posStyle,
              display: isMultiShot ? "flex" : undefined,
              flexDirection: isMultiShot ? "row" : undefined,
              justifyContent: isMultiShot ? "center" : undefined,
              alignItems: isMultiShot ? "center" : undefined,
              gap: isMultiShot ? 16 : undefined,
              flexWrap: isMultiShot ? "wrap" : undefined,
            }}
          >
            {shots.map((shot) => (
              <ShotRenderer key={shot.id} shot={shot} globalFrame={globalFrame} />
            ))}
          </div>
        );
      })}
    </>
  );
};

// ── Main composition ──

export const ScriptDrivenVideo: React.FC<ScriptDrivenVideoProps> = ({
  script,
}) => {
  const frame = useCurrentFrame();
  const bgColor = script.globalStyle?.bgColor || "#050510";
  const beats = groupShotsByBeat(script.shots);

  return (
    <AbsoluteFill>
      {/* Global background — always rendered, never cut */}
      <BackgroundLayer bgColor={bgColor} />

      {/* Beat groups — each beat renders its shots with flex layout */}
      {beats.map((group) => (
        <AbsoluteFill key={group.start}>
          <BeatRenderer group={group} globalFrame={frame} />
        </AbsoluteFill>
      ))}
    </AbsoluteFill>
  );
};
