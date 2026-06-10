"""Motion Kinematics — 运动学特征提取 + 闭集动效分类器。

从元素轨迹计算散度(divergence)、旋度(curl)、尺度变化(scale_change)，
然后映射到封闭动效词表（Tier A/B/C）。

参考：DCS 运动描述子（Divergence-Curl-Shear）
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── 动效词表 ──────────────────────────────────────────────────────────────

EFFECT_VOCABULARY = {
    # Tier A — 已有 MG 组件可直接渲染
    'pop_in':        {'tier': 'A', 'desc': '元素弹出入场', 'component': 'WordReveal'},
    'text_scroll':   {'tier': 'A', 'desc': '文字横向滚动', 'component': 'MarqueeText'},
    'scale_pulse':   {'tier': 'A', 'desc': '缩放脉冲', 'component': 'interpolate scale'},
    'slide_caption': {'tier': 'A', 'desc': '下滑字幕', 'component': 'StandardCaption'},
    'logo_reveal':   {'tier': 'A', 'desc': 'Logo 展示', 'component': 'LogoReveal'},
    'image_swap':    {'tier': 'A', 'desc': '图片切换', 'component': 'crossfade'},
    'logo_shrink':   {'tier': 'A', 'desc': 'Logo 缩小左移', 'component': 'LogoReveal'},
    # Tier B — 需新组件，Remotion 友好
    'flip':          {'tier': 'B', 'desc': '3D 翻转', 'component': 'CSS rotateY+perspective'},
    'scatter':       {'tier': 'B', 'desc': '元素散开', 'component': 'radial emit'},
    'gather':        {'tier': 'B', 'desc': '元素聚拢', 'component': 'radial converge'},
    'rotate_180':    {'tier': 'B', 'desc': '旋转半圈', 'component': 'rotate 180deg'},
    'line_split':    {'tier': 'B', 'desc': '两行分开', 'component': 'two text opposite translate'},
    'emit_images':   {'tier': 'B', 'desc': '发射图片', 'component': 'ImageOrbit emit'},
    'highlight_sel': {'tier': 'B', 'desc': '选中高亮', 'component': 'opacity+color change'},
    '2_5d_push':     {'tier': 'B', 'desc': '2.5D 推拉', 'component': 'perspective translateZ'},
    'spin_in':       {'tier': 'B', 'desc': '旋转入场', 'component': 'rotate entrance'},
    'elastic_pop':   {'tier': 'B', 'desc': '弹性缩放', 'component': 'scale overshoot'},
    # Tier C — 不可复现，当媒体槽位
    'volumetric_3d': {'tier': 'C', 'desc': '体积 3D', 'component': 'media_slot'},
    'camera_fly':    {'tier': 'C', 'desc': '相机飞行', 'component': 'media_slot'},
    'generated_vid': {'tier': 'C', 'desc': '生成视频', 'component': 'media_slot'},
}


# ── 运动学特征 ────────────────────────────────────────────────────────────

@dataclass
class MotionFeatures:
    """一个元素的运动学特征。"""
    divergence: float = 0.0       # 径向发散度（>0 散开，<0 聚拢）
    curl: float = 0.0             # 旋度（绕心旋转量，弧度/秒）
    scale_change: float = 0.0     # 尺度变化率（末态/初态 - 1）
    speed_mean: float = 0.0       # 平均速度 (%/帧)
    speed_peak: float = 0.0       # 峰值速度
    path_length: float = 0.0      # 路径总长 (%)
    entrance_delay: float = 0.0   # 入场延迟（相对于场景开始，秒）
    duration: float = 0.0         # 可见时长（秒）
    has_rotation: bool = False    # 是否有旋转
    rotation_degrees: float = 0.0 # 总旋转角度


def extract_features(keyframes, fps: float = 30.0) -> MotionFeatures:
    """从关键帧序列提取运动学特征。"""
    if not keyframes or len(keyframes) < 2:
        return MotionFeatures()

    features = MotionFeatures()

    # 位置序列
    xs = [kf.x for kf in keyframes if kf.x is not None]
    ys = [kf.y for kf in keyframes if kf.y is not None]
    if not xs or not ys:
        return features

    # 入场延迟
    features.entrance_delay = keyframes[0].frame / fps if fps > 0 else 0

    # 可见时长
    features.duration = (keyframes[-1].frame - keyframes[0].frame) / fps if fps > 0 else 0

    # 路径总长
    path_len = 0.0
    speeds = []
    for i in range(1, len(keyframes)):
        dx = (keyframes[i].x or 0) - (keyframes[i-1].x or 0)
        dy = (keyframes[i].y or 0) - (keyframes[i-1].y or 0)
        seg_len = (dx * dx + dy * dy) ** 0.5
        path_len += seg_len
        dt_frames = keyframes[i].frame - keyframes[i-1].frame
        if dt_frames > 0:
            speeds.append(seg_len / dt_frames)
    features.path_length = path_len
    features.speed_mean = sum(speeds) / len(speeds) if speeds else 0
    features.speed_peak = max(speeds) if speeds else 0

    # 旋转检测
    rots = [kf.rotation for kf in keyframes if kf.rotation is not None and kf.rotation != 0]
    if rots:
        features.has_rotation = True
        features.rotation_degrees = max(rots) - min(rots) if len(rots) > 1 else abs(rots[0])

    # 尺度变化
    scales_x = [kf.scale_x for kf in keyframes if kf.scale_x is not None]
    scales_y = [kf.scale_y for kf in keyframes if kf.scale_y is not None]
    if scales_x and len(scales_x) >= 2:
        features.scale_change = (scales_x[-1] / scales_x[0]) - 1 if scales_x[0] != 0 else 0
    elif scales_y and len(scales_y) >= 2:
        features.scale_change = (scales_y[-1] / scales_y[0]) - 1 if scales_y[0] != 0 else 0

    return features


def compute_group_kinematics(keyframes_list: list, fps: float = 30.0) -> tuple[float, float]:
    """计算一组元素的散度和旋度。

    Args:
        keyframes_list: 每个元素的关键帧列表
        fps: 帧率

    Returns:
        (divergence, curl) — 散度和旋度
    """
    if len(keyframes_list) < 2:
        return 0.0, 0.0

    # 找到所有元素共有的帧范围
    all_frames = set()
    for kfs in keyframes_list:
        for kf in kfs:
            all_frames.add(kf.frame)
    sorted_frames = sorted(all_frames)
    if len(sorted_frames) < 2:
        return 0.0, 0.0

    # 过滤掉空的 keyframes
    valid_keyframes = [kfs for kfs in keyframes_list if kfs]
    if len(valid_keyframes) < 2:
        return 0.0, 0.0

    # 对每个帧，计算所有元素的质心和到质心的平均距离
    distances = []
    angles = []

    for frame in sorted_frames:
        positions = []
        for kfs in valid_keyframes:
            # 找到此元素在当前帧的位置
            prev_kf = kfs[0]
            for kf in kfs:
                if kf.frame <= frame:
                    prev_kf = kf
                else:
                    break
            if prev_kf.x is not None and prev_kf.y is not None:
                positions.append((prev_kf.x, prev_kf.y))

        if len(positions) < 2:
            continue

        # 质心
        cx = sum(p[0] for p in positions) / len(positions)
        cy = sum(p[1] for p in positions) / len(positions)

        # 到质心的平均距离
        avg_dist = sum(((p[0]-cx)**2 + (p[1]-cy)**2)**0.5 for p in positions) / len(positions)
        distances.append((frame, avg_dist))

        # 角度（第一个元素相对质心的角度）
        if positions[0][0] != cx or positions[0][1] != cy:
            angle = math.atan2(positions[0][1] - cy, positions[0][0] - cx)
            angles.append((frame, angle))

    # 散度：距离变化率
    divergence = 0.0
    if len(distances) >= 2:
        d_start = distances[0][1]
        d_end = distances[-1][1]
        if d_start > 0:
            divergence = (d_end - d_start) / d_start

    # 旋度：角度变化总量
    curl = 0.0
    if len(angles) >= 2:
        total_angle_change = 0.0
        for i in range(1, len(angles)):
            da = angles[i][1] - angles[i-1][1]
            # 处理角度跳跃（-π 到 π 边界）
            if da > math.pi:
                da -= 2 * math.pi
            elif da < -math.pi:
                da += 2 * math.pi
            total_angle_change += da
        curl = total_angle_change  # 总旋转弧度

    return divergence, curl


# ── 动效分类器 ────────────────────────────────────────────────────────────

def classify_effect(
    features: MotionFeatures,
    group_divergence: float = 0.0,
    group_curl: float = 0.0,
    group_size: int = 1,
) -> str:
    """从运动学特征分类动效。

    Args:
        features: 单个元素的运动学特征
        group_divergence: 该元素所在组的散度
        group_curl: 该元素所在组的旋度
        group_size: 组内元素数量

    Returns:
        动效标签（EFFECT_VOCABULARY 中的 key）
    """
    # 多元素散开
    if group_divergence > 0.15 and group_size >= 3:
        return 'scatter'
    # 多元素聚拢
    if group_divergence < -0.15 and group_size >= 3:
        return 'gather'
    # 旋转（>45度）
    if features.has_rotation and abs(features.rotation_degrees) > 45:
        return 'rotate_180'
    # 组旋度
    if abs(group_curl) > 0.8:  # >~45度
        return 'rotate_180'
    # 尺度脉冲（变化 >30%）
    if abs(features.scale_change) > 0.3:
        return 'scale_pulse'
    # 弹性缩放（快速大变化）
    if abs(features.scale_change) > 0.5 and features.speed_peak > 0.3:
        return 'elastic_pop'
    # 快速入场（高速 + 短延迟）
    if features.speed_peak > 0.5 and features.entrance_delay < 0.3:
        return 'pop_in'
    # 旋转入场
    if features.has_rotation and abs(features.rotation_degrees) > 15:
        return 'spin_in'
    # 2.5D 推拉（有尺度变化 + 位移）
    if abs(features.scale_change) > 0.15 and features.path_length > 5:
        return '2_5d_push'
    # 默认：弹出
    return 'pop_in'


def classify_scene_effects(elements, fps: float = 30.0) -> None:
    """为场景中的所有元素分类动效，写入 effect_type 和 effect_tier。

    直接修改 elements 列表中的元素。
    """
    if not elements:
        return

    # 提取每个元素的特征
    all_features = []
    all_keyframes = []
    for elem in elements:
        kfs = elem.motion_path if elem.motion_path else []
        feat = extract_features(kfs, fps)
        all_features.append(feat)
        all_keyframes.append(kfs)

    # 计算组运动学（所有元素一起）
    group_div, group_curl = compute_group_kinematics(all_keyframes, fps)

    # 分类每个元素
    for i, elem in enumerate(elements):
        effect = classify_effect(
            all_features[i],
            group_divergence=group_div,
            group_curl=group_curl,
            group_size=len(elements),
        )
        elem.effect_type = effect
        elem.effect_tier = EFFECT_VOCABULARY.get(effect, {}).get('tier', 'A')

    logger.info(f"动效分类: {len(elements)} 元素, "
                f"散度={group_div:.2f}, 旋度={group_curl:.2f}, "
                f"类型={[e.effect_type for e in elements[:5]]}")
