import React from 'react';
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  interpolateColors,
  Img,
  staticFile,
} from 'remotion';
import { noise2D } from '@remotion/noise';
import { SPRING, EASE, staggeredEntrance, pulse, noiseOffset } from '../../design-tokens/motion';

/**
 * 产品展示动画组件 v2 — 专业级动效
 *
 * 升级点:
 * - 视差深度: 前景产品/背景/装饰层不同速度
 * - 噪声驱动的浮动产品 (替代静态居中)
 * - 交错入场: 产品→名称→价格→CTA 各有独立 spring
 * - Glassmorphism 玻璃质感卡片
 * - OKLCH 颜色渐变背景
 * - 阴影跟随产品高度动态变化
 */

interface ProductShowcaseProps {
  productImage: string;
  productName: string;
  price?: string;
  cta?: string;
  bgColor1?: string;
  bgColor2?: string;
  layout?: 'center' | 'left' | 'split';
}

function resolveImageUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith('http') || url.startsWith('/') || url.startsWith('data:')) return url;
  return staticFile(`materials/${url}`);
}

export const ProductShowcase: React.FC<ProductShowcaseProps> = ({
  productImage,
  productName,
  price,
  cta = '立即抢购',
  bgColor1 = '#FF6B6B',
  bgColor2 = '#4ECDC4',
  layout = 'center',
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // ── 背景层: 缓慢漂移的渐变 ──
  const bgDrift = noiseOffset(1, frame, 0.005, 20);
  const bgHueShift = interpolate(frame, [0, 300], [0, 30]);
  const bgRotation = interpolate(frame, [0, 600], [0, 360]);

  // ── 产品入场 (第 0 帧) ──
  const productEntrance = staggeredEntrance(frame, fps, 0, 'bouncy');
  // 产品浮动 (入场后)
  const floatY = frame > 30 ? noise2D(10, frame * 0.015, 0) * 12 : 0;
  const floatRotate = frame > 30 ? noise2D(11, frame * 0.01, 0) * 2 : 0;

  // ── 产品阴影跟随高度 ──
  const shadowBlur = interpolate(floatY, [-12, 12], [30, 15]);
  const shadowScale = interpolate(floatY, [-12, 12], [1.1, 0.9]);
  const shadowOpacity = interpolate(floatY, [-12, 12], [0.4, 0.2]);

  // ── 名称入场 (第 8 帧) ──
  const nameEntrance = staggeredEntrance(frame, fps, 8, 'snappy');

  // ── 价格入场 (第 16 帧) ──
  const priceEntrance = staggeredEntrance(frame, fps, 16, 'elastic');

  // ── CTA 入场 (第 24 帧) + 脉冲 ──
  const ctaEntrance = staggeredEntrance(frame, fps, 24, 'snappy');
  const ctaPulse = frame > 50 ? pulse(frame, 0.12, 0.05) : 1;
  const ctaGlow = frame > 50 ? 15 + Math.sin(frame * 0.1) * 8 : 15;

  return (
    <AbsoluteFill>
      {/* ═══ 背景层 (最慢) ═══ */}
      <div style={{
        position: 'absolute',
        width: '200%',
        height: '200%',
        top: '-50%',
        left: '-50%',
        background: `conic-gradient(from ${bgRotation}deg, ${bgColor1}, ${bgColor2}, ${bgColor1})`,
        filter: 'blur(80px)',
        transform: `translate(${bgDrift.x}px, ${bgDrift.y}px)`,
      }} />

      {/* 网格装饰 (中速) */}
      <div style={{
        position: 'absolute',
        inset: 0,
        backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.08) 1px, transparent 1px)',
        backgroundSize: '30px 30px',
        transform: `translate(${bgDrift.x * 0.5}px, ${bgDrift.y * 0.5}px)`,
      }} />

      {/* ═══ 产品层 (中速) ═══ */}
      <AbsoluteFill style={{
        justifyContent: layout === 'left' ? 'center' : 'center',
        alignItems: layout === 'left' ? 'flex-start' : 'center',
        paddingLeft: layout === 'left' ? 60 : 0,
      }}>
        <div style={{
          transform: `
            scale(${productEntrance.scale})
            translateY(${productEntrance.translateY + floatY}px)
            rotate(${productEntrance.rotate + floatRotate}deg)
          `,
          opacity: productEntrance.opacity,
          filter: `
            drop-shadow(0 ${10 + floatY}px ${shadowBlur}px rgba(0,0,0,${shadowOpacity}))
          `,
        }}>
          <Img src={resolveImageUrl(productImage)} style={{
            maxWidth: width * 0.6,
            maxHeight: height * 0.5,
            objectFit: 'contain',
          }} />
        </div>
      </AbsoluteFill>

      {/* ═══ 信息层 (快速) ═══ */}

      {/* 产品名称 — Glassmorphism 卡片 */}
      <div style={{
        position: 'absolute',
        bottom: height * 0.28,
        left: 40,
        right: 40,
        textAlign: 'center',
        transform: `translateY(${nameEntrance.translateY}px) scale(${nameEntrance.scale})`,
        opacity: nameEntrance.opacity,
      }}>
        <div style={{
          display: 'inline-block',
          background: 'rgba(255,255,255,0.1)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderRadius: 16,
          padding: '12px 32px',
          border: '1px solid rgba(255,255,255,0.2)',
        }}>
          <span style={{
            fontSize: 48,
            fontWeight: 900,
            color: '#FFFFFF',
            fontFamily: 'PingFang SC, Heiti SC, Arial Black, sans-serif',
            textShadow: '0 2px 10px rgba(0,0,0,0.3)',
          }}>
            {productName}
          </span>
        </div>
      </div>

      {/* 价格标签 — 弹性入场 + 光晕 */}
      {price && (
        <div style={{
          position: 'absolute',
          bottom: height * 0.18,
          left: 0,
          right: 0,
          textAlign: 'center',
          transform: `scale(${priceEntrance.scale}) translateY(${priceEntrance.translateY}px)`,
          opacity: priceEntrance.opacity,
        }}>
          <div style={{
            display: 'inline-block',
            background: 'linear-gradient(135deg, #FF416C, #FF4B2B)',
            padding: '12px 40px',
            borderRadius: 50,
            boxShadow: `0 8px 30px rgba(255,65,108,0.5), 0 0 60px rgba(255,65,108,0.2)`,
          }}>
            <span style={{
              fontSize: 56,
              fontWeight: 900,
              color: '#FFFFFF',
              fontFamily: 'Arial Black, sans-serif',
            }}>
              {price}
            </span>
          </div>
        </div>
      )}

      {/* CTA 按钮 — 脉冲 + 光晕 */}
      <div style={{
        position: 'absolute',
        bottom: height * 0.08,
        left: 0,
        right: 0,
        textAlign: 'center',
        transform: `scale(${ctaEntrance.scale * ctaPulse}) translateY(${ctaEntrance.translateY}px)`,
        opacity: ctaEntrance.opacity,
      }}>
        <div style={{
          display: 'inline-block',
          background: '#FFD700',
          padding: '16px 60px',
          borderRadius: 50,
          boxShadow: `0 6px 25px rgba(255,215,0,0.5), 0 0 ${ctaGlow}px rgba(255,215,0,0.3)`,
        }}>
          <span style={{
            fontSize: 36,
            fontWeight: 900,
            color: '#000000',
            fontFamily: 'PingFang SC, Heiti SC, sans-serif',
          }}>
            {cta}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
