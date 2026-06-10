import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from 'remotion';

/**
 * 数据可视化动画 — 带货/营销视频常用
 *
 * 支持柱状图、环形图、数字滚动
 */

// 柱状图动画
interface BarChartProps {
  data: { label: string; value: number; color?: string }[];
  maxValue?: number;
  title?: string;
}

export const BarChart: React.FC<BarChartProps> = ({ data, maxValue, title }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();

  const max = maxValue || Math.max(...data.map((d) => d.value));

  return (
    <AbsoluteFill style={{ padding: 60, justifyContent: 'center' }}>
      {title && (
        <div style={{
          fontSize: 42,
          fontWeight: 900,
          color: '#FFFFFF',
          textAlign: 'center',
          marginBottom: 40,
          fontFamily: 'PingFang SC, sans-serif',
          opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: 'clamp' }),
        }}>
          {title}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-around', height: height * 0.5 }}>
        {data.map((item, i) => {
          const delay = i * 5;
          const progress = spring({ frame: Math.max(0, frame - delay), fps, config: { damping: 10, stiffness: 80 } });
          const barHeight = (item.value / max) * 100;
          const color = item.color || ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD'][i % 6];

          return (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 }}>
              {/* 数值 */}
              <div style={{
                fontSize: 28,
                fontWeight: 700,
                color: '#FFFFFF',
                marginBottom: 8,
                opacity: progress,
                transform: `translateY(${interpolate(progress, [0, 1], [20, 0])}px)`,
              }}>
                {Math.round(item.value * progress)}
              </div>
              {/* 柱子 */}
              <div style={{
                width: '60%',
                height: `${barHeight * progress}%`,
                background: `linear-gradient(180deg, ${color}, ${color}80)`,
                borderRadius: '8px 8px 0 0',
                boxShadow: `0 0 20px ${color}40`,
                minHeight: 4,
              }} />
              {/* 标签 */}
              <div style={{
                fontSize: 20,
                color: '#AAAAAA',
                marginTop: 12,
                textAlign: 'center',
                fontFamily: 'PingFang SC, sans-serif',
              }}>
                {item.label}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// 环形图动画
interface DonutChartProps {
  segments: { label: string; value: number; color: string }[];
  size?: number;
  thickness?: number;
  title?: string;
}

export const DonutChart: React.FC<DonutChartProps> = ({
  segments,
  size = 300,
  thickness = 40,
  title,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;

  const progress = spring({ frame, fps, config: { damping: 15, stiffness: 50 } });

  let accumulatedOffset = 0;

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center' }}>
      {title && (
        <div style={{
          position: 'absolute',
          top: 60,
          fontSize: 42,
          fontWeight: 900,
          color: '#FFFFFF',
          fontFamily: 'PingFang SC, sans-serif',
        }}>
          {title}
        </div>
      )}
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        {segments.map((seg, i) => {
          const ratio = seg.value / total;
          const dashLength = circumference * ratio * progress;
          const dashOffset = -accumulatedOffset * circumference * progress;
          accumulatedOffset += ratio;

          return (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={thickness}
              strokeDasharray={`${dashLength} ${circumference}`}
              strokeDashoffset={dashOffset}
              strokeLinecap="round"
            />
          );
        })}
      </svg>
      {/* 中心数字 */}
      <div style={{
        position: 'absolute',
        fontSize: 48,
        fontWeight: 900,
        color: '#FFFFFF',
      }}>
        {Math.round(total * progress)}
      </div>
      {/* 图例 */}
      <div style={{
        position: 'absolute',
        bottom: 80,
        display: 'flex',
        gap: 24,
      }}>
        {segments.map((seg, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 14, height: 14, borderRadius: '50%', backgroundColor: seg.color }} />
            <span style={{ color: '#CCCCCC', fontSize: 18, fontFamily: 'PingFang SC, sans-serif' }}>
              {seg.label}
            </span>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

// 数字滚动动画(如粉丝数、销售额)
interface NumberRollProps {
  value: number;
  prefix?: string;
  suffix?: string;
  fontSize?: number;
  color?: string;
  duration?: number; // 帧数
}

export const NumberRoll: React.FC<NumberRollProps> = ({
  value,
  prefix = '',
  suffix = '',
  fontSize = 80,
  color = '#FFD700',
  duration = 60,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({ frame, fps: fps * (300 / duration), config: { damping: 20, stiffness: 30 } });
  const currentValue = Math.round(value * progress);

  // 每位数字独立动画
  const digits = String(currentValue).split('');

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', flexDirection: 'row' }}>
      {prefix && (
        <span style={{ fontSize, color, fontFamily: 'Arial Black, sans-serif', marginRight: 4 }}>
          {prefix}
        </span>
      )}
      {digits.map((d, i) => {
        const digitDelay = i * 3;
        const digitProgress = spring({
          frame: Math.max(0, frame - digitDelay),
          fps,
          config: { damping: 8, stiffness: 150 },
        });
        return (
          <span
            key={i}
            style={{
              fontSize,
              fontWeight: 900,
              color,
              fontFamily: 'Arial Black, sans-serif',
              display: 'inline-block',
              transform: `translateY(${interpolate(digitProgress, [0, 1], [30, 0])}px)`,
              opacity: digitProgress,
            }}
          >
            {d}
          </span>
        );
      })}
      {suffix && (
        <span style={{ fontSize, color, fontFamily: 'Arial Black, sans-serif', marginLeft: 4 }}>
          {suffix}
        </span>
      )}
    </AbsoluteFill>
  );
};
