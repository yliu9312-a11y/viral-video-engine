import React from "react";
import { Composition } from "remotion";
import { ViralVideo } from "./compositions/ViralVideo";
import { ScriptDrivenVideo } from "./compositions/ScriptDrivenVideo";
import { ProductPromo, DEFAULT_PROMO_CONFIG } from "./compositions/ProductPromo";
import { SparkPromo } from "./compositions/SparkPromo";
import { StyleDrivenVideo, MultiSceneVideo } from "./compositions/StyleDrivenVideo";

/** 从 script.shots 计算实际需要的帧数，而非硬编码。
 *  calculateMetadata 接收的 props 结构: { defaultProps, props } 或直接是 merged props。
 */
const calcScriptDuration = (params: {
  defaultProps: Record<string, unknown>;
  props: Record<string, unknown>;
}): { durationInFrames: number } => {
  const merged = { ...params.defaultProps, ...params.props };
  const script = merged.script as { shots?: Array<{ start?: number; duration?: number }> } | undefined;
  const shots = script?.shots || [];
  if (shots.length === 0) return { durationInFrames: 90 };
  const maxEnd = Math.max(...shots.map((s) => (s.start || 0) + (s.duration || 90)));
  return { durationInFrames: Math.max(maxEnd, 30) };
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ViralVideo"
        component={ViralVideo as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={900}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          assignment: {
            template_id: "",
            generated_at: "",
            phases: [],
            total_duration_s: 0,
          },
        } as Record<string, unknown>}
      />
      <Composition
        id="ScriptDrivenVideo"
        component={ScriptDrivenVideo as unknown as React.FC<Record<string, unknown>>}
        calculateMetadata={calcScriptDuration}
        durationInFrames={2700}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          script: {
            phase: "hook",
            scenes: [],
            shots: [],
          },
        } as Record<string, unknown>}
      />
      <Composition
        id="ProductPromo"
        component={ProductPromo as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={1170}
        fps={30}
        width={1080}
        height={640}
        defaultProps={{ config: DEFAULT_PROMO_CONFIG } as Record<string, unknown>}
      />
      <Composition
        id="SparkPromo"
        component={SparkPromo as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={1860}
        fps={60}
        width={1280}
        height={720}
        defaultProps={{} as Record<string, unknown>}
      />
      <Composition
        id="StyleDrivenVideo"
        component={StyleDrivenVideo as unknown as React.FC<Record<string, unknown>>}
        durationInFrames={600}
        fps={30}
        width={1080}
        height={1920}
        calculateMetadata={(params: { defaultProps: Record<string, unknown>; props: Record<string, unknown> }) => {
          const merged = { ...params.defaultProps, ...params.props };
          const scene = merged.scene as { duration?: number; fps?: number; canvas_width?: number; canvas_height?: number } | undefined;
          return {
            durationInFrames: scene?.duration || 600,
            fps: scene?.fps || 30,
            width: scene?.canvas_width || 1080,
            height: scene?.canvas_height || 1920,
          };
        }}
        defaultProps={{
          scene: {
            canvas_width: 1080,
            canvas_height: 1920,
            fps: 30,
            duration: 600,
            background_color: "#000000",
            elements: [],
            transitions: [],
          },
        } as Record<string, unknown>}
      />
      <Composition
        id="MultiSceneVideo"
        component={MultiSceneVideo as unknown as React.FC<Record<string, unknown>>}
        calculateMetadata={(params: { defaultProps: Record<string, unknown>; props: Record<string, unknown> }) => {
          const merged = { ...params.defaultProps, ...params.props };
          const decomp = merged.decomposition as { total_frames?: number; fps?: number; canvas_width?: number; canvas_height?: number } | undefined;
          return {
            durationInFrames: decomp?.total_frames || 1800,
            fps: decomp?.fps || 30,
            width: decomp?.canvas_width || 1280,
            height: decomp?.canvas_height || 720,
          };
        }}
        defaultProps={{
          decomposition: {
            canvas_width: 1280,
            canvas_height: 720,
            fps: 30,
            total_frames: 1800,
            scenes: [],
          },
        } as Record<string, unknown>}
      />
    </>
  );
};
