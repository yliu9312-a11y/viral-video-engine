import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  interpolate,
} from 'remotion';
import { noise2D } from '@remotion/noise';

/**
 * 电影级视觉效果组件集
 *
 * - LightLeak: 光晕泄漏效果
 * - GlitchTransition: RGB 色差转场
 * - GradientMesh: 动态渐变网格背景
 * - FilmGrain: 胶片颗粒纹理
 */

// ═══════════════════════════════════════════════════════
// LightLeak — 电影光晕泄漏
// ═══════════════════════════════════════════════════════

interface LightLeakProps {
  intensity?: number; // 0-1
  speed?: number;
  color1?: string;
  color2?: string;
}

export const LightLeak: React.FC<LightLeakProps> = ({
  intensity = 0.15,
  speed = 0.02,
  color1 = 'rgba(255, 150, 50, 0.3)',
  color2 = 'rgba(255, 200, 100, 0.2)',
}) => {
  const frame = useCurrentFrame();

  // 光晕位置漂移
  const x1 = interpolate(noise2D(1, frame * speed, 0), [-1, 1], [10, 90]);
  const y1 = interpolate(noise2D(2, 0, frame * speed), [-1, 1], [10, 60]);
  const x2 = interpolate(noise2D(3, frame * speed * 0.7, 0), [-1, 1], [30, 80]);
  const y2 = interpolate(noise2D(4, 0, frame * speed * 0.5), [-1, 1], [40, 80]);

  // 透明度呼吸
  const opacity1 = interpolate(noise2D(5, frame * 0.01, 0), [-1, 1], [0.05, intensity]);
  const opacity2 = interpolate(noise2D(6, frame * 0.008, 0), [-1, 1], [0.03, intensity * 0.7]);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none', mixBlendMode: 'screen' }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        background: `
          radial-gradient(ellipse 40% 50% at ${x1}% ${y1}%, ${color1}, transparent 70%),
          radial-gradient(ellipse 30% 40% at ${x2}% ${y2}%, ${color2}, transparent 60%)
        `,
        opacity: (opacity1 + opacity2) / 2,
      }} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// GlitchTransition — RGB 色差 + clip-path 切割转场
// ═══════════════════════════════════════════════════════

interface GlitchTransitionProps {
  frame: number;
  duration: number; // 帧数
  children?: React.ReactNode;
}

export const GlitchTransition: React.FC<GlitchTransitionProps> = ({
  frame,
  duration,
  children,
}) => {
  const progress = frame / duration;
  // 中间最强，两端为 0
  const intensity = Math.sin(progress * Math.PI);

  if (intensity < 0.01) return <>{children}</>;

  // RGB 偏移
  const rX = Math.sin(frame * 5.3) * intensity * 12;
  const gX = Math.cos(frame * 3.7) * intensity * 8;
  const bY = Math.sin(frame * 7.1) * intensity * 6;

  // clip-path 随机切割
  const cuts = 3;
  const clipPaths = Array.from({ length: cuts }, (_, i) => {
    const top = Math.floor(noise2D(i * 10, frame * 0.3, 0) * 15 * intensity);
    const bot = 100 - Math.floor(noise2D(i * 10 + 5, 0, frame * 0.3) * 15 * intensity);
    return `inset(${top}% 0 ${100 - bot}% 0)`;
  });

  return (
    <AbsoluteFill>
      {/* Red channel */}
      <div style={{
        position: 'absolute', inset: 0,
        transform: `translateX(${rX}px)`,
        clipPath: clipPaths[0],
        opacity: 0.8,
        mixBlendMode: 'screen',
      }}>
        <div style={{ filter: 'url("data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22><filter id=%22r%22><feColorMatrix values=%221 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0%22/></filter></svg>#r")' }}>
          {children}
        </div>
      </div>
      {/* Green channel */}
      <div style={{
        position: 'absolute', inset: 0,
        transform: `translateX(${gX}px)`,
        clipPath: clipPaths[1],
        opacity: 0.8,
        mixBlendMode: 'screen',
      }}>
        <div style={{ filter: 'url("data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22><filter id=%22g%22><feColorMatrix values=%220 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0 1 0%22/></filter></svg>#g")' }}>
          {children}
        </div>
      </div>
      {/* Blue channel */}
      <div style={{
        position: 'absolute', inset: 0,
        transform: `translateY(${bY}px)`,
        clipPath: clipPaths[2],
        opacity: 0.8,
        mixBlendMode: 'screen',
      }}>
        <div style={{ filter: 'url("data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22><filter id=%22b%22><feColorMatrix values=%220 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 0 0 1 0%22/></filter></svg>#b")' }}>
          {children}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// GradientMesh — 多点动态渐变网格
// ═══════════════════════════════════════════════════════

interface GradientMeshProps {
  colors?: string[];
  speed?: number;
  blur?: number;
}

export const GradientMesh: React.FC<GradientMeshProps> = ({
  colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c'],
  speed = 0.008,
  blur = 100,
}) => {
  const frame = useCurrentFrame();

  // 每个颜色点独立漂移
  const points = colors.map((_, i) => ({
    x: interpolate(noise2D(i * 100, frame * speed, 0), [-1, 1], [10, 90]),
    y: interpolate(noise2D(i * 100 + 50, 0, frame * speed), [-1, 1], [10, 90]),
  }));

  const gradients = colors.map((color, i) =>
    `radial-gradient(circle at ${points[i].x}% ${points[i].y}%, ${color} 0%, transparent 50%)`
  ).join(', ');

  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute',
        inset: 0,
        background: gradients,
        filter: `blur(${blur}px)`,
      }} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// FilmGrain — 胶片颗粒纹理
// ═══════════════════════════════════════════════════════

interface FilmGrainProps {
  opacity?: number;
  speed?: number;
}

export const FilmGrain: React.FC<FilmGrainProps> = ({
  opacity = 0.06,
  speed = 1,
}) => {
  const frame = useCurrentFrame();
  // 用噪声模拟颗粒
  const grainSeed = Math.floor(frame * speed);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none', mixBlendMode: 'overlay' }}>
      <div style={{
        position: 'absolute',
        inset: 0,
        opacity,
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' seed='${grainSeed}' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
        backgroundSize: '128px 128px',
      }} />
    </AbsoluteFill>
  );
};

// ═══════════════════════════════════════════════════════
// Vignette — 暗角效果
// ═══════════════════════════════════════════════════════

export const Vignette: React.FC<{ intensity?: number }> = ({ intensity = 0.6 }) => (
  <AbsoluteFill style={{ pointerEvents: 'none' }}>
    <div style={{
      position: 'absolute',
      inset: 0,
      background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${intensity}) 100%)`,
    }} />
  </AbsoluteFill>
);
