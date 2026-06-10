/**
 * MigrationMap — Task 7 迁移溯源表
 *
 * 让评审一眼看见: 源结构 → 缺口 → 策略 → 产出 (因果链)
 * 每行是一个 phase，点击展开显示素材→槽位钻取面板。
 */

import React, { useState, useMemo } from "react";

// ── Types ──

type Severity = "high" | "medium" | "low" | "none";

interface OutputComponent {
  name: string;
  kind: "strategy_choice" | "llm_choice" | "fallback_default" | "user_material" | "aigc_generated";
  detail?: string;
}

interface PhaseMigration {
  phase: string;
  durationPct: [number, number];
  requiredShotTypes: string[];
  shotCountRange: [number, number];
  missingShotTypes: string[];
  severity: Severity;
  impact: string;
  strategyId: string;
  strategyLabel: string;
  completionActions: string[];
  outputs: OutputComponent[];
  hasGap: boolean;
  usedFallback: boolean;
}

// ── Strategy labels ──

const STRATEGY_LABELS: Record<string, string> = {
  A: "结构重排",
  B: "字幕补全",
  C: "包装补全",
  D: "AIGC 生成",
  E: "素材重组",
  F: "LLM 编排",
  PASS: "直接通过",
};

// ── Severity colors ──

const SEVERITY_COLORS: Record<Severity, { bg: string; text: string; border: string }> = {
  high: { bg: "#FEE2E2", text: "#991B1B", border: "#F87171" },
  medium: { bg: "#FEF3C7", text: "#92400E", border: "#FBBF24" },
  low: { bg: "#FEF9C3", text: "#854D0E", border: "#FACC15" },
  none: { bg: "#ECFDF5", text: "#065F46", border: "#34D399" },
};

// ── Output kind badges ──

const KIND_BADGES: Record<string, { label: string; bg: string; text: string }> = {
  strategy_choice: { label: "策略", bg: "#DBEAFE", text: "#1E40AF" },
  llm_choice: { label: "LLM", bg: "#E0E7FF", text: "#3730A3" },
  fallback_default: { label: "默认", bg: "#F3F4F6", text: "#6B7280" },
  user_material: { label: "素材", bg: "#D1FAE5", text: "#065F46" },
  aigc_generated: { label: "AIGC", bg: "#FDE68A", text: "#92400E" },
};

// ── Builder: join store data into PhaseMigration[] ──

function buildPhaseMigrations(
  structureTemplate: Record<string, unknown>,
  gapReport: Record<string, unknown>,
  assignment: Record<string, unknown>,
): PhaseMigration[] {
  const timeline = (structureTemplate?.timeline || []) as Array<Record<string, unknown>>;
  const gaps = (gapReport?.gaps || gapReport?.phase_gaps || []) as Array<Record<string, unknown>>;
  const phases = (assignment?.phases || []) as Array<Record<string, unknown>>;

  // Build lookup maps by phase key
  const gapMap = new Map<string, Record<string, unknown>>();
  for (const g of gaps) {
    const key = String(g.phase || g.phase_name || "");
    if (key) gapMap.set(key, g);
  }

  const assignMap = new Map<string, Record<string, unknown>>();
  for (const p of phases) {
    const key = String(p.phase || p.phase_name || "");
    if (key) assignMap.set(key, p);
  }

  const result: PhaseMigration[] = [];

  for (const t of timeline) {
    const phase = String(t.phase || "");
    if (!phase) continue;

    const gap = gapMap.get(phase) || {};
    const assign = assignMap.get(phase) || {};

    // Required shot types
    const requiredShotTypes = (t.required_shot_types || []) as string[];
    const shotCountRange = (t.shot_count_range || [1, 3]) as [number, number];
    const durationPct = (t.duration_pct || [0, 1]) as [number, number];

    // Gap info
    const missingShotTypes = (gap.missing_shot_types || []) as string[];
    const severity = (gap.severity || "none") as Severity;
    const impact = String(gap.impact_on_video || gap.impact || "");

    // Strategy
    const strategyId = String(assign.strategy_id || assign.strategy || "PASS");
    const strategyLabel = STRATEGY_LABELS[strategyId] || strategyId;

    // Completion actions
    const actions = (assign.completion_actions || []) as Array<Record<string, unknown>>;
    const completionActions = actions.map(
      (a) => String(a.action_type || a.type || ""),
    );

    // Derive output components from completion actions
    const outputs: OutputComponent[] = [];
    for (const a of actions) {
      const actionType = String(a.action_type || a.type || "");
      const component = String(a.component || "");
      const params = (a.params || {}) as Record<string, unknown>;

      if (actionType === "animation_script") {
        // Strategy F: LLM orchestrates
        const kbAtoms = (params.kb_atoms || []) as Array<Record<string, unknown>>;
        if (kbAtoms.length > 0) {
          for (const atom of kbAtoms.slice(0, 3)) {
            outputs.push({
              name: String(atom.remotion_component || "Unknown"),
              kind: "llm_choice",
              detail: String(atom.description || ""),
            });
          }
        } else {
          outputs.push({ name: "ScriptDrivenVideo", kind: "llm_choice", detail: "LLM 编排" });
        }
      } else if (actionType === "remotion_component" && component) {
        outputs.push({ name: component, kind: "strategy_choice" });
      } else if (actionType === "aigc_image") {
        outputs.push({ name: "AIGC 图片", kind: "aigc_generated", detail: String(params.prompt || "").slice(0, 40) });
      } else if (actionType === "material_transform") {
        outputs.push({ name: String(params.transform || "素材变换"), kind: "user_material" });
      } else if (actionType === "subtitle_overlay") {
        outputs.push({ name: "字幕叠加", kind: "strategy_choice" });
      } else if (actionType === "skip_phase") {
        outputs.push({ name: "跳过", kind: "strategy_choice", detail: "结构重排" });
      }
    }

    // No actions → direct pass
    if (outputs.length && strategyId === "PASS") {
      // Keep outputs as-is
    } else if (outputs.length === 0 && strategyId === "PASS") {
      // No gap, no strategy — show "—" but with required types as context
    }

    const hasGap = missingShotTypes.length > 0;
    const usedFallback = outputs.some((o) => o.kind === "fallback_default");

    result.push({
      phase,
      durationPct,
      requiredShotTypes,
      shotCountRange,
      missingShotTypes,
      severity: hasGap ? severity : "none",
      impact,
      strategyId,
      strategyLabel: hasGap ? strategyLabel : "—",
      completionActions,
      outputs,
      hasGap,
      usedFallback,
    });
  }

  // Warn if gaps/assignment reference phases not in timeline
  for (const key of gapMap.keys()) {
    if (!timeline.some((t) => String(t.phase) === key)) {
      console.warn(`[MigrationMap] Gap references unknown phase: ${key}`);
    }
  }
  for (const key of assignMap.keys()) {
    if (!timeline.some((t) => String(t.phase) === key)) {
      console.warn(`[MigrationMap] Assignment references unknown phase: ${key}`);
    }
  }

  return result;
}

// ── Drill-down panel ──

const DrillDown: React.FC<{ migration: PhaseMigration }> = ({ migration }) => {
  return (
    <div
      style={{
        background: "#F9FAFB",
        border: "1px solid #E5E7EB",
        borderRadius: 8,
        padding: 16,
        marginTop: 8,
      }}
    >
      {/* Required shot types */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#6B7280", marginBottom: 4 }}>
          需要的镜头类型
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {migration.requiredShotTypes.length > 0 ? (
            migration.requiredShotTypes.map((t) => (
              <span
                key={t}
                style={{
                  padding: "2px 8px",
                  background: migration.missingShotTypes.includes(t) ? "#FEE2E2" : "#ECFDF5",
                  color: migration.missingShotTypes.includes(t) ? "#991B1B" : "#065F46",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 500,
                }}
              >
                {t}
              </span>
            ))
          ) : (
            <span style={{ fontSize: 11, color: "#9CA3AF" }}>无特定要求</span>
          )}
        </div>
      </div>

      {/* Missing types */}
      {migration.hasGap && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#991B1B", marginBottom: 4 }}>
            缺口
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {migration.missingShotTypes.map((t) => (
              <span
                key={t}
                style={{
                  padding: "2px 8px",
                  background: "#FEE2E2",
                  color: "#991B1B",
                  borderRadius: 4,
                  fontSize: 11,
                  fontWeight: 500,
                  border: "1px solid #F87171",
                }}
              >
                {t}
              </span>
            ))}
          </div>
          {migration.impact && (
            <div style={{ fontSize: 11, color: "#991B1B", marginTop: 4, fontStyle: "italic" }}>
              影响: {migration.impact}
            </div>
          )}
        </div>
      )}

      {/* Completion actions detail */}
      {migration.completionActions.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#6B7280", marginBottom: 4 }}>
            补全动作
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {migration.completionActions.map((a, i) => (
              <span
                key={i}
                style={{
                  padding: "2px 8px",
                  background: "#EFF6FF",
                  color: "#1E40AF",
                  borderRadius: 4,
                  fontSize: 11,
                }}
              >
                {a}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Output components detail */}
      {migration.outputs.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#6B7280", marginBottom: 4 }}>
            产出组件
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {migration.outputs.map((o, i) => {
              const badge = KIND_BADGES[o.kind] || KIND_BADGES.strategy_choice;
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 8px",
                    background: "#FFFFFF",
                    borderRadius: 4,
                    border: "1px solid #E5E7EB",
                  }}
                >
                  <span
                    style={{
                      padding: "1px 6px",
                      background: badge.bg,
                      color: badge.text,
                      borderRadius: 3,
                      fontSize: 10,
                      fontWeight: 600,
                    }}
                  >
                    {badge.label}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{o.name}</span>
                  {o.detail && (
                    <span style={{ fontSize: 11, color: "#9CA3AF" }}>{o.detail}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

// ── Main component ──

interface MigrationMapProps {
  structureTemplate: Record<string, unknown>;
  gapReport: Record<string, unknown>;
  assignment: Record<string, unknown>;
}

export const MigrationMap: React.FC<MigrationMapProps> = ({
  structureTemplate,
  gapReport,
  assignment,
}) => {
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);

  const migrations = useMemo(
    () => buildPhaseMigrations(structureTemplate, gapReport, assignment),
    [structureTemplate, gapReport, assignment],
  );

  if (migrations.length === 0) {
    return null;
  }

  return (
    <div
      style={{
        background: "#FFFFFF",
        border: "1px solid #E5E7EB",
        borderRadius: 12,
        padding: 20,
        marginTop: 16,
      }}
    >
      <h3
        style={{
          fontSize: 16,
          fontWeight: 700,
          color: "#111827",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 18 }}>&#x1F50D;</span>
        迁移溯源
      </h3>

      {/* Causal chain rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {migrations.map((m) => {
          const colors = SEVERITY_COLORS[m.severity];
          const isExpanded = expandedPhase === m.phase;

          return (
            <div key={m.phase}>
              {/* Main row — causal chain */}
              <div
                onClick={() => setExpandedPhase(isExpanded ? null : m.phase)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 14px",
                  background: colors.bg,
                  border: `1px solid ${colors.border}`,
                  borderRadius: 8,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
              >
                {/* Phase name */}
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 14,
                    color: colors.text,
                    minWidth: 50,
                    textTransform: "capitalize",
                  }}
                >
                  {m.phase}
                </div>

                {/* Arrow */}
                <span style={{ color: "#9CA3AF", fontSize: 12 }}>&#x25B8;</span>

                {/* Required types */}
                <div style={{ fontSize: 12, color: "#374151", flex: 1 }}>
                  {m.requiredShotTypes.length > 0
                    ? `需要 ${m.requiredShotTypes.join(", ")} (${Math.round(m.durationPct[0] * 100)}–${Math.round(m.durationPct[1] * 100)}%)`
                    : `无特定要求 (${Math.round(m.durationPct[0] * 100)}–${Math.round(m.durationPct[1] * 100)}%)`}
                </div>

                {/* Gap badge */}
                {m.hasGap ? (
                  <span
                    style={{
                      padding: "2px 8px",
                      background: colors.border,
                      color: "#FFFFFF",
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  >
                    {m.severity === "high" ? "严重缺口" : m.severity === "medium" ? "中等缺口" : "轻微缺口"}
                  </span>
                ) : (
                  <span
                    style={{
                      padding: "2px 8px",
                      background: "#34D399",
                      color: "#FFFFFF",
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  >
                    无缺口
                  </span>
                )}

                {/* Strategy */}
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: m.strategyId === "PASS" ? "#9CA3AF" : "#1E40AF",
                    minWidth: 70,
                  }}
                >
                  {m.strategyLabel}
                </div>

                {/* Arrow */}
                <span style={{ color: "#9CA3AF", fontSize: 12 }}>&#x25B8;</span>

                {/* Output components */}
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", minWidth: 150 }}>
                  {m.outputs.length > 0 ? (
                    m.outputs.map((o, i) => {
                      const badge = KIND_BADGES[o.kind] || KIND_BADGES.strategy_choice;
                      return (
                        <span
                          key={i}
                          style={{
                            padding: "1px 6px",
                            background: badge.bg,
                            color: badge.text,
                            borderRadius: 3,
                            fontSize: 11,
                            fontWeight: 500,
                          }}
                        >
                          {o.name}
                          {o.kind === "fallback_default" && (
                            <span style={{ marginLeft: 2, fontSize: 9 }}>(默认)</span>
                          )}
                        </span>
                      );
                    })
                  ) : (
                    <span style={{ fontSize: 11, color: "#9CA3AF" }}>—</span>
                  )}
                </div>

                {/* Expand indicator */}
                <span
                  style={{
                    fontSize: 10,
                    color: "#9CA3AF",
                    transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                    transition: "transform 0.15s",
                  }}
                >
                  &#x25B6;
                </span>
              </div>

              {/* Drill-down panel */}
              {isExpanded && <DrillDown migration={m} />}
            </div>
          );
        })}
      </div>
    </div>
  );
};
