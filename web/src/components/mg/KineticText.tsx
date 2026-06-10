import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from 'remotion';
import { noise2D } from '@remotion/noise';
import { FONT_SIZES, FONTS } from '../../design-tokens';
import { SPRING, pulse, noiseOffset } from '../../design-tokens/motion';

/**
 * 动感文字动画组件 v2 — 专业级动效
 *
 * 升级点:
 * - 每个字交错入场，每属性独立 spring (opacity/scale/translateY/rotate)
 * - 噪声驱动的有机抖动 (替代 Math.sin)
 * - 二次运动: 阴影、描边、颜色微移
 * - 入场后呼吸脉冲保持视觉活力
 */

type AnimationMode = 'bounce' | 'slide' | 'typewriter' | 'shake' | 'glitch' | 'draw';

interface KineticTextProps {
  text: string;
  mode?: AnimationMode;
  fontSize?: number;
  color?: string;
  strokeColor?: string;
  strokeWidth?: number;
  fontFamily?: string;
  delay?: number;
}

export const KineticText: React.FC<KineticTextProps> = ({
  text,
  mode = 'bounce',
  fontSize = FONT_SIZES.headline,
  color = '#FFFFFF',
  strokeColor = '#000000',
  strokeWidth = 4,
  fontFamily = FONTS.display,
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const adjustedFrame = Math.max(0, frame - delay);

  switch (mode) {
    case 'bounce':
      return <BounceText {...{ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame: adjustedFrame, fps }} />;
    case 'slide':
      return <SlideText {...{ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame: adjustedFrame, fps }} />;
    case 'typewriter':
      return <TypewriterText {...{ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame: adjustedFrame, fps }} />;
    case 'shake':
      return <ShakeText {...{ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame: adjustedFrame, fps }} />;
    case 'glitch':
      return <GlitchText {...{ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame: adjustedFrame, fps }} />;
    default:
      return <BounceText {...{ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame: adjustedFrame, fps }} />;
  }
};

// ═══════════════════════════════════════════════════════
// Bounce — 每字交错弹入 + 二次运动
// ═══════════════════════════════════════════════════════

const BounceText: React.FC<any> = ({ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame, fps }) => {
  const chars = text.split('');
  const STAGGER_FRAMES = 2;

  return (
    <AbsoluteFill style={{
      justifyContent: 'center',
      alignItems: 'center',
      flexDirection: 'row',
      flexWrap: 'wrap',
      padding: 40,
    }}>
      {chars.map((char: string, i: number) => {
        const charDelay = i * STAGGER_FRAMES;
        const f = Math.max(0, frame - charDelay);

        // 主入场 — snappy spring
        const mainSpring = spring({ frame: f, fps, config: SPRING.snappy });

        // 每个属性用不同 spring 配置 (交错 2 帧)
        const opacity = spring({ frame: f, fps, config: { ...SPRING.snappy, damping: 20 } });
        const scale = spring({ frame: f - 1, fps, config: SPRING.snappy });
        const translateY = spring({ frame: f - 2, fps, config: { ...SPRING.snappy, stiffness: 160 } });
        const rotate = spring({ frame: f - 3, fps, config: { ...SPRING.snappy, damping: 8 } });

        // 入场后的呼吸微动 (第 20 帧后开始)
        const breathe = f > 20 ? Math.sin((f - 20) * 0.08 + i * 0.5) * 1.5 : 0;
        const breatheScale = f > 20 ? 1 + Math.sin((f - 20) * 0.06 + i * 0.3) * 0.015 : 1;

        // 阴影深度跟随 scale
        const shadowBlur = interpolate(scale, [0, 1], [0, 20]);
        const shadowY = interpolate(scale, [0, 1], [0, 8]);

        return (
          <span
            key={i}
            style={{
              fontSize,
              color,
              fontFamily,
              WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
              display: 'inline-block',
              opacity: interpolate(opacity, [0, 1], [0, 1]),
              transform: `
                scale(${interpolate(scale, [0, 1], [0.3, 1]) * breatheScale})
                translateY(${interpolate(translateY, [0, 1], [80, 0]) + breathe}px)
                rotate(${interpolate(rotate, [0, 1], [-15, 0])}deg)
              `,
              filter: `drop-shadow(0 ${shadowY}px ${shadowBlur}px rgba(0,0,0,0.4))`,
              marginRight: char === ' ' ? fontSize * 0.3 : 0,
              willChange: 'transform, opacity',
            }}
          >
            {char}
          </span>
        );
      })}
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Slide — 带 motion trail 的滑入
// ═══════════════════════════════════════════════════════

const SlideText: React.FC<any> = ({ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame, fps }) => {
  const progress = spring({ frame, fps, config: SPRING.heavy });
  const translateX = interpolate(progress, [0, 1], [-900, 0]);
  const opacity = interpolate(progress, [0, 0.2], [0, 1], { extrapolateRight: 'clamp' });

  // Motion trail 残影
  const trail1Opacity = interpolate(progress, [0.1, 0.5], [0, 0.3], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const trail2Opacity = interpolate(progress, [0.2, 0.6], [0, 0.15], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      {/* 残影层 2 */}
      <div style={{
        position: 'absolute',
        fontSize, color, fontFamily,
        WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
        transform: `translateX(${translateX + 30}px)`,
        opacity: trail2Opacity,
        filter: 'blur(4px)',
        textAlign: 'center',
        padding: '0 40px',
      }}>
        {text}
      </div>
      {/* 残影层 1 */}
      <div style={{
        position: 'absolute',
        fontSize, color, fontFamily,
        WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
        transform: `translateX(${translateX + 15}px)`,
        opacity: trail1Opacity,
        filter: 'blur(2px)',
        textAlign: 'center',
        padding: '0 40px',
      }}>
        {text}
      </div>
      {/* 主文字 */}
      <div style={{
        fontSize, color, fontFamily,
        WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
        transform: `translateX(${translateX}px)`,
        opacity,
        textAlign: 'center',
        padding: '0 40px',
      }}>
        {text}
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Typewriter — 逐字显示 + 光标闪烁 + 打字音效感
// ═══════════════════════════════════════════════════════

const TypewriterText: React.FC<any> = ({ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame }) => {
  const charsToShow = Math.min(Math.floor(frame / 2), text.length);
  const showCursor = frame % 16 < 10;

  // 每个已显示字符的微弹跳
  const lastCharSpring = spring({
    frame: Math.max(0, frame - charsToShow * 2),
    fps: 30,
    config: SPRING.snappy,
  });

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      <div style={{
        fontSize, color, fontFamily,
        WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
        textAlign: 'center',
      }}>
        {text.slice(0, charsToShow)}
        {charsToShow < text.length && showCursor && (
          <span style={{
            display: 'inline-block',
            borderRight: `${strokeWidth}px solid ${color}`,
            marginLeft: 2,
            transform: `scaleY(${interpolate(lastCharSpring, [0, 1], [0.5, 1])})`,
          }}>
            &nbsp;
          </span>
        )}
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Shake — 噪声驱动的有机抖动 (替代 Math.sin)
// ═══════════════════════════════════════════════════════

const ShakeText: React.FC<any> = ({ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame, fps }) => {
  // 入场
  const entrySpring = spring({ frame, fps, config: SPRING.bouncy });
  const entryScale = interpolate(entrySpring, [0, 1], [0.2, 1]);
  const entryY = interpolate(entrySpring, [0, 1], [60, 0]);

  // 噪声抖动 (入场完成后)
  const shake = frame > 15 ? noiseOffset(42, frame, 0.08, 5) : { x: 0, y: 0 };
  const rotNoise = frame > 15 ? noise2D(99, frame * 0.06, 0) * 3 : 0;

  // 脉冲呼吸
  const breathScale = frame > 15 ? pulse(frame, 0.12, 0.04) : 1;

  // 阴影脉冲
  const shadowPulse = frame > 15 ? 15 + Math.sin(frame * 0.1) * 8 : 15;

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      <div style={{
        fontSize,
        color,
        fontFamily,
        WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
        transform: `
          scale(${entryScale * breathScale})
          translate(${shake.x}px, ${entryY + shake.y}px)
          rotate(${rotNoise}deg)
        `,
        filter: `drop-shadow(0 4px ${shadowPulse}px rgba(255,65,108,0.5))`,
        textAlign: 'center',
      }}>
        {text}
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Glitch — RGB 色差 + clip-path 切割
// ═══════════════════════════════════════════════════════

const GlitchText: React.FC<any> = ({ text, fontSize, color, strokeColor, strokeWidth, fontFamily, frame, fps }) => {
  // 入场
  const entry = spring({ frame, fps, config: SPRING.snappy });
  const baseOpacity = interpolate(entry, [0, 1], [0, 1]);

  // Glitch 强度 — 周期性爆发
  const glitchCycle = frame % 40;
  const isGlitching = glitchCycle < 8;
  const intensity = isGlitching ? Math.sin(glitchCycle * 0.4) * 1 : 0;

  // RGB 偏移
  const rX = Math.sin(frame * 3.7) * intensity * 8;
  const gX = Math.cos(frame * 2.3) * intensity * 6;
  const bY = Math.sin(frame * 4.1) * intensity * 5;

  // clip-path 切割
  const clipTop = isGlitching ? Math.random() * 20 : 0;
  const clipBot = isGlitching ? 100 - Math.random() * 20 : 100;

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      {/* Red channel */}
      <div style={{
        position: 'absolute',
        fontSize, fontFamily,
        color: 'rgba(255,0,0,0.8)',
        WebkitTextStroke: `${strokeWidth}px rgba(255,0,0,0.5)`,
        transform: `translate(${rX}px, 0)`,
        opacity: baseOpacity,
        clipPath: `inset(${clipTop}% 0 ${100 - clipBot}% 0)`,
        mixBlendMode: 'screen',
      }}>
        {text}
      </div>
      {/* Green channel */}
      <div style={{
        position: 'absolute',
        fontSize, fontFamily,
        color: 'rgba(0,255,0,0.8)',
        WebkitTextStroke: `${strokeWidth}px rgba(0,255,0,0.5)`,
        transform: `translate(${gX}px, 0)`,
        opacity: baseOpacity,
        clipPath: `inset(${clipTop + 5}% 0 ${100 - clipBot + 5}% 0)`,
        mixBlendMode: 'screen',
      }}>
        {text}
      </div>
      {/* Main text */}
      <div style={{
        position: 'relative',
        fontSize, color, fontFamily,
        WebkitTextStroke: `${strokeWidth}px ${strokeColor}`,
        transform: `translateY(${isGlitching ? bY : 0}px)`,
        opacity: baseOpacity,
      }}>
        {text}
      </div>
    </AbsoluteFill>
  );
};
