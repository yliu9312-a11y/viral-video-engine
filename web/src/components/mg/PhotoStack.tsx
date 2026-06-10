import React from 'react';
import { useCurrentFrame, useVideoConfig, spring, interpolate } from 'remotion';
import { SPRING } from '../../design-tokens/motion';

interface PhotoStackProps {
  items: Array<{ color: string; width?: number; height?: number }>;
  direction?: 'vertical' | 'horizontal' | 'grid';
  delay?: number;
}

export const PhotoStack: React.FC<PhotoStackProps> = ({
  items,
  direction = 'vertical',
  delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const getTransform = (index: number) => {
    const itemDelay = delay + index * 2;
    const entry = spring({ frame: Math.max(0, frame - itemDelay), fps, config: SPRING.snappy });
    const scale = interpolate(entry, [0, 1], [0.6, 1]);
    const opacity = interpolate(entry, [0, 1], [0, 1]);
    const float = Math.sin((frame + index * 10) * 0.03) * 3;

    if (direction === 'vertical') {
      return {
        opacity,
        transform: `translateY(${float}px) scale(${scale})`,
        width: 180 + (index % 2) * 20,
        height: 120 + (index % 3) * 15,
      };
    }
    if (direction === 'horizontal') {
      return {
        opacity,
        transform: `translateX(${float}px) scale(${scale})`,
        width: 140,
        height: 100,
      };
    }
    // grid
    return {
      opacity,
      transform: `scale(${scale})`,
      width: 120,
      height: 90,
    };
  };

  if (direction === 'grid') {
    const cols = Math.ceil(Math.sqrt(items.length));
    return (
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${cols}, 120px)`,
        gap: 12,
        padding: 20,
      }}>
        {items.map((item, i) => {
          const style = getTransform(i);
          return (
            <div key={i} style={{
              ...style,
              borderRadius: 8,
              background: item.color,
              boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
            }} />
          );
        })}
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: direction === 'vertical' ? 'column' : 'row',
      alignItems: 'center',
      gap: 8,
    }}>
      {items.map((item, i) => {
        const style = getTransform(i);
        return (
          <div key={i} style={{
            ...style,
            borderRadius: 8,
            background: item.color,
            boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
            flexShrink: 0,
          }} />
        );
      })}
    </div>
  );
};
