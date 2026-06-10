import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { HookPhase } from "../components/HookPhase";
import { BuildPhase } from "../components/BuildPhase";
import { PayoffPhase } from "../components/PayoffPhase";

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

interface PhaseAssignment {
  phase: string;
  strategy_id: string;
  strategy_name: string;
  materials: Material[];
  completion_actions: CompletionAction[];
  total_duration_s: number;
}

interface Assignment {
  template_id: string;
  generated_at: string;
  phases: PhaseAssignment[];
  total_duration_s: number;
}

interface ViralVideoProps {
  assignment: Assignment;
}

const PHASE_COMPONENTS: Record<
  string,
  React.FC<{ phase: PhaseAssignment; fps: number }>
> = {
  hook: HookPhase as React.FC<{ phase: PhaseAssignment; fps: number }>,
  build: BuildPhase as React.FC<{ phase: PhaseAssignment; fps: number }>,
  payoff_cta: PayoffPhase as React.FC<{ phase: PhaseAssignment; fps: number }>,
};

export const ViralVideo: React.FC<ViralVideoProps> = ({ assignment }) => {
  const fps = 30;
  let currentFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {assignment.phases.map((phase, i) => {
        const durationFrames = Math.max(
          Math.round(phase.total_duration_s * fps),
          fps
        );
        const fromFrame = currentFrame;
        currentFrame += durationFrames;

        const PhaseComponent = PHASE_COMPONENTS[phase.phase] || HookPhase;

        return (
          <Sequence
            key={`${phase.phase}-${i}`}
            from={fromFrame}
            durationInFrames={durationFrames}
            name={`${phase.phase} (${phase.strategy_name})`}
          >
            <PhaseComponent phase={phase} fps={fps} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
