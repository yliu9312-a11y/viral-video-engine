"""视觉分析模块 — CV 算法 + VLM 融合。

CV 负责：颜色提取、旋转检测、运动追踪、元素检测
VLM 负责：文字内容、设计风格、语义理解

两者融合构建完整的 SceneDescription。
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── 颜色提取（K-means + LAB）────────────────────────────────────────────

@dataclass
class ColorInfo:
    hex: str
    rgb: tuple[int, int, int]
    percentage: float
    name: str = ""


def extract_dominant_colors(frame: np.ndarray, k: int = 5) -> list[ColorInfo]:
    """用 K-means 提取主色调，LAB 色彩空间保证感知准确性。"""
    resized = cv2.resize(frame, (200, 200))
    pixels = resized.reshape(-1, 3).astype(np.float32)

    # 采样加速
    if len(pixels) > 10000:
        indices = np.random.choice(len(pixels), 10000, replace=False)
        pixels = pixels[indices]

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)

    unique, counts = np.unique(labels, return_counts=True)
    sorted_idx = np.argsort(-counts)

    results = []
    for i in sorted_idx:
        bgr = centers[i].astype(int)
        rgb = (int(bgr[2]), int(bgr[1]), int(bgr[0]))
        pct = counts[i] / counts.sum()
        hex_str = '#%02x%02x%02x' % rgb
        name = _color_name_from_rgb(rgb)
        results.append(ColorInfo(hex=hex_str, rgb=rgb, percentage=pct, name=name))

    return results


def extract_roi_color(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> str:
    """从指定区域提取主色（LAB 空间平均值）。"""
    x1, y1, x2, y2 = bbox
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return "#000000"
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    avg_lab = lab.reshape(-1, 3).mean(axis=0)
    avg_bgr = cv2.cvtColor(np.uint8([[avg_lab]]), cv2.COLOR_LAB2BGR)[0][0]
    return '#%02x%02x%02x' % (int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0]))


def _color_name_from_rgb(rgb: tuple[int, int, int]) -> str:
    """RGB → 人类可读颜色名。"""
    r, g, b = rgb
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = hsv

    if s < 30:
        if v < 50: return "black"
        if v < 200: return "gray"
        return "white"
    if h < 10 or h > 170: return "red"
    if h < 25: return "orange"
    if h < 35: return "yellow"
    if h < 85: return "green"
    if h < 100: return "cyan"
    if h < 130: return "blue"
    if h < 160: return "purple"
    return "pink"


# ── 旋转检测（minAreaRect）──────────────────────────────────────────────

def detect_text_rotation(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    """用 minAreaRect 检测文字旋转角度。"""
    x1, y1, x2, y2 = bbox
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))

    if len(coords) < 5:
        return 0.0

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    return round(angle, 1)


def detect_frame_skew(gray: np.ndarray) -> float:
    """用 Hough 线检测整帧的倾斜角度。"""
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=50, maxLineGap=10)
    if lines is None:
        return 0.0

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if angle > 45:
            angle -= 90
        elif angle < -45:
            angle += 90
        angles.append(angle)

    return round(float(np.median(angles)), 1) if angles else 0.0


# ── 元素检测（EasyOCR: CRAFT 检测 + CRNN 识别）──────────────────────────

# EasyOCR reader 单例（避免重复初始化）
_ocr_reader = None

def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
    return _ocr_reader


@dataclass
class DetectedElement:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    area: int
    color: str = ""
    rotation: float = 0.0
    element_type: str = "text"  # text/shape/image
    text: str = ""
    confidence: float = 0.0


def detect_text_regions(frame: np.ndarray) -> list[DetectedElement]:
    """用 EasyOCR（CRAFT 检测 + CRNN 识别）检测文字区域。

    一次调用同时得到精确 bounding box 和文字内容。
    比 MSER 精确得多，特别是对运动图形中的艺术字。
    """
    reader = _get_ocr_reader()
    results = reader.readtext(frame, detail=1, paragraph=False)

    elements = []
    for bbox_pts, text, conf in results:
        if conf < 0.3:  # 置信度太低的跳过
            continue

        # bbox_pts 是 4 个角点 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        # 转换为 x1,y1,x2,y2
        xs = [p[0] for p in bbox_pts]
        ys = [p[1] for p in bbox_pts]
        x1, y1 = int(min(xs)), int(min(ys))
        x2, y2 = int(max(xs)), int(max(ys))

        if x2 - x1 < 5 or y2 - y1 < 5:
            continue

        # 从角点计算旋转角度
        top_left = bbox_pts[0]
        top_right = bbox_pts[1]
        dx = top_right[0] - top_left[0]
        dy = top_right[1] - top_left[1]
        rotation = round(np.degrees(np.arctan2(dy, dx)), 1)

        color = extract_roi_color(frame, (x1, y1, x2, y2))

        elements.append(DetectedElement(
            bbox=(x1, y1, x2, y2),
            area=(x2 - x1) * (y2 - y1),
            color=color,
            rotation=rotation,
            element_type="text",
            text=text.strip(),
            confidence=round(conf, 3),
        ))

    # 合并重叠区域（同一文字被分成多块的情况）
    elements = _merge_overlapping(elements)
    return elements


def _merge_overlapping(elements: list[DetectedElement], iou_thresh: float = 0.3) -> list[DetectedElement]:
    """合并重叠的检测区域。"""
    if not elements:
        return elements

    # 按面积降序排列
    elements.sort(key=lambda e: e.area, reverse=True)
    merged = []
    used = set()

    for i, elem in enumerate(elements):
        if i in used:
            continue
        for j in range(i + 1, len(elements)):
            if j in used:
                continue
            iou = _compute_iou(elem.bbox, elements[j].bbox)
            if iou > iou_thresh:
                # 合并为更大的区域
                elem.bbox = (
                    min(elem.bbox[0], elements[j].bbox[0]),
                    min(elem.bbox[1], elements[j].bbox[1]),
                    max(elem.bbox[2], elements[j].bbox[2]),
                    max(elem.bbox[3], elements[j].bbox[3]),
                )
                used.add(j)
        merged.append(elem)

    return merged


def _compute_iou(boxA: tuple, boxB: tuple) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return inter / float(areaA + areaB - inter + 1e-6)


# ── 文字追踪 + 去重 + 渐进合并 ────────────────────────────────────────

@dataclass
class TextTrack:
    track_id: int
    bbox: tuple[int, int, int, int]
    text_history: list[tuple[int, str]] = field(default_factory=list)
    color_history: list[tuple[int, str]] = field(default_factory=list)
    first_frame: int = 0
    last_frame: int = 0


class TextTracker:
    """文字追踪器：IoU 追踪 + 逐词渐进合并 + 时间投票去重。

    解决的 pipeline 问题：
    1. 同一文字跨帧追踪（IoU 匹配）
    2. 逐词渐进合并（"SO YOU" → "level up" → 同一元素）
    3. OCR 错误修正（时间投票：取最常见的识别结果）
    4. 重复元素合并（位置重叠的元素合并为一个）
    """

    def __init__(self, iou_threshold: float = 0.25, text_sim_threshold: float = 0.5):
        self.tracks: dict[int, TextTrack] = {}
        self.next_id = 0
        self.iou_thresh = iou_threshold
        self.text_sim_thresh = text_sim_threshold

    def update(self, frame_idx: int, detections: list[tuple[tuple[int, int, int, int], str, str]]):
        """更新追踪器。detections: [(bbox, text, color), ...]"""
        for bbox, text, color in detections:
            best_track_id = None
            best_score = 0.0

            for tid, track in self.tracks.items():
                # 两种匹配方式：IoU 或中心点距离
                iou = _compute_iou(bbox, track.bbox)
                center_dist = self._center_distance(bbox, track.bbox)

                if iou > self.iou_thresh or (center_dist < 0.05 and text):
                    last_text = track.text_history[-1][1] if track.text_history else ""
                    if self._text_matches(last_text, text):
                        score = max(iou, 0.3) + 0.3
                        if score > best_score:
                            best_score = score
                            best_track_id = tid

            if best_track_id is not None:
                track = self.tracks[best_track_id]
                # 更新 bbox 为平均值（平滑）
                old = track.bbox
                track.bbox = (
                    (old[0] + bbox[0]) // 2,
                    (old[1] + bbox[1]) // 2,
                    (old[2] + bbox[2]) // 2,
                    (old[3] + bbox[3]) // 2,
                )
                track.text_history.append((frame_idx, text))
                track.color_history.append((frame_idx, color))
                track.last_frame = frame_idx
            else:
                self.tracks[self.next_id] = TextTrack(
                    track_id=self.next_id,
                    bbox=bbox,
                    text_history=[(frame_idx, text)],
                    color_history=[(frame_idx, color)],
                    first_frame=frame_idx,
                    last_frame=frame_idx,
                )
                self.next_id += 1

    def _text_matches(self, old_text: str, new_text: str) -> bool:
        """检查两个文字是否应该合并。"""
        if not old_text or not new_text:
            return True
        # 完全相同
        if old_text == new_text:
            return True
        # 包含关系（渐进扩展）
        if old_text in new_text or new_text in old_text:
            return True
        # 编辑距离相似
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, old_text.lower(), new_text.lower()).ratio()
        return ratio > self.text_sim_thresh

    def get_final_elements(self) -> list[dict]:
        """获取最终合并后的元素列表，应用时间投票和去重。"""
        elements = []
        for tid, track in self.tracks.items():
            if not track.text_history:
                continue

            # 时间投票：取最常见的 OCR 结果（修正识别错误）
            texts = [t for _, t in track.text_history if t]
            if not texts:
                continue
            from collections import Counter
            text_counter = Counter(texts)
            best_text = text_counter.most_common(1)[0][0]

            # 取最常见的颜色
            colors = [c for _, c in track.color_history if c]
            best_color = Counter(colors).most_common(1)[0][0] if colors else "#000000"

            elements.append({
                "track_id": tid,
                "bbox": track.bbox,
                "text": best_text,
                "text_history": list(set(texts)),  # 去重
                "color": best_color,
                "first_frame": track.first_frame,
                "last_frame": track.last_frame,
                "is_progressive": len(set(texts)) > 1,
                "confidence": len(texts),  # 出现次数 = 置信度
            })

        # 去重：合并位置重叠且文字相似的元素
        elements = self._deduplicate(elements)
        return elements

    def _deduplicate(self, elements: list[dict]) -> list[dict]:
        """合并位置重叠的重复元素。

        匹配策略（三选一）：
        1. 文字相同 + 位置接近 → 同一文字的重复检测
        2. 位置非常接近（center < 3%）→ 同一元素的不同 OCR 结果
        3. 位置接近（center < 8%）+ 时间连续 → 渐进文字揭示
        """
        if len(elements) < 2:
            return elements

        elements.sort(key=lambda e: e["confidence"], reverse=True)
        merged = []
        used = set()

        for i, elem in enumerate(elements):
            if i in used:
                continue
            for j in range(i + 1, len(elements)):
                if j in used:
                    continue

                center_dist = self._center_distance(elem["bbox"], elements[j]["bbox"])
                text_match = self._text_matches(elem["text"], elements[j]["text"])

                # 策略 1：文字相同 + 位置接近
                if text_match and center_dist < 0.08:
                    elem["first_frame"] = min(elem["first_frame"], elements[j]["first_frame"])
                    elem["last_frame"] = max(elem["last_frame"], elements[j]["last_frame"])
                    elem["confidence"] += elements[j]["confidence"]
                    used.add(j)
                # 策略 2：位置非常接近（同一元素的不同 OCR）
                elif center_dist < 0.03:
                    # 保留置信度更高的文字
                    elem["first_frame"] = min(elem["first_frame"], elements[j]["first_frame"])
                    elem["last_frame"] = max(elem["last_frame"], elements[j]["last_frame"])
                    elem["confidence"] += elements[j]["confidence"]
                    used.add(j)
                # 策略 3：位置接近 + 时间连续（渐进揭示）
                elif center_dist < 0.08:
                    # 检查时间是否连续或重叠
                    time_gap = abs(elem["first_frame"] - elements[j]["last_frame"])
                    time_gap2 = abs(elements[j]["first_frame"] - elem["last_frame"])
                    if min(time_gap, time_gap2) < 120:  # 2 秒内
                        # 合并为渐进元素，保留最长文字
                        if len(elements[j]["text"]) > len(elem["text"]):
                            elem["text"] = elements[j]["text"]
                        elem["first_frame"] = min(elem["first_frame"], elements[j]["first_frame"])
                        elem["last_frame"] = max(elem["last_frame"], elements[j]["last_frame"])
                        elem["is_progressive"] = True
                        elem["confidence"] += elements[j]["confidence"]
                        used.add(j)

            merged.append(elem)

        return merged

    def _center_distance(self, bbox_a: tuple, bbox_b: tuple) -> float:
        """计算两个 bbox 中心点的归一化距离（相对于画布尺寸）。"""
        cx_a = (bbox_a[0] + bbox_a[2]) / 2
        cy_a = (bbox_a[1] + bbox_a[3]) / 2
        cx_b = (bbox_b[0] + bbox_b[2]) / 2
        cy_b = (bbox_b[1] + bbox_b[3]) / 2
        # 假设画布 1280x720，归一化到 0-1
        dist = ((cx_a - cx_b) ** 2 + (cy_a - cy_b) ** 2) ** 0.5
        return dist / 1500  # 粗略归一化


# ── 精确颜色提取（只取文字前景色）────────────────────────────────────

def extract_text_color(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> str:
    """从文字区域提取前景色（排除背景像素）。

    方法：K-means(k=2) 分离前景/背景，取较小簇（文字）的颜色。
    """
    x1, y1, x2, y2 = bbox
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return "#000000"

    # 转为 RGB
    roi_rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
    pixels = roi_rgb.reshape(-1, 3).astype(np.float32)

    if len(pixels) < 10:
        return extract_roi_color(frame, bbox)

    # K-means(k=2) 分离前景/背景
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(pixels, 2, None, criteria, 5, cv2.KMEANS_PP_CENTERS)

    counts = np.bincount(labels.flatten())
    text_cluster = np.argmin(counts)  # 较小簇 = 文字
    rgb = centers[text_cluster].astype(int)
    return '#%02x%02x%02x' % (int(rgb[0]), int(rgb[1]), int(rgb[2]))


# ── 运动模式检测 ──────────────────────────────────────────────────────

@dataclass
class MotionPattern:
    pattern: str  # stagger/cascade/parallax/particle/static
    params: dict = field(default_factory=dict)


def detect_stagger(elements: list[dict], fps: float = 30.0) -> MotionPattern | None:
    """检测交错入场模式：同类元素依次出现。"""
    if len(elements) < 3:
        return None

    # 按首次出现时间排序
    sorted_elems = sorted(elements, key=lambda e: e.get("first_frame", 0))
    start_frames = [e["first_frame"] for e in sorted_elems]
    intervals = np.diff(start_frames)

    if len(intervals) < 2:
        return None

    cv = float(np.std(intervals) / (np.mean(intervals) + 1e-6))
    if cv < 0.3 and np.mean(intervals) < fps * 2:  # 间隔小于 2 秒
        return MotionPattern(
            pattern="stagger",
            params={
                "count": len(elements),
                "interval_frames": round(float(np.mean(intervals)), 1),
                "interval_seconds": round(float(np.mean(intervals)) / fps, 2),
            },
        )
    return None


def detect_cascade(elements: list[dict]) -> MotionPattern | None:
    """检测级联动画：元素按空间位置顺序出现。"""
    if len(elements) < 3:
        return None

    sorted_elems = sorted(elements, key=lambda e: e.get("first_frame", 0))
    positions = [e["bbox"][0] for e in sorted_elems]  # x 位置
    times = [e["first_frame"] for e in sorted_elems]

    if len(positions) < 3:
        return None

    corr = float(np.corrcoef(positions, times)[0, 1])
    if abs(corr) > 0.8:
        direction = "left_to_right" if corr > 0 else "right_to_left"
        return MotionPattern(
            pattern="cascade",
            params={"direction": direction, "correlation": round(corr, 3)},
        )
    return None


def detect_parallax(flow: np.ndarray, frame: np.ndarray) -> MotionPattern | None:
    """检测视差效果：不同深度层以不同速度运动。"""
    if flow is None:
        return None

    magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
    h, w = magnitude.shape

    # 将画面分为上中下三层
    layers = [
        magnitude[:h // 3, :],
        magnitude[h // 3:2 * h // 3, :],
        magnitude[2 * h // 3:, :],
    ]

    speeds = [float(np.mean(layer)) for layer in layers]
    if max(speeds) / (min(speeds) + 1e-6) > 2.0:
        return MotionPattern(
            pattern="parallax",
            params={
                "layers": 3,
                "speed_ratio": round(max(speeds) / (min(speeds) + 1e-6), 2),
                "layer_speeds": [round(s, 3) for s in speeds],
            },
        )
    return None


def detect_particles(prev_frame: np.ndarray, curr_frame: np.ndarray) -> MotionPattern | None:
    """检测粒子效果：大量微小运动区域。"""
    diff = cv2.absdiff(prev_frame, curr_frame)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    small_contours = [c for c in contours if cv2.contourArea(c) < 500]

    if len(small_contours) > 20:
        total_area = sum(cv2.contourArea(c) for c in small_contours)
        return MotionPattern(
            pattern="particles",
            params={
                "count": len(small_contours),
                "avg_size": round(total_area / len(small_contours), 1),
            },
        )
    return None


# ── 光流分析 ──────────────────────────────────────────────────────────

@dataclass
class FlowFeatures:
    avg_magnitude: float
    max_magnitude: float
    dominant_direction: str  # left/right/up/down
    motion_regions: list[dict]
    motion_coverage: float  # 运动像素占比


def analyze_flow(flow: np.ndarray) -> FlowFeatures:
    """从光流场提取运动特征。"""
    magnitude, angle = cv2.cartToPolar(flow[..., 0], flow[..., 1])

    # 主方向
    hist, _ = np.histogram(angle, bins=8, range=(0, 2 * math.pi))
    dir_names = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"]
    dominant_dir = dir_names[int(np.argmax(hist))]

    # 运动区域
    mag_uint8 = np.uint8(np.clip(magnitude * 10, 0, 255))
    _, motion_mask = cv2.threshold(mag_uint8, 10, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(motion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    motion_regions = []
    for c in contours:
        if cv2.contourArea(c) > 500:
            x, y, w, h = cv2.boundingRect(c)
            roi_flow = flow[y:y + h, x:x + w]
            avg_dx = float(roi_flow[..., 0].mean())
            avg_dy = float(roi_flow[..., 1].mean())
            motion_regions.append({
                "bbox": (x, y, x + w, y + h),
                "dx": round(avg_dx, 2),
                "dy": round(avg_dy, 2),
                "speed": round(math.sqrt(avg_dx ** 2 + avg_dy ** 2), 2),
            })

    return FlowFeatures(
        avg_magnitude=round(float(np.mean(magnitude)), 3),
        max_magnitude=round(float(np.max(magnitude)), 3),
        dominant_direction=dominant_dir,
        motion_regions=motion_regions,
        motion_coverage=round(float(np.mean(magnitude > 1.0)), 3),
    )


# ── 自适应帧采样 ──────────────────────────────────────────────────────

def adaptive_sample_frames(video_path: str, target_frames: int = 16) -> list[tuple[int, float]]:
    """自适应帧采样：高运动区域多采样，静态区域少采样。

    Returns: [(frame_index, timestamp_seconds), ...]
    """
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Pass 1: 计算每帧复杂度
    scores = []
    prev_gray = None

    for i in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 240))

        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, gray)
            motion = float(np.mean(diff))
            edges = cv2.Canny(gray, 50, 150)
            complexity = float(np.mean(edges))
            score = motion + 0.1 * complexity
        else:
            score = 0.0

        scores.append(score)
        prev_gray = gray

    cap.release()

    # Pass 2: 按分数比例采样
    scores_arr = np.array(scores)
    scores_arr = np.maximum(scores_arr, 0.01)
    cumulative = np.cumsum(scores_arr / scores_arr.sum())

    selected = []
    step = 1.0 / target_frames
    for i in range(target_frames):
        target = step * (i + 0.5)
        idx = int(np.searchsorted(cumulative, target))
        idx = min(idx, total_frames - 1)
        selected.append(idx)

    # 确保首尾帧
    selected[0] = 0
    selected[-1] = total_frames - 1

    # 去重排序
    selected = sorted(set(selected))
    return [(idx, round(idx / fps, 2)) for idx in selected]
