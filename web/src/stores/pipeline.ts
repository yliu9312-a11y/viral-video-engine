import { create } from "zustand";

export type Stage =
  | "idle"
  | "uploading"
  | "extracting"
  | "gapping"
  | "assigning"
  | "rendering"
  | "orchestrating"
  | "done"
  | "error";

export interface VideoInfo {
  index: number;
  path: string;
  duration: number;
  fps: number;
  width: number;
  height: number;
  shot_count: number;
  has_audio: boolean;
  bpm: number;
}

interface Shot {
  index: number;
  start_time: number;
  end_time: number;
  duration: number;
  caption: string;
  clip_path: string;
  thumbnail_path: string;
}

interface PipelineState {
  // Stage
  stage: Stage;
  error: string;

  // Upload results
  jobId: string;
  videoPath: string;
  videoPaths: string[];
  materialDir: string;

  // Extract results
  templateId: string;
  shots: Shot[];
  structureTemplate: Record<string, unknown>;
  templatePath: string;
  videoInfos: VideoInfo[];

  // Gap results
  gapReport: Record<string, unknown>;
  gapReportPath: string;

  // Assign results
  assignment: Record<string, unknown>;
  assignmentPath: string;

  // Render results
  videoData: string; // base64 (standard variant, kept for backward compat)
  outputPath: string;
  variants: { mode: string; duration: number; videoData: string; videoSize: number }[];
  activeVariant: string; // 'compact' | 'standard' | 'relaxed' | 'edited'

  // Scene data for editor
  sceneShots: Record<string, unknown>[];
  videoSpecPath: string;
  activeVariant: string; // 'compact' | 'standard' | 'relaxed'

  // Actions
  setStage: (stage: Stage) => void;
  setError: (error: string) => void;
  setUploadResult: (r: {
    jobId: string;
    videoPath: string;
    videoPaths?: string[];
    materialDir: string;
  }) => void;
  setExtractResult: (r: {
    templateId: string;
    shots: Shot[];
    structureTemplate: Record<string, unknown>;
    outputDir: string;
    templatePath: string;
    videoInfos?: VideoInfo[];
  }) => void;
  setGapResult: (r: {
    gapReport: Record<string, unknown>;
    outputDir: string;
    gapReportPath: string;
  }) => void;
  setAssignResult: (r: {
    assignment: Record<string, unknown>;
    outputDir: string;
    assignmentPath: string;
  }) => void;
  setRenderResult: (r: { videoData: string; outputPath: string }) => void;
  setVariants: (variants: { mode: string; duration: number; videoData: string; videoSize: number }[]) => void;
  setActiveVariant: (mode: string) => void;
  setSceneShots: (shots: Record<string, unknown>[]) => void;
  setVideoSpecPath: (path: string) => void;
  reset: () => void;
}

const initialState = {
  stage: "idle" as Stage,
  error: "",
  jobId: "",
  videoPath: "",
  videoPaths: [] as string[],
  materialDir: "",
  templateId: "",
  shots: [] as Shot[],
  structureTemplate: {},
  templatePath: "",
  videoInfos: [] as VideoInfo[],
  gapReport: {},
  gapReportPath: "",
  assignment: {},
  assignmentPath: "",
  videoData: "",
  outputPath: "",
  variants: [],
  activeVariant: "standard",
  sceneShots: [] as Record<string, unknown>[],
  videoSpecPath: "",
};

export const usePipelineStore = create<PipelineState>((set) => ({
  ...initialState,

  setStage: (stage) => set({ stage }),
  setError: (error) => set({ error, stage: "error" }),
  setUploadResult: (r) =>
    set({
      jobId: r.jobId,
      videoPath: r.videoPath,
      videoPaths: r.videoPaths || [r.videoPath],
      materialDir: r.materialDir,
    }),
  setExtractResult: (r) =>
    set({
      templateId: r.templateId,
      shots: r.shots,
      structureTemplate: r.structureTemplate,
      templatePath: r.templatePath,
      videoInfos: r.videoInfos || [],
    }),
  setGapResult: (r) =>
    set({
      gapReport: r.gapReport,
      gapReportPath: r.gapReportPath,
    }),
  setAssignResult: (r) =>
    set({
      assignment: r.assignment,
      assignmentPath: r.assignmentPath,
    }),
  setRenderResult: (r) =>
    set({
      videoData: r.videoData,
      outputPath: r.outputPath,
    }),
  setVariants: (variants) => set({ variants }),
  setActiveVariant: (mode) => {
    const state = usePipelineStore.getState();
    const v = state.variants.find((v) => v.mode === mode);
    if (v) {
      set({ activeVariant: mode, videoData: v.videoData });
    }
  },
  setSceneShots: (sceneShots) => set({ sceneShots }),
  setVideoSpecPath: (videoSpecPath) => set({ videoSpecPath }),
  reset: () => set(initialState),
}));
