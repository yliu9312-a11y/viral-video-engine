import React from 'react';
import { SAFE_ZONE } from '../design-tokens';

/**
 * SafeZone — 铁律 1：所有重要内容必须在中央安全区内。
 *
 * 抖音/TikTok 1080×1920 画布：
 * - 顶部 200px：用户头像、声音浮标
 * - 底部 320px：标题、@、音乐名
 * - 右侧 120px：点赞/评论/分享按钮
 */
export const SafeZone: React.FC<{
  children: React.ReactNode;
  debug?: boolean;
}> = ({ children, debug = false }) => (
  <div
    style={{
      position: 'absolute',
      top: SAFE_ZONE.top,
      bottom: SAFE_ZONE.bottom,
      left: SAFE_ZONE.left,
      right: SAFE_ZONE.right,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      ...(debug
        ? {
            border: '2px dashed rgba(255,0,0,0.5)',
            background: 'rgba(255,0,0,0.05)',
          }
        : {}),
    }}
  >
    {children}
  </div>
);
