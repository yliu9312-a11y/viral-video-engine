import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from 'remotion';

/**
 * 倒计时动画 — 爆款短视频开头常用
 *
 * 3-2-1-GO 倒计时 + 数字缩放 + 背景闪烁
 * 可用于视频开头 hook
 */

interface CountdownTimerProps {
  from?: number;          // 起始数字(默认 3)
  durationPerNumber?: number;  // 每个数字持续帧数(默认 20)
  color?: string;
  bgColor?: string;
  goText?: string;        // 倒计时结束后显示的文字
}

export const CountdownTimer: React.FC<CountdownTimerProps> = ({
  from = 3,
  durationPerNumber = 20,
  color = '#FF416C',
  bgColor = '#0A0A0A',
  goText = 'GO!',
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const totalFrames = from * durationPerNumber;
  const isGo = frame >= totalFrames;
  const currentNumber = isGo ? goText : String(from - Math.floor(frame / durationPerNumber));

  // 数字动画
  const localFrame = frame % durationPerNumber;
  const numberProgress = spring({ frame: localFrame, fps, config: { damping: 8, stiffness: 200, mass: 0.5 } });
  const scale = interpolate(numberProgress, [0, 0.3, 1], [3, 0.9, 1]);
  const opacity = interpolate(localFrame, [0, 3], [0, 1], { extrapolateRight: 'clamp' });

  // 背景闪烁
  const flashOpacity = localFrame < 5 ? interpolate(localFrame, [0, 5], [0.8, 0]) : 0;

  // 圆环进度
  const progress = frame / totalFrames;
  const circumference = 2 * Math.PI * 120;

  return (
    <AbsoluteFill style={{ backgroundColor: bgColor }}>
      {/* 背景闪光 */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundColor: color,
        opacity: flashOpacity,
      }} />

      {/* 背景辐射线 */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: `repeating-conic-gradient(from ${frame * 2}deg, transparent 0deg, transparent 8deg, rgba(255,255,255,0.03) 8deg, rgba(255,255,255,0.03) 10deg)`,
      }} />

      {/* 圆环进度 */}
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <svg width={280} height={280} style={{ position: 'absolute', transform: 'rotate(-90deg)' }}>
          <circle
            cx={140} cy={140} r={120}
            fill="none"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth={6}
          />
          <circle
            cx={140} cy={140} r={120}
            fill="none"
            stroke={color}
            strokeWidth={6}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - Math.min(progress * from, 1))}
          />
        </svg>

        {/* 数字 */}
        <div style={{
          fontSize: isGo ? 120 : 200,
          fontWeight: 900,
          color: isGo ? '#FFD700' : color,
          fontFamily: 'Arial Black, PingFang SC, sans-serif',
          transform: `scale(${scale})`,
          opacity,
          textShadow: `0 0 40px ${color}80, 0 0 80px ${color}40`,
          letterSpacing: isGo ? 10 : 0,
        }}>
          {currentNumber}
        </div>
      </AbsoluteFill>

      {/* 底部装饰线 */}
      <div style={{
        position: 'absolute',
        bottom: 100,
        left: '50%',
        transform: 'translateX(-50%)',
        width: interpolate(frame, [0, totalFrames], [0, width * 0.6], { extrapolateRight: 'clamp' }),
        height: 4,
        background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
        borderRadius: 2,
      }} />
    </AbsoluteFill>
  );
};

/**
 * 简单转场效果组件
 *
 * 提供 4 种转场:fade, wipe, zoom, glitch
 */

type TransitionType = 'fade' | 'wipe' | 'zoom' | 'glitch';

interface TransitionProps {
  type?: TransitionType;
  duration?: number;  // 帧数
  color?: string;
  direction?: 'left' | 'right' | 'up' | 'down';
}

export const Transition: React.FC<TransitionProps> = ({
  type = 'fade',
  duration = 15,
  color = '#000000',
  direction = 'left',
}) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [0, duration], [0, 1], { extrapolateRight: 'clamp' });

  if (type === 'fade') {
    const opacity = frame < duration / 2
      ? interpolate(frame, [0, duration / 2], [0, 1])
      : interpolate(frame, [duration / 2, duration], [1, 0]);
    return <AbsoluteFill style={{ backgroundColor: color, opacity }} />;
  }

  if (type === 'wipe') {
    const clipAmount = interpolate(progress, [0, 1], [0, 100]);
    const clipPath = direction === 'right'
      ? `inset(0 ${100 - clipAmount}% 0 0)`
      : direction === 'left'
      ? `inset(0 0 0 ${100 - clipAmount}%)`
      : direction === 'down'
      ? `inset(0 0 ${100 - clipAmount}% 0)`
      : `inset(${100 - clipAmount}% 0 0 0)`;
    return <AbsoluteFill style={{ backgroundColor: color, clipPath }} />;
  }

  if (type === 'zoom') {
    const scale = interpolate(progress, [0, 0.5, 1], [1, 15, 1]);
    const opacity = progress < 0.5
      ? interpolate(progress, [0, 0.5], [0, 1])
      : interpolate(progress, [0.5, 1], [1, 0]);
    return (
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div style={{
          width: 100,
          height: 100,
          borderRadius: '50%',
          backgroundColor: color,
          transform: `scale(${scale})`,
          opacity,
        }} />
      </AbsoluteFill>
    );
  }

  // glitch
  const glitchX = Math.sin(frame * 3) * 20;
  const glitchOpacity = interpolate(progress, [0, 0.3, 0.7, 1], [0, 1, 1, 0]);
  return (
    <AbsoluteFill style={{ backgroundColor: color, opacity: glitchOpacity }}>
      <div style={{
        position: 'absolute',
        top: '30%',
        left: 0,
        right: 0,
        height: 40,
        backgroundColor: '#FF000080',
        transform: `translateX(${glitchX}px)`,
      }} />
      <div style={{
        position: 'absolute',
        top: '60%',
        left: 0,
        right: 0,
        height: 20,
        backgroundColor: '#00FF0080',
        transform: `translateX(${-glitchX}px)`,
      }} />
    </AbsoluteFill>
  );
};
