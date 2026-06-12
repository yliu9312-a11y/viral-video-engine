import React, { useCallback, useRef, useState } from "react";
import { usePipelineStore, type Stage } from "../stores/pipeline";
import { MigrationMap } from "../components/MigrationMap";
import { FileDropZone } from "../components/FileDropZone";

const API = ""; // proxy handles /api

const STAGE_LABELS: Record<Stage, string> = {
  idle: "准备就绪",
  uploading: "上传文件中...",
  extracting: "S1+S2 视频分析中...",
  gapping: "S3 缺口检测中...",
  assigning: "S3 策略分配中...",
  rendering: "S4 Remotion 渲染中...",
  orchestrating: "编排 + 生成场景...",
  done: "完成！",
  error: "出错了",
};

const STAGE_ORDER: Stage[] = [
  "uploading",
  "extracting",
  "gapping",
  "assigning",
  "rendering",
  "orchestrating",
];

function stageIndex(s: Stage): number {
  return STAGE_ORDER.indexOf(s);
}

export default function HomePage() {
  const store = usePipelineStore();
  const migrateVideoRef = useRef<HTMLInputElement>(null);
  const [running, setRunning] = useState(false);
  const [videoFiles, setVideoFiles] = useState<File[]>([]);
  const [materialFiles, setMaterialFiles] = useState<File[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("standard");
  const [selectedDuration, setSelectedDuration] = useState<string>("standard");
  const [nlInstruction, setNlInstruction] = useState("");
  const [nlResult, setNlResult] = useState<string | null>(null);
  const [videoSpecPath, setVideoSpecPath] = useState<string | null>(null);

  // NL Scene Editor state
  const [sceneInstruction, setSceneInstruction] = useState("");
  const [sceneEditing, setSceneEditing] = useState(false);
  const [sceneDiff, setSceneDiff] = useState<string[]>([]);
  const [editedSpecPath, setEditedSpecPath] = useState<string | null>(null);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [sceneWarnings, setSceneWarnings] = useState<string[]>([]);
  const [sceneBeforeShots, setSceneBeforeShots] = useState<Record<string, unknown>[]>([]);
  const [sceneAfterShots, setSceneAfterShots] = useState<Record<string, unknown>[]>([]);
  const [changedShotIndices, setChangedShotIndices] = useState<Set<number>>(new Set());

  // Style Migration state
  const [migrateTopic, setMigrateTopic] = useState("武汉文化");
  const [migrating, setMigrating] = useState(false);
  const [migrateResult, setMigrateResult] = useState<Record<string, unknown> | null>(null);
  const [migrateError, setMigrateError] = useState<string | null>(null);
  const [migrateVideoData, setMigrateVideoData] = useState<string | null>(null);
  const [migrateStep, setMigrateStep] = useState("");
  const [migrateProgress, setMigrateProgress] = useState(0);

  const gapReport = store.gapReport as Record<string, unknown>;
  const gapSummary = gapReport?.summary as Record<string, unknown> | undefined;
  const gapCount: string = gapSummary?.total_gaps != null ? String(gapSummary.total_gaps) : "-";

  const runPipeline = useCallback(async () => {
    if (videoFiles.length === 0) {
      store.setError("请选择至少一个参考视频");
      return;
    }
    if (materialFiles.length === 0) {
      store.setError("请选择至少一个素材文件");
      return;
    }

    setRunning(true);
    store.reset();
    store.setStage("uploading");

    try {
      // Step 0: Upload files
      const toBase64 = (f: File): Promise<string> =>
        new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            const result = reader.result as string;
            resolve(result.split(",")[1]); // strip data:mime;base64, prefix
          };
          reader.onerror = reject;
          reader.readAsDataURL(f);
        });

      const videoDataList = await Promise.all(
        videoFiles.map(async (f) => ({
          name: f.name,
          data: await toBase64(f),
        }))
      );
      const materials = await Promise.all(
        materialFiles.map(async (f) => ({
          name: f.name,
          data: await toBase64(f),
        }))
      );

      const uploadRes = await fetch(`${API}/api/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ videos: videoDataList, materials }),
      });
      const uploadData = (await uploadRes.json()) as Record<string, unknown>;
      if (!uploadData.success) {
        throw new Error(String(uploadData.error || "Upload failed"));
      }
      store.setUploadResult({
        jobId: String(uploadData.jobId),
        videoPath: String(uploadData.videoPath),
        videoPaths: uploadData.videoPaths as string[] || [String(uploadData.videoPath)],
        materialDir: String(uploadData.materialDir),
      });

      // Step 1: Extract (S1+S2)
      store.setStage("extracting");
      const extractRes = await fetch(`${API}/api/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ videoPaths: uploadData.videoPaths || [uploadData.videoPath] }),
      });
      const extractData = (await extractRes.json()) as Record<string, unknown>;
      if (!extractData.success) {
        throw new Error(String(extractData.error || "Extract failed"));
      }
      store.setExtractResult({
        templateId: String(extractData.templateId),
        shots: extractData.shots as never[],
        structureTemplate: extractData.structureTemplate as Record<string, unknown>,
        outputDir: String(extractData.outputDir),
        templatePath: String(extractData.templatePath),
        videoInfos: extractData.videoInfos as import("../stores/pipeline").VideoInfo[] || [],
      });

      // Step 2: Gap detection (S3)
      store.setStage("gapping");
      const gapRes = await fetch(`${API}/api/gap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          structureTemplate: extractData.structureTemplate,
          materialDir: uploadData.materialDir,
        }),
      });
      const gapData = (await gapRes.json()) as Record<string, unknown>;
      if (!gapData.success) {
        throw new Error(String(gapData.error || "Gap detection failed"));
      }
      store.setGapResult({
        gapReport: gapData.gapReport as Record<string, unknown>,
        outputDir: String(gapData.outputDir),
        gapReportPath: String(gapData.gapReportPath),
      });

      // Step 3: Assign strategies (S3)
      store.setStage("assigning");
      const assignRes = await fetch(`${API}/api/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          gapReportPath: gapData.gapReportPath,
          templatePath: extractData.templatePath,
          materialDir: uploadData.materialDir,
        }),
      });
      const assignData = (await assignRes.json()) as Record<string, unknown>;
      if (!assignData.success) {
        throw new Error(String(assignData.error || "Assign failed"));
      }
      store.setAssignResult({
        assignment: assignData.assignment as Record<string, unknown>,
        outputDir: String(assignData.outputDir),
        assignmentPath: String(assignData.assignmentPath),
      });

      // Step 4: Render (S4) — 3 variants
      store.setStage("rendering");
      const renderRes = await fetch(`${API}/api/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assignmentPath: assignData.assignmentPath,
        }),
      });
      const renderData = (await renderRes.json()) as Record<string, unknown>;
      if (!renderData.success) {
        throw new Error(String(renderData.error || "Render failed"));
      }

      const variants = renderData.variants as { mode: string; duration: number; videoData: string; videoSize: number }[];
      if (variants && variants.length > 0) {
        store.setVariants(variants);
        const standard = variants.find((v) => v.mode === "standard") || variants[0];
        store.setRenderResult({
          videoData: standard.videoData,
          outputPath: "",
        });
      } else {
        store.setRenderResult({
          videoData: String(renderData.videoData || ""),
          outputPath: String(renderData.outputPath || ""),
        });
      }

      // Step 5: Auto-orchestrate (生成 VideoSpec + 场景数据)
      store.setStage("orchestrating");
      try {
        const orchRes = await fetch(`${API}/api/orchestrate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            assignment_path: assignData.assignmentPath,
            template_path: extractData.templatePath,
            material_dir: uploadData.materialDir,
            profile: "standard",
          }),
        });
        const orchData = (await orchRes.json()) as Record<string, unknown>;
        if (orchData.success) {
          const specPath = String(orchData.spec_path);
          store.setVideoSpecPath(specPath);
          const spec = orchData.video_spec as Record<string, unknown> | undefined;
          if (spec?.shots) {
            const shotsList = spec.shots as Record<string, unknown>[];
            store.setSceneShots(shotsList.map((s, i) => ({
              index: i,
              component: s.component,
              role: s.role || s.phase,
              duration_s: Math.round((s.duration as number || 0) / 30 * 10) / 10,
              text: (s.props as Record<string, unknown>)?.text || (s.props as Record<string, unknown>)?.product_name || "",
            })));
          }
          // 用 ScriptDrivenVideo 渲染替代旧的 ViralVideo
          const scriptRenderRes = await fetch(`${API}/api/render_script`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ specPath }),
          });
          const scriptRenderData = (await scriptRenderRes.json()) as Record<string, unknown>;
          if (scriptRenderData.success && scriptRenderData.videoData) {
            store.setRenderResult({
              videoData: String(scriptRenderData.videoData),
              outputPath: "",
            });
          }
        }
      } catch (orchErr) {
        console.warn("Auto-orchestrate failed, using fallback render:", orchErr);
      }

      store.setStage("done");
    } catch (err) {
      store.setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [store, videoFiles, materialFiles]);

  const downloadVideo = useCallback(() => {
    if (!store.videoData) return;
    const bytes = atob(store.videoData);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: "video/mp4" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `vst_${store.activeVariant}.mp4`;
    a.click();
    URL.revokeObjectURL(url);
  }, [store.videoData, store.activeVariant]);

  // ── NL Scene Editor ──
  const applySceneEdit = useCallback(async () => {
    if (!sceneInstruction.trim()) return;
    const specPath = editedSpecPath || videoSpecPath;
    if (!specPath) {
      setSceneError("没有可编辑的视频规格文件，请先完成编排");
      return;
    }

    setSceneEditing(true);
    setSceneError(null);
    setSceneDiff([]);
    setSceneWarnings([]);

    try {
      const resp = await fetch(`${API}/api/edit/scene`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          specPath: specPath,
          instruction: sceneInstruction,
        }),
      });
      const data = (await resp.json()) as Record<string, unknown>;
      if (data.success) {
        setSceneDiff(data.diff as string[]);
        setEditedSpecPath(String(data.updated_spec_path));
        setSceneWarnings((data.warnings as string[]) || []);
        // 存储 before/after shots 用于场景卡片渲染
        const before = data.before as Record<string, unknown> | undefined;
        const after = data.after as Record<string, unknown> | undefined;
        if (before?.shots) setSceneBeforeShots(before.shots as Record<string, unknown>[]);
        if (after?.shots) setSceneAfterShots(after.shots as Record<string, unknown>[]);
        // 计算哪些 shot 变了
        const changed = new Set<number>();
        const diffLines = data.diff as string[];
        for (const line of diffLines) {
          const m = line.match(/shot\[(\d+)\]/);
          if (m) changed.add(parseInt(m[1]));
          if (line.includes("新增")) {
            const m2 = line.match(/新增 shot\[(\d+)\]/);
            if (m2) changed.add(parseInt(m2[1]));
          }
        }
        setChangedShotIndices(changed);
        setSceneInstruction("");
      } else {
        setSceneError(String(data.error || "编辑失败"));
      }
    } catch {
      setSceneError("请求失败");
    } finally {
      setSceneEditing(false);
    }
  }, [sceneInstruction, editedSpecPath, videoSpecPath]);

  const reRenderWithEditedSpec = useCallback(async () => {
    const specPath = editedSpecPath;
    if (!specPath) return;
    setRunning(true);
    try {
      const resp = await fetch(`${API}/api/render_script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ specPath }),
      });
      const data = (await resp.json()) as Record<string, unknown>;
      if (data.success && data.videoData) {
        store.setVariants([{
          mode: "edited",
          duration: 0,
          videoData: String(data.videoData),
          videoSize: Number(data.videoSize || 0),
        }]);
        store.setRenderResult({ videoData: String(data.videoData), outputPath: "" });
      } else {
        store.setError(String(data.error || "渲染失败"));
      }
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "Re-render failed");
    } finally {
      setRunning(false);
    }
  }, [editedSpecPath, store]);

  // ── Style Migration ──
  const runStyleMigrate = useCallback(async () => {
    const videoFiles = migrateVideoRef.current?.files;
    if (!videoFiles || videoFiles.length === 0) {
      setMigrateError("请选择参考视频");
      return;
    }
    if (!migrateTopic.trim()) {
      setMigrateError("请输入主题");
      return;
    }

    setMigrating(true);
    setMigrateError(null);
    setMigrateResult(null);
    setMigrateVideoData(null);
    setMigrateProgress(0);

    try {
      // Step 1: Upload
      setMigrateStep("上传视频...");
      setMigrateProgress(5);
      const toBase64 = (f: File): Promise<string> =>
        new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve((reader.result as string).split(",")[1]);
          reader.onerror = reject;
          reader.readAsDataURL(f);
        });

      const videoFile = videoFiles[0];
      const videoData = await toBase64(videoFile);

      const uploadResp = await fetch(`${API}/api/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videos: [{ name: videoFile.name, data: videoData }],
          materials: [],
        }),
      });
      const uploadResult = await uploadResp.json();
      if (!uploadResult.success) {
        throw new Error(uploadResult.error || "上传失败");
      }
      setMigrateProgress(10);

      // Step 2: Style migration (long running - show estimated progress)
      setMigrateStep("场景分解 + 风格提取 + 图片生成 + 文字编排...");
      setMigrateProgress(15);

      // Start a progress timer that advances while waiting
      const progressTimer = setInterval(() => {
        setMigrateProgress((prev) => Math.min(prev + 1, 85));
      }, 3000);

      const resp = await fetch(`${API}/api/style_migrate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          videoPath: uploadResult.videoPath,
          topic: migrateTopic,
        }),
      });

      clearInterval(progressTimer);
      const result = await resp.json();
      if (!result.success) {
        throw new Error(result.error || "风格迁移失败");
      }

      setMigrateResult(result);
      setMigrateStep("风格迁移完成");
      setMigrateProgress(90);

      // 设置 specPath 以便编辑器可以使用
      if (result.decomp_path) {
        setVideoSpecPath(result.decomp_path);
        // 同时初始化场景卡片数据
        if (result.decomposition?.scenes) {
          const shotsList = result.decomposition.scenes.map((s: Record<string, unknown>, i: number) => ({
            index: i,
            component: s.elements?.[0]?.type === 'image' ? 'ProductShowcase' : 'KineticText',
            role: s.scene_role || 'build',
            duration_s: Math.round((s.duration_frames as number || 0) / 30 * 10) / 10,
            text: (s.elements as Record<string, unknown>[])?.find((e: Record<string, unknown>) => e.type === 'text')?.content_text || '',
          }));
          setSceneBeforeShots(shotsList);
          setSceneAfterShots([]);
          setChangedShotIndices(new Set());
        }
      }

      // Step 3: Render
      setMigrateStep("Remotion 渲染中...");
      const renderResp = await fetch(`${API}/api/render_scene`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          composition: "MultiSceneVideo",
          props: { decomposition: result.decomposition },
          width: result.decomposition.canvas_width || 1280,
          height: result.decomposition.canvas_height || 720,
          durationInFrames: result.decomposition.total_frames || 900,
          fps: result.decomposition.fps || 30,
        }),
      });
      const renderResult = await renderResp.json();
      if (renderResult.videoData) {
        setMigrateVideoData(renderResult.videoData);
      }
      setMigrateStep("完成！");
      setMigrateProgress(100);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setMigrateError(message);
      setMigrateStep("");
    } finally {
      setMigrating(false);
    }
  }, [migrateTopic]);

  const downloadMigrateVideo = useCallback(() => {
    if (!migrateVideoData) return;
    const bytes = atob(migrateVideoData);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: "video/mp4" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `style_migrate_${migrateTopic}.mp4`;
    a.click();
    URL.revokeObjectURL(url);
  }, [migrateVideoData, migrateTopic]);

  const currentIdx = stageIndex(store.stage);

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>VST - 爆款结构迁移引擎</h1>
      <p style={styles.subtitle}>上传视频 + 素材 → 一键生成爆款短视频</p>

      {/* Upload Section */}
      <div style={styles.card} className="animate-in">
        <h2 style={styles.cardTitle}>1. 上传素材</h2>
        <div style={styles.uploadRow}>
          <FileDropZone
            files={videoFiles}
            onChange={setVideoFiles}
            accept="video/*"
            label="参考视频"
            hint="拖拽视频文件到这里，或点击选择"
          />
          <FileDropZone
            files={materialFiles}
            onChange={setMaterialFiles}
            accept="image/*,video/*"
            label="用户素材"
            hint="拖拽图片/视频素材到这里，或点击选择"
          />
        </div>
        <button
          className="btn-primary"
          style={{
            ...styles.button,
            opacity: running ? 0.5 : 1,
          }}
          onClick={runPipeline}
          disabled={running}
        >
          {running ? "处理中..." : "开始生成"}
        </button>
      </div>

      {/* Style Migration Section */}
      <div style={styles.card} className="animate-in">
        <h2 style={styles.cardTitle}>🎬 风格迁移</h2>
        <p style={{ color: "#888", fontSize: 14, marginBottom: 16 }}>
          上传参考视频 → 提取视觉风格 → 生成新主题视频
        </p>
        <div style={styles.uploadRow}>
          <label style={styles.uploadLabel}>
            <span style={styles.labelText}>参考视频</span>
            <input
              ref={migrateVideoRef}
              type="file"
              accept="video/*"
              style={styles.fileInput}
            />
          </label>
          <label style={styles.uploadLabel}>
            <span style={styles.labelText}>目标主题</span>
            <input
              type="text"
              value={migrateTopic}
              onChange={(e) => setMigrateTopic(e.target.value)}
              placeholder="例如：武汉文化、成都美食、上海夜景"
              style={{
                ...styles.fileInput,
                padding: "12px 16px",
                cursor: "text",
              }}
            />
          </label>
        </div>
        <button
          className="btn-primary"
          style={{
            ...styles.button,
            opacity: migrating ? 0.5 : 1,
            background: migrating ? undefined : "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
          }}
          onClick={runStyleMigrate}
          disabled={migrating}
        >
          {migrating ? "风格迁移中..." : "开始风格迁移"}
        </button>

        {/* 进度条 */}
        {migrating && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "#888", marginBottom: 6 }}>
              <span>{migrateStep}</span>
              <span>{migrateProgress}%</span>
            </div>
            <div style={{ width: "100%", height: 6, background: "#1a1a2e", borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                width: `${migrateProgress}%`,
                height: "100%",
                background: "linear-gradient(90deg, #667eea, #764ba2)",
                borderRadius: 3,
                transition: "width 0.3s ease",
              }} />
            </div>
          </div>
        )}

        {/* 错误信息 */}
        {migrateError && (
          <div style={{ marginTop: 16, padding: 12, background: "#ff4d4d22", borderRadius: 8, color: "#ff4d4d" }}>
            ❌ {migrateError}
          </div>
        )}

        {/* 迁移结果 */}
        {migrateResult && (
          <div style={{ marginTop: 16, padding: 16, background: "#00d68f11", borderRadius: 8 }}>
            <h3 style={{ color: "#00d68f", margin: "0 0 12px 0" }}>✅ 风格迁移完成</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 14 }}>
              <div>风格家族: <strong>{String(migrateResult.style_family || "-")}</strong></div>
              <div>场景数: <strong>{String(migrateResult.scene_count || "-")}</strong></div>
              <div>元素数: <strong>{String(migrateResult.element_count || "-")}</strong></div>
              <div>Job ID: <strong>{String(migrateResult.job_id || "-")}</strong></div>
            </div>
          </div>
        )}

        {/* 视频预览 */}
        {migrateVideoData && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ color: "#fff", margin: "0 0 12px 0" }}>🎬 渲染结果</h3>
            <video
              src={`data:video/mp4;base64,${migrateVideoData}`}
              controls
              autoPlay
              loop
              style={{ width: "100%", maxWidth: 400, borderRadius: 8 }}
            />
            <button
              className="btn-primary"
              style={{ ...styles.button, marginTop: 12 }}
              onClick={downloadMigrateVideo}
            >
              下载视频
            </button>
          </div>
        )}
      </div>

      {/* Progress Section */}
      {store.stage !== "idle" && (
        <div style={styles.card} className="animate-in animate-in-delay-1">
          <h2 style={styles.cardTitle}>2. 处理进度</h2>
          <div style={styles.progressContainer}>
            {STAGE_ORDER.map((s, i) => {
              const isActive = store.stage === s;
              const isDone = currentIdx > i;
              const isError = store.stage === "error" && isActive;
              return (
                <div key={s} style={styles.progressStep}>
                  <div
                    style={{
                      ...styles.progressDot,
                      background: isError
                        ? "#FF4D4D"
                        : isDone
                        ? "#4CAF50"
                        : isActive
                        ? "#2196F3"
                        : "#333",
                    }}
                  >
                    {isDone ? "✓" : isActive ? "..." : i + 1}
                  </div>
                  <span
                    style={{
                      ...styles.progressLabel,
                      color: isActive ? "#fff" : "#888",
                    }}
                  >
                    {STAGE_LABELS[s]}
                  </span>
                </div>
              );
            })}
          </div>
          {store.error && (
            <div style={styles.errorBox}>{store.error}</div>
          )}
        </div>
      )}

      {/* Video Info Section */}
      {store.videoInfos.length > 0 && (
        <div style={styles.card} className="animate-in animate-in-delay-1">
          <h2 style={styles.cardTitle}>样例视频信息</h2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {store.videoInfos.map((vi) => (
              <div key={vi.index} style={{
                background: "#1a1a2e", borderRadius: 8, padding: "12px 16px",
                flex: "1 1 200px", minWidth: 200,
              }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  视频 {vi.index + 1}
                </div>
                <div style={{ fontSize: 13, color: "#aaa", lineHeight: 1.6 }}>
                  分辨率: {vi.width}×{vi.height}<br />
                  时长: {vi.duration}s<br />
                  帧率: {vi.fps}fps<br />
                  镜头数: {vi.shot_count}<br />
                  {vi.has_audio ? `音频: 有 (BPM ${vi.bpm})` : "音频: 无"}
                </div>
              </div>
            ))}
          </div>
          {/* Show structure summary */}
          {store.structureTemplate && (() => {
            const tpl = store.structureTemplate as Record<string, unknown>;
            const narr = (tpl.narrative || {}) as Record<string, unknown>;
            return (
              <div style={{ marginTop: 12, fontSize: 13, color: "#aaa" }}>
                <strong>提取结构:</strong>{" "}
                类别={tpl.category as string || "通用"}，
                Hook={narr.hook_type as string || "-"}，
                Build={narr.build_pattern as string || "-"}，
                CTA={narr.cta_type as string || "-"}
              </div>
            );
          })()}
        </div>
      )}

      {/* Results Section */}
      {store.stage === "done" && (
        <div style={styles.card} className="animate-in animate-in-delay-2">
          <h2 style={styles.cardTitle}>3. 渲染结果</h2>

          {/* Video Preview */}
          {store.videoData && (
            <>
              {/* Variant selector */}
              {store.variants.length > 1 && (
                <div style={styles.variantRow}>
                  {store.variants.map((v) => (
                    <button
                      key={v.mode}
                      style={{
                        ...styles.variantBtn,
                        ...(store.activeVariant === v.mode ? styles.variantActive : {}),
                      }}
                      onClick={() => store.setActiveVariant(v.mode)}
                    >
                      {v.mode === "compact" ? "紧凑" : v.mode === "standard" ? "标准" : "宽松"}
                      <span style={styles.variantDur}>{v.duration}s</span>
                    </button>
                  ))}
                </div>
              )}
              <div style={styles.previewContainer}>
                <video
                  key={store.activeVariant}
                  src={`data:video/mp4;base64,${store.videoData}`}
                  controls
                  autoPlay
                  loop
                  style={styles.video}
                />
              </div>
            </>
          )}

          {/* Stats */}
          <div style={styles.statsRow}>
            <div style={styles.stat}>
              <span style={styles.statValue}>{String(store.templateId)}</span>
              <span style={styles.statLabel}>模板 ID</span>
            </div>
            <div style={styles.stat}>
              <span style={styles.statValue}>{String(store.shots.length)}</span>
              <span style={styles.statLabel}>检测镜头</span>
            </div>
            <div style={styles.stat}>
              <span style={styles.statValue}>{gapCount}</span>
              <span style={styles.statLabel}>识别缺口</span>
            </div>
          </div>

          {/* Gap Report */}
          {Array.isArray((store.gapReport as Record<string, unknown>)?.gaps) && (
            <div style={styles.gapSection}>
              <h3 style={styles.sectionTitle}>缺口报告</h3>
              {(
                (store.gapReport as Record<string, unknown>).gaps as Record<
                  string,
                  unknown
                >[]
              ).map((gap, i) => (
                <div key={i} style={styles.gapItem}>
                  <span style={styles.gapPhase}>{String(gap.phase)}</span>
                  <span
                    style={{
                      ...styles.gapSeverity,
                      color:
                        gap.severity === "HIGH"
                          ? "#FF4D4D"
                          : gap.severity === "MEDIUM"
                          ? "#FFC107"
                          : "#4CAF50",
                    }}
                  >
                    {String(gap.severity)}
                  </span>
                  <span style={styles.gapImpact}>
                    {String(gap.impact_on_video)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Migration Map — 迁移溯源表 */}
          {store.stage === "done" && (
            <MigrationMap
              structureTemplate={store.structureTemplate}
              gapReport={store.gapReport}
              assignment={store.assignment}
            />
          )}

          {/* Assignment with adjustment */}
          {Array.isArray((store.assignment as Record<string, unknown>)?.phases) && (
            <div style={styles.gapSection}>
              <h3 style={styles.sectionTitle}>素材分配方案（可调整）</h3>
              {(
                (store.assignment as Record<string, unknown>).phases as Record<
                  string,
                  unknown
                >[]
              ).map((phase, i) => (
                <div key={i} style={styles.phaseCard}>
                  <div style={styles.phaseItem}>
                    <span style={styles.phaseName}>{String(phase.phase)}</span>
                    <select
                      style={styles.strategySelect}
                      value={String(phase.strategy_id)}
                      onChange={(e) => {
                        const assignment = store.assignment as Record<string, unknown>;
                        const phases = [...(assignment.phases as Record<string, unknown>[])];
                        phases[i] = { ...phases[i], strategy_id: e.target.value };
                        store.setAssignResult({
                          assignment: { ...assignment, phases },
                          outputDir: store.assignmentPath ? String(store.assignmentPath).replace('/material_assignment.json', '') : '',
                          assignmentPath: store.assignmentPath,
                        });
                      }}
                    >
                      <option value="A">A 结构重排</option>
                      <option value="B">B 字幕补全</option>
                      <option value="C">C 包装补全</option>
                      <option value="D">D AIGC 生成</option>
                      <option value="E">E 素材重组</option>
                      <option value="PASS">PASS 直接使用</option>
                    </select>
                    <span style={styles.phaseMaterials}>
                      {(phase.materials as Record<string, unknown>[])?.length || 0}{" "}
                      个素材
                    </span>
                    <label style={styles.materialUploadBtn}>
                      +素材
                      <input
                        type="file"
                        accept="image/*,video/*"
                        multiple
                        style={{ display: 'none' }}
                        onChange={async (e) => {
                          const files = e.target.files;
                          if (!files?.length) return;
                          // Upload materials and add to this phase
                          const toBase64 = (f: File): Promise<string> =>
                            new Promise((resolve, reject) => {
                              const reader = new FileReader();
                              reader.onload = () => resolve((reader.result as string).split(",")[1]);
                              reader.onerror = reject;
                              reader.readAsDataURL(f);
                            });
                          const mats = await Promise.all(
                            Array.from(files).map(async (f) => ({ name: f.name, data: await toBase64(f) }))
                          );
                          const uploadRes = await fetch('/api/upload', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ video: { name: 'placeholder.mp4', data: '' }, materials: mats }),
                          });
                          const uploadData = (await uploadRes.json()) as Record<string, unknown>;
                          if (uploadData.success && uploadData.materialPaths) {
                            const assignment = store.assignment as Record<string, unknown>;
                            const phases = [...(assignment.phases as Record<string, unknown>[])];
                            const existing = [...(phases[i].materials as Record<string, unknown>[] || [])];
                            for (const p of uploadData.materialPaths as string[]) {
                              existing.push({ path: p, type: 'image', role: 'manual', duration_s: 3.0 });
                            }
                            phases[i] = { ...phases[i], materials: existing };
                            store.setAssignResult({
                              assignment: { ...assignment, phases },
                              outputDir: store.assignmentPath ? String(store.assignmentPath).replace('/material_assignment.json', '') : '',
                              assignmentPath: store.assignmentPath,
                            });
                          }
                          e.target.value = '';
                        }}
                      />
                    </label>
                  </div>
                  {/* KB-recommended atoms */}
                  {(phase.kb_atoms as Record<string, unknown>[])?.length > 0 && (
                    <div style={styles.kbSection}>
                      <span style={styles.kbLabel}>知识库推荐:</span>
                      {(phase.kb_atoms as Record<string, unknown>[]).map(
                        (atom, j) => (
                          <div key={j} style={styles.kbAtom}>
                            <span style={styles.kbAtomId}>
                              {String(atom.atom_id)}
                            </span>
                            <span style={styles.kbAtomDesc}>
                              {String(atom.description)}
                            </span>
                            <span style={styles.kbAtomScore}>
                              {typeof atom.visual_impact_score === "number"
                                ? `影响力 ${(atom.visual_impact_score as number).toFixed(2)}`
                                : ""}
                            </span>
                            <span style={styles.kbAtomDist}>
                              dist={typeof atom.distance === "number"
                                ? (atom.distance as number).toFixed(3)
                                : String(atom.distance)}
                            </span>
                          </div>
                        )
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* 2-axis selector: content profile × duration (orthogonal) */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#374151", minWidth: 70 }}>内容策略:</span>
              {[
                { key: "standard", label: "标准" },
                { key: "ctr", label: "高点击 CTR" },
                { key: "conversion", label: "高转化" },
                { key: "pace", label: "高节奏" },
                { key: "premium", label: "高质感" },
              ].map((p) => (
                <button
                  key={p.key}
                  onClick={() => setSelectedProfile(p.key)}
                  style={{
                    padding: "3px 10px",
                    border: selectedProfile === p.key ? "2px solid #3B82F6" : "1px solid #D1D5DB",
                    borderRadius: 6,
                    background: selectedProfile === p.key ? "#EFF6FF" : "#FFFFFF",
                    color: selectedProfile === p.key ? "#1E40AF" : "#374151",
                    fontSize: 12,
                    fontWeight: selectedProfile === p.key ? 600 : 400,
                    cursor: "pointer",
                  }}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "#374151", minWidth: 70 }}>时长节奏:</span>
              {[
                { key: "compact", label: "紧凑 15s" },
                { key: "standard", label: "标准 22s" },
                { key: "relaxed", label: "舒展 30s" },
              ].map((d) => (
                <button
                  key={d.key}
                  onClick={() => setSelectedDuration(d.key)}
                  style={{
                    padding: "3px 10px",
                    border: selectedDuration === d.key ? "2px solid #10B981" : "1px solid #D1D5DB",
                    borderRadius: 6,
                    background: selectedDuration === d.key ? "#ECFDF5" : "#FFFFFF",
                    color: selectedDuration === d.key ? "#065F46" : "#374151",
                    fontSize: 12,
                    fontWeight: selectedDuration === d.key ? 600 : 400,
                    cursor: "pointer",
                  }}
                >
                  {d.label}
                </button>
              ))}
              <span style={{ fontSize: 11, color: "#9CA3AF", marginLeft: 4 }}>
                {selectedProfile} × {selectedDuration} = {selectedProfile === "standard" ? selectedDuration : `${selectedProfile}+${selectedDuration}`}
              </span>
            </div>
          </div>

          {/* NL editing (Task 13) */}
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input
              type="text"
              value={nlInstruction}
              onChange={(e) => setNlInstruction(e.target.value)}
              placeholder="用自然语言调整，如 '开头更抓人' '减少字幕' '把商品提前'"
              style={{
                flex: 1,
                padding: "6px 12px",
                border: "1px solid #D1D5DB",
                borderRadius: 6,
                fontSize: 13,
              }}
              onKeyDown={async (e) => {
                if (e.key === "Enter" && nlInstruction.trim()) {
                  setRunning(true);
                  setNlResult(null);
                  try {
                    const resp = await fetch(`${API}/api/edit/nl`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        assignment_path: store.assignmentPath,
                        instruction: nlInstruction,
                      }),
                    });
                    const data = (await resp.json()) as Record<string, unknown>;
                    if (data.success) {
                      const diff = data.diff as string[];
                      setNlResult(diff.length > 0 ? diff.join(" | ") : "无变化");
                      setNlInstruction("");
                    } else {
                      setNlResult(`错误: ${data.error}`);
                    }
                  } catch {
                    setNlResult("请求失败");
                  } finally {
                    setRunning(false);
                  }
                }
              }}
            />
            <button
              className="btn-secondary"
              style={{ padding: "6px 16px", fontSize: 12 }}
              onClick={async () => {
                if (!nlInstruction.trim()) return;
                setRunning(true);
                setNlResult(null);
                try {
                  const resp = await fetch(`${API}/api/edit/nl`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      assignment_path: store.assignmentPath,
                      instruction: nlInstruction,
                    }),
                  });
                  const data = (await resp.json()) as Record<string, unknown>;
                  if (data.success) {
                    const diff = data.diff as string[];
                    setNlResult(diff.length > 0 ? diff.join(" | ") : "无变化");
                    setNlInstruction("");
                  } else {
                    setNlResult(`错误: ${data.error}`);
                  }
                } catch {
                  setNlResult("请求失败");
                } finally {
                  setRunning(false);
                }
              }}
            >
              应用
            </button>
          </div>
          {nlResult && (
            <div style={{ marginBottom: 12, padding: "6px 12px", background: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 6, fontSize: 12, color: "#166534" }}>
              {nlResult}
            </div>
          )}

          {/* ── NL Scene Editor ── */}
          <div style={{
            borderTop: "1px solid var(--border)",
            paddingTop: 20, marginTop: 8, marginBottom: 16,
          }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <span style={{ fontSize: 16 }}>🎬</span>
              <h3 style={{
                fontSize: 14, fontWeight: 700, color: "var(--text-primary)",
                letterSpacing: "-0.01em", margin: 0,
              }}>
                场景编辑器
              </h3>
              <span style={{
                fontSize: 10, color: "var(--text-muted)",
                fontFamily: "var(--font-mono)", marginLeft: "auto",
              }}>
                NL-powered
              </span>
            </div>

            {/* Scene strip — 可视化每个 shot */}
            {(() => {
              // 优先显示编辑后的 shots，否则显示编排阶段的
              const shots = (sceneAfterShots.length > 0 ? sceneAfterShots : sceneBeforeShots);
              if (shots.length === 0) return null;

              const PHASE_COLORS: Record<string, string> = {
                hook: "#FF6B6B",
                build: "#4ECDC4",
                cta: "#FFE66D",
              };
              const COMP_ICONS: Record<string, string> = {
                KineticText: "✏️", ProductShowcase: "🛍️", CountdownTimer: "⏱️",
                PriceReveal: "💰", BeforeAfter: "🔄", BarChart: "📊",
                NumberRoll: "🔢", DonutChart: "🍩", ParticleBg: "✨",
                GradientText: "🌈", WordReveal: "📖", TypewriterPrompt: "⌨️",
                GlassCard: "🃏", FloatingMockup: "📱", MarqueeText: "📰",
                FeatureGrid: "🧩", LogoReveal: "🏷️", GlowTrail: "💫",
              };

              return (
                <div style={{
                  display: "flex", gap: 6, overflowX: "auto", paddingBottom: 8,
                  marginBottom: 12, scrollbarWidth: "thin",
                }}>
                  {shots.map((s: Record<string, unknown>, i: number) => {
                    const isChanged = changedShotIndices.has(i);
                    return (
                      <div key={i} style={{
                        minWidth: 120, flex: "0 0 auto",
                        background: isChanged ? "rgba(59, 130, 246, 0.08)" : "var(--bg-input)",
                        border: `1px solid ${isChanged ? "var(--accent)" : "var(--border)"}`,
                        borderRadius: 8, padding: "10px 12px",
                        transition: "all 0.2s",
                      }}>
                        {/* Index + Phase badge */}
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                          <span style={{
                            fontSize: 10, fontWeight: 700, color: "#fff",
                            background: PHASE_COLORS[s.role as string] || "#666",
                            borderRadius: 3, padding: "1px 5px",
                            fontFamily: "var(--font-mono)",
                            textTransform: "uppercase",
                          }}>
                            {String(s.role)}
                          </span>
                          <span style={{
                            fontSize: 10, color: "var(--text-muted)",
                            fontFamily: "var(--font-mono)",
                          }}>
                            #{i}
                          </span>
                          {isChanged && (
                            <span style={{ fontSize: 10, marginLeft: "auto" }}>✏️</span>
                          )}
                        </div>

                        {/* Component icon + name */}
                        <div style={{ fontSize: 18, marginBottom: 4 }}>
                          {COMP_ICONS[s.component as string] || "🎞️"}
                        </div>
                        <div style={{
                          fontSize: 11, fontWeight: 600, color: "var(--text-primary)",
                          marginBottom: 4, fontFamily: "var(--font-mono)",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>
                          {String(s.component)}
                        </div>

                        {/* Key text content */}
                        {s.text && (
                          <div style={{
                            fontSize: 10, color: "var(--text-muted)",
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            marginBottom: 4,
                          }}>
                            "{String(s.text)}"
                          </div>
                        )}

                        {/* Duration */}
                        <div style={{
                          fontSize: 10, color: "var(--text-muted)",
                          fontFamily: "var(--font-mono)",
                        }}>
                          {String(s.duration_s)}s
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })()}

            {/* Quick chips */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
              {["开头更抓人", "换个红色配色", "加快节奏", "减少文字", "结尾加CTA", "删掉最后一个场景", "所有文字改成大号"].map((chip) => (
                <button
                  key={chip}
                  onClick={() => setSceneInstruction(chip)}
                  style={{
                    padding: "4px 12px",
                    border: `1px solid ${sceneInstruction === chip ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: 12,
                    background: sceneInstruction === chip ? "rgba(59,130,246,0.1)" : "transparent",
                    color: sceneInstruction === chip ? "var(--accent)" : "var(--text-muted)",
                    fontSize: 11, cursor: "pointer",
                    transition: "all 0.15s",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {chip}
                </button>
              ))}
            </div>

            {/* Input + button */}
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <input
                type="text"
                value={sceneInstruction}
                onChange={(e) => setSceneInstruction(e.target.value)}
                placeholder='用自然语言描述修改，如 "把第二个镜头换成倒计时，3秒"'
                style={{
                  flex: 1, padding: "10px 14px",
                  border: "1px solid var(--border)", borderRadius: 8,
                  fontSize: 13, background: "var(--bg-input)",
                  color: "var(--text-primary)", fontFamily: "var(--font-mono)",
                  outline: "none",
                  transition: "border-color 0.2s",
                }}
                onFocus={(e) => e.currentTarget.style.borderColor = "var(--accent)"}
                onBlur={(e) => e.currentTarget.style.borderColor = "var(--border)"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && sceneInstruction.trim()) applySceneEdit();
                }}
              />
              <button
                style={{
                  padding: "10px 20px", border: "none", borderRadius: 8,
                  background: sceneEditing ? "var(--bg-input)" : "var(--accent-gradient)",
                  color: "#fff", fontSize: 13, fontWeight: 600,
                  cursor: sceneEditing ? "wait" : "pointer",
                  opacity: sceneEditing ? 0.6 : 1,
                  transition: "all 0.2s",
                  fontFamily: "var(--font-display)",
                  whiteSpace: "nowrap",
                }}
                onClick={applySceneEdit}
                disabled={sceneEditing || !sceneInstruction.trim()}
              >
                {sceneEditing ? "AI 编辑中..." : "✨ 应用"}
              </button>
            </div>

            {/* Error */}
            {sceneError && (
              <div style={{
                padding: "10px 14px", marginBottom: 10,
                background: "rgba(255,77,77,0.06)", border: "1px solid rgba(255,77,77,0.15)",
                borderRadius: 8, color: "#ff4d4d", fontSize: 12,
              }}>
                ❌ {sceneError}
              </div>
            )}

            {/* Diff + re-render */}
            {sceneDiff.length > 0 && (
              <div style={{
                padding: 14, background: "rgba(59,130,246,0.04)",
                border: "1px solid rgba(59,130,246,0.15)", borderRadius: 8,
                marginBottom: 10,
              }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, color: "var(--accent)",
                  marginBottom: 8, textTransform: "uppercase",
                  letterSpacing: "0.08em",
                }}>
                  ✏️ 变更记录
                </div>
                {sceneDiff.map((d, i) => (
                  <div key={i} style={{
                    fontSize: 12, color: "var(--text-secondary)",
                    padding: "4px 0", fontFamily: "var(--font-mono)",
                    borderBottom: i < sceneDiff.length - 1 ? "1px solid var(--border)" : "none",
                    lineHeight: 1.5,
                  }}>
                    {d}
                  </div>
                ))}
                {sceneWarnings.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 11, color: "var(--warning)" }}>
                    ⚠️ {sceneWarnings.join("; ")}
                  </div>
                )}
                <button
                  style={{
                    marginTop: 12, padding: "10px 0", width: "100%",
                    border: "none", borderRadius: 8,
                    background: "var(--accent-gradient)",
                    color: "#fff", fontSize: 13, fontWeight: 600,
                    cursor: "pointer",
                    fontFamily: "var(--font-display)",
                  }}
                  onClick={reRenderWithEditedSpec}
                  disabled={running}
                >
                  {running ? "渲染中..." : "🎬 用修改后的版本重新渲染"}
                </button>
              </div>
            )}
          </div>

          {/* Orchestrate with selected profile */}
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <button
              className="btn-primary"
              style={{ ...styles.button, flex: 1 }}
              onClick={async () => {
                const assignmentPath = store.assignmentPath;
                const templatePath = store.templatePath;
                if (!assignmentPath || !templatePath) return;
                setRunning(true);
                try {
                  const resp = await fetch(`${API}/api/orchestrate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      assignment_path: assignmentPath,
                      template_path: templatePath,
                      material_dir: store.materialDir,
                      profile: selectedProfile === "standard" ? "standard" : selectedProfile,
                    }),
                  });
                  const data = (await resp.json()) as Record<string, unknown>;
                  if (data.success) {
                    setVideoSpecPath(String(data.spec_path));
                    store.setVideoSpecPath(String(data.spec_path));
                    const total = data.total_frames as number;
                    const shots = data.shot_count as number;
                    setNlResult(`编排完成: ${shots} shots, ${(total / 30).toFixed(1)}s, profile=${selectedProfile}`);
                    // 提取 shots 摘要用于场景卡片展示
                    const spec = data.video_spec as Record<string, unknown> | undefined;
                    if (spec?.shots) {
                      const shotsList = spec.shots as Record<string, unknown>[];
                      const shotsSummary = shotsList.map((s, i) => ({
                        index: i,
                        component: s.component,
                        role: s.role || s.phase,
                        duration_s: Math.round((s.duration as number || 0) / 30 * 10) / 10,
                        text: (s.props as Record<string, unknown>)?.text || (s.props as Record<string, unknown>)?.product_name || "",
                      }));
                      setSceneBeforeShots(shotsSummary);
                      store.setSceneShots(shotsSummary);
                      setSceneAfterShots([]);
                      setChangedShotIndices(new Set());
                    }
                  } else {
                    setNlResult(`编排失败: ${data.error}`);
                  }
                } catch (err) {
                  setNlResult(`编排失败: ${err instanceof Error ? err.message : "未知错误"}`);
                } finally {
                  setRunning(false);
                }
              }}
              disabled={running || !store.assignmentPath}
            >
              {running ? "编排中..." : `用「${selectedProfile === "standard" ? "标准" : selectedProfile}」策略编排`}
            </button>

            {/* Render VideoSpec if available */}
            {videoSpecPath && (
              <button
                className="btn-primary"
                style={{ ...styles.button, flex: 1 }}
                onClick={async () => {
                  setRunning(true);
                  try {
                    const resp = await fetch(`${API}/api/render`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ assignmentPath: videoSpecPath }),
                    });
                    const data = (await resp.json()) as Record<string, unknown>;
                    if (data.success && data.variants) {
                      const variants = data.variants as { mode: string; duration: number; videoData: string; videoSize: number }[];
                      store.setVariants(variants);
                      const standard = variants.find((v) => v.mode === "standard") || variants[0];
                      store.setRenderResult({ videoData: standard.videoData, outputPath: "" });
                    }
                  } catch (err) {
                    store.setError(err instanceof Error ? err.message : "Render failed");
                  } finally {
                    setRunning(false);
                  }
                }}
                disabled={running}
              >
                {running ? "渲染中..." : "渲染此版本"}
              </button>
            )}
          </div>

          {/* Re-render after adjustment */}
          <button
            className="btn-primary"
            style={{ ...styles.button, marginBottom: 12 }}
            onClick={async () => {
              // Save adjusted assignment and re-render
              const assignmentPath = store.assignmentPath;
              if (!assignmentPath) return;
              setRunning(true);
              try {
                const resp = await fetch(`${API}/api/render`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ assignmentPath }),
                });
                const data = (await resp.json()) as Record<string, unknown>;
                if (data.success && data.variants) {
                  const variants = data.variants as { mode: string; duration: number; videoData: string; videoSize: number }[];
                  store.setVariants(variants);
                  const standard = variants.find((v) => v.mode === "standard") || variants[0];
                  store.setRenderResult({ videoData: standard.videoData, outputPath: '' });
                }
              } catch (err) {
                store.setError(err instanceof Error ? err.message : 'Re-render failed');
              } finally {
                setRunning(false);
              }
            }}
            disabled={running}
          >
            {running ? "重新渲染中..." : "重新渲染"}
          </button>

          {/* Download */}
          <button className="btn-success" style={styles.downloadButton} onClick={downloadVideo}>
            下载视频 (mp4)
          </button>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: 800,
    margin: "0 auto",
    padding: "2.5rem 1rem",
    minHeight: "100vh",
  },
  title: {
    fontSize: 36,
    fontWeight: 800,
    marginBottom: 6,
    background: "var(--accent-gradient)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
    letterSpacing: "-0.02em",
  },
  subtitle: {
    color: "var(--text-muted)",
    fontSize: 15,
    marginBottom: 36,
    fontFamily: "var(--font-mono)",
    letterSpacing: "0.01em",
  },
  card: {
    background: "var(--bg-card)",
    borderRadius: "var(--radius)",
    padding: 24,
    marginBottom: 20,
    border: "1px solid var(--border)",
    transition: "border-color 0.3s, box-shadow 0.3s",
  },
  cardTitle: {
    fontSize: 18,
    fontWeight: 700,
    marginBottom: 16,
    color: "var(--text-primary)",
    letterSpacing: "-0.01em",
  },
  uploadRow: {
    display: "flex",
    gap: 16,
    marginBottom: 20,
    flexWrap: "wrap" as const,
  },
  uploadLabel: {
    flex: 1,
    minWidth: 200,
    display: "flex",
    flexDirection: "column" as const,
    gap: 8,
  },
  labelText: {
    fontSize: 13,
    color: "var(--text-secondary)",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
  },
  fileInput: {
    background: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    padding: "12px 16px",
    color: "var(--text-primary)",
    fontSize: 13,
    fontFamily: "var(--font-mono)",
    transition: "border-color 0.2s",
  },
  button: {
    width: "100%",
    padding: "16px 0",
    background: "var(--accent-gradient)",
    border: "none",
    borderRadius: "var(--radius-sm)",
    color: "#fff",
    fontSize: 16,
    fontWeight: 700,
    fontFamily: "var(--font-display)",
    cursor: "pointer",
    transition: "transform 0.15s, box-shadow 0.3s",
    letterSpacing: "0.02em",
  },
  progressContainer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
  },
  progressStep: {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 10,
    flex: 1,
  },
  progressDot: {
    width: 38,
    height: 38,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    fontWeight: 700,
    color: "#fff",
    transition: "background 0.4s, box-shadow 0.4s",
    fontFamily: "var(--font-mono)",
  },
  progressLabel: {
    fontSize: 11,
    textAlign: "center" as const,
    transition: "color 0.3s",
    fontFamily: "var(--font-mono)",
    letterSpacing: "0.01em",
  },
  errorBox: {
    marginTop: 16,
    padding: 14,
    background: "rgba(255, 77, 106, 0.08)",
    border: "1px solid rgba(255, 77, 106, 0.2)",
    borderRadius: "var(--radius-sm)",
    color: "var(--accent)",
    fontSize: 13,
    fontFamily: "var(--font-mono)",
  },
  previewContainer: {
    marginBottom: 20,
    borderRadius: "var(--radius)",
    overflow: "hidden",
    background: "#000",
    border: "1px solid var(--border)",
  },
  variantRow: {
    display: "flex",
    gap: 8,
    marginBottom: 12,
  },
  variantBtn: {
    flex: 1,
    padding: "10px 0",
    background: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-secondary)",
    fontSize: 14,
    fontWeight: 600,
    fontFamily: "var(--font-display)",
    cursor: "pointer",
    transition: "all 0.2s",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 2,
  },
  variantActive: {
    background: "var(--accent-glow)",
    borderColor: "var(--accent)",
    color: "var(--text-primary)",
  },
  variantDur: {
    fontSize: 11,
    color: "var(--text-muted)",
    fontFamily: "var(--font-mono)",
  },
  video: {
    width: "100%",
    maxHeight: 500,
    objectFit: "contain",
  },
  statsRow: {
    display: "flex",
    gap: 12,
    marginBottom: 20,
  },
  stat: {
    flex: 1,
    background: "var(--bg-input)",
    borderRadius: "var(--radius-sm)",
    padding: "14px 12px",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 4,
    border: "1px solid var(--border)",
  },
  statValue: {
    fontSize: 22,
    fontWeight: 800,
    color: "var(--accent)",
    fontFamily: "var(--font-mono)",
  },
  statLabel: {
    fontSize: 11,
    color: "var(--text-muted)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
  },
  gapSection: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--text-secondary)",
    marginBottom: 12,
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
  },
  gapItem: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 0",
    borderBottom: "1px solid var(--border)",
  },
  gapPhase: {
    fontWeight: 700,
    color: "var(--text-primary)",
    minWidth: 80,
    fontSize: 13,
  },
  gapSeverity: {
    fontWeight: 700,
    fontSize: 11,
    padding: "3px 10px",
    borderRadius: 4,
    background: "rgba(255,255,255,0.04)",
    minWidth: 60,
    textAlign: "center" as const,
    fontFamily: "var(--font-mono)",
    letterSpacing: "0.04em",
  },
  gapImpact: {
    color: "var(--text-secondary)",
    fontSize: 13,
    flex: 1,
  },
  phaseItem: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 0",
  },
  phaseName: {
    fontWeight: 700,
    color: "var(--text-primary)",
    minWidth: 80,
    fontSize: 13,
  },
  phaseStrategy: {
    color: "var(--accent)",
    fontWeight: 600,
    minWidth: 80,
    fontSize: 13,
  },
  phaseMaterials: {
    color: "var(--text-muted)",
    fontSize: 13,
    fontFamily: "var(--font-mono)",
  },
  strategySelect: {
    background: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "4px 8px",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 600,
    fontFamily: "var(--font-mono)",
    cursor: "pointer",
    minWidth: 100,
  },
  materialUploadBtn: {
    background: "var(--bg-input)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "4px 10px",
    color: "var(--text-secondary)",
    fontSize: 11,
    fontWeight: 600,
    fontFamily: "var(--font-mono)",
    cursor: "pointer",
    transition: "border-color 0.2s",
    display: "inline-block",
  },
  phaseCard: {
    borderBottom: "1px solid var(--border)",
    paddingBottom: 8,
    marginBottom: 4,
  },
  kbSection: {
    marginTop: 8,
    marginLeft: 8,
    paddingLeft: 12,
    borderLeft: "2px solid var(--accent)",
  },
  kbLabel: {
    fontSize: 11,
    color: "var(--accent)",
    fontWeight: 600,
    display: "block",
    marginBottom: 6,
    textTransform: "uppercase" as const,
    letterSpacing: "0.06em",
  },
  kbAtom: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "4px 0",
    fontSize: 12,
  },
  kbAtomId: {
    color: "var(--warning)",
    fontWeight: 600,
    fontFamily: "var(--font-mono)",
    minWidth: 140,
    fontSize: 11,
  },
  kbAtomDesc: {
    color: "var(--text-secondary)",
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
  kbAtomScore: {
    color: "var(--success)",
    fontSize: 11,
    minWidth: 70,
    fontFamily: "var(--font-mono)",
  },
  kbAtomDist: {
    color: "var(--text-muted)",
    fontSize: 11,
    fontFamily: "var(--font-mono)",
    minWidth: 70,
  },
  downloadButton: {
    width: "100%",
    padding: "16px 0",
    background: "linear-gradient(135deg, var(--success), #00b87a)",
    border: "none",
    borderRadius: "var(--radius-sm)",
    color: "#fff",
    fontSize: 16,
    fontWeight: 700,
    fontFamily: "var(--font-display)",
    cursor: "pointer",
    marginTop: 12,
    transition: "transform 0.15s, box-shadow 0.3s",
    letterSpacing: "0.02em",
  },
};
