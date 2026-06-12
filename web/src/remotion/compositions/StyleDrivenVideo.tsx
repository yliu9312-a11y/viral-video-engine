/**
 * StyleDrivenVideo — 风格驱动渲染器
 *
 * 读取 SceneDescription JSON（含 motion_path 关键帧），
 * 渲染带连续运动的多元素视频。
 *
 * 与旧版的区别：
 * - 旧版：元素只有入场/出场，中间完全静态
 * - 新版：元素有 motion_path 关键帧，逐帧插值实现连续运动
 */
import React from "react";
import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  interpolate,
  Img,
  staticFile,
} from "remotion";
import {
  TextOverlayLayer,
  FocusTextSpec,
  TextEntranceType,
} from "./TextOverlayLayer";
import {
  Vignette,
  FilmGrain,
  LightLeak,
  GradientMesh,
} from "../../components/mg/CinematicEffects";

// ── Types ────────────────────────────────────────────────────────────────

interface Keyframe {
  frame: number;
  x?: number | null;
  y?: number | null;
  rotation?: number | null;
  scale_x?: number | null;
  scale_y?: number | null;
  opacity?: number | null;
  easing?: string;
}

interface SpatialProps {
  x: number;
  y: number;
  width: number;
  height: number;
  anchor_x?: number;
  anchor_y?: number;
  rotation?: number;
  scale_x?: number;
  scale_y?: number;
  z_index?: number;
}

interface AppearanceProps {
  opacity?: number;
  fill?: string;
  stroke?: string;
  stroke_width?: number;
  border_radius?: number;
  shadow?: string;
  blend_mode?: string;
  blur?: number;
}

interface TypographyProps {
  font_family?: string;
  font_size?: number;
  font_weight?: number;
  line_height?: number;
  letter_spacing?: number;
  text_align?: string;
  color?: string;
  gradient?: string;
  text_transform?: string;
}

interface AnimationSpec {
  type: string;
  direction?: string;
  duration?: number;
  easing?: string;
  start_value?: number;
  end_value?: number;
}

interface TimingProps {
  in_point: number;
  out_point: number;
  entrance?: AnimationSpec;
  exit?: AnimationSpec;
  stagger_index?: number;
  stagger_delay?: number;
}

interface SceneElement {
  id: string;
  type: string;
  content_text?: string;
  content_src?: string;
  spatial: SpatialProps;
  appearance?: AppearanceProps;
  typography?: TypographyProps;
  timing: TimingProps;
  motion_path?: Keyframe[];
  z_order?: number;
  role?: string;
  source?: string;
  track_confidence?: number;
  effect_type?: string;
  effect_tier?: string;
  idle_animation?: string;
  exit_animation?: string;
  text_animation?: {
    entrance?: TextEntranceType;
    exit?: string;
    split_mode?: "char" | "word" | "line";
    direction?: "left" | "right" | "center" | "top" | "bottom";
    zone?: "focus" | "corner";
  };
}

interface MotionPattern {
  name: string;
  element_ids?: string[];
  params?: Record<string, number>;
  confidence?: number;
}

interface SceneDescription {
  canvas_width: number;
  canvas_height: number;
  fps: number;
  duration: number;
  background_color?: string;
  background_gradient?: string;
  elements: SceneElement[];
  motion_patterns?: MotionPattern[];
}

// ── 关键帧插值引擎 ──────────────────────────────────────────────────────

/**
 * 在关键帧序列中插值，返回当前帧的属性值。
 * 支持：位置、旋转、缩放、透明度
 */
function interpolateKeyframes(
  keyframes: Keyframe[],
  currentFrame: number,
  property: "x" | "y" | "rotation" | "scale_x" | "scale_y" | "opacity",
  fallback: number
): number {
  if (!keyframes || keyframes.length === 0) return fallback;
  if (keyframes.length === 1) {
    const val = keyframes[0][property];
    return val != null ? val : fallback;
  }

  // 当前帧在关键帧范围之前
  if (currentFrame <= keyframes[0].frame) {
    const val = keyframes[0][property];
    return val != null ? val : fallback;
  }

  // 当前帧在关键帧范围之后
  if (currentFrame >= keyframes[keyframes.length - 1].frame) {
    const val = keyframes[keyframes.length - 1][property];
    return val != null ? val : fallback;
  }

  // 找到包围当前帧的两个关键帧
  let left = keyframes[0];
  let right = keyframes[1];
  for (let i = 0; i < keyframes.length - 1; i++) {
    if (keyframes[i].frame <= currentFrame && keyframes[i + 1].frame >= currentFrame) {
      left = keyframes[i];
      right = keyframes[i + 1];
      break;
    }
  }

  const leftVal = left[property];
  const rightVal = right[property];

  // 如果两端都没有这个属性，用 fallback
  if (leftVal == null && rightVal == null) return fallback;
  if (leftVal == null) return rightVal!;
  if (rightVal == null) return leftVal;

  // 区间长度
  const span = right.frame - left.frame;
  if (span <= 0) return leftVal;

  // 线性进度
  const t = (currentFrame - left.frame) / span;

  // 缓动
  const easedT = applyEasing(t, left.easing || "ease-out");

  return leftVal + (rightVal - leftVal) * easedT;
}

function applyEasing(t: number, easing: string): number {
  switch (easing) {
    case "linear":
      return t;
    case "ease-in":
      return t * t;
    case "ease-out":
      return 1 - (1 - t) * (1 - t);
    case "ease-in-out":
      return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    case "spring":
      // 简单弹性缓动
      return 1 - Math.cos(t * Math.PI * 2.5) * Math.exp(-t * 4);
    case "bounce":
      if (t < 1 / 2.75) return 7.5625 * t * t;
      if (t < 2 / 2.75) return 7.5625 * (t -= 1.5 / 2.75) * t + 0.75;
      if (t < 2.5 / 2.75) return 7.5625 * (t -= 2.25 / 2.75) * t + 0.9375;
      return 7.5625 * (t -= 2.625 / 2.75) * t + 0.984375;
    default:
      return 1 - (1 - t) * (1 - t); // ease-out
  }
}

// ── 入场/出场动画 ────────────────────────────────────────────────────────

function getEntranceStyle(
  spec: AnimationSpec | undefined,
  progress: number
): React.CSSProperties {
  if (!spec || spec.type === "none") return {};

  const p = progress;
  const dir = spec.direction || "bottom";

  switch (spec.type) {
    case "fade":
      return { opacity: interpolate(p, [0, 1], [spec.start_value ?? 0, spec.end_value ?? 1]) };
    case "slide": {
      const dist = 100 * (1 - p);
      const translateMap: Record<string, string> = {
        left: `translateX(${-dist}%)`,
        right: `translateX(${dist}%)`,
        top: `translateY(${-dist}%)`,
        bottom: `translateY(${dist}%)`,
        center: `scale(${p})`,
      };
      return { transform: translateMap[dir] || `translateY(${dist}%)`, opacity: p };
    }
    case "scale":
      return { transform: `scale(${interpolate(p, [0, 1], [0.3, 1])})`, opacity: p };
    case "3d":
      return { transform: `perspective(800px) rotateY(${interpolate(p, [0, 1], [90, 0])}deg)`, opacity: p };
    case "clip":
      return { clipPath: `inset(0 ${interpolate(p, [0, 1], [100, 0])}% 0 0)` };
    case "mask_reveal": {
      // 遮罩揭示：从指定方向刷出（MG 最常用效果之一）
      const clipMap: Record<string, string> = {
        left: `inset(0 ${interpolate(p, [0, 1], [100, 0])}% 0 0)`,
        right: `inset(0 0 0 ${interpolate(p, [0, 1], [100, 0])}%)`,
        top: `inset(0 0 ${interpolate(p, [0, 1], [100, 0])}% 0)`,
        bottom: `inset(${interpolate(p, [0, 1], [100, 0])}% 0 0 0)`,
        up: `inset(0 0 ${interpolate(p, [0, 1], [100, 0])}% 0)`,
        center: `inset(${interpolate(p, [0, 1], [50, 0])}% ${interpolate(p, [0, 1], [50, 0])}% ${interpolate(p, [0, 1], [50, 0])}% ${interpolate(p, [0, 1], [50, 0])}%)`,
      };
      return { clipPath: clipMap[dir] || clipMap["bottom"] };
    }
    case "rotate":
      return { transform: `rotate(${interpolate(p, [0, 1], [-180, 0])}deg)`, opacity: p };
    case "blur":
      return { filter: `blur(${interpolate(p, [0, 1], [20, 0])}px)`, opacity: p };
    case "typewriter":
      return { opacity: p > 0.5 ? 1 : p * 2 };
    default:
      return {};
  }
}

// ── 持续动效（sustain phase）──────────────────────────────────────────────

function getSustainStyle(
  effectType: string | undefined,
  sustainFrame: number,
  fps: number
): React.CSSProperties {
  if (!effectType || effectType === "pop_in" || effectType === "none") return {};

  const t = sustainFrame / fps; // 秒

  switch (effectType) {
    case "scale_pulse": {
      // 缩放脉冲：0.9 ↔ 1.1 循环
      const s = 1 + 0.1 * Math.sin(t * Math.PI * 2);
      return { transform: `scale(${s}, ${s})` };
    }
    case "rotate_180": {
      // 旋转半圈：0 → 180°
      const r = Math.min(180, t * 60); // 3秒转完
      return { transform: `rotate(${r}deg)` };
    }
    case "scatter": {
      // 径向散开：向外移动
      const dist = Math.min(30, t * 15);
      return { transform: `translate(${dist}%, ${dist}%)` };
    }
    case "gather": {
      // 聚拢：向中心移动
      const dist = Math.max(0, 30 - t * 15);
      return { transform: `translate(${dist}%, ${dist}%)` };
    }
    case "flip": {
      // 3D 翻转
      const r = (t * 120) % 360; // 持续翻转
      return {
        transform: `perspective(800px) rotateY(${r}deg)`,
        transformStyle: "preserve-3d",
      };
    }
    case "spin_in": {
      // 旋转入场后保持
      const r = Math.min(360, t * 120);
      return { transform: `rotate(${r}deg)` };
    }
    case "elastic_pop": {
      // 弹性缩放（有回弹）
      const s = 1 + 0.15 * Math.sin(t * Math.PI * 3) * Math.exp(-t * 0.5);
      return { transform: `scale(${s}, ${s})` };
    }
    case "2_5d_push": {
      // 2.5D 推拉
      const z = 20 * Math.sin(t * Math.PI);
      return {
        transform: `perspective(800px) translateZ(${z}px)`,
        transformStyle: "preserve-3d",
      };
    }
    // ── idle 持续微动（次级动作）──
    case "float": {
      // 上下浮动（amplitude 3%, period 2.5s）
      const y = 3.0 * Math.sin(t * Math.PI * 0.8);
      return { transform: `translateY(${y}px)` };
    }
    case "breathe": {
      // 缩放呼吸（0.95 ↔ 1.05, period 3s）
      const s = 1 + 0.05 * Math.sin(t * Math.PI * 0.6);
      return { transform: `scale(${s}, ${s})` };
    }
    case "rotate": {
      // 慢速连续旋转（~30°/s）
      const r = (t * 30) % 360;
      return { transform: `rotate(${r}deg)` };
    }
    default:
      return {};
  }
}

// ── 元素渲染器 ───────────────────────────────────────────────────────────

interface ElementRendererProps {
  element: SceneElement;
  globalFrame: number;
  fps?: number;
}

const ElementRenderer: React.FC<ElementRendererProps> = ({
  element,
  globalFrame,
  fps = 30,
}) => {
  const { spatial, appearance, typography, timing, motion_path } = element;
  const entrance = timing.entrance;
  const exit = timing.exit;
  const duration = timing.out_point - timing.in_point;

  // ── 阶段 1: 入场动画（~6 帧 = 200ms @30fps）──
  const entranceDuration = entrance?.duration ?? 6;
  const entranceProgress = Math.min(1, globalFrame / Math.max(entranceDuration, 1));
  const entranceStyle = getEntranceStyle(entrance, entranceProgress);

  // ── 阶段 2: 出场动画（~3 帧 = 100ms，比入场快 — Material 规范）──
  const exitDuration = Math.min(exit?.duration ?? 3, 6);
  const exitStart = Math.max(0, duration - exitDuration);
  const exitProgress =
    globalFrame >= exitStart
      ? Math.min(1, (globalFrame - exitStart) / Math.max(exitDuration, 1))
      : 0;
  const exitStyle = getEntranceStyle(exit, 1 - exitProgress);

  // ── 阶段 3: 连续运动（motion_path 关键帧插值）──
  const absoluteFrame = timing.in_point + globalFrame;

  let motionX = spatial.x;
  let motionY = spatial.y;
  let motionRotation = spatial.rotation || 0;
  let motionScaleX = spatial.scale_x || 1;
  let motionScaleY = spatial.scale_y || 1;
  let motionOpacity = appearance?.opacity ?? 1;

  if (motion_path && motion_path.length > 1) {
    motionX = interpolateKeyframes(motion_path, absoluteFrame, "x", spatial.x);
    motionY = interpolateKeyframes(motion_path, absoluteFrame, "y", spatial.y);
    motionRotation = interpolateKeyframes(motion_path, absoluteFrame, "rotation", spatial.rotation || 0);
    motionScaleX = interpolateKeyframes(motion_path, absoluteFrame, "scale_x", spatial.scale_x || 1);
    motionScaleY = interpolateKeyframes(motion_path, absoluteFrame, "scale_y", spatial.scale_y || 1);
    motionOpacity = interpolateKeyframes(motion_path, absoluteFrame, "opacity", appearance?.opacity ?? 1);
  }

  // ── 阶段 3b: 持续动效（idle 优先，fallback 到 effect_type）──
  const sustainStart = entranceDuration;
  const sustainEnd = exitStart;
  const sustainFrame = globalFrame - sustainStart;
  const isInSustain = globalFrame >= sustainStart && globalFrame < sustainEnd;
  // idle_animation 来自 LLM 作曲家（float/breathe/rotate/none），effect_type 来动效分类器
  const idleAnim = (element as any).idle_animation || element.effect_type || "";
  const sustainStyle = isInSustain ? getSustainStyle(idleAnim, sustainFrame, fps) : {};

  // ── 轴心点（anchor）── 默认 50,50 = 中心
  const anchorX = spatial.anchor_x ?? 50;
  const anchorY = spatial.anchor_y ?? 50;

  // ── 合成最终样式 ──
  const baseStyle: React.CSSProperties = {
    position: "absolute",
    left: `${motionX}%`,
    top: `${motionY}%`,
    width: `${spatial.width}%`,
    height: `${spatial.height}%`,
    transformOrigin: `${anchorX}% ${anchorY}%`,
    transform: `translate(${anchorX - 100}%, ${anchorY - 100}%) rotate(${motionRotation}deg) scale(${motionScaleX}, ${motionScaleY}) ${entranceStyle.transform || ""} ${exitStyle.transform || ""} ${sustainStyle.transform || ""}`,
    opacity: motionOpacity * (Number(entranceStyle.opacity) || 1) * (Number(exitStyle.opacity) || 1),
    zIndex: spatial.z_index || 0,
    filter: entranceStyle.filter || exitStyle.filter,
    clipPath: entranceStyle.clipPath || exitStyle.clipPath || sustainStyle.clipPath,
    ...(sustainStyle.transformStyle ? { transformStyle: sustainStyle.transformStyle } : {}),
    ...(appearance?.shadow ? { boxShadow: appearance.shadow } : {}),
    ...(appearance?.border_radius ? { borderRadius: `${appearance.border_radius}px` } : {}),
  };

  // ── 文字元素 ──
  if (element.type === "text" && element.content_text) {
    const typo = typography || {};
    const textStyle: React.CSSProperties = {
      ...baseStyle,
      fontFamily: typo.font_family || "sans-serif",
      fontSize: `${typo.font_size || 4}vh`,
      fontWeight: typo.font_weight || 400,
      lineHeight: typo.line_height || 1.2,
      letterSpacing: `${typo.letter_spacing || 0}px`,
      textAlign: (typo.text_align as any) || "center",
      color: typo.color || "#fff",
      textTransform: typo.text_transform as any,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
      ...(typo.gradient
        ? {
            backgroundImage: typo.gradient,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }
        : {}),
    };

    return <div style={textStyle}>{element.content_text}</div>;
  }

  // ── 图片元素 ──
  if (element.type === "image" && element.content_src) {
    // 处理路径：去掉开头的 / 以适配 staticFile
    const src = element.content_src.startsWith("/")
      ? element.content_src.slice(1)
      : element.content_src;

    const imgStyle: React.CSSProperties = {
      ...baseStyle,
      objectFit: "cover",
    };

    try {
      return <Img src={staticFile(src)} style={imgStyle} />;
    } catch {
      // staticFile 失败时直接用原路径
      return <Img src={element.content_src} style={imgStyle} />;
    }
  }

  // ── 图片占位（无 content_src 时用颜色块）──
  if (element.type === "image") {
    const placeholderStyle: React.CSSProperties = {
      ...baseStyle,
      background: appearance?.fill || "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      borderRadius: `${appearance?.border_radius || 8}px`,
    };
    return <div style={placeholderStyle} />;
  }

  return null;
};

// ── 主合成 ───────────────────────────────────────────────────────────────

export const StyleDrivenVideo: React.FC<{ scene: SceneDescription }> = ({
  scene,
}) => {
  const frame = useCurrentFrame();

  const bgColor = scene.background_color || "#000";
  const bgGradient = scene.background_gradient || "";

  return (
    <AbsoluteFill
      style={{
        background: bgGradient || bgColor,
      }}
    >
      {scene.elements.map((el) => {
        const from = el.timing.in_point;
        const duration = el.timing.out_point - el.timing.in_point;
        if (duration <= 0) return null;

        return (
          <Sequence key={el.id} from={from} durationInFrames={duration}>
            <ElementRenderer
              element={el}
              globalFrame={frame - from}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

// ── 多场景合成（VideoDecomposition）────────────────────────────────────────

interface VideoSceneData {
  scene_index: number;
  start_frame: number;
  end_frame: number;
  duration_frames: number;
  background_color: string;
  background_gradient?: string;
  layout_type?: string;
  mode?: string;         // "grid" | "stage"
  archetype?: string;    // "split_emit" | "scatter" | ""
  elements: SceneElement[];
  entrance_transition?: { type: string; duration?: number; direction?: string };
  transition_out?: { type: string; direction?: string };
}

interface VideoDecompositionData {
  canvas_width: number;
  canvas_height: number;
  fps: number;
  total_frames: number;
  scenes: VideoSceneData[];
  global_color_palette?: string[];
  style_profile?: StyleProfileData;
}

interface StyleProfileData {
  style_family: string;
  palette: Record<string, string>;
  grade: Record<string, number | string>;
  fx: Record<string, number>;
  overlay: Record<string, boolean | string>;
  typography: Record<string, string | boolean>;
}

// ── CSS Grid 布局（参数化动态生成）────────────────────────────────────────

function genGridConfig(n: number): { cols: string; rows: string; areas: string } {
  const cols = Math.min(4, Math.max(2, Math.round(Math.sqrt(n))));
  const rows = Math.max(2, Math.ceil(n / cols));

  // 生成 area 名称
  const names: string[][] = [];
  let idx = 0;
  for (let r = 0; r < rows; r++) {
    const row: string[] = [];
    for (let c = 0; c < cols; c++) {
      row.push(`s${idx++}`);
    }
    names.push(row);
  }
  const areas = names.map(r => `"${r.join(' ')}"`).join(' ');

  return {
    cols: `repeat(${cols}, 1fr)`,
    rows: `repeat(${rows}, 1fr)`,
    areas,
  };
}

// 预计算小尺寸的 grid 配置（避免每次渲染重算）
const GRID_CACHE: Record<string, { cols: string; rows: string; areas: string }> = {};
for (let n = 1; n <= 20; n++) {
  GRID_CACHE[`grid_${n}`] = genGridConfig(n);
}

const LAYOUTS: Record<string, { cols: string; rows: string; areas: string }> = {
  centered_hero: {
    cols: "1fr",
    rows: "16fr 68fr 16fr",
    areas: `"title" "hero" "caption"`,
  },
  centered: {
    cols: "1fr",
    rows: "16fr 68fr 16fr",
    areas: `"title" "hero" "caption"`,
  },
  split: {
    cols: "1fr 1fr",
    rows: "1fr",
    areas: `"s0 s1"`,
  },
  full_bleed: {
    cols: "1fr",
    rows: "1fr",
    areas: `"s0"`,
  },
  stack: {
    cols: "1fr",
    rows: "1fr",
    areas: `"s0"`,
  },
  radial: {
    cols: "1fr 1fr 1fr",
    rows: "1fr 1fr 1fr",
    areas: `"s0 s1 s2" "s3 s4 s5" "s6 s7 s8"`,
  },
  grid: {
    cols: "1fr 1fr 1fr",
    rows: "1fr 1fr 1fr",
    areas: `"s0 s1 s2" "s3 s4 s5" "s6 s7 s8"`,
  },
  ...GRID_CACHE,
};

// 默认槽位分配（按元素类型和顺序）
const DEFAULT_SLOTS: Record<string, string[]> = {
  centered_hero: ["hero", "hero", "caption"],
  centered: ["hero", "hero", "caption"],
  grid_2x2: ["a", "b", "c", "d"],
  split_lr: ["left", "right"],
  split: ["s0", "s1"],
  full_bleed: ["s0"],
  stack: ["s0"],
  radial: ["s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"],
  grid: ["s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"],
  three_row: ["top", "mid", "bottom"],
  hero_side: ["hero", "side1", "side2"],
};

// ── 动画内层（解耦布局和动画）──────────────────────────────────────────

const AnimatedInner: React.FC<{
  element: SceneElement;
  globalFrame: number;
  fps: number;
}> = ({ element, globalFrame, fps }) => {
  const { timing } = element;
  const entrance = timing.entrance;
  const exit = timing.exit;
  const duration = timing.out_point - timing.in_point;

  // 入场
  const entranceDuration = entrance?.duration ?? 6;
  const entranceProgress = Math.min(1, globalFrame / Math.max(entranceDuration, 1));
  const entranceStyle = getEntranceStyle(entrance, entranceProgress);

  // 出场
  const exitDuration = Math.min(exit?.duration ?? 3, 6);
  const exitStart = Math.max(0, duration - exitDuration);
  const exitProgress =
    globalFrame >= exitStart
      ? Math.min(1, (globalFrame - exitStart) / Math.max(exitDuration, 1))
      : 0;
  const exitStyle = getEntranceStyle(exit, 1 - exitProgress);

  // 持续微动
  const sustainStart = entranceDuration;
  const sustainEnd = exitStart;
  const sustainFrame = globalFrame - sustainStart;
  const isInSustain = globalFrame >= sustainStart && globalFrame < sustainEnd;
  const idleAnim = element.effect_type || "";
  const sustainStyle = isInSustain ? getSustainStyle(idleAnim, sustainFrame, fps) : {};

  const opacity =
    (Number(entranceStyle.opacity) || 1) *
    (Number(exitStyle.opacity) || 1);

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        transform: `${entranceStyle.transform || ""} ${exitStyle.transform || ""} ${sustainStyle.transform || ""}`.trim() || undefined,
        opacity,
        clipPath: entranceStyle.clipPath || exitStyle.clipPath || sustainStyle.clipPath,
        filter: entranceStyle.filter || exitStyle.filter,
      }}
    >
      {element.type === "image" && element.content_src ? (
        <Img
          src={staticFile(element.content_src.startsWith("/") ? element.content_src.slice(1) : element.content_src)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "center",
            borderRadius: 8,
          }}
        />
      ) : element.type === "text" && element.content_text ? (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: element.typography?.font_family || "sans-serif",
            fontSize: `${element.typography?.font_size || 4}vh`,
            fontWeight: element.typography?.font_weight || 400,
            color: element.typography?.color || "#fff",
            textAlign: "center",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            padding: "8%",
          }}
        >
          {element.content_text}
        </div>
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: element.appearance?.fill || "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            borderRadius: 12,
          }}
        />
      )}
    </div>
  );
};

// ── Stage 模式渲染（绝对定位，放射/散开）──────────────────────────────────

const SceneStage: React.FC<{
  scene: VideoSceneData;
  fps: number;
  sceneLocalFrame: number;
}> = ({ scene, fps, sceneLocalFrame }) => {
  const imageElements = scene.elements.filter((el) => el.type === "image" && el.content_src);

  return (
    <AbsoluteFill
      style={{
        background: scene.background_gradient || scene.background_color || "#0b1020",
      }}
    >
      {imageElements.map((el) => {
        // timing.in_point/out_point 是 scene-local（从0开始）
        const elStart = el.timing.in_point;
        const elEnd = el.timing.out_point;
        if (sceneLocalFrame < elStart || sceneLocalFrame >= elEnd) return null;
        if (elEnd - elStart <= 0) return null;

        const localFrame = sceneLocalFrame - elStart;
        const { spatial } = el;
        const rotation = spatial.rotation || 0;

        return (
          <div
            key={el.id}
            style={{
              position: "absolute",
              left: `${spatial.x}%`,
              top: `${spatial.y}%`,
              width: `${spatial.width}%`,
              height: `${spatial.height}%`,
              transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
              overflow: "hidden",
              borderRadius: 12,
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            }}
          >
            <AnimatedInner element={el} globalFrame={localFrame} fps={fps} />
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

// ── Grid 模式渲染 ────────────────────────────────────────────────────────

const SceneGrid: React.FC<{
  scene: VideoSceneData;
  fps: number;
  sceneLocalFrame: number;
}> = ({ scene, fps, sceneLocalFrame }) => {
  const layoutType = scene.layout_type || "centered_hero";
  // 只渲染有图片的元素到 Grid（过滤掉空 content_src 的占位块，文字走 TextOverlayLayer）
  const imageElements = scene.elements.filter((el) => el.type === "image" && el.content_src);
  const nImages = imageElements.length;

  // 动态查找：先查预定义，再按元素数动态生成
  // 如果预定义布局的槽位不够放所有图片，自动切换到 grid 布局
  let layout = LAYOUTS[layoutType];
  let slots = DEFAULT_SLOTS[layoutType];
  if (!layout || (slots && slots.length < nImages)) {
    // 槽位不够 → 用动态 grid
    layout = genGridConfig(Math.max(nImages, 4));
    slots = Array.from({ length: nImages }, (_, i) => `s${i}`);
  }
  if (!slots) {
    slots = Array.from({ length: nImages }, (_, i) => `s${i}`);
  }

  // 给每个图片元素分配槽位
  const elementsWithSlots = imageElements.map((el, i) => ({
    ...el,
    _slot: (el as any).slot || slots[i % slots.length] || "stage",
  }));

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        display: "grid",
        gridTemplateColumns: layout.cols,
        gridTemplateRows: layout.rows,
        gridTemplateAreas: layout.areas,
        gap: "8px",
        padding: "4%",
        background: scene.background_gradient || scene.background_color || "#0b1020",
        boxSizing: "border-box",
      }}
    >
      {elementsWithSlots.map((el) => {
        const elStart = el.timing.in_point;
        const elEnd = el.timing.out_point;
        const elDuration = elEnd - elStart;

        if (sceneLocalFrame < elStart || sceneLocalFrame >= elEnd) return null;
        if (elDuration <= 0) return null;

        const localFrame = sceneLocalFrame - elStart;

        return (
          <div
            key={el.id}
            style={{
              gridArea: el._slot,
              position: "relative",
              overflow: "hidden",
              borderRadius: 8,
              minWidth: 0,
              minHeight: 0,
            }}
          >
            <AnimatedInner element={el} globalFrame={localFrame} fps={fps} />
          </div>
        );
      })}
    </div>
  );
};

// ── 文字元素 → FocusTextSpec 转换 ────────────────────────────────────────

/** 默认文字动画技法选择（Python 未指定时的 fallback） */
function pickTextEntrance(el: SceneElement): TextEntranceType {
  const text = el.content_text || "";
  const len = text.length;
  const words = text.split(/\s+/).length;

  // 短词（≤4字）→ char_pop
  if (len <= 4) return "char_pop";
  // 一行话 → word_stagger
  if (words <= 6) return "word_stagger";
  // 多行 → mask_reveal
  if (text.includes("\n") || words > 8) return "mask_reveal";
  // fallback
  return "word_stagger";
}

/** 将场景文字元素转为 FocusTextSpec 列表 */
function textElementsToFocusSpecs(
  elements: SceneElement[],
  canvasHeight?: number
): FocusTextSpec[] {
  const textEls = elements.filter((el) => el.type === "text" && el.content_text);

  return textEls.map((el, i) => {
    const ta = (el as any).text_animation || {};
    const entrance: TextEntranceType = ta.entrance || pickTextEntrance(el);

    return {
      id: el.id,
      text: el.content_text!,
      entrance,
      exit: (ta.exit as any) || "fade_up",
      split_mode: ta.split_mode || (entrance === "char_pop" ? "char" : "word"),
      direction: ta.direction || "center",
      zone: ta.zone || (i === 0 ? "focus" : "focus"),
      style: {
        fontSize: el.typography?.font_size
          ? el.typography.font_size * (canvasHeight || 1080) / 60 // vh → px，按画布高度缩放
          : undefined,
        fontWeight: el.typography?.font_weight || undefined,
        color: el.typography?.color || undefined,
        fontFamily: el.typography?.font_family || undefined,
        gradient: el.typography?.gradient || undefined,
        textTransform: el.typography?.text_transform || undefined,
        letterSpacing: el.typography?.letter_spacing || undefined,
      },
    };
  });
}

// ── 多场景合成 ───────────────────────────────────────────────────────────

export const MultiSceneVideo: React.FC<{ decomposition: VideoDecompositionData }> = ({
  decomposition,
}) => {
  const frame = useCurrentFrame();
  const { scenes, fps } = decomposition;

  if (!scenes || scenes.length === 0) {
    return <AbsoluteFill style={{ background: "#000" }} />;
  }

  // 找到当前帧属于哪个场景
  let currentSceneIdx = 0;
  let sceneLocalFrame = 0;

  for (let i = 0; i < scenes.length; i++) {
    const scene = scenes[i];
    if (frame >= scene.start_frame && frame < scene.end_frame) {
      currentSceneIdx = i;
      sceneLocalFrame = frame - scene.start_frame;
      break;
    }
  }

  const currentScene = scenes[currentSceneIdx];
  if (!currentScene) {
    return <AbsoluteFill style={{ background: "#000" }} />;
  }

  // 转场 fade
  const TRANSITION_FRAMES = 15;
  const sceneDur = currentScene.duration_frames;
  let opacity = 1;

  if (sceneLocalFrame < TRANSITION_FRAMES) {
    opacity = sceneLocalFrame / TRANSITION_FRAMES;
  }
  if (sceneLocalFrame > sceneDur - TRANSITION_FRAMES) {
    opacity = (sceneDur - sceneLocalFrame) / TRANSITION_FRAMES;
  }
  if (currentScene.transition_out?.type === "cut") {
    opacity = 1;
  }

  // 文字 → 焦点规格（图片数 > 0 时需要 scrim）
  const hasImages = currentScene.elements.some((el) => el.type === "image" && el.content_src);
  const focusTexts = textElementsToFocusSpecs(
    currentScene.elements,
    decomposition.canvas_height
  );

  // 根据模式选择渲染器
  // 风格迁移优先用 Stage（绝对定位保留原视频布局），Grid 只在明确 grid 模式时用
  const isStage = currentScene.mode === "stage" || currentScene.mode !== "grid";

  // ── 风格层：从 StyleProfile 读取 ──
  const sp = decomposition.style_profile;
  const cssFilter = sp?.grade
    ? [
        sp.grade.brightness && sp.grade.brightness !== 1 ? `brightness(${sp.grade.brightness})` : "",
        sp.grade.contrast && sp.grade.contrast !== 1 ? `contrast(${sp.grade.contrast})` : "",
        sp.grade.saturate && sp.grade.saturate !== 1 ? `saturate(${sp.grade.saturate})` : "",
        sp.grade.hue_rotate && sp.grade.hue_rotate !== 0 ? `hue-rotate(${sp.grade.hue_rotate}deg)` : "",
      ]
        .filter(Boolean)
        .join(" ")
    : "";

  const bgColor = sp?.palette?.bg_color || currentScene.background_color || "#0b1020";
  const bgGradient = sp?.palette?.bg_gradient || currentScene.background_gradient || "";

  return (
    <AbsoluteFill
      style={{
        opacity,
        background: bgGradient || bgColor,
      }}
    >
      {/* z:0 — 内容层（Grid/Stage 图片）+ 调色 CSS filter */}
      <AbsoluteFill style={{ filter: cssFilter || undefined }}>
        {isStage ? (
          <SceneStage scene={currentScene} fps={fps} sceneLocalFrame={sceneLocalFrame} />
        ) : (
          <SceneGrid scene={currentScene} fps={fps} sceneLocalFrame={sceneLocalFrame} />
        )}
      </AbsoluteFill>

      {/* z:5 — FX 层（按 StyleProfile.fx 开关） */}
      {sp?.fx?.vignette && sp.fx.vignette > 0 ? (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
          <Vignette intensity={sp.fx.vignette} />
        </AbsoluteFill>
      ) : null}
      {sp?.fx?.film_grain && sp.fx.film_grain > 0 ? (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
          <FilmGrain opacity={sp.fx.film_grain} />
        </AbsoluteFill>
      ) : null}
      {sp?.fx?.light_leak && sp.fx.light_leak > 0 ? (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
          <LightLeak intensity={sp.fx.light_leak} />
        </AbsoluteFill>
      ) : null}
      {sp?.fx?.gradient_mesh && sp.fx.gradient_mesh > 0 ? (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
          <GradientMesh
            colors={[sp.palette?.accent || "#3B82F6", sp.palette?.accent2 || "#8B5CF6"]}
            speed={0.3}
          />
        </AbsoluteFill>
      ) : null}

      {/* z:10 — 文字层：浮在图片之上，顺序焦点 */}
      <TextOverlayLayer
        texts={focusTexts}
        sceneStartFrame={currentScene.start_frame}
        sceneDurationFrames={sceneDur}
        globalFrame={frame}
        fps={fps}
        hasImageBackground={hasImages}
        scrimIntensity={0.35}
      />
    </AbsoluteFill>
  );
};
