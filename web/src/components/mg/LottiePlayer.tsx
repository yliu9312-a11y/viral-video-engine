import React, {useEffect, useState} from 'react';
import {Lottie, LottieAnimationData} from '@remotion/lottie';
import {useCurrentFrame, staticFile} from 'remotion';

/**
 * Lottie 动画播放组件
 *
 * 用法:
 *   <LottiePlayer src="checkmark.json" size={200} loop />
 *   <LottiePlayer src="confetti.json" size={400} loop={false} />
 *
 * src 是 public/ 目录下的相对路径,或直接传 Lottie JSON 对象
 */

interface LottiePlayerProps {
  src: string | LottieAnimationData;
  size?: number;
  loop?: boolean;
  playbackRate?: number;
  style?: React.CSSProperties;
}

export const LottiePlayer: React.FC<LottiePlayerProps> = ({
  src,
  size = 200,
  loop = true,
  playbackRate = 1,
  style,
}) => {
  const [animationData, setAnimationData] = useState<LottieAnimationData | null>(null);
  const frame = useCurrentFrame();

  useEffect(() => {
    if (typeof src !== 'string') {
      setAnimationData(src);
      return;
    }

    // Load from URL or static file
    const url = src.startsWith('http') ? src : staticFile(src);
    fetch(url)
      .then((res) => res.json())
      .then((data) => setAnimationData(data))
      .catch((err) => console.error('Failed to load Lottie:', err));
  }, [src]);

  if (!animationData) {
    return null;
  }

  return (
    <Lottie
      animationData={animationData}
      loop={loop}
      playbackRate={playbackRate}
      style={{
        width: size,
        height: size,
        ...style,
      }}
    />
  );
};
