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
import { CountdownTimer } from "../../components/mg/CountdownTimer";

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

export const HookPhase: React.FC<{ phase: PhaseData; fps: number }> = ({
  phase,
  fps,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const scale = interpolate(frame, [0, durationInFrames], [1.0, 1.15], {
    extrapolateRight: "clamp",
  });

  const opacity = interpolate(frame, [0, fps * 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });

  const firstMaterial = phase.materials[0];

  // Check for countdown action
  const countdownAction = phase.completion_actions.find(
    (a) => a.component === "CountdownTimer"
  );

  // Check for text overlay actions
  const titleAction = phase.completion_actions.find(
    (a) => a.component === "TitleBar" || a.component === "KineticText"
  );

  // Determine text animation mode based on strategy
  const textMode =
    phase.strategy_id === "D" ? "bounce" : phase.strategy_id === "C" ? "slide" : "typewriter";

  return (
    <AbsoluteFill style={{ backgroundColor: "#111" }}>
      {/* Background material with Ken Burns */}
      {firstMaterial && (
        <AbsoluteFill style={{ opacity, transform: `scale(${scale})` }}>
          <Img
            src={staticFile(`materials/${firstMaterial.filename}`)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </AbsoluteFill>
      )}

      {/* Gradient overlay */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.1) 40%, rgba(0,0,0,0.7) 100%)",
        }}
      />

      {/* Countdown overlay (first 3 seconds) */}
      {countdownAction && frame < fps * 3 && (
        <AbsoluteFill
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <CountdownTimer
            from={Number(countdownAction.params.countdown) || 3}
            color={String(countdownAction.params.color) || "#FF416C"}
            goText={String(countdownAction.params.goText) || "开始!"}
          />
        </AbsoluteFill>
      )}

      {/* KineticText overlay */}
      {titleAction && (
        <div
          style={{
            position: "absolute",
            bottom: 300,
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <KineticText
            text={String(titleAction.params.text || "想要改变？")}
            mode={textMode}
            fontSize={Number(titleAction.params.fontSize) || 64}
            color={String(titleAction.params.color) || "#FFFFFF"}
            strokeColor="#000000"
            strokeWidth={3}
          />
        </div>
      )}

      {/* Default text if no action specified */}
      {!titleAction && !countdownAction && (
        <div
          style={{
            position: "absolute",
            bottom: 300,
            left: 0,
            right: 0,
            textAlign: "center",
            opacity: interpolate(frame, [fps * 0.5, fps], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        >
          <KineticText
            text="想要改变？"
            mode="bounce"
            fontSize={64}
            color="#FFFFFF"
            strokeColor="#000000"
            strokeWidth={3}
          />
        </div>
      )}
    </AbsoluteFill>
  );
};
