/**
 * TextOverlayLayer — 顺序焦点文字覆盖层
 *
 * 核心原则（Staging）：人眼无法同时处理多个竞争焦点，
 * 同一时刻焦点区只揭示一个文字。
 *
 * 架构：文字浮在 CSS Grid 之上（z-index:10），独立定位，
 * 与图片层正交（Grid 不放焦点文字，文字层不放图片）。
 */
import React from "react";
import {
  AbsoluteFill,
  spring,
  interpolate,
} from "remotion";
import { SPRING, STAGGER } from "../../design-tokens/motion";
import {
  FONT_SIZES,
  FONT_WEIGHTS,
  FONTS,
  SPACING,
  SAFE_ZONE,
} from "../../design-tokens";

// ── Types ────────────────────────────────────────────────────────────────

export interface FocusTextSpec {
  id: string;
  text: string;
  /** 动画技法名 */
  entrance: TextEntranceType;
  exit?: TextExitType;
  /** 逐字/逐词/逐行 */
  split_mode?: "char" | "word" | "line";
  /** 方向：引导视线 */
  direction?: "left" | "right" | "center" | "top" | "bottom";
  /** 入场区：焦点区（中心/三分点）还是常驻区（角落） */
  zone?: "focus" | "corner";
  /** 样式覆写 */
  style?: Partial<{
    fontSize: number;
    fontWeight: number;
    color: string;
    fontFamily: string;
    gradient: string;
    textTransform: string;
    letterSpacing: number;
    strokeColor: string;
    strokeWidth: number;
  }>;
}

export type TextEntranceType =
  | "word_stagger"
  | "char_pop"
  | "mask_reveal"
  | "blur_in"
  | "typewriter"
  | "line_split"
  | "scroll_list_pointer"
  | "none";

export type TextExitType =
  | "fade_up"
  | "mask_out"
  | "scale_down"
  | "none";

export interface ScheduleEntry {
  spec: FocusTextSpec;
  /** 绝对起始帧 */
  startFrame: number;
  /** 绝对结束帧 */
  endFrame: number;
}

// ── 顺序焦点排程 ────────────────────────────────────────────────────────

/**
 * 焦点文字串行排程：一个退场后下一个才进场（允许极短交叠）。
 * 按 Staging 原则：一次只给一个焦点。
 */
export function scheduleFocusTexts(
  specs: FocusTextSpec[],
  sceneStartFrame: number,
  sceneDurationFrames: number,
  fps: number,
  holdSec = 1.4,
  gapSec = 0.15
): ScheduleEntry[] {
  const entries: ScheduleEntry[] = [];
  const holdFrames = Math.round(holdSec * fps);
  const gapFrames = Math.round(gapSec * fps);

  // 分离焦点区和常驻区
  const focusSpecs = specs.filter((s) => (s.zone || "focus") === "focus");
  const cornerSpecs = specs.filter((s) => s.zone === "corner");

  // 焦点区：串行排程
  let cursor = sceneStartFrame;
  for (const spec of focusSpecs) {
    const start = cursor;
    const end = Math.min(start + holdFrames, sceneStartFrame + sceneDurationFrames);
    if (start >= sceneStartFrame + sceneDurationFrames) break;
    entries.push({ spec, startFrame: start, endFrame: end });
    cursor = end - gapFrames; // 下一个略微提前接上（crossfade）
  }

  // 常驻区：整场景持续
  for (const spec of cornerSpecs) {
    entries.push({
      spec,
      startFrame: sceneStartFrame,
      endFrame: sceneStartFrame + sceneDurationFrames,
    });
  }

  return entries;
}

// ── 文字分割工具 ─────────────────────────────────────────────────────────

function splitText(text: string, mode: "char" | "word" | "line"): string[] {
  switch (mode) {
    case "char":
      return text.split("");
    case "word":
      return text.split(/\s+/);
    case "line":
      return text.split(/\n/);
    default:
      return text.split(/\s+/);
  }
}

// ── 入场动画实现 ────────────────────────────────────────────────────────

/** word_stagger：逐词淡入上移，错峰 ease-out */
const WordStaggerEntrance: React.FC<{
  text: string;
  frame: number;
  fps: number;
  direction?: string;
  fontSize: number;
  color: string;
  fontFamily: string;
  fontWeight: number;
  gradient?: string;
  letterSpacing?: number;
  textTransform?: string;
}> = ({ text, frame, fps, direction, fontSize, color, fontFamily, fontWeight, gradient, letterSpacing, textTransform }) => {
  const words = splitText(text, "word");
  const perWord = STAGGER.char; // 错峰帧数

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        gap: `0 ${fontSize * 0.3}px`,
        lineHeight: 1.3,
      }}
    >
      {words.map((word, i) => {
        const delay = i * perWord;
        const f = Math.max(0, frame - delay);
        const s = spring({ frame: f, fps, config: SPRING.snappy });

        const translateY = direction === "top"
          ? interpolate(s, [0, 1], [-60, 0])
          : interpolate(s, [0, 1], [60, 0]);

        const wordStyle: React.CSSProperties = {
          display: "inline-block",
          fontSize,
          fontWeight,
          fontFamily,
          opacity: s,
          transform: `translateY(${translateY}px)`,
          letterSpacing: letterSpacing ? `${letterSpacing}px` : undefined,
          textTransform: textTransform as any,
          lineHeight: 1.3,
          ...(gradient
            ? {
                backgroundImage: gradient,
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundSize: "200% 100%",
              }
            : { color }),
        };

        return (
          <span key={i} style={wordStyle}>
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** char_pop：逐字 scale 0→1 + 弹跳 overshoot */
const CharPopEntrance: React.FC<{
  text: string;
  frame: number;
  fps: number;
  fontSize: number;
  color: string;
  fontFamily: string;
  fontWeight: number;
  strokeColor?: string;
  strokeWidth?: number;
}> = ({ text, frame, fps, fontSize, color, fontFamily, fontWeight, strokeColor, strokeWidth }) => {
  const chars = splitText(text, "char");

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        lineHeight: 1.3,
      }}
    >
      {chars.map((char, i) => {
        const delay = i * STAGGER.char;
        const f = Math.max(0, frame - delay);

        const s = spring({ frame: f, fps, config: { damping: 8, stiffness: 180, mass: 0.8 } });
        const opacity = interpolate(s, [0, 1], [0, 1]);
        const scale = interpolate(s, [0, 1], [0.2, 1]);
        const translateY = interpolate(s, [0, 1], [40, 0]);

        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              fontSize,
              fontWeight,
              fontFamily,
              color,
              opacity,
              transform: `scale(${scale}) translateY(${translateY}px)`,
              ...(strokeColor && strokeWidth
                ? { WebkitTextStroke: `${strokeWidth}px ${strokeColor}` }
                : {}),
              marginRight: char === " " ? fontSize * 0.3 : 0,
              willChange: "transform, opacity",
            }}
          >
            {char === " " ? " " : char}
          </span>
        );
      })}
    </div>
  );
};

/** mask_reveal：overflow:hidden 包裹 + translateY 刷出（电影感标题） */
const MaskRevealEntrance: React.FC<{
  text: string;
  frame: number;
  fps: number;
  direction?: string;
  fontSize: number;
  color: string;
  fontFamily: string;
  fontWeight: number;
  gradient?: string;
}> = ({ text, frame, fps, direction, fontSize, color, fontFamily, fontWeight, gradient }) => {
  const lines = splitText(text, "line");

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      {lines.map((line, i) => {
        const delay = i * STAGGER.element;
        const f = Math.max(0, frame - delay);
        const s = spring({ frame: f, fps, config: SPRING.snappy });

        const isUp = direction === "bottom" || direction === "center";
        const translateY = isUp
          ? interpolate(s, [0, 1], [110, 0])
          : interpolate(s, [0, 1], [-110, 0]);

        return (
          <div
            key={i}
            style={{
              overflow: "hidden",
              display: "inline-block",
              lineHeight: 1.2,
            }}
          >
            <div
              style={{
                display: "inline-block",
                fontSize,
                fontWeight,
                fontFamily,
                transform: `translateY(${translateY}%)`,
                lineHeight: 1.2,
                ...(gradient
                  ? {
                      backgroundImage: gradient,
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                    }
                  : { color }),
              }}
            >
              {line}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** blur_in：模糊→清晰 + 上移 */
const BlurInEntrance: React.FC<{
  text: string;
  frame: number;
  fps: number;
  fontSize: number;
  color: string;
  fontFamily: string;
  fontWeight: number;
}> = ({ text, frame, fps, fontSize, color, fontFamily, fontWeight }) => {
  const s = spring({ frame, fps, config: SPRING.gentle });
  const blur = interpolate(s, [0, 1], [20, 0]);
  const translateY = interpolate(s, [0, 1], [30, 0]);

  return (
    <div
      style={{
        fontSize,
        fontWeight,
        fontFamily,
        color,
        filter: `blur(${blur}px)`,
        transform: `translateY(${translateY}px)`,
        opacity: s,
        textAlign: "center",
        lineHeight: 1.3,
      }}
    >
      {text}
    </div>
  );
};

/** typewriter：逐字出现（搜索框/代码感） */
const TypewriterEntrance: React.FC<{
  text: string;
  frame: number;
  fontSize: number;
  color: string;
  fontFamily: string;
  fontWeight: number;
}> = ({ text, frame, fontSize, color, fontFamily, fontWeight }) => {
  const charsToShow = Math.min(Math.floor(frame / 2), text.length);
  const showCursor = frame % 16 < 10;

  return (
    <div
      style={{
        fontSize,
        fontWeight,
        fontFamily,
        color,
        textAlign: "center",
        lineHeight: 1.3,
      }}
    >
      {text.slice(0, charsToShow)}
      {charsToShow < text.length && showCursor && (
        <span
          style={{
            display: "inline-block",
            borderRight: `3px solid ${color}`,
            marginLeft: 2,
          }}
        >
          &nbsp;
        </span>
      )}
    </div>
  );
};

/** line_split：两行上下分开（= 参考视频 EXPAND/YOUR REACH） */
const LineSplitEntrance: React.FC<{
  text: string;
  frame: number;
  fps: number;
  fontSize: number;
  color: string;
  fontFamily: string;
  fontWeight: number;
  gradient?: string;
}> = ({ text, frame, fps, fontSize, color, fontFamily, fontWeight, gradient }) => {
  const lines = text.split(/\n|(?<=\S)\s{2,}(?=\S)/); // 按换行或多个空格分

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0,
      }}
    >
      {lines.map((line, i) => {
        const f = Math.max(0, frame - i * STAGGER.element);
        const s = spring({ frame: f, fps, config: SPRING.snappy });
        const dir = i % 2 === 0 ? -1 : 1; // 奇偶行反向
        const translateX = interpolate(s, [0, 1], [80 * dir, 0]);

        return (
          <div
            key={i}
            style={{
              fontSize,
              fontWeight,
              fontFamily,
              lineHeight: 1.2,
              transform: `translateX(${translateX}px)`,
              opacity: s,
              ...(gradient
                ? {
                    backgroundImage: gradient,
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                  }
                : { color }),
            }}
          >
            {line}
          </div>
        );
      })}
    </div>
  );
};

// ── 出场动画 ────────────────────────────────────────────────────────────

function getExitStyle(
  exitType: TextExitType | undefined,
  progress: number
): React.CSSProperties {
  const p = progress;
  switch (exitType) {
    case "fade_up":
      return {
        opacity: 1 - p,
        transform: `translateY(${-30 * p}px)`,
      };
    case "mask_out":
      return {
        clipPath: `inset(0 0 ${interpolate(p, [0, 1], [0, 100])}% 0)`,
      };
    case "scale_down":
      return {
        opacity: 1 - p,
        transform: `scale(${interpolate(p, [0, 1], [1, 0.7])})`,
      };
    case "none":
    default:
      return {};
  }
}

// ── Scrim（可读性底衬）───────────────────────────────────────────────────

const Scrim: React.FC<{
  visible: boolean;
  intensity?: number;
}> = ({ visible, intensity = 0.4 }) => {
  if (!visible) return null;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `linear-gradient(180deg, transparent 0%, rgba(0,0,0,${intensity}) 40%, rgba(0,0,0,${intensity}) 60%, transparent 100%)`,
        pointerEvents: "none",
        zIndex: -1,
      }}
    />
  );
};

// ── 单个焦点文字 ─────────────────────────────────────────────────────────

const FocusTextItem: React.FC<{
  spec: FocusTextSpec;
  localFrame: number;
  totalDuration: number;
  fps: number;
}> = ({ spec, localFrame, totalDuration, fps }) => {
  const entrance = spec.entrance;
  const exitType = spec.exit || "fade_up";
  const exitDuration = 6; // ~200ms, 比入场快 (Material)
  const exitStart = totalDuration - exitDuration;

  // 出场
  const exitProgress =
    localFrame >= exitStart
      ? Math.min(1, (localFrame - exitStart) / Math.max(exitDuration, 1))
      : 0;
  const exitStyle = getExitStyle(exitType, exitProgress);

  // 样式
  const fontSize = spec.style?.fontSize || FONT_SIZES.headline;
  const fontWeight = spec.style?.fontWeight || FONT_WEIGHTS.heavy;
  const color = spec.style?.color || "#FFFFFF";
  const fontFamily = spec.style?.fontFamily || FONTS.display;
  const gradient = spec.style?.gradient;
  const strokeColor = spec.style?.strokeColor || "#000000";
  const strokeWidth = spec.style?.strokeWidth || 0;
  const letterSpacing = spec.style?.letterSpacing;
  const textTransform = spec.style?.textTransform;

  // 选择入场动画
  const renderEntrance = () => {
    const commonProps = {
      text: spec.text,
      frame: localFrame,
      fps,
      fontSize,
      color,
      fontFamily,
      fontWeight,
    };

    switch (entrance) {
      case "word_stagger":
        return (
          <WordStaggerEntrance
            {...commonProps}
            direction={spec.direction}
            gradient={gradient}
            letterSpacing={letterSpacing}
            textTransform={textTransform}
          />
        );
      case "char_pop":
        return (
          <CharPopEntrance
            {...commonProps}
            strokeColor={strokeColor || undefined}
            strokeWidth={strokeWidth || undefined}
          />
        );
      case "mask_reveal":
        return (
          <MaskRevealEntrance
            {...commonProps}
            direction={spec.direction}
            gradient={gradient}
          />
        );
      case "blur_in":
        return <BlurInEntrance {...commonProps} />;
      case "typewriter":
        return <TypewriterEntrance {...commonProps} />;
      case "line_split":
        return <LineSplitEntrance {...commonProps} gradient={gradient} />;
      case "none":
        return (
          <div
            style={{
              fontSize,
              fontWeight,
              fontFamily,
              color,
              textAlign: "center",
            }}
          >
            {spec.text}
          </div>
        );
      default:
        return (
          <WordStaggerEntrance
            {...commonProps}
            direction={spec.direction}
            gradient={gradient}
          />
        );
    }
  };

  const containerStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    height: "100%",
    ...exitStyle,
  };

  return (
    <div style={containerStyle}>
      {renderEntrance()}
    </div>
  );
};

// ── ScrollListPointer（参考视频 endless tools / Text to Speech 同款）────

export interface ScrollListItem {
  text: string;
  icon?: string; // emoji 或 icon 名
}

export const ScrollListPointer: React.FC<{
  items: ScrollListItem[];
  frame: number;
  fps: number;
  speed?: number; // 像素/帧
  fontSize?: number;
  highlightColor?: string;
  dimColor?: string;
}> = ({
  items,
  frame,
  fps,
  speed = 2.5,
  fontSize = FONT_SIZES.body,
  highlightColor = "#FF416C",
  dimColor = "rgba(255,255,255,0.4)",
}) => {
  const itemHeight = fontSize * 2.2;
  const visibleCount = 5;
  const containerHeight = visibleCount * itemHeight;

  // 滚动偏移
  const scrollY = frame * speed;
  const totalHeight = items.length * itemHeight;
  const loopedY = scrollY % totalHeight;

  // 计算中心高亮索引
  const centerIdx = Math.floor((loopedY + containerHeight / 2) / itemHeight) % items.length;

  // 入场
  const entryFrame = Math.max(0, frame - 5);
  const entryS = spring({ frame: entryFrame, fps, config: SPRING.gentle });

  return (
    <div
      style={{
        width: "100%",
        height: containerHeight,
        overflow: "hidden",
        position: "relative",
        opacity: entryS,
      }}
    >
      {/* 指针三角 */}
      <div
        style={{
          position: "absolute",
          left: 8,
          top: containerHeight / 2 - fontSize * 0.5,
          width: 0,
          height: 0,
          borderTop: `${fontSize * 0.5}px solid transparent`,
          borderBottom: `${fontSize * 0.5}px solid transparent`,
          borderLeft: `${fontSize * 0.7}px solid ${highlightColor}`,
          zIndex: 2,
        }}
      />

      {/* 列表项 */}
      <div
        style={{
          transform: `translateY(${-loopedY + containerHeight / 2 - itemHeight / 2}px)`,
          transition: "none",
        }}
      >
        {/* 重复两次实现无缝循环 */}
        {[...items, ...items].map((item, i) => {
          const realIdx = i % items.length;
          const distFromCenter = Math.abs(
            loopedY - (i * itemHeight - containerHeight / 2 + itemHeight / 2)
          );
          const normalized = Math.min(1, distFromCenter / (containerHeight / 2));
          const isCenter = realIdx === centerIdx;

          return (
            <div
              key={i}
              style={{
                height: itemHeight,
                display: "flex",
                alignItems: "center",
                paddingLeft: fontSize * 2.5,
                fontSize: isCenter ? fontSize * 1.1 : fontSize * 0.85,
                fontWeight: isCenter ? FONT_WEIGHTS.bold : FONT_WEIGHTS.regular,
                color: isCenter ? "#FFFFFF" : dimColor,
                transform: `scale(${isCenter ? 1.05 : 1 - normalized * 0.1})`,
                transition: "font-size 0.1s, color 0.1s, transform 0.1s",
                whiteSpace: "nowrap",
              }}
            >
              {item.icon && (
                <span style={{ marginRight: SPACING.sm, fontSize: fontSize * 1.2 }}>
                  {item.icon}
                </span>
              )}
              {item.text}
            </div>
          );
        })}
      </div>

      {/* 顶部/底部渐变遮罩 */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: containerHeight * 0.25,
          background: "linear-gradient(180deg, rgba(0,0,0,0.8) 0%, transparent 100%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: containerHeight * 0.25,
          background: "linear-gradient(0deg, rgba(0,0,0,0.8) 0%, transparent 100%)",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};

// ── 文字覆盖层（主组件）──────────────────────────────────────────────────

export interface TextOverlayLayerProps {
  /** 焦点文字规格列表 */
  texts: FocusTextSpec[];
  /** 场景绝对起始帧 */
  sceneStartFrame: number;
  /** 场景持续帧数 */
  sceneDurationFrames: number;
  /** 当前全局帧 */
  globalFrame: number;
  fps: number;
  /** 是否需要 scrim（图片背景上的文字） */
  hasImageBackground?: boolean;
  /** scrim 强度 */
  scrimIntensity?: number;
}

export const TextOverlayLayer: React.FC<TextOverlayLayerProps> = ({
  texts,
  sceneStartFrame,
  sceneDurationFrames,
  globalFrame,
  fps,
  hasImageBackground = true,
  scrimIntensity = 0.35,
}) => {
  if (!texts || texts.length === 0) return null;

  // 排程
  const entries = scheduleFocusTexts(
    texts,
    sceneStartFrame,
    sceneDurationFrames,
    fps
  );

  // 分离焦点区和常驻区
  const focusEntries = entries.filter(
    (e) => (e.spec.zone || "focus") === "focus"
  );
  const cornerEntries = entries.filter((e) => e.spec.zone === "corner");

  // 当前可见的焦点文字（一次一个）
  const activeFocus = focusEntries.find(
    (e) => globalFrame >= e.startFrame && globalFrame < e.endFrame
  );

  return (
    <AbsoluteFill
      style={{
        zIndex: 10,
        pointerEvents: "none",
      }}
    >
      {/* 焦点区：中心 */}
      <div
        style={{
          position: "absolute",
          left: SAFE_ZONE.left,
          right: SAFE_ZONE.right,
          top: SAFE_ZONE.top + 100,
          bottom: SAFE_ZONE.bottom + 200,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/* Scrim：图片背景上需要可读性底衬 */}
        <Scrim visible={hasImageBackground && !!activeFocus} intensity={scrimIntensity} />

        {activeFocus && (
          <FocusTextItem
            key={activeFocus.spec.id}
            spec={activeFocus.spec}
            localFrame={globalFrame - activeFocus.startFrame}
            totalDuration={activeFocus.endFrame - activeFocus.startFrame}
            fps={fps}
          />
        )}
      </div>

      {/* 常驻区：角落水印/品牌（小、静、不竞争） */}
      {cornerEntries.map((entry) => {
        if (globalFrame < entry.startFrame || globalFrame >= entry.endFrame)
          return null;
        return (
          <div
            key={entry.spec.id}
            style={{
              position: "absolute",
              right: SAFE_ZONE.right,
              bottom: SAFE_ZONE.bottom,
              fontSize: FONT_SIZES.caption,
              fontWeight: FONT_WEIGHTS.medium,
              fontFamily: FONTS.primary,
              color: "rgba(255,255,255,0.5)",
              opacity: 0.7,
            }}
          >
            {entry.spec.text}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
