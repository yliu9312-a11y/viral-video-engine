"""视觉缺口检测器 — 分析参考视频，识别需要补充的视觉素材。

不是只提取文字，而是识别视频中的视觉层次：
- 背景层（纯色/渐变/图片/视频）
- 前景层（产品截图/mockup/图片）
- 装饰层（logo/图标/贴纸）
- 文字层（标题/正文/字幕）

然后对比新内容，识别缺口。
"""
from __future__ import annotations

import logging
import cv2
import numpy as np
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VisualLayer:
    """视频中的一个视觉层。"""
    layer_type: str  # background/foreground/decoration/text
    description: str
    bbox: tuple[int, int, int, int] | None = None  # x1, y1, x2, y2
    frame_range: tuple[int, int] = (0, 0)  # 出现的帧范围
    color: str = ""
    has_image: bool = False  # 是否包含图片内容（非纯色）
    importance: str = "medium"  # high/medium/low


@dataclass
class GapItem:
    """一个视觉缺口。"""
    gap_type: str  # missing_background/missing_image/missing_logo/missing_mockup
    description: str
    suggested_action: str  # generate/ask_user/reuse
    priority: str = "high"  # high/medium/low
    context: dict = field(default_factory=dict)


def analyze_visual_layers(video_path: str, sample_frames: int = 10) -> list[VisualLayer]:
    """分析视频的视觉层次结构。"""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    layers = []

    # 采样关键帧
    frame_indices = np.linspace(0, total_frames - 1, sample_frames, dtype=int)

    prev_frame = None
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # 分析这一帧的视觉层次
        frame_layers = _analyze_frame(frame, idx, fps)
        layers.extend(frame_layers)
        prev_frame = frame.copy()

    cap.release()

    # 合并相似层
    layers = _merge_layers(layers)
    return layers


def _analyze_frame(frame: np.ndarray, frame_idx: int, fps: float) -> list[VisualLayer]:
    """分析单帧的视觉层次。"""
    h, w = frame.shape[:2]
    layers = []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 1. 背景层检测
    brightness = np.mean(hsv[:, :, 2])
    if brightness < 30:
        layers.append(VisualLayer(
            layer_type="background",
            description="纯黑/深色背景",
            frame_range=(frame_idx, frame_idx),
            color=_dominant_color(frame),
        ))
    elif brightness > 200:
        layers.append(VisualLayer(
            layer_type="background",
            description="纯白/浅色背景",
            frame_range=(frame_idx, frame_idx),
            color=_dominant_color(frame),
        ))
    else:
        # 检查是否有渐变
        gradient_score = _detect_gradient(frame)
        if gradient_score > 0.3:
            layers.append(VisualLayer(
                layer_type="background",
                description=f"渐变背景 (渐变度: {gradient_score:.2f})",
                frame_range=(frame_idx, frame_idx),
                color=_dominant_color(frame),
            ))
        else:
            layers.append(VisualLayer(
                layer_type="background",
                description="复杂背景（可能含图片/纹理）",
                frame_range=(frame_idx, frame_idx),
                has_image=True,
                color=_dominant_color(frame),
            ))

    # 2. 前景层检测（大面积非文字区域）
    # 用边缘检测找前景区域
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    large_regions = []
    for c in contours:
        area = cv2.contourArea(c)
        if area > (w * h * 0.05):  # 大于画面 5%
            x, y, rw, rh = cv2.boundingRect(c)
            # 排除文字区域（通常是小而密集的边缘）
            if rw > w * 0.2 and rh > h * 0.2:
                large_regions.append((x, y, x + rw, y + rh))

    if large_regions:
        # 取最大的区域作为前景
        largest = max(large_regions, key=lambda r: (r[2]-r[0]) * (r[3]-r[1]))
        layers.append(VisualLayer(
            layer_type="foreground",
            description="前景元素（可能是产品截图/mockup）",
            bbox=largest,
            frame_range=(frame_idx, frame_idx),
            has_image=True,
            importance="high",
        ))

    # 3. 文字层检测（用边缘密度判断）
    # 文字区域通常有高边缘密度
    block_size = 32
    text_regions = []
    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = edges[y:y+block_size, x:x+block_size]
            density = np.mean(block) / 255
            if density > 0.1:  # 高边缘密度 = 可能是文字
                text_regions.append((x, y, x+block_size, y+block_size))

    if text_regions:
        # 合并相邻文字区域
        text_bbox = (
            min(r[0] for r in text_regions),
            min(r[1] for r in text_regions),
            max(r[2] for r in text_regions),
            max(r[3] for r in text_regions),
        )
        layers.append(VisualLayer(
            layer_type="text",
            description="文字区域",
            bbox=text_bbox,
            frame_range=(frame_idx, frame_idx),
            importance="medium",
        ))

    return layers


def _detect_gradient(frame: np.ndarray) -> float:
    """检测帧是否包含渐变。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 检查水平方向的亮度变化
    left_mean = np.mean(gray[:, :w//3])
    right_mean = np.mean(gray[:, 2*w//3:])
    center_mean = np.mean(gray[:, w//3:2*w//3])

    # 渐变 = 亮度单调变化
    diff_lr = abs(left_mean - right_mean)
    diff_lc = abs(left_mean - center_mean)
    diff_cr = abs(center_mean - right_mean)

    # 如果亮度单调递增或递减，说明有渐变
    if (left_mean < center_mean < right_mean) or (left_mean > center_mean > right_mean):
        return min(1.0, diff_lr / 100)
    return 0.0


def _dominant_color(frame: np.ndarray) -> str:
    """提取主色调。"""
    pixels = frame.reshape(-1, 3)
    avg = pixels.mean(axis=0).astype(int)
    return '#%02x%02x%02x' % (int(avg[2]), int(avg[1]), int(avg[0]))


def _merge_layers(layers: list[VisualLayer]) -> list[VisualLayer]:
    """合并相似的视觉层。"""
    if len(layers) < 2:
        return layers

    merged = []
    used = set()

    for i, layer in enumerate(layers):
        if i in used:
            continue

        # 查找同类型、同位置的层
        for j in range(i + 1, len(layers)):
            if j in used:
                continue
            if layers[j].layer_type == layer.layer_type:
                # 合并帧范围
                layer.frame_range = (
                    min(layer.frame_range[0], layers[j].frame_range[0]),
                    max(layer.frame_range[1], layers[j].frame_range[1]),
                )
                used.add(j)

        merged.append(layer)

    return merged


def detect_gaps(
    original_layers: list[VisualLayer],
    new_scene: dict,
    material_dir: str = "",
) -> list[GapItem]:
    """检测新视频相对于原视频的视觉缺口。"""
    gaps = []

    # 检查背景层
    bg_layers = [l for l in original_layers if l.layer_type == "background"]
    new_bg = new_scene.get("background_color", "#000000")

    for bg in bg_layers:
        if bg.has_image and new_bg in ("#000000", ""):
            gaps.append(GapItem(
                gap_type="missing_background",
                description=f"原视频有复杂背景（{bg.description}），新视频只有纯黑底",
                suggested_action="generate",
                priority="high",
                context={"original_color": bg.color, "description": bg.description},
            ))

    # 检查前景层（产品截图/mockup）
    fg_layers = [l for l in original_layers if l.layer_type == "foreground"]
    new_elements = new_scene.get("elements", [])
    has_image_elements = any(e.get("type") == "image" for e in new_elements)

    if fg_layers and not has_image_elements:
        gaps.append(GapItem(
            gap_type="missing_mockup",
            description=f"原视频有 {len(fg_layers)} 个前景元素（产品截图/mockup），新视频没有",
            suggested_action="ask_user",
            priority="high",
            context={"count": len(fg_layers)},
        ))

    # 检查 logo
    text_elements = [e for e in new_elements if e.get("type") == "text"]
    logo_elements = [e for e in text_elements if "logo" in e.get("content_text", "").lower() or "品牌" in e.get("content_text", "")]
    if not logo_elements:
        gaps.append(GapItem(
            gap_type="missing_logo",
            description="新视频缺少品牌 logo",
            suggested_action="ask_user",
            priority="medium",
        ))

    # 检查素材目录
    if material_dir:
        import os
        materials = os.listdir(material_dir) if os.path.isdir(material_dir) else []
        image_materials = [m for m in materials if m.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        if not image_materials and fg_layers:
            gaps.append(GapItem(
                gap_type="missing_materials",
                description="素材目录中没有图片，无法填充前景元素",
                suggested_action="ask_user",
                priority="high",
            ))

    return gaps


def format_gap_report(gaps: list[GapItem]) -> str:
    """格式化缺口报告。"""
    if not gaps:
        return "✅ 无视觉缺口"

    lines = ["⚠️ 视觉缺口报告：\n"]
    for i, gap in enumerate(gaps, 1):
        icon = "🔴" if gap.priority == "high" else "🟡" if gap.priority == "medium" else "🟢"
        action = {"generate": "🎨 可自动生成", "ask_user": "👤 需要用户提供", "reuse": "♻️ 可复用素材"}[gap.suggested_action]
        lines.append(f"{icon} {i}. {gap.description}")
        lines.append(f"   → {action}")

    return "\n".join(lines)
