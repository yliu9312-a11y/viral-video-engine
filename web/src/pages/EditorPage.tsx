import React, { useCallback, useState, useEffect } from "react";
import { usePipelineStore } from "../stores/pipeline";
import { MigrationMap } from "../components/MigrationMap";

const API = "";

// ── Component icons & phase colors ──
const COMP_ICONS: Record<string, string> = {
  KineticText: "✏️", ProductShowcase: "🛍️", CountdownTimer: "⏱️",
  PriceReveal: "💰", BeforeAfter: "🔄", BarChart: "📊",
  NumberRoll: "🔢", DonutChart: "🍩", ParticleBg: "✨",
  GradientText: "🌈", WordReveal: "📖", TypewriterPrompt: "⌨️",
  GlassCard: "🃏", FloatingMockup: "📱", MarqueeText: "📰",
  FeatureGrid: "🧩", LogoReveal: "🏷️", GlowTrail: "💫",
};
const PHASE_COLORS: Record<string, string> = {
  hook: "#FF6B6B", build: "#4ECDC4", cta: "#FFE66D",
};

interface EditorPageProps {
  onBack: () => void;
}

export default function EditorPage({ onBack }: EditorPageProps) {
  const store = usePipelineStore();
  const [running, setRunning] = useState(false);

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
  const [editHistory, setEditHistory] = useState<string[]>([]);

  const videoSpecPath = store.videoSpecPath || (store.templatePath
    ? store.templatePath.replace("structure_template.json", "video_spec_standard.json")
    : null);

  const gapReport = store.gapReport as Record<string, unknown>;
  const gapSummary = gapReport?.summary as Record<string, unknown> | undefined;
  const gapCount = gapSummary?.total_gaps != null ? String(gapSummary.total_gaps) : "-";

  // Initialize scene shots from store
  useEffect(() => {
    if (store.sceneShots.length > 0 && sceneBeforeShots.length === 0) {
      setSceneBeforeShots(store.sceneShots);
    }
  }, [store.sceneShots]);

  // ── Scene edit ──
  const applySceneEdit = useCallback(async () => {
    if (!sceneInstruction.trim()) return;
    const specPath = editedSpecPath || videoSpecPath;
    if (!specPath) {
      setSceneError("没有可编辑的视频规格文件");
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
        body: JSON.stringify({ specPath, instruction: sceneInstruction }),
      });
      const data = (await resp.json()) as Record<string, unknown>;
      if (data.success) {
        setSceneDiff(data.diff as string[]);
        setEditedSpecPath(String(data.updated_spec_path));
        setSceneWarnings((data.warnings as string[]) || []);
        const before = data.before as Record<string, unknown> | undefined;
        const after = data.after as Record<string, unknown> | undefined;
        if (before?.shots) setSceneBeforeShots(before.shots as Record<string, unknown>[]);
        if (after?.shots) setSceneAfterShots(after.shots as Record<string, unknown>[]);
        const changed = new Set<number>();
        for (const line of (data.diff as string[])) {
          const m = line.match(/shot\[(\d+)\]/);
          if (m) changed.add(parseInt(m[1]));
          if (line.includes("新增")) {
            const m2 = line.match(/新增 shot\[(\d+)\]/);
            if (m2) changed.add(parseInt(m2[1]));
          }
        }
        setChangedShotIndices(changed);
        setEditHistory((prev) => [...prev, sceneInstruction]);
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

  // ── Re-render ──
  const reRender = useCallback(async () => {
    const specPath = editedSpecPath || videoSpecPath;
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
          mode: "edited", duration: 0,
          videoData: String(data.videoData),
          videoSize: Number(data.videoSize || 0),
        }]);
        store.setRenderResult({ videoData: String(data.videoData), outputPath: "" });
      } else {
        store.setError(String(data.error || "渲染失败"));
      }
    } catch (err) {
      store.setError(err instanceof Error ? err.message : "渲染失败");
    } finally {
      setRunning(false);
    }
  }, [editedSpecPath, videoSpecPath, store]);

  // ── Download ──
  const downloadVideo = useCallback(() => {
    if (!store.videoData) return;
    const bytes = atob(store.videoData);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: "video/mp4" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `vst_edited.mp4`;
    a.click();
    URL.revokeObjectURL(url);
  }, [store.videoData]);

  // ── Shots to display ──
  const shots = sceneAfterShots.length > 0 ? sceneAfterShots : sceneBeforeShots;

  return (
    <div style={s.page}>
      {/* Header bar */}
      <div style={s.header}>
        <button onClick={onBack} style={s.backBtn}>← 返回</button>
        <h1 style={s.title}>视频编辑器</h1>
        <div style={s.headerMeta}>
          <span style={s.badge}>{store.shots.length} 镜头</span>
          <span style={s.badge}>{gapCount} 缺口</span>
          <span style={s.badge}>{(store.structureTemplate as Record<string, unknown>)?.category as string || "通用"}</span>
        </div>
      </div>

      <div style={s.layout}>
        {/* ── Left: Video Preview ── */}
        <div style={s.previewPanel}>
          {store.videoData ? (
            <>
              <div style={s.videoWrap}>
                <video
                  key={store.videoData.slice(0, 20)}
                  src={`data:video/mp4;base64,${store.videoData}`}
                  controls autoPlay loop
                  style={s.video}
                />
              </div>
              <div style={s.previewActions}>
                <button onClick={reRender} disabled={running} style={s.actionBtn}>
                  {running ? "渲染中..." : "🔄 重新渲染"}
                </button>
                <button onClick={downloadVideo} style={{ ...s.actionBtn, ...s.downloadBtn }}>
                  ⬇️ 下载 MP4
                </button>
              </div>
              {editHistory.length > 0 && (
                <div style={s.historyBox}>
                  <div style={s.historyLabel}>编辑历史</div>
                  {editHistory.map((h, i) => (
                    <div key={i} style={s.historyItem}>{i + 1}. {h}</div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={s.emptyPreview}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>🎬</div>
              <div style={{ color: "var(--text-muted)", fontSize: 14 }}>
                点击右侧"编排"生成视频后，渲染结果会在这里显示
              </div>
            </div>
          )}

          {/* Migration Map */}
          {store.stage === "done" && (
            <div style={{ marginTop: 16 }}>
              <MigrationMap
                structureTemplate={store.structureTemplate}
                gapReport={store.gapReport}
                assignment={store.assignment}
              />
            </div>
          )}
        </div>

        {/* ── Right: Scene Editor ── */}
        <div style={s.editorPanel}>
          {/* Scene timeline strip */}
          {shots.length > 0 && (
            <div style={s.section}>
              <div style={s.sectionHeader}>
                <span style={s.sectionIcon}>🎞️</span>
                <span style={s.sectionTitle}>场景时间线</span>
                <span style={s.sectionMeta}>{shots.length} shots</span>
              </div>
              <div style={s.sceneStrip}>
                {shots.map((s_: Record<string, unknown>, i: number) => {
                  const isChanged = changedShotIndices.has(i);
                  return (
                    <div key={i} style={{
                      ...s.sceneCard,
                      borderColor: isChanged ? "var(--accent)" : "var(--border)",
                      background: isChanged ? "rgba(59,130,246,0.06)" : "var(--bg-input)",
                    }}>
                      <div style={s.sceneCardTop}>
                        <span style={{
                          ...s.phaseBadge,
                          background: PHASE_COLORS[s_.role as string] || "#666",
                        }}>
                          {String(s_.role)}
                        </span>
                        <span style={s.sceneIdx}>#{i}</span>
                        {isChanged && <span style={{ fontSize: 10, marginLeft: "auto" }}>✏️</span>}
                      </div>
                      <div style={s.sceneIcon}>{COMP_ICONS[s_.component as string] || "🎞️"}</div>
                      <div style={s.sceneComp}>{String(s_.component)}</div>
                      {s_.text && (
                        <div style={s.sceneText}>"{String(s_.text)}"</div>
                      )}
                      <div style={s.sceneDur}>{String(s_.duration_s)}s</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* NL Editor */}
          <div style={s.section}>
            <div style={s.sectionHeader}>
              <span style={s.sectionIcon}>✨</span>
              <span style={s.sectionTitle}>AI 场景编辑</span>
              <span style={s.sectionMeta}>NL-powered</span>
            </div>
            <p style={s.editHint}>
              用自然语言描述你想修改的内容，AI 会自动理解并修改视频结构
            </p>

            {/* Quick chips */}
            <div style={s.chips}>
              {["开头更抓人", "换个红色配色", "加快节奏", "减少文字", "结尾加CTA", "删掉最后一个场景", "所有文字改成大号"].map((chip) => (
                <button
                  key={chip}
                  onClick={() => setSceneInstruction(chip)}
                  style={{
                    ...s.chip,
                    borderColor: sceneInstruction === chip ? "var(--accent)" : "var(--border)",
                    background: sceneInstruction === chip ? "rgba(59,130,246,0.1)" : "transparent",
                    color: sceneInstruction === chip ? "var(--accent)" : "var(--text-muted)",
                  }}
                >
                  {chip}
                </button>
              ))}
            </div>

            {/* Input */}
            <div style={s.inputRow}>
              <input
                value={sceneInstruction}
                onChange={(e) => setSceneInstruction(e.target.value)}
                placeholder='如 "把第二个镜头换成倒计时，3秒"'
                style={s.input}
                onFocus={(e) => e.currentTarget.style.borderColor = "var(--accent)"}
                onBlur={(e) => e.currentTarget.style.borderColor = "var(--border)"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && sceneInstruction.trim()) applySceneEdit();
                }}
              />
              <button
                onClick={applySceneEdit}
                disabled={sceneEditing || !sceneInstruction.trim()}
                style={{
                  ...s.applyBtn,
                  opacity: sceneEditing ? 0.6 : 1,
                  cursor: sceneEditing ? "wait" : "pointer",
                }}
              >
                {sceneEditing ? "AI 编辑中..." : "✨ 应用"}
              </button>
            </div>

            {/* Error */}
            {sceneError && (
              <div style={s.errorBox}>❌ {sceneError}</div>
            )}

            {/* Diff */}
            {sceneDiff.length > 0 && (
              <div style={s.diffBox}>
                <div style={s.diffHeader}>✏️ 变更记录</div>
                {sceneDiff.map((d, i) => (
                  <div key={i} style={s.diffLine}>{d}</div>
                ))}
                {sceneWarnings.length > 0 && (
                  <div style={{ marginTop: 8, fontSize: 11, color: "var(--warning)" }}>
                    ⚠️ {sceneWarnings.join("; ")}
                  </div>
                )}
                <button
                  onClick={reRender}
                  disabled={running}
                  style={s.renderBtn}
                >
                  {running ? "渲染中..." : "🎬 用修改后的版本重新渲染"}
                </button>
              </div>
            )}
          </div>

          {/* Assignment viewer */}
          {Array.isArray((store.assignment as Record<string, unknown>)?.phases) && (
            <div style={s.section}>
              <div style={s.sectionHeader}>
                <span style={s.sectionIcon}>📋</span>
                <span style={s.sectionTitle}>素材分配方案</span>
              </div>
              {(
                (store.assignment as Record<string, unknown>).phases as Record<string, unknown>[]
              ).map((phase, i) => (
                <div key={i} style={s.phaseRow}>
                  <span style={s.phaseName}>{String(phase.phase)}</span>
                  <span style={s.phaseStrategy}>策略 {String(phase.strategy_id)}</span>
                  <span style={s.phaseMats}>
                    {(phase.materials as Record<string, unknown>[])?.length || 0} 素材
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Styles ──
const s: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "var(--bg-root)",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "12px 24px",
    background: "rgba(6,6,10,0.9)",
    backdropFilter: "blur(12px)",
    borderBottom: "1px solid var(--border)",
    position: "sticky",
    top: 0,
    zIndex: 50,
  },
  backBtn: {
    background: "transparent",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "6px 14px",
    color: "var(--text-muted)",
    fontSize: 13,
    cursor: "pointer",
    fontFamily: "var(--font-mono)",
    transition: "all 0.15s",
  },
  title: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: 0,
    letterSpacing: "-0.01em",
    fontFamily: "var(--font-display)",
  },
  headerMeta: {
    display: "flex",
    gap: 8,
    marginLeft: "auto",
  },
  badge: {
    fontSize: 11,
    color: "var(--accent)",
    background: "rgba(59,130,246,0.08)",
    border: "1px solid rgba(59,130,246,0.15)",
    borderRadius: 10,
    padding: "3px 10px",
    fontFamily: "var(--font-mono)",
  },
  layout: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
  },
  previewPanel: {
    flex: "0 0 50%",
    padding: 24,
    overflowY: "auto",
    borderRight: "1px solid var(--border)",
  },
  editorPanel: {
    flex: "0 0 50%",
    padding: 24,
    overflowY: "auto",
  },
  videoWrap: {
    borderRadius: 12,
    overflow: "hidden",
    background: "#000",
    border: "1px solid var(--border)",
    marginBottom: 16,
  },
  video: {
    width: "100%",
    maxHeight: 500,
    objectFit: "contain",
    display: "block",
  },
  previewActions: {
    display: "flex",
    gap: 8,
    marginBottom: 16,
  },
  actionBtn: {
    flex: 1,
    padding: "10px 0",
    border: "1px solid var(--border)",
    borderRadius: 8,
    background: "var(--bg-input)",
    color: "var(--text-primary)",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "var(--font-display)",
    transition: "all 0.15s",
  },
  downloadBtn: {
    background: "linear-gradient(135deg, var(--success), #00b87a)",
    border: "none",
    color: "#fff",
  },
  emptyPreview: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: 400,
    background: "var(--bg-input)",
    borderRadius: 12,
    border: "1px dashed var(--border)",
  },
  historyBox: {
    background: "var(--bg-input)",
    borderRadius: 8,
    border: "1px solid var(--border)",
    padding: 12,
    marginBottom: 16,
  },
  historyLabel: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--accent)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    marginBottom: 6,
  },
  historyItem: {
    fontSize: 12,
    color: "var(--text-secondary)",
    padding: "3px 0",
    fontFamily: "var(--font-mono)",
  },
  section: {
    marginBottom: 20,
    background: "var(--bg-card)",
    borderRadius: 10,
    border: "1px solid var(--border)",
    padding: 16,
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  sectionIcon: { fontSize: 16 },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 700,
    color: "var(--text-primary)",
    letterSpacing: "-0.01em",
  },
  sectionMeta: {
    fontSize: 10,
    color: "var(--text-muted)",
    fontFamily: "var(--font-mono)",
    marginLeft: "auto",
  },
  sceneStrip: {
    display: "flex",
    gap: 6,
    overflowX: "auto",
    paddingBottom: 4,
    scrollbarWidth: "thin",
  },
  sceneCard: {
    minWidth: 110,
    flex: "0 0 auto",
    borderRadius: 8,
    padding: "8px 10px",
    border: "1px solid var(--border)",
    transition: "all 0.2s",
  },
  sceneCardTop: {
    display: "flex",
    alignItems: "center",
    gap: 4,
    marginBottom: 4,
  },
  phaseBadge: {
    fontSize: 9,
    fontWeight: 700,
    color: "#fff",
    borderRadius: 3,
    padding: "1px 5px",
    fontFamily: "var(--font-mono)",
    textTransform: "uppercase",
  },
  sceneIdx: {
    fontSize: 9,
    color: "var(--text-muted)",
    fontFamily: "var(--font-mono)",
  },
  sceneIcon: { fontSize: 16, marginBottom: 2 },
  sceneComp: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--text-primary)",
    fontFamily: "var(--font-mono)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    marginBottom: 2,
  },
  sceneText: {
    fontSize: 9,
    color: "var(--text-muted)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    marginBottom: 2,
  },
  sceneDur: {
    fontSize: 9,
    color: "var(--text-muted)",
    fontFamily: "var(--font-mono)",
  },
  editHint: {
    color: "var(--text-muted)",
    fontSize: 12,
    marginBottom: 10,
    lineHeight: 1.5,
  },
  chips: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
    marginBottom: 10,
  },
  chip: {
    padding: "4px 12px",
    border: "1px solid var(--border)",
    borderRadius: 12,
    fontSize: 11,
    cursor: "pointer",
    transition: "all 0.15s",
    fontFamily: "var(--font-mono)",
    background: "transparent",
  },
  inputRow: {
    display: "flex",
    gap: 8,
    marginBottom: 10,
  },
  input: {
    flex: 1,
    padding: "10px 14px",
    border: "1px solid var(--border)",
    borderRadius: 8,
    fontSize: 13,
    background: "var(--bg-input)",
    color: "var(--text-primary)",
    fontFamily: "var(--font-mono)",
    outline: "none",
    transition: "border-color 0.2s",
  },
  applyBtn: {
    padding: "10px 20px",
    border: "none",
    borderRadius: 8,
    background: "var(--accent-gradient)",
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: "var(--font-display)",
    whiteSpace: "nowrap",
    transition: "all 0.2s",
  },
  errorBox: {
    padding: "10px 14px",
    marginBottom: 10,
    background: "rgba(255,77,77,0.06)",
    border: "1px solid rgba(255,77,77,0.15)",
    borderRadius: 8,
    color: "#ff4d4d",
    fontSize: 12,
  },
  diffBox: {
    padding: 14,
    background: "rgba(59,130,246,0.04)",
    border: "1px solid rgba(59,130,246,0.15)",
    borderRadius: 8,
    marginBottom: 10,
  },
  diffHeader: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--accent)",
    marginBottom: 8,
    textTransform: "uppercase",
    letterSpacing: "0.08em",
  },
  diffLine: {
    fontSize: 12,
    color: "var(--text-secondary)",
    padding: "4px 0",
    fontFamily: "var(--font-mono)",
    borderBottom: "1px solid var(--border)",
    lineHeight: 1.5,
  },
  renderBtn: {
    marginTop: 12,
    padding: "10px 0",
    width: "100%",
    border: "none",
    borderRadius: 8,
    background: "var(--accent-gradient)",
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "var(--font-display)",
  },
  phaseRow: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "8px 0",
    borderBottom: "1px solid var(--border)",
  },
  phaseName: {
    fontWeight: 700,
    color: "var(--text-primary)",
    fontSize: 13,
    minWidth: 60,
  },
  phaseStrategy: {
    color: "var(--accent)",
    fontWeight: 600,
    fontSize: 12,
    fontFamily: "var(--font-mono)",
  },
  phaseMats: {
    color: "var(--text-muted)",
    fontSize: 12,
    fontFamily: "var(--font-mono)",
    marginLeft: "auto",
  },
};
