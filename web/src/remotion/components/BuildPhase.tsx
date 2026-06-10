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
import { BarChart, NumberRoll } from "../../components/mg/DataChart";
import { BeforeAfter } from "../../components/mg/BeforeAfter";
import { ParticleBg } from "../../components/mg/ParticleBg";

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

export const BuildPhase: React.FC<{ phase: PhaseData; fps: number }> = ({
  phase,
  fps,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const materialCount = Math.max(phase.materials.length, 1);
  const framesPerMaterial = Math.floor(durationInFrames / materialCount);
  const currentIndex = Math.min(
    Math.floor(frame / framesPerMaterial),
    materialCount - 1
  );
  const currentMaterial = phase.materials[currentIndex];

  const panX = interpolate(
    frame % framesPerMaterial,
    [0, framesPerMaterial],
    [-30, 30],
    { extrapolateRight: "clamp" }
  );

  // Check for data display actions
  const chartAction = phase.completion_actions.find(
    (a) => a.component === "BarChart" || a.component === "DataChart"
  );
  const numberAction = phase.completion_actions.find(
    (a) => a.component === "NumberRoll"
  );

  // Check for before/after action
  const beforeAfterAction = phase.completion_actions.find(
    (a) => a.component === "BeforeAfter"
  );

  // Use particle bg if strategy is C (包装补全) or D (AIGC)
  const useParticles = phase.strategy_id === "C" || phase.strategy_id === "D";

  // Check for selling point cards
  const cardActions = phase.completion_actions.filter(
    (a) => a.component === "SellingPointCard"
  );
  const points =
    cardActions.length > 0
      ? (cardActions[0].params.points as string[]) || []
      : [];

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
      {/* Background material with pan */}
      {currentMaterial && (
        <AbsoluteFill style={{ transform: `translateX(${panX}px) scale(1.1)` }}>
          <Img
            src={staticFile(`materials/${currentMaterial.filename}`)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </AbsoluteFill>
      )}

      {/* Gradient overlay */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.2) 50%, rgba(0,0,0,0.7) 100%)",
        }}
      />

      {/* Particle background for strategies C/D */}
      {useParticles && (
        <ParticleBg
          count={25}
          color="#FFD700"
          secondaryColor="#FF416C"
          style="float"
          opacity={0.3}
        />
      )}

      {/* Before/After comparison */}
      {beforeAfterAction && (
        <BeforeAfter
          beforeImage={String(beforeAfterAction.params.beforeImage || phase.materials[0]?.filename || "")}
          afterImage={String(beforeAfterAction.params.afterImage || phase.materials[1]?.filename || "")}
          beforeLabel={String(beforeAfterAction.params.beforeLabel || "Before")}
          afterLabel={String(beforeAfterAction.params.afterLabel || "After")}
        />
      )}

      {/* BarChart overlay */}
      {chartAction && (
        <div
          style={{
            position: "absolute",
            top: 200,
            left: 60,
            right: 60,
          }}
        >
          <BarChart
            data={
              (chartAction.params.data as { label: string; value: number; color?: string }[]) || [
                { label: "效果", value: 85, color: "#FF416C" },
                { label: "性价比", value: 92, color: "#4ECDC4" },
                { label: "颜值", value: 78, color: "#FFD700" },
              ]
            }
          />
        </div>
      )}

      {/* NumberRoll overlay */}
      {numberAction && (
        <div
          style={{
            position: "absolute",
            top: 250,
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <NumberRoll
            value={Number(numberAction.params.value) || 10000}
            prefix={String(numberAction.params.prefix) || ""}
            suffix={String(numberAction.params.suffix) || "+"}
            color={String(numberAction.params.color) || "#FFD700"}
            fontSize={80}
          />
        </div>
      )}

      {/* Selling point cards */}
      {points.length > 0 && (
        <div
          style={{
            position: "absolute",
            bottom: 400,
            left: 40,
            right: 40,
            display: "flex",
            flexDirection: "column",
            gap: 20,
          }}
        >
          {points.map((point, i) => {
            const cardDelay = fps * 0.3 + i * fps * 0.5;
            const cardOpacity = interpolate(
              frame,
              [cardDelay, cardDelay + fps * 0.3],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );
            const cardY = interpolate(
              frame,
              [cardDelay, cardDelay + fps * 0.3],
              [40, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );

            return (
              <div
                key={i}
                style={{
                  background: "rgba(255,255,255,0.12)",
                  backdropFilter: "blur(10px)",
                  borderRadius: 16,
                  padding: "20px 28px",
                  opacity: cardOpacity,
                  transform: `translateY(${cardY}px)`,
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  border: "1px solid rgba(255,255,255,0.15)",
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: "linear-gradient(135deg, #FF6B6B, #FF4D4D)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 24,
                    color: "#fff",
                    fontWeight: 700,
                  }}
                >
                  {i + 1}
                </div>
                <div
                  style={{
                    fontSize: 32,
                    fontWeight: 600,
                    color: "#fff",
                    fontFamily: "sans-serif",
                  }}
                >
                  {point}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Default text if no cards */}
      {points.length === 0 && !chartAction && !numberAction && (
        <div
          style={{
            position: "absolute",
            bottom: 400,
            left: 40,
            right: 40,
            textAlign: "center",
          }}
        >
          <KineticText
            text="核心卖点展示"
            mode="slide"
            fontSize={48}
            color="#FFFFFF"
          />
        </div>
      )}
    </AbsoluteFill>
  );
};
