import React from 'react';
import { interpolate, Easing, useCurrentFrame } from 'remotion';
import {
  FONT_SIZES, FONTS, CAPTION_STYLES, EASING,
  type FontSize, type CaptionStyle,
} from '../design-tokens';
import { SafeZone } from './SafeZone';

/**
 * StandardCaption — 铁律 2/3/4/6/8 的强制执行组件。
 *
 * 所有参数都是枚举值，不可能产生丑结果。
 */

interface StandardCaptionProps {
  text: string;
  size?: FontSize;
  style?: CaptionStyle;
  position?: 'center' | 'upper_third' | 'lower_third';
  enterFrame?: number;
  exitFrame?: number;
  highlightWord?: string;
  highlightColor?: string;
}

export const StandardCaption: React.FC<StandardCaptionProps> = ({
  text,
  size = 'body',
  style = 'black_pill',
  position = 'center',
  enterFrame = 0,
  exitFrame,
  highlightWord,
  highlightColor,
}) => {
  const frame = useCurrentFrame();

  // 入场动画：0.3s ease-out-expo（铁律 8）
  const opacity = interpolate(
    frame,
    [enterFrame, enterFrame + 9, exitFrame ? exitFrame - 6 : 999999, exitFrame ?? 999999],
    [0, 1, 1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.bezier(...EASING.enter),
    }
  );

  // 入场位移：16px → 0
  const translateY = interpolate(
    frame,
    [enterFrame, enterFrame + 9],
    [16, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.bezier(...EASING.enter),
    }
  );

  const verticalAlign = {
    center: 'center',
    upper_third: 'flex-start',
    lower_third: 'flex-end',
  }[position];

  // 关键字高亮
  const renderText = () => {
    if (!highlightWord || !text.includes(highlightWord)) return text;
    const parts = text.split(highlightWord);
    return (
      <>
        {parts[0]}
        <span
          style={{
            color: highlightColor || '#FFD60A',
            background: 'rgba(0,0,0,0.8)',
            padding: '0 12px',
            borderRadius: 8,
          }}
        >
          {highlightWord}
        </span>
        {parts[1]}
      </>
    );
  };

  const captionStyle = CAPTION_STYLES[style];

  return (
    <SafeZone>
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: verticalAlign,
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            opacity,
            transform: `translateY(${translateY}px)`,
            fontSize: FONT_SIZES[size],
            textAlign: 'center',
            maxWidth: '90%',
            lineHeight: 1.3,
            ...captionStyle,
            fontFamily: size === 'display' ? FONTS.display : FONTS.primary,
          }}
        >
          {renderText()}
        </div>
      </div>
    </SafeZone>
  );
};
