import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from "remotion";
import { KineticText } from "../../components/mg/KineticText";
import { PriceReveal } from "../../components/mg/PriceReveal";

interface Material {
  filename: string;
  type: string;
  role: string;
  duration_s: number;
}

interface CompletionAction {
  action_type: string;
  component: string;
  params: Record<string, unknown>;
  duration_s: number;
}

interface PhaseData {
  phase: string;
  strategy_id: string;
  strategy_name: string;
  materials: Material[];
  completion_actions: CompletionAction[];
  total_duration_s: number;
}

export const PayoffPhase: React.FC<{ phase: PhaseData; fps: number }> = ({
  phase,
  fps,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const firstMaterial = phase.materials[0];

  const scale = interpolate(frame, [0, durationInFrames], [1.0, 1.2], {
    extrapolateRight: "clamp",
  });

  // Check for CTA action
  const ctaAction = phase.completion_actions.find(
    (a) => a.component === "CTAButton" || a.component === "KineticText"
  );

  const priceAction = phase.completion_actions.find(
    (a) => a.component === "PriceReveal"
  );

  const ctaDelay = fps * 0.5;
  const ctaScale = interpolate(
    frame,
    [ctaDelay, ctaDelay + fps * 0.3, ctaDelay + fps * 0.5],
    [0, 1.1, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const ctaOpacity = interpolate(
    frame,
    [ctaDelay, ctaDelay + fps * 0.2],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const pulse = interpolate(
    frame % (fps * 0.8),
    [0, fps * 0.4, fps * 0.8],
    [1, 1.05, 1],
    { extrapolateRight: "clamp" }
  );

  const ctaText = ctaAction
    ? String(ctaAction.params.text || "立即行动")
    : "立即行动";
  const subText = ctaAction
    ? String(ctaAction.params.subText || "点击下方链接 ↓")
    : "点击下方链接 ↓";

  return (
    <AbsoluteFill style={{ backgroundColor: "#111" }}>
      {firstMaterial && (
        <AbsoluteFill style={{ transform: `scale(${scale})` }}>
          <Img
            src={staticFile(`materials/${firstMaterial.filename}`)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </AbsoluteFill>
      )}

      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 40%, rgba(0,0,0,0.8) 100%)",
        }}
      />

      {/* PriceReveal overlay */}
      {priceAction && (
        <PriceReveal
          originalPrice={String(priceAction.params.originalPrice || "¥199")}
          currentPrice={String(priceAction.params.currentPrice || "¥39.9")}
          badge={String(priceAction.params.badge || "限时特价")}
          color="#FF416C"
        />
      )}

      {/* CTA section - positioned in safe zone, above PriceReveal */}
      {!priceAction && (
        <div
          style={{
            position: "absolute",
            bottom: 400, // above the 320px danger zone
            left: 60,
            right: 120, // right safe zone
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 20,
            opacity: ctaOpacity,
          }}
        >
          {/* Social proof */}
          <div
            style={{
              opacity: interpolate(
                frame,
                [fps * 0.2, fps * 0.6],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              ),
            }}
          >
            <KineticText
              text="10万+ 用户的选择"
              mode="slide"
              fontSize={28}
              color="rgba(255,255,255,0.8)"
            />
          </div>

          {/* CTA button with shake emphasis */}
          <div
            style={{
              transform: `scale(${ctaScale * pulse})`,
              background: "linear-gradient(135deg, #FF4D4D, #FF6B6B)",
              borderRadius: 60,
              padding: "20px 64px",
              boxShadow: "0 8px 40px rgba(255,77,77,0.4)",
            }}
          >
            <KineticText
              text={ctaText}
              mode="shake"
              fontSize={40}
              color="#FFFFFF"
              delay={Math.round(ctaDelay)}
            />
          </div>

          {/* Sub text */}
          <div
            style={{
              opacity: interpolate(
                frame,
                [fps * 1, fps * 1.5],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              ),
            }}
          >
            <KineticText
              text={subText}
              mode="typewriter"
              fontSize={24}
              color="rgba(255,255,255,0.6)"
              delay={Math.round(fps)}
            />
          </div>
        </div>
      )}

      {/* When PriceReveal is active, show CTA above it */}
      {priceAction && (
        <div
          style={{
            position: "absolute",
            bottom: 400,
            left: 60,
            right: 120,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
            opacity: ctaOpacity,
          }}
        >
          <div
            style={{
              transform: `scale(${ctaScale * pulse})`,
              background: "linear-gradient(135deg, #FF4D4D, #FF6B6B)",
              borderRadius: 60,
              padding: "16px 48px",
              boxShadow: "0 8px 40px rgba(255,77,77,0.4)",
            }}
          >
            <KineticText
              text="立即抢购"
              mode="shake"
              fontSize={36}
              color="#FFFFFF"
              delay={Math.round(ctaDelay)}
            />
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
