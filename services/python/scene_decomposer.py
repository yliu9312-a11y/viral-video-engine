"""Scene Decomposer — 场景级视频分解。

将参考视频分解为多个独立场景，每个场景有独立的元素/背景/转场/运动。
然后从场景序列中自动抽取 beat_sheet，喂回 Beat-Level 编排器。

流程:
1. Shot 检测 (PySceneDetect) → shot = scene
2. 逐场景窗口化提取 (SAM2 + EasyOCR + VLM)
3. 元素融合去重 (SAM2 mask ∪ OCR box)
4. beat_sheet 自动抽取 → BeatStructure
"""
from __future__ import annotations

import logging
import json
import os
from dataclasses import dataclass, field

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class VideoScene:
    """一个场景的完整描述。"""
    scene_index: int = 0
    start_frame: int = 0
    end_frame: int = 0
    duration_frames: int = 0

    background_color: str = "#000000"
    background_gradient: str = ""

    elements: list = field(default_factory=list)  # SceneElement list
    entrance_transition: dict = field(default_factory=lambda: {"type": "cut", "duration": 0})
    transition_out: dict = field(default_factory=lambda: {"type": "fade", "direction": ""})

    motion_patterns: list = field(default_factory=list)
    motion_tracks: list = field(default_factory=list)

    layout_type: str = "centered"     # centered / stacked / split / full_bleed
    mode: str = "grid"                # grid（平铺）/ stage（重叠/旋转/放射）
    archetype: str = ""               # split_emit / scatter / ""（无签名）
    vlm_layout: str = ""              # VLM 判定的目标布局 (centered/radial/stack/full_bleed/grid/split)
    scene_role: str = "unknown"       # hook / feature / comparison / cta
    visual_summary: str = ""
    design_style: str = "minimal"

    source: str = "measured"
    confidence: float = 1.0


@dataclass
class BeatSlot:
    """beat_sheet 中的一个元素槽位。"""
    element_type: str = "text"    # text / image / card / icon
    role: str = "unknown"         # title / subtitle / body / card_N / background
    text_length: int = 0          # 文字长度（0 = 非文字）


@dataclass
class BeatEntry:
    """beat_sheet 中的一个 beat。"""
    role: str = "unknown"         # hook / feature / comparison / cta
    layout: str = "centered"
    duration_frames: int = 0
    transition_in: str = "cut"
    transition_direction: str = ""
    pattern: str = ""             # cascade_stack / orbit / parallax / none
    pattern_params: dict = field(default_factory=dict)
    slots: list[BeatSlot] = field(default_factory=list)


@dataclass
class BeatStructure:
    """从参考视频自动抽取的 beat_sheet —— 直接喂 orchestrate_from_beats()。"""
    beats: list[BeatEntry] = field(default_factory=list)
    global_palette: list[str] = field(default_factory=list)
    canvas: tuple = (1080, 1920)
    fps: int = 30
    source_video: str = ""
    extraction_method: str = "scene_decomposer"


@dataclass
class VideoDecomposition:
    """完整视频分解为多个场景。"""
    source_video: str = ""
    canvas_width: int = 1080
    canvas_height: int = 1920
    fps: int = 30
    total_frames: int = 0
    scenes: list[VideoScene] = field(default_factory=list)
    global_color_palette: list[str] = field(default_factory=list)
    beat_structure: BeatStructure | None = None


# ── Step 1: Shot 检测 ─────────────────────────────────────────────────────

def _merge_short_shots(shots: list[dict], min_seconds: float = 1.5) -> list[dict]:
    """D1: 合并碎场景。把持续时长 < min_seconds 的 shot 并入前一个（第一个则并入后一个）。

    循环直到无碎片或只剩 1 个，然后重排 index。总时长不变。
    """
    if len(shots) <= 1:
        return shots

    changed = True
    while changed:
        changed = False
        if len(shots) <= 1:
            break
        new_shots: list[dict] = []
        i = 0
        while i < len(shots):
            s = shots[i]
            dur = s["end_time"] - s["start_time"]
            if dur < min_seconds:
                if new_shots:
                    # 并入前一个：延伸 end
                    new_shots[-1]["end_frame"] = s["end_frame"]
                    new_shots[-1]["end_time"] = s["end_time"]
                elif i + 1 < len(shots):
                    # 第一个碎片：并入后一个
                    shots[i + 1]["start_frame"] = s["start_frame"]
                    shots[i + 1]["start_time"] = s["start_time"]
                    i += 1
                    changed = True
                    continue
                else:
                    new_shots.append(s)
                changed = True
            else:
                new_shots.append(s)
            i += 1
        shots = new_shots

    # 重排 index
    for idx, s in enumerate(shots):
        s["index"] = idx
    return shots


def detect_shots(video_path: str) -> list[dict]:
    """用 PySceneDetect 检测 shot 边界。返回 [{start_frame, end_frame, start_time, end_time}]"""
    try:
        from scenedetect import detect, AdaptiveDetector
        scene_list = detect(
            video_path,
            AdaptiveDetector(
                adaptive_threshold=3.0,
                min_scene_len=15,
            ),
        )
        shots = []
        for i, (start, end) in enumerate(scene_list):
            shots.append({
                "index": i,
                "start_frame": start.get_frames(),
                "end_frame": end.get_frames(),
                "start_time": start.get_seconds(),
                "end_time": end.get_seconds(),
            })
        logger.info(f"Shot 检测: {len(shots)} 个 shot")
        shots = _merge_short_shots(shots)
        logger.info(f"Shot 合并后: {len(shots)} 个 shot")
        return shots
    except Exception as e:
        logger.warning(f"PySceneDetect 失败: {e}, 用固定切分")
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        # 每 3 秒切一刀
        step = int(fps * 3)
        shots = []
        for i in range(0, total, step):
            shots.append({
                "index": len(shots),
                "start_frame": i,
                "end_frame": min(i + step, total),
                "start_time": i / fps,
                "end_time": min(i + step, total) / fps,
            })
        logger.info(f"固定切分: {len(shots)} 个 shot")
        shots = _merge_short_shots(shots)
        logger.info(f"Shot 合并后: {len(shots)} 个 shot")
        return shots


# ── Step 2: 逐场景窗口化提取 ─────────────────────────────────────────────

def _crop_and_save(frame, cx: float, cy: float, w: float, h: float, output_dir: str, name: str) -> str:
    """从帧中裁剪元素区域并保存为图片。

    cx, cy, w, h 是归一化坐标 (0~1)。
    返回保存路径（相对于 output_dir）。
    跳过全黑或对比度过低的裁剪。
    自动增强：CLAHE 提升暗部细节 + 锐化。
    """
    import cv2
    import numpy as np
    fh, fw = frame.shape[:2]
    x1 = max(0, int((cx - w / 2) * fw))
    y1 = max(0, int((cy - h / 2) * fh))
    x2 = min(fw, int((cx + w / 2) * fw))
    y2 = min(fh, int((cy + h / 2) * fh))

    if x2 <= x1 or y2 <= y1:
        return ""

    crop = frame[y1:y2, x1:x2]

    # 跳过全黑或低对比度裁剪
    if crop.mean() < 10 or crop.std() < 5:
        return ""

    # CLAHE 增强：提升暗部细节，不改变整体色调
    try:
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_ch)
        enhanced = cv2.merge([l_enhanced, a_ch, b_ch])
        crop = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    except Exception:
        pass  # 增强失败就用原图

    fname = f"{name}.jpg"
    fpath = os.path.join(output_dir, fname)
    cv2.imwrite(fpath, crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
    # 返回相对路径（相对于项目根目录）
    return os.path.join(output_dir, fname)


def _vlm_analyze_layout(frame) -> str:
    """用 VLM 分析帧画面，返回目标布局家族。

    这是"结构提取"的核心：不靠 SAM2 坐标（天然是散开的），
    而是让 VLM 看原视频帧，判断真实布局。

    返回: centered / radial / stack / full_bleed / grid / split / ""
    """
    import base64
    _, buf = cv2.imencode('.jpg', frame)
    b64 = base64.b64encode(buf).decode()

    try:
        from scene_description import _vlm_call
        prompt = (
            "这是一个短视频的截图。请判断画面的布局类型，只回答一个词：\n"
            "- centered: 主体居中（一个大图/形状/文字在中心）\n"
            "- radial: 多张图片围绕中心呈环形排列\n"
            "- stack: 图片垂直或水平堆叠\n"
            "- full_bleed: 一张图占满整个画面\n"
            "- grid: 图片平铺成网格\n"
            "- split: 画面分成两块区域\n"
            "只回答布局类型名称，不要其他文字。"
        )
        result = _vlm_call([b64], prompt)
        result = result.strip().lower()
        # 中英文映射
        cn_map = {"居中": "centered", "环绕": "radial", "放射": "radial",
                   "堆叠": "stack", "全屏": "full_bleed", "满屏": "full_bleed",
                   "网格": "grid", "平铺": "grid", "分割": "split", "左右": "split"}
        for cn, en in cn_map.items():
            if cn in result:
                return en
        valid = {"centered", "radial", "stack", "full_bleed", "grid", "split"}
        for v in valid:
            if v in result:
                return v
        return ""
    except Exception as e:
        logger.warning(f"VLM 布局分析失败: {e}")
        return ""


def extract_scene(video_path: str, shot: dict, fps: float, width: int, height: int, output_dir: str = "") -> VideoScene:
    """对一个场景的时间窗口提取完整视觉信息。"""
    from scene_description import (
        Keyframe, MotionTrack, SceneElement, SpatialProps, AppearanceProps,
        TypographyProps, AnimationSpec, TimingProps, TransitionSpec,
        _vlm_call, _parse_vlm_json,
    )
    from vision_analyzer import detect_text_regions, TextTracker, extract_dominant_colors, adaptive_sample_frames
    from motion_analyzer import MotionAnalyzer

    start_f = shot["start_frame"]
    end_f = shot["end_frame"]
    duration_f = end_f - start_f

    scene = VideoScene(
        scene_index=shot["index"],
        start_frame=start_f,
        end_frame=end_f,
        duration_frames=duration_f,
    )

    # 读取多帧用于图片裁剪（找最亮的帧，避免全黑裁剪）
    rep_frames = []
    if output_dir:
        cap = cv2.VideoCapture(video_path)
        # 采样 3 帧：1/4, 1/2, 3/4
        for ratio in [0.25, 0.5, 0.75]:
            f_num = start_f + int(duration_f * ratio)
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(f_num, end_f - 1))
            ret, frame = cap.read()
            if ret:
                rep_frames.append(frame)
        cap.release()

    # 选最亮的帧作为代表帧
    rep_frame = None
    if rep_frames:
        rep_frame = max(rep_frames, key=lambda f: f.mean())

    # ── 2a-0: VLM 布局分析（分析原视频帧确定目标布局）──
    vlm_layout = ""
    if rep_frame is not None:
        vlm_layout = _vlm_analyze_layout(rep_frame)
        logger.info(f"场景 {shot['index']}: VLM 布局 = {vlm_layout}")

    # ── 2a: 背景色（场景首帧 K-means）──
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    ret, first_frame = cap.read()
    if ret:
        colors = extract_dominant_colors(first_frame, k=3)
        if colors:
            scene.background_color = colors[0].hex
    cap.release()

    # ── 2b: 多关键帧元素发现（捕捉中途入场）──
    # 在场景内多个时间点检测元素，记录首次出现帧
    sample_count = min(6, max(2, duration_f // 60))
    sample_frames = []
    for i in range(sample_count):
        idx = start_f + int(duration_f * (i + 0.5) / sample_count)
        sample_frames.append(min(idx, end_f - 1))

    # ── 2c: SAM2 元素发现 + 光流追踪（窗口化）──
    # 创建一个只覆盖场景时间窗口的子视频追踪
    motion_tracks = []
    sam_elements = []

    try:
        # 用 MotionAnalyzer 追踪，但只在场景窗口内
        analyzer = MotionAnalyzer.create(video_path)
        # 手动限制追踪范围
        timeline = _track_in_window(analyzer, video_path, start_f, end_f)

        for track in timeline.tracks:
            kfs = _samples_to_keyframes(track.samples, fps)
            if not kfs:
                continue
            mt = MotionTrack(
                element_id=f"scene{shot['index']}_motion_{track.element_id}",
                keyframes=kfs,
                z_order=0,
                role="unknown",
                source="measured",
                confidence=track.confidence,
            )
            motion_tracks.append(mt)
            sam_elements.append({
                "cx": track.samples[0].x if track.samples else 0.5,
                "cy": track.samples[0].y if track.samples else 0.5,
                "w": track.samples[0].w if track.samples else 0.1,
                "h": track.samples[0].h if track.samples else 0.1,
                "label": track.label,
                "entrance_frame": int(track.enter_t * fps) + start_f,
            })
    except Exception as e:
        logger.warning(f"场景 {shot['index']} MotionAnalyzer 失败: {e}")

    # ── 2d: EasyOCR 文字检测（窗口内多帧）──
    text_tracker = TextTracker()
    cap = cv2.VideoCapture(video_path)
    for frame_idx in sample_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue
        elements = detect_text_regions(frame)
        detections = [(e.bbox, e.text, e.color) for e in elements]
        text_tracker.update(frame_idx, detections)
    cap.release()
    text_tracks = text_tracker.get_final_elements()

    # ── 2e: 元素融合去重 (SAM2 ∪ OCR) ──
    fused_elements = _fuse_elements(sam_elements, text_tracks, width, height)

    # ── 2f: 构建 SceneElement 列表 ──
    scene_elements = []
    elem_idx = 0

    # 文字颜色：根据背景色自动选高对比色
    text_color = _contrast_color(scene.background_color)

    for fe in fused_elements:
        if fe["role"] == "card":
            # 带文字的卡片
            x_pct = fe["cx"] * 100
            y_pct = fe["cy"] * 100
            w_pct = fe["w"] * 100
            h_pct = fe["h"] * 100

            # 裁剪并保存图片
            img_src = ""
            if rep_frame is not None and output_dir:
                img_src = _crop_and_save(
                    rep_frame, fe["cx"], fe["cy"], fe["w"], fe["h"],
                    output_dir, f"s{shot['index']}_card_{elem_idx}"
                )

            elem = SceneElement(
                id=f"s{shot['index']}_elem_{elem_idx}",
                type="image",
                content_src=img_src,
                spatial=SpatialProps(x=x_pct, y=y_pct, width=w_pct, height=h_pct),
                appearance=AppearanceProps(opacity=1.0),
                timing=TimingProps(
                    in_point=start_f,
                    out_point=end_f,
                    entrance=AnimationSpec(type="fade", duration=6),
                    exit=AnimationSpec(type="fade", duration=6, start_value=1.0, end_value=0.0),
                ),
                motion_path=fe.get("motion_path", []),
                role="card",
                source="measured",
            )
            scene_elements.append(elem)
            elem_idx += 1

        elif fe["role"] == "graphic":
            # 纯图形/图片
            x_pct = fe["cx"] * 100
            y_pct = fe["cy"] * 100
            w_pct = fe["w"] * 100
            h_pct = fe["h"] * 100

            # 裁剪并保存图片
            img_src = ""
            if rep_frame is not None and output_dir:
                img_src = _crop_and_save(
                    rep_frame, fe["cx"], fe["cy"], fe["w"], fe["h"],
                    output_dir, f"s{shot['index']}_img_{elem_idx}"
                )

            elem = SceneElement(
                id=f"s{shot['index']}_elem_{elem_idx}",
                type="image",
                content_src=img_src,
                spatial=SpatialProps(x=x_pct, y=y_pct, width=w_pct, height=h_pct),
                appearance=AppearanceProps(opacity=1.0),
                timing=TimingProps(
                    in_point=start_f,
                    out_point=end_f,
                    entrance=AnimationSpec(type="fade", duration=6),
                    exit=AnimationSpec(type="fade", duration=6, start_value=1.0, end_value=0.0),
                ),
                motion_path=fe.get("motion_path", []),
                role="graphic",
                source="measured",
            )
            scene_elements.append(elem)
            elem_idx += 1

        elif fe["role"] == "caption":
            # 独立文字
            text = fe.get("text", "")
            if not text:
                continue
            x_pct = fe["cx"] * 100
            y_pct = fe["cy"] * 100
            w_pct = fe["w"] * 100
            h_pct = fe["h"] * 100

            # 用融合时保留的 OCR 颜色，但如果太暗就用自动对比色
            ocr_color = fe.get("color", text_color)
            if _luminance(ocr_color) < 0.3:
                ocr_color = text_color

            elem = SceneElement(
                id=f"s{shot['index']}_elem_{elem_idx}",
                type="text",
                content_text=text,
                spatial=SpatialProps(x=x_pct, y=y_pct, width=max(w_pct, 20), height=h_pct),
                appearance=AppearanceProps(opacity=1.0, fill=ocr_color),
                typography=TypographyProps(
                    font_family="sans-serif",
                    font_size=max(h_pct * 0.8, 3.0),
                    font_weight=700,
                    color=ocr_color,
                ),
                timing=TimingProps(
                    in_point=start_f,
                    out_point=end_f,
                    entrance=AnimationSpec(type="fade", duration=6),
                    exit=AnimationSpec(type="fade", duration=6, start_value=1.0, end_value=0.0),
                ),
                role="text",
                source="measured",
            )
            scene_elements.append(elem)
            elem_idx += 1

    scene.elements = scene_elements
    scene.motion_tracks = motion_tracks

    # ── 2f-2: 将 motion_tracks 的 keyframes 关联到 elements 的 motion_path ──
    _link_tracks_to_elements(motion_tracks, scene_elements)

    # ── 2f-3: 运动学特征提取 + 动效分类 ──
    from motion_kinematics import classify_scene_effects
    classify_scene_effects(scene_elements, fps)

    # ── 2f-4: VLM 语义标注（先于布局模板，提供 scene_role 参考）──
    scene.elements = scene_elements
    _annotate_scene_vlm(scene, video_path, sample_frames[:2], text_tracks)

    # ── 2f-5: 布局分配（VLM 驱动 + fallback 到空间分类）──
    family = vlm_layout if vlm_layout else _classify_layout_family(scene_elements)
    mode = FAMILY_MODE.get(family, "grid")
    scene.mode = mode
    scene.archetype = family

    # 应用对应的布局生成器
    _apply_parametric_layout(scene_elements, start_f, end_f, fps, family)
    scene.layout_type = family
    scene.elements = scene_elements
    logger.info(f"场景 {shot['index']}: family={family} mode={mode} {len(scene_elements)}元素")

    # ── 2f-6: 文字动画分配（Kinetic Typography，Staging 原则）──
    # 先用 VLM 分析原视频的文字动画风格，再分配
    text_style_hint = _vlm_analyze_text_style(video_path, start_f, end_f)
    _assign_text_animations(scene_elements, fps, style_hint=text_style_hint)

    # ── 2f-7: 用 VLM 运动分析生成 motion_path 关键帧 ──
    # VLM 识别的动画类型（平移/缩放/弹性/飘浮）→ 生成对应的 motion_path

    # ── 2h: 转场检测 ──
    if shot["index"] > 0:
        scene.entrance_transition = _detect_transition(video_path, start_f, fps)

    logger.info(
        f"场景 {shot['index']}: {len(scene.elements)} 元素, "
        f"{len(scene.motion_tracks)} 轨迹, "
        f"role={scene.scene_role}, layout={scene.layout_type}"
    )

    return scene


def _track_in_window(analyzer, video_path: str, start_f: int, end_f: int):
    """在场景时间窗口内追踪元素。"""
    from motion_analyzer import MotionTimeline

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return MotionTimeline()

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = end_f - start_f

    # 跳到场景起始帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)

    # 只在窗口内检测元素
    best_frame_idx = start_f
    best_variance = -1.0
    best_bgr = None

    sample_step = max(1, total_frames // 10)
    for idx in range(start_f, end_f, sample_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, bgr = cap.read()
        if not ret:
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        v = float(np.var(gray))
        if v > best_variance:
            best_variance = v
            best_frame_idx = idx
            best_bgr = bgr

    if best_bgr is None:
        cap.release()
        return MotionTimeline()

    elements = analyzer._detect_elements(best_bgr)
    if not elements:
        cap.release()
        return MotionTimeline()

    # 追踪窗口内
    from motion_analyzer import MotionSample, ElementTrack, _classify_motion, TRACK_SAMPLE_INTERVAL

    sample_step = max(1, int(fps * TRACK_SAMPLE_INTERVAL))
    sample_indices = list(range(start_f, end_f, sample_step))
    n_samples = len(sample_indices)
    n_el = len(elements)

    cx_arr = np.zeros((n_el, n_samples), dtype=np.float32)
    cy_arr = np.zeros((n_el, n_samples), dtype=np.float32)
    w_arr = np.zeros((n_el, n_samples), dtype=np.float32)
    h_arr = np.zeros((n_el, n_samples), dtype=np.float32)
    vis_arr = np.zeros((n_el, n_samples), dtype=bool)

    # 初始化
    det_sample_idx = 0
    for si, sfi in enumerate(sample_indices):
        if sfi >= best_frame_idx:
            det_sample_idx = si
            break

    for i in range(n_el):
        cx_arr[i, det_sample_idx] = elements[i]["cx"]
        cy_arr[i, det_sample_idx] = elements[i]["cy"]
        w_arr[i, det_sample_idx] = elements[i]["w"]
        h_arr[i, det_sample_idx] = elements[i]["h"]
        vis_arr[i, det_sample_idx] = True

    # 光流追踪
    from motion_analyzer import TRACK_SEARCH_RADIUS_RATIO, DEAD_ZONE, SCENE_CHANGE_THRESHOLD, MAX_DRIFT_RATIO, MAX_TRACK_DURATION_SEC

    sr = TRACK_SEARCH_RADIUS_RATIO
    prev_gray = None
    orig_cx = np.array([e["cx"] for e in elements], dtype=np.float32)
    orig_cy = np.array([e["cy"] for e in elements], dtype=np.float32)
    track_start = np.full(n_el, -1.0)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    for f_idx in range(start_f, end_f):
        ret, bgr = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        if f_idx in sample_indices:
            s_idx = sample_indices.index(f_idx)

            if s_idx > det_sample_idx and prev_gray is not None:
                cur_t = (sample_indices[s_idx] - start_f) / fps

                for i in range(n_el):
                    if not vis_arr[i, s_idx - 1]:
                        continue

                    if track_start[i] < 0:
                        track_start[i] = cur_t
                    if cur_t - track_start[i] > MAX_TRACK_DURATION_SEC:
                        vis_arr[i, s_idx] = False
                        continue

                    cx, cy = cx_arr[i, s_idx - 1], cy_arr[i, s_idx - 1]
                    if cx < 0 or cy < 0 or cx >= 1.0 or cy >= 1.0:
                        vis_arr[i, s_idx] = False
                        continue

                    disp = analyzer._element_displacement(
                        prev_gray, gray, cx, cy,
                        max(w_arr[i, s_idx - 1], h_arr[i, s_idx - 1]), sr,
                    )
                    if disp is None:
                        vis_arr[i, s_idx] = False
                        continue

                    dx, dy = disp
                    if (dx ** 2 + dy ** 2) ** 0.5 > SCENE_CHANGE_THRESHOLD:
                        vis_arr[i, s_idx] = False
                        continue

                    if abs(dx) < DEAD_ZONE and abs(dy) < DEAD_ZONE:
                        dx, dy = 0.0, 0.0

                    nx = orig_cx[i] + max(-MAX_DRIFT_RATIO, min(MAX_DRIFT_RATIO, cx + dx - orig_cx[i]))
                    ny = orig_cy[i] + max(-MAX_DRIFT_RATIO, min(MAX_DRIFT_RATIO, cy + dy - orig_cy[i]))
                    cx_arr[i, s_idx] = max(0.0, min(1.0, nx))
                    cy_arr[i, s_idx] = max(0.0, min(1.0, ny))
                    w_arr[i, s_idx] = w_arr[i, s_idx - 1]
                    h_arr[i, s_idx] = h_arr[i, s_idx - 1]
                    vis_arr[i, s_idx] = True

        prev_gray = gray

    cap.release()

    # 构建轨迹
    tracks = []
    for i, el in enumerate(elements):
        samples = []
        enter_t, exit_t = 0.0, 0.0
        first = True
        for j in range(n_samples):
            if vis_arr[i, j]:
                t = (sample_indices[j] - start_f) / fps
                samples.append(MotionSample(
                    t=t, x=float(cx_arr[i, j]), y=float(cy_arr[i, j]),
                    w=float(w_arr[i, j]), h=float(h_arr[i, j]),
                ))
                if first:
                    enter_t = t
                    first = False
                exit_t = t
        if not samples:
            continue
        motion_type, path_summary = _classify_motion(samples)
        tracks.append(ElementTrack(
            element_id=i, label=el.get("label", f"element_{i}"),
            samples=samples, enter_t=enter_t, exit_t=exit_t,
            motion_type=motion_type, path_summary=path_summary,
            confidence=max(0.0, 1.0 - (len(samples) / max(n_samples, 1)) * 0.3),
        ))

    return MotionTimeline(tracks=tracks)


# ── 元素融合去重 ──────────────────────────────────────────────────────────

def _fuse_elements(sam_elements: list, text_tracks: list, width: int, height: int) -> list:
    """SAM2 掩码 ∪ OCR 文本框 → 统一元素，去重并定角色。

    规则:
    - SAM2 bbox 与 OCR bbox 重叠 IoU > 0.4 → role="card"（带文字的卡片）
    - SAM2 bbox 无 OCR 匹配 → role="graphic"（纯图形/图片）
    - OCR bbox 无 SAM2 匹配 → role="caption"（独立字幕）
    """
    fused = []
    used_ocr = set()

    for sam in sam_elements:
        sam_bbox = _norm_to_abs(sam["cx"], sam["cy"], sam["w"], sam["h"], width, height)
        best_iou = 0.0
        best_ocr_idx = -1

        for j, ocr in enumerate(text_tracks):
            if j in used_ocr:
                continue
            ocr_bbox = ocr["bbox"]  # (x1, y1, x2, y2)
            iou = _compute_iou(sam_bbox, ocr_bbox)
            if iou > best_iou:
                best_iou = iou
                best_ocr_idx = j

        if best_iou > 0.4 and best_ocr_idx >= 0:
            # 带文字的卡片
            used_ocr.add(best_ocr_idx)
            ocr = text_tracks[best_ocr_idx]
            fused.append({
                "cx": sam["cx"], "cy": sam["cy"],
                "w": sam["w"], "h": sam["h"],
                "role": "card",
                "text": ocr.get("text", ""),
                "color": ocr.get("color", "#FFFFFF"),
                "entrance_frame": sam.get("entrance_frame", 0),
                "motion_path": sam.get("motion_path", []),
            })
        else:
            # 纯图形
            fused.append({
                "cx": sam["cx"], "cy": sam["cy"],
                "w": sam["w"], "h": sam["h"],
                "role": "graphic",
                "entrance_frame": sam.get("entrance_frame", 0),
                "motion_path": sam.get("motion_path", []),
            })

    # 未匹配的 OCR → 独立字幕
    for j, ocr in enumerate(text_tracks):
        if j in used_ocr:
            continue
        bx, by, bx2, by2 = ocr["bbox"]
        cx = ((bx + bx2) / 2) / width
        cy = ((by + by2) / 2) / height
        w = (bx2 - bx) / width
        h = (by2 - by) / height
        fused.append({
            "cx": cx, "cy": cy, "w": w, "h": h,
            "role": "caption",
            "text": ocr.get("text", ""),
            "color": ocr.get("color", "#FFFFFF"),
        })

    return fused


def _norm_to_abs(cx, cy, w, h, width, height):
    """归一化坐标 → 绝对像素 bbox (x1, y1, x2, y2)。"""
    x1 = int((cx - w / 2) * width)
    y1 = int((cy - h / 2) * height)
    x2 = int((cx + w / 2) * width)
    y2 = int((cy + h / 2) * height)
    return (x1, y1, x2, y2)


def _compute_iou(bbox1, bbox2):
    """计算两个 bbox 的 IoU。"""
    x1 = max(bbox1[0], bbox2[0])
    y1 = max(bbox1[1], bbox2[1])
    x2 = min(bbox1[2], bbox2[2])
    y2 = min(bbox1[3], bbox2[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - inter

    return inter / max(union, 1)


# ── VLM 语义标注 ──────────────────────────────────────────────────────────

def _annotate_scene_vlm(scene: VideoScene, video_path: str, frame_indices: list, text_tracks: list):
    """用 VLM 标注场景的 layout_type / scene_role / design_style。"""
    import base64
    from scene_description import _vlm_call, _parse_vlm_json

    frames_b64 = []
    cap = cv2.VideoCapture(video_path)
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        h, w = frame.shape[:2]
        if w > 540:
            scale = 540 / w
            frame = cv2.resize(frame, (540, int(h * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        frames_b64.append(base64.b64encode(buf).decode("utf-8"))
    cap.release()

    if not frames_b64:
        return

    ocr_text = ", ".join([t.get("text", "") for t in text_tracks[:10] if t.get("text")])

    prompt = f"""分析这个视频场景（{len(frames_b64)} 帧），返回 JSON：

{{
  "layout_type": "centered/stacked/split/full_bleed",
  "scene_role": "hook/feature/comparison/data/cta",
  "design_style": "3个关键词",
  "visual_summary": "一句话描述这个场景的视觉特征"
}}

当前 OCR 文字: {ocr_text or "无"}

只返回 JSON。"""

    result = _vlm_call(frames_b64, prompt)
    data = _parse_vlm_json(result) if result else None

    if data:
        scene.scene_role = data.get("scene_role", scene.scene_role)
        scene.design_style = data.get("design_style", scene.design_style)
        scene.visual_summary = data.get("visual_summary", scene.visual_summary)


# ── 转场检测 ──────────────────────────────────────────────────────────────

def _detect_transition(video_path: str, boundary_frame: int, fps: float) -> dict:
    """检测两个场景之间的转场类型。

    收敛到 3 类: cut / fade / slide，每类映射到渲染器能力。
    """
    cap = cv2.VideoCapture(video_path)

    # 取边界前后各 10 帧的亮度
    before_brightness = []
    after_brightness = []

    for i in range(max(0, boundary_frame - 10), boundary_frame):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, f = cap.read()
        if ret:
            gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            before_brightness.append(float(np.mean(gray)))

    for i in range(boundary_frame, min(boundary_frame + 10, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, f = cap.read()
        if ret:
            gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            after_brightness.append(float(np.mean(gray)))

    cap.release()

    if not before_brightness or not after_brightness:
        return {"type": "cut", "duration": 0}

    # Cut: 亮度突变
    diff = abs(after_brightness[0] - before_brightness[-1])
    if diff > 30:
        return {"type": "cut", "duration": 0}

    # Fade: 亮度线性变化（前暗后亮 = fade-in，前亮后暗 = fade-out）
    brightness = before_brightness + after_brightness
    if len(brightness) >= 4:
        # 检查是否近似线性
        x = np.arange(len(brightness))
        slope, intercept = np.polyfit(x, brightness, 1)
        predicted = slope * x + intercept
        residuals = np.abs(np.array(brightness) - predicted)
        if np.mean(residuals) < 8 and abs(slope) > 1.5:
            return {"type": "fade", "duration": len(brightness)}

    # Slide: 检测光流方向
    try:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, boundary_frame - 1))
        ret, f1 = cap.read()
        cap.set(cv2.CAP_PROP_POS_FRAMES, boundary_frame)
        ret2, f2 = cap.read()
        cap.release()

        if ret and ret2:
            g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
            g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(g1, g2, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mean_dx = float(np.mean(flow[..., 0]))
            mean_dy = float(np.mean(flow[..., 1]))

            if abs(mean_dx) > 5 or abs(mean_dy) > 5:
                direction = "left" if mean_dx < -5 else "right" if mean_dx > 5 else "top" if mean_dy < -5 else "bottom"
                return {"type": "slide", "direction": direction, "duration": 10}
    except Exception:
        pass

    return {"type": "cut", "duration": 0}


# ── 颜色辅助 ──────────────────────────────────────────────────────────────

def _luminance(hex_color: str) -> float:
    """计算颜色的相对亮度 (0-1)。"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) < 6:
        return 0.5
    try:
        r, g, b = int(hex_color[:2], 16) / 255, int(hex_color[2:4], 16) / 255, int(hex_color[4:6], 16) / 255
    except ValueError:
        return 0.5
    return 0.299 * r + 0.587 * g + 0.114 * b


def _contrast_color(bg_color: str) -> str:
    """根据背景色返回高对比文字色（白色或黑色）。"""
    if _luminance(bg_color) > 0.5:
        return "#000000"
    return "#FFFFFF"


# ── 布局模板系统 ──────────────────────────────────────────────────────────

# 安全区（百分比，相对于画布）
SAFE_ZONE = {
    "top": 10.0,      # 顶部留白
    "bottom": 17.0,   # 底部留白（TikTok 底栏）
    "left": 5.0,      # 左侧留白
    "right": 9.0,     # 右侧留白
}

MAX_SIMULTANEOUS = 4  # 同屏最多 4 个元素（编排内不限，散件≤2）

# 布局模板：每个槽位 = (x%, y%, w%, h%)
LAYOUT_TEMPLATES = {
    "centered-hero": {
        "desc": "居中英雄：标题上中 + 主图中 + 字幕下中",
        "slots": [
            {"role": "text",   "x": 50, "y": 20, "w": 80, "h": 10},   # 标题
            {"role": "image",  "x": 50, "y": 50, "w": 70, "h": 50},   # 主图
            {"role": "text",   "x": 50, "y": 85, "w": 60, "h": 8},    # 字幕
        ],
    },
    "grid-2x2": {
        "desc": "2x2 网格：4 个等大图",
        "slots": [
            {"role": "image", "x": 28, "y": 30, "w": 40, "h": 30},
            {"role": "image", "x": 72, "y": 30, "w": 40, "h": 30},
            {"role": "image", "x": 28, "y": 70, "w": 40, "h": 30},
            {"role": "image", "x": 72, "y": 70, "w": 40, "h": 30},
        ],
    },
    "split-LR": {
        "desc": "左右分：左图右文字",
        "slots": [
            {"role": "image", "x": 30, "y": 50, "w": 45, "h": 60},
            {"role": "text",  "x": 72, "y": 40, "w": 40, "h": 15},
            {"role": "text",  "x": 72, "y": 60, "w": 40, "h": 10},
        ],
    },
    "full-bleed-bg": {
        "desc": "满屏背景 + 居中文字（背景允许出血，文字在安全区）",
        "slots": [
            {"role": "image", "x": 50, "y": 50, "w": 110, "h": 110, "bleed": True},  # 背景（允许出血）
            {"role": "text",  "x": 50, "y": 40, "w": 80, "h": 12},    # 标题
            {"role": "text",  "x": 50, "y": 60, "w": 60, "h": 8},     # 副标题
        ],
    },
    "stacked-cards": {
        "desc": "堆叠卡片：3 张错位堆叠",
        "slots": [
            {"role": "image", "x": 40, "y": 40, "w": 50, "h": 40},
            {"role": "image", "x": 55, "y": 45, "w": 50, "h": 40},
            {"role": "image", "x": 60, "y": 50, "w": 50, "h": 40},
        ],
    },
    "single-focus": {
        "desc": "单焦点：一张大图 + 标题",
        "slots": [
            {"role": "image", "x": 50, "y": 45, "w": 80, "h": 60},
            {"role": "text",  "x": 50, "y": 85, "w": 70, "h": 10},
        ],
    },
}


def _select_layout_template(elements: list) -> str:
    """根据元素组成选择布局模板（对应 CSS Grid 命名区域）。"""
    n_images = sum(1 for e in elements if e.type == "image")
    n_texts = sum(1 for e in elements if e.type == "text")

    if n_images >= 4:
        return "grid_2x2"       # 4 格网格
    if n_images == 3:
        return "hero_side"      # 1 大 + 2 小
    if n_images == 2 and n_texts >= 1:
        return "split_lr"       # 左右分
    if n_images == 2 and n_texts == 0:
        return "split_lr"
    if n_images == 1 and n_texts >= 2:
        return "centered_hero"  # 标题 + 主图 + 字幕
    if n_images == 1 and n_texts <= 1:
        return "centered_hero"
    if n_images == 0 and n_texts > 0:
        return "centered_hero"
    return "centered_hero"


def _clamp_to_safe_zone(x: float, y: float, w: float, h: float) -> tuple:
    """将元素限制在安全区内（整个 bbox，不只是中心点）。

    确保：元素左边缘 ≥ left%，右边缘 ≤ 100-right%，
    上边缘 ≥ top%，下边缘 ≤ 100-bottom%。
    """
    sz = SAFE_ZONE
    left_bound = sz["left"]
    right_bound = 100 - sz["right"]
    top_bound = sz["top"]
    bottom_bound = 100 - sz["bottom"]

    # 如果元素比安全区还大，缩小到安全区大小
    max_w = right_bound - left_bound
    max_h = bottom_bound - top_bound
    if w > max_w:
        w = max_w
    if h > max_h:
        h = max_h

    # 计算中心点的合法范围（保证整个 bbox 在安全区内）
    min_x = left_bound + w / 2
    max_x = right_bound - w / 2
    min_y = top_bound + h / 2
    max_y = bottom_bound - h / 2

    # 如果 min > max（元素太大），居中
    if min_x > max_x:
        x = (left_bound + right_bound) / 2
    else:
        x = max(min_x, min(max_x, x))

    if min_y > max_y:
        y = (top_bound + bottom_bound) / 2
    else:
        y = max(min_y, min(max_y, y))

    return x, y


# CSS Grid 槽位名映射
# ── 参数化布局家族（9 家族，覆盖 MG 短视频绝大多数布局）────────────────────

# ── 参数化布局系统（9 家族，VLM 驱动）──────────────────────────────────────

FAMILY_MODE = {
    "grid": "grid", "centered": "grid", "split": "grid",
    "full_bleed": "grid",
    "radial": "stage", "stack": "stage", "scatter": "stage",
}

ENTRANCE_TYPES = ["scale", "3d", "blur", "slide", "mask_reveal", "fade", "rotate"]
IDLE_EFFECTS = ["float", "breathe", "rotate", "elastic_pop", "2_5d_push", "spin_in", "flip", "scatter"]


def _apply_parametric_layout(elements: list, start_f: int, end_f: int, fps: float, family: str):
    """统一参数化布局：根据家族名选择生成器。"""
    import math
    from scene_description import AnimationSpec

    images = [e for e in elements if e.type == "image"]
    texts = [e for e in elements if e.type == "text"]

    def _set_timing(el, s, e):
        el.timing.in_point = s
        el.timing.out_point = e

    def _assign_animations(imgs, start, stagger_base=3):
        # D2: 同屏统一一种入场 + 一种 idle，按 start_f 确定性选择，避免同屏打架
        ENTRANCE_UNIFIED = ["scale", "slide", "fade", "mask_reveal"]
        IDLE_UNIFIED = ["float", "breathe"]
        unified_entrance = ENTRANCE_UNIFIED[start_f % len(ENTRANCE_UNIFIED)]
        # slide/mask_reveal 用 "bottom"，scale/fade 用 "center"
        unified_dir = "bottom" if unified_entrance in ("slide", "mask_reveal") else "center"
        unified_idle = IDLE_UNIFIED[start_f % len(IDLE_UNIFIED)]
        stagger = min(5, max(2, stagger_base))
        for i, img in enumerate(imgs):
            img.timing.entrance = AnimationSpec(
                type=unified_entrance,
                direction=unified_dir,
                duration=8,
            )
            img.timing.exit = AnimationSpec(type="fade", duration=4, start_value=1.0, end_value=0.0)
            img.effect_type = unified_idle
            img.spatial.rotation = 0  # 旋转一律 0（stack 家族的扇形旋转在其自己分支处理）
            _set_timing(img, start + i * stagger, end_f)

    def _center_texts(txts, start):
        for txt in txts:
            txt.spatial.x = 50; txt.spatial.y = 50
            txt.spatial.width = 80; txt.spatial.height = 20
            txt._grid_slot = ""
            _set_timing(txt, start, end_f)

    # ── centered: 一个大元素居中 + 小配角 ──
    if family == "centered":
        if images:
            # 最大的图居中占 60%
            images.sort(key=lambda e: e.spatial.width * e.spatial.height, reverse=True)
            hero = images[0]
            hero.spatial.x = 50; hero.spatial.y = 50
            hero.spatial.width = 60; hero.spatial.height = 60
            hero._grid_slot = "s0"
            hero.timing.entrance = AnimationSpec(type="scale", direction="center", duration=10)
            hero.timing.exit = AnimationSpec(type="fade", duration=4, start_value=1.0, end_value=0.0)
            hero.effect_type = "breathe"
            _set_timing(hero, start_f, end_f)
            # 小图围绕
            for i, img in enumerate(images[1:], 1):
                angle = (2 * math.pi * (i - 1)) / max(len(images) - 1, 1)
                r = 38
                img.spatial.x = 50 + r * math.cos(angle)
                img.spatial.y = 50 + r * math.sin(angle)
                img.spatial.width = 18; img.spatial.height = 18
                img._grid_slot = ""
                stagger = min(4, max(2, 12 // len(images)))
                _set_timing(img, start_f + i * stagger, end_f)
            _center_texts(texts, start_f)
        else:
            _center_texts(texts, start_f)

    # ── radial: N 张围绕中心成环 ──
    elif family == "radial":
        n = len(images)
        if n == 0:
            _center_texts(texts, start_f)
            return
        card_size = 35 if n <= 4 else 28 if n <= 8 else 22 if n <= 12 else 18
        radius = 18 + n * 1.8
        for i, img in enumerate(images):
            angle = (2 * math.pi * i) / n + (i * 0.3) % 0.5
            cx = 50 + radius * math.cos(angle)
            cy = 50 + radius * math.sin(angle)
            half = card_size / 2
            cx = max(half + 2, min(100 - half - 2, cx))
            cy = max(half + 2, min(100 - half - 2, cy))
            img.spatial.x = cx; img.spatial.y = cy
            img.spatial.width = card_size; img.spatial.height = card_size * 1.3
            img._grid_slot = ""
        _assign_animations(images, start_f)
        _center_texts(texts, start_f)

    # ── stack: 垂直堆叠 ──
    elif family == "stack":
        n = len(images)
        if n == 0:
            _center_texts(texts, start_f)
            return
        card_h = min(30, 80 // n)
        card_w = 40
        for i, img in enumerate(images):
            img.spatial.x = 50 + (i % 2) * 10 - 5  # 微小交错
            img.spatial.y = 10 + i * (card_h + 3)
            img.spatial.width = card_w; img.spatial.height = card_h
            img._grid_slot = ""
            img.spatial.rotation = (i - n / 2) * 8  # 扇形展开
        _assign_animations(images, start_f, stagger_base=4)
        _center_texts(texts, start_f)

    # ── full_bleed: 一图占满 + 叠字 ──
    elif family == "full_bleed":
        if images:
            hero = images[0]
            hero.spatial.x = 50; hero.spatial.y = 50
            hero.spatial.width = 100; hero.spatial.height = 100
            hero._grid_slot = "s0"
            _set_timing(hero, start_f, end_f)
            hero.effect_type = "float"
        _center_texts(texts, start_f)

    # ── grid: 动态列行平铺 ──
    elif family == "grid":
        n = len(images)
        if n == 0:
            _center_texts(texts, start_f)
            return
        cols = min(4, max(2, round(n ** 0.5)))
        rows = max(2, -(-n // cols))
        slots = [f"s{i}" for i in range(cols * rows)]
        cell_w = 100 / cols
        cell_h = 100 / rows
        for i, img in enumerate(images):
            r, c = divmod(i, cols)
            img.spatial.x = c * cell_w + cell_w / 2
            img.spatial.y = r * cell_h + cell_h / 2
            img.spatial.width = cell_w - 2; img.spatial.height = cell_h - 2
            img._grid_slot = slots[i % len(slots)]
            _set_timing(img, start_f, end_f)
        text_slots = [s for s in slots if s not in [getattr(e, '_grid_slot', '') for e in images]]
        for i, txt in enumerate(texts):
            txt._grid_slot = text_slots[i % len(text_slots)] if text_slots else slots[-1]
            txt.spatial.x = 50; txt.spatial.y = 50
            txt.spatial.width = 100; txt.spatial.height = 100
            _set_timing(txt, start_f, end_f)

    # ── split: 两块区域 ──
    elif family == "split":
        if len(images) >= 2:
            images[0].spatial.x = 25; images[0].spatial.y = 50
            images[0].spatial.width = 48; images[0].spatial.height = 90
            images[0]._grid_slot = "s0"
            _set_timing(images[0], start_f, end_f)
            images[1].spatial.x = 75; images[1].spatial.y = 50
            images[1].spatial.width = 48; images[1].spatial.height = 90
            images[1]._grid_slot = "s1"
            _set_timing(images[1], start_f, end_f)
        _center_texts(texts, start_f)

    # ── scatter fallback: 放射散开 ──
    else:
        n = len(images)
        if n == 0:
            _center_texts(texts, start_f)
            return
        card_size = 35 if n <= 4 else 28 if n <= 8 else 22
        radius = 18 + n * 1.8
        for i, img in enumerate(images):
            angle = (2 * math.pi * i) / n
            cx = 50 + radius * math.cos(angle)
            cy = 50 + radius * math.sin(angle)
            half = card_size / 2
            cx = max(half + 2, min(100 - half - 2, cx))
            cy = max(half + 2, min(100 - half - 2, cy))
            img.spatial.x = cx; img.spatial.y = cy
            img.spatial.width = card_size; img.spatial.height = card_size * 1.3
            img._grid_slot = ""
        _assign_animations(images, start_f)
        _center_texts(texts, start_f)


# ── Fallback 分类器（VLM 失败时用）─────────────────────────────────────────

def _classify_layout_family(elements: list) -> str:
    """基于 SAM2 坐标的 fallback 分类器（VLM 不可用时）。"""
    import math
    images = [e for e in elements if e.type == "image"]
    n = len(images)
    if n == 0: return "centered"
    if n == 1: return "full_bleed"
    if n == 2: return "split"
    # 默认 grid
    return "grid"


# ── 文字动画分配（Kinetic Typography）───────────────────────────────────────

# 入场技法封闭表
TEXT_ENTRANCE_TABLE = {
    "char_pop":     {"max_chars": 4,  "desc": "逐字弹入，短词/标语"},
    "word_stagger": {"max_chars": 20, "desc": "逐词淡入上移，一句话"},
    "mask_reveal":  {"max_chars": 40, "desc": "遮罩刷出，电影感标题"},
    "blur_in":      {"max_chars": 30, "desc": "模糊→清晰，高级柔和"},
    "typewriter":   {"max_chars": 15, "desc": "逐字打字，代码/搜索感"},
    "line_split":   {"max_chars": 30, "desc": "两行上下分开"},
}


def _vlm_analyze_text_style(video_path: str, start_f: int, end_f: int) -> str:
    """用 VLM 分析原视频场景的文字动画风格。

    返回: typewriter / blur_in / fade / mask_reveal / word_stagger / ""
    """
    import cv2, base64
    from scene_description import _vlm_call

    cap = cv2.VideoCapture(video_path)
    total = end_f - start_f
    mid_f = start_f + int(total * 0.3)
    gap = max(2, int(total * 0.05))

    frames_b64 = []
    for pos in [mid_f, min(mid_f + gap, end_f - 1)]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if ret:
            _, buf = cv2.imencode('.jpg', frame)
            frames_b64.append(base64.b64encode(buf).decode())
    cap.release()

    if len(frames_b64) < 2:
        return ""

    prompt = (
        "分析这两帧中文字的出现方式，只回答一个词：\n"
        "- typewriter: 逐字打出\n"
        "- blur_in: 从模糊到清晰\n"
        "- fade: 淡入\n"
        "- mask_reveal: 遮罩刷出\n"
        "- word_stagger: 逐词出现\n"
        "只回答类型名称，不要其他文字。"
    )
    result = _vlm_call(frames_b64, prompt)
    if not result:
        return ""
    result = result.strip().lower()
    # 中英文映射
    cn_map = {"打字": "typewriter", "模糊": "blur_in", "淡入": "fade",
              "遮罩": "mask_reveal", "逐词": "word_stagger", "刷出": "mask_reveal"}
    for cn, en in cn_map.items():
        if cn in result:
            return en
    valid = {"typewriter", "blur_in", "fade", "mask_reveal", "word_stagger"}
    for v in valid:
        if v in result:
            return v
    return ""


def _assign_text_animations(elements: list, fps: float, style_hint: str = ""):
    """为文字元素分配 Kinetic Typography 动画。

    Staging 原则：一次只揭示一个焦点。
    style_hint: VLM 分析的原视频文字动画风格（typewriter/blur_in/fade/mask_reveal/word_stagger）。
    """
    from scene_description import TextAnimationSpec

    texts = [e for e in elements if e.type == "text"]

    for i, txt in enumerate(texts):
        content = txt.content_text or ""
        char_count = len(content)
        has_newline = "\n" in content

        # 如果 VLM 检测到了文字动画风格，优先使用
        if style_hint in ("typewriter", "blur_in", "mask_reveal", "word_stagger"):
            entrance = style_hint
            if style_hint == "typewriter":
                split_mode = "char"
            elif style_hint == "mask_reveal":
                split_mode = "line"
            elif style_hint == "blur_in":
                split_mode = "word"
            else:
                split_mode = "word"
        else:
            # fallback: 按字数选择
            if char_count <= 4:
                entrance = "char_pop"
                split_mode = "char"
            elif has_newline or char_count > 20:
                entrance = "mask_reveal"
                split_mode = "line"
            elif char_count <= 15:
                entrance = "word_stagger"
                split_mode = "word"
            else:
                entrance = "word_stagger"
                split_mode = "word"

        # 首个文字 = 焦点区，后续文字也进焦点区（渲染器串行排程）
        zone = "focus"

        txt.text_animation = TextAnimationSpec(
            entrance=entrance,
            exit="fade_up",
            split_mode=split_mode,
            direction="center",
            zone=zone,
        )

    if texts:
        logger.info(
            f"文字动画: {len(texts)}个, "
            f"技法={[t.text_animation.entrance if t.text_animation else '?' for t in texts]}"
        )


def _link_tracks_to_elements(motion_tracks, elements):
    """将运动轨迹的 keyframes 关联到最近的元素的 motion_path。

    匹配逻辑：motion_track 首帧位置 (x%, y%) 与 element.spatial (x%, y%) 最近邻。
    """
    if not motion_tracks or not elements:
        return

    used = set()
    for track in motion_tracks:
        if not track.keyframes:
            continue
        kf0 = track.keyframes[0]
        tx = kf0.x if kf0.x is not None else 50.0
        ty = kf0.y if kf0.y is not None else 50.0

        best_dist = float('inf')
        best_idx = -1
        for i, elem in enumerate(elements):
            if i in used:
                continue
            dx = elem.spatial.x - tx
            dy = elem.spatial.y - ty
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0 and best_dist < 30:  # 30% 阈值
            elements[best_idx].motion_path = track.keyframes
            used.add(best_idx)


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _samples_to_keyframes(samples, fps: float, eps: float = 2.0):
    """MotionSample → 稀疏 Keyframe（RDP 简化）。"""
    from scene_description import Keyframe, _rdp_simplify

    if not samples:
        return []

    raw_points = []
    for s in samples:
        frame = int(s.t * fps)
        raw_points.append({
            "frame": frame,
            "x": s.x * 100,
            "y": s.y * 100,
            "rotation": getattr(s, "rotation", 0.0) or 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "opacity": getattr(s, "opacity", 1.0) or 1.0,
        })

    if len(raw_points) <= 2:
        return [Keyframe(frame=p["frame"], x=p["x"], y=p["y"],
                         rotation=p["rotation"], opacity=p["opacity"])
                for p in raw_points]

    simplified_indices = _rdp_simplify(
        [(p["x"], p["y"]) for p in raw_points], eps
    )

    keyframes = []
    for idx in simplified_indices:
        p = raw_points[idx]
        keyframes.append(Keyframe(
            frame=p["frame"], x=round(p["x"], 2), y=round(p["y"], 2),
            rotation=round(p["rotation"], 1), scale_x=p["scale_x"],
            scale_y=p["scale_y"], opacity=round(p["opacity"], 2), easing="ease-out",
        ))

    # 确保首尾
    if keyframes and keyframes[0].frame != raw_points[0]["frame"]:
        p = raw_points[0]
        keyframes.insert(0, Keyframe(frame=p["frame"], x=p["x"], y=p["y"],
                                     rotation=p["rotation"], opacity=p["opacity"]))
    if keyframes and keyframes[-1].frame != raw_points[-1]["frame"]:
        p = raw_points[-1]
        keyframes.append(Keyframe(frame=p["frame"], x=p["x"], y=p["y"],
                                  rotation=p["rotation"], opacity=p["opacity"]))

    return keyframes


# ── beat_sheet 自动抽取 ───────────────────────────────────────────────────

def build_beat_sheet(decomp: VideoDecomposition) -> BeatStructure:
    """从 VideoDecomposition 自动抽取 beat_sheet。

    每个场景 → 一个 beat，包含 role/layout/duration/transition/pattern/slots。
    """
    beats = []
    for sc in decomp.scenes:
        slots = []
        for el in sc.elements:
            slots.append(BeatSlot(
                element_type=el.type,
                role=el.role,
                text_length=len(el.content_text) if el.content_text else 0,
            ))

        # 检测运动模式
        pattern_name = ""
        pattern_params = {}
        if sc.motion_tracks and len(sc.motion_tracks) >= 2:
            pattern_name, pattern_params = _detect_motion_pattern(sc.motion_tracks)

        beats.append(BeatEntry(
            role=sc.scene_role,
            layout=sc.layout_type,
            duration_frames=sc.duration_frames,
            transition_in=sc.entrance_transition.get("type", "cut"),
            transition_direction=sc.entrance_transition.get("direction", ""),
            pattern=pattern_name,
            pattern_params=pattern_params,
            slots=slots,
        ))

    return BeatStructure(
        beats=beats,
        global_palette=decomp.global_color_palette,
        canvas=(decomp.canvas_width, decomp.canvas_height),
        fps=decomp.fps,
        source_video=decomp.source_video,
    )


def _detect_motion_pattern(tracks) -> tuple[str, dict]:
    """从多个运动轨迹中检测运动模式。"""
    if len(tracks) < 2:
        return "", {}

    # 检查入场时间是否有规律间隔
    entrance_frames = []
    for t in tracks:
        if t.keyframes:
            entrance_frames.append(t.keyframes[0].frame)

    if len(entrance_frames) >= 2:
        entrance_frames.sort()
        diffs = [entrance_frames[i+1] - entrance_frames[i] for i in range(len(entrance_frames)-1)]
        avg_diff = sum(diffs) / len(diffs)

        # 间隔一致 → cascade_stack
        if all(abs(d - avg_diff) < avg_diff * 0.3 for d in diffs) and avg_diff > 3:
            return "cascade_stack", {"count": len(tracks), "stagger_frames": int(avg_diff)}

    # 检查运动方向是否一致
    directions = []
    for t in tracks:
        if len(t.keyframes) >= 2:
            dx = (t.keyframes[-1].x or 50) - (t.keyframes[0].x or 50)
            dy = (t.keyframes[-1].y or 50) - (t.keyframes[0].y or 50)
            directions.append((dx, dy))

    if len(directions) >= 2:
        # 方向一致 → parallax
        avg_dx = sum(d[0] for d in directions) / len(directions)
        avg_dy = sum(d[1] for d in directions) / len(directions)
        consistent = all(
            abs(d[0] - avg_dx) < abs(avg_dx) * 0.5 and abs(d[1] - avg_dy) < abs(avg_dy) * 0.5
            for d in directions if abs(avg_dx) > 1 or abs(avg_dy) > 1
        )
        if consistent and (abs(avg_dx) > 3 or abs(avg_dy) > 3):
            return "parallax", {"dx": round(avg_dx, 1), "dy": round(avg_dy, 1)}

    return "", {}


# ── 主入口 ────────────────────────────────────────────────────────────────

def decompose_video(video_path: str, output_dir: str = "") -> VideoDecomposition:
    """将参考视频分解为多个场景 + 自动抽取 beat_sheet。

    完整流程:
    1. Shot 检测 → shot = scene
    2. 逐场景窗口化提取 (SAM2 + OCR + VLM)
    3. 元素融合去重
    4. beat_sheet 自动抽取
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # 创建输出目录（用于保存裁剪的图片）
    if not output_dir:
        import uuid
        output_dir = os.path.join("data", "output", uuid.uuid4().hex[:8])
    os.makedirs(output_dir, exist_ok=True)

    decomp = VideoDecomposition(
        source_video=video_path,
        canvas_width=width,
        canvas_height=height,
        fps=int(fps),
        total_frames=total_frames,
    )

    # Step 1: Shot 检测
    shots = detect_shots(video_path)
    if not shots:
        logger.warning("未检测到 shot，使用整条视频作为单场景")
        shots = [{"index": 0, "start_frame": 0, "end_frame": total_frames,
                  "start_time": 0, "end_time": total_frames / fps}]

    # 全局调色板（第一帧）
    from vision_analyzer import extract_dominant_colors
    cap = cv2.VideoCapture(video_path)
    ret, first = cap.read()
    if ret:
        colors = extract_dominant_colors(first, k=5)
        decomp.global_color_palette = [c.hex for c in colors]
    cap.release()

    # Step 2: 逐场景提取
    for shot in shots:
        scene = extract_scene(video_path, shot, fps, width, height, output_dir=output_dir)
        decomp.scenes.append(scene)

    # Step 3: beat_sheet 抽取
    decomp.beat_structure = build_beat_sheet(decomp)

    logger.info(
        f"视频分解完成: {len(decomp.scenes)} 场景, "
        f"{sum(len(s.elements) for s in decomp.scenes)} 元素, "
        f"{len(decomp.beat_structure.beats)} beats"
    )

    return decomp


def decomposition_to_dict(decomp: VideoDecomposition) -> dict:
    """序列化 VideoDecomposition，元素帧号归一化为 scene-local。"""
    from dataclasses import asdict
    d = asdict(decomp)

    # 将元素的 in_point/out_point 归一化为 scene-local（从 0 开始）
    # 并写入 layout_type 和 slot（CSS Grid 槽位名）
    for sc_idx, sc_d in enumerate(d.get("scenes", [])):
        start = sc_d.get("start_frame", 0)
        # 写入 layout_type 和 mode
        scene_obj = decomp.scenes[sc_idx] if sc_idx < len(decomp.scenes) else None
        if scene_obj:
            sc_d["layout_type"] = scene_obj.layout_type
            sc_d["mode"] = scene_obj.mode
            sc_d["archetype"] = scene_obj.archetype
            sc_d["vlm_layout"] = scene_obj.vlm_layout

        for el_idx, el_d in enumerate(sc_d.get("elements", [])):
            timing = el_d.get("timing", {})

            # 写入 slot 和 timing（从 scene_obj 的元素，它们已经是 scene-local）
            if scene_obj and el_idx < len(scene_obj.elements):
                elem_obj = scene_obj.elements[el_idx]
                slot = getattr(elem_obj, '_grid_slot', '')
                el_d["slot"] = slot

                # 归一化为 scene-local timing（减去场景起始帧）
                timing["in_point"] = max(0, elem_obj.timing.in_point - start)
                timing["out_point"] = max(0, elem_obj.timing.out_point - start)

                # 归一化 content_src: 绝对路径 → 相对 web/public 的路径
                cs = el_d.get("content_src", "")
                if cs:
                    # 提取 "data/output/xxx/file.jpg" 部分
                    marker = "data/output/"
                    idx = cs.find(marker)
                    if idx >= 0:
                        el_d["content_src"] = cs[idx:]
                    elif cs.startswith("/"):
                        el_d["content_src"] = cs.lstrip("/")

                # 写入 text_animation
                if elem_obj.text_animation:
                    el_d["text_animation"] = {
                        "entrance": elem_obj.text_animation.entrance,
                        "exit": elem_obj.text_animation.exit,
                        "split_mode": elem_obj.text_animation.split_mode,
                        "direction": elem_obj.text_animation.direction,
                        "zone": elem_obj.text_animation.zone,
                    }

    return d


def decomposition_from_dict(d: dict) -> VideoDecomposition:
    """反序列化 VideoDecomposition。"""
    from scene_description import Keyframe, MotionTrack, SceneElement, SpatialProps, AppearanceProps, TypographyProps, AnimationSpec, TimingProps

    decomp = VideoDecomposition(
        source_video=d.get("source_video", ""),
        canvas_width=d.get("canvas_width", 1080),
        canvas_height=d.get("canvas_height", 1920),
        fps=d.get("fps", 30),
        total_frames=d.get("total_frames", 0),
        global_color_palette=d.get("global_color_palette", []),
    )

    for sc_d in d.get("scenes", []):
        scene = VideoScene(
            scene_index=sc_d.get("scene_index", 0),
            start_frame=sc_d.get("start_frame", 0),
            end_frame=sc_d.get("end_frame", 0),
            duration_frames=sc_d.get("duration_frames", 0),
            background_color=sc_d.get("background_color", "#000000"),
            layout_type=sc_d.get("layout_type", "centered"),
            mode=sc_d.get("mode", "grid"),
            archetype=sc_d.get("archetype", ""),
            scene_role=sc_d.get("scene_role", "unknown"),
            visual_summary=sc_d.get("visual_summary", ""),
            design_style=sc_d.get("design_style", "minimal"),
            entrance_transition=sc_d.get("entrance_transition", {"type": "cut"}),
            transition_out=sc_d.get("transition_out", {"type": "fade", "direction": ""}),
            source=sc_d.get("source", "measured"),
            confidence=sc_d.get("confidence", 1.0),
        )

        for el_d in sc_d.get("elements", []):
            motion_path = []
            for kf_d in el_d.get("motion_path", []):
                motion_path.append(Keyframe(
                    frame=kf_d.get("frame", 0),
                    x=kf_d.get("x"), y=kf_d.get("y"),
                    rotation=kf_d.get("rotation"),
                    scale_x=kf_d.get("scale_x"), scale_y=kf_d.get("scale_y"),
                    opacity=kf_d.get("opacity"),
                    easing=kf_d.get("easing", "ease-out"),
                ))

            elem = SceneElement(
                id=el_d.get("id", ""),
                type=el_d.get("type", "text"),
                content_text=el_d.get("content_text", ""),
                content_src=el_d.get("content_src", ""),
                spatial=SpatialProps(**{k: el_d.get("spatial", {}).get(k, v)
                                       for k, v in SpatialProps().__dict__.items()}),
                appearance=AppearanceProps(**{k: el_d.get("appearance", {}).get(k, v)
                                             for k, v in AppearanceProps().__dict__.items()}),
                typography=TypographyProps(**{k: el_d.get("typography", {}).get(k, v)
                                             for k, v in TypographyProps().__dict__.items()}),
                timing=TimingProps(**{k: el_d.get("timing", {}).get(k, v)
                                     for k, v in TimingProps().__dict__.items()}),
                motion_path=motion_path,
                z_order=el_d.get("z_order", 0),
                role=el_d.get("role", "unknown"),
                source=el_d.get("source", "measured"),
                track_confidence=el_d.get("track_confidence", 1.0),
            )
            # 反序列化 text_animation
            ta_d = el_d.get("text_animation")
            if ta_d:
                from scene_description import TextAnimationSpec
                elem.text_animation = TextAnimationSpec(
                    entrance=ta_d.get("entrance", "word_stagger"),
                    exit=ta_d.get("exit", "fade_up"),
                    split_mode=ta_d.get("split_mode", "word"),
                    direction=ta_d.get("direction", "center"),
                    zone=ta_d.get("zone", "focus"),
                )
            scene.elements.append(elem)

        for mt_d in sc_d.get("motion_tracks", []):
            kfs = []
            for kf_d in mt_d.get("keyframes", []):
                kfs.append(Keyframe(
                    frame=kf_d.get("frame", 0),
                    x=kf_d.get("x"), y=kf_d.get("y"),
                    rotation=kf_d.get("rotation"),
                    opacity=kf_d.get("opacity"),
                    easing=kf_d.get("easing", "ease-out"),
                ))
            scene.motion_tracks.append(MotionTrack(
                element_id=mt_d.get("element_id", ""),
                keyframes=kfs,
                z_order=mt_d.get("z_order", 0),
                role=mt_d.get("role", "unknown"),
                pattern=mt_d.get("pattern", ""),
                source=mt_d.get("source", "measured"),
                confidence=mt_d.get("confidence", 1.0),
            ))

        decomp.scenes.append(scene)

    # beat_structure
    bs_d = d.get("beat_structure")
    if bs_d:
        beats = []
        for b in bs_d.get("beats", []):
            slots = [BeatSlot(**s) for s in b.get("slots", [])]
            beats.append(BeatEntry(
                role=b.get("role", "unknown"),
                layout=b.get("layout", "centered"),
                duration_frames=b.get("duration_frames", 0),
                transition_in=b.get("transition_in", "cut"),
                transition_direction=b.get("transition_direction", ""),
                pattern=b.get("pattern", ""),
                pattern_params=b.get("pattern_params", {}),
                slots=slots,
            ))
        decomp.beat_structure = BeatStructure(
            beats=beats,
            global_palette=bs_d.get("global_palette", []),
            canvas=tuple(bs_d.get("canvas", [1080, 1920])),
            fps=bs_d.get("fps", 30),
            source_video=bs_d.get("source_video", ""),
        )

    return decomp


# ── LLM 作曲家桥接 ────────────────────────────────────────────────────────

SPRING_PRESETS = {
    "snappy": {"stiffness": 200, "damping": 18},
    "bouncy": {"stiffness": 180, "damping": 10},
    "smooth": {"stiffness": 90, "damping": 20},
}


def compose_scene_animations(decomp: VideoDecomposition, topic: str = "") -> VideoDecomposition:
    """调用 LLM 为每个场景选择动效参数（spring/idle/out/direction）。

    这是"LLM 作曲家"的入口：decompose_video 之后、渲染之前调用。
    直接修改 decomp 中的元素属性。
    """
    import os
    api_key = os.environ.get("MIMO_API_KEY", "")
    if not api_key:
        logger.warning("无 MIMO_API_KEY，跳过 LLM 作曲家")
        return decomp

    # 构建场景描述
    scene_descs = []
    for sc in decomp.scenes:
        imgs = [e for e in sc.elements if e.type == "image"]
        txts = [e for e in sc.elements if e.type == "text"]
        desc = (
            f"场景{sc.scene_index} ({sc.duration_frames/decomp.fps:.1f}s): "
            f"{len(imgs)}图+{len(txts)}文, 布局={sc.layout_type}, 角色={sc.scene_role}, "
            f"背景={sc.background_color}"
        )
        if txts:
            desc += f", 文字={[t.content_text[:10] for t in txts]}"
        scene_descs.append(desc)

    scenes_text = "\n".join(scene_descs)

    prompt = f"""你是短视频动画导演。主题: {topic or '通用'}

以下是视频的场景结构：
{scenes_text}

为每个场景选择动效参数。返回 JSON：
{{
  "animations": [
    {{"scene": 0, "spring": "snappy", "idle": "float", "out": "fade", "direction": "bottom", "transition": "fade", "transition_direction": ""}},
    {{"scene": 1, "spring": "bouncy", "idle": "breathe", "out": "fade_scale", "direction": "left", "transition": "slide", "transition_direction": "right"}}
  ]
}}

每个场景可选：
- spring: 'snappy'(利落) / 'bouncy'(回弹) / 'smooth'(柔和)
- idle: 'float'(上下浮动) / 'breathe'(缩放呼吸) / 'rotate'(慢旋) / 'none'(静止)
- out: 'fade'(淡出) / 'fade_scale'(缩小淡出) / 'slide_left'/'slide_right'/'slide_up'
- direction: 'top'/'bottom'/'left'/'right'/'center'
- transition: 该场景结束时的转场: 'fade'(默认) / 'slide' / 'clockWipe' / 'cut'(硬切)
- transition_direction: slide 方向: 'left'/'right'/'top'/'bottom'
- text_entrance: 文字入场技法: 'word_stagger'(逐词淡入) / 'char_pop'(逐字弹入) / 'mask_reveal'(遮罩刷出) / 'blur_in'(模糊清晰) / 'typewriter'(打字) / 'line_split'(两行分开)
- text_exit: 文字出场: 'fade_up'(上移淡出) / 'mask_out'(遮罩收) / 'scale_down'(缩小) / 'none'

hook 场景用 snappy+float，feature 用 bouncy+breathe，cta 用 smooth+none。
文字动画：短词(≤4字)用 char_pop，一句话用 word_stagger，标题用 mask_reveal。
场景间转场默认 fade，不要用 cut（硬切=PPT感）。
只输出 JSON。"""

    try:
        import httpx
        resp = httpx.post(
            os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"),
            json={
                "model": os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        if resp.status_code == 200:
            msg = resp.json()["choices"][0]["message"]
            raw = msg.get("content", "").strip() or msg.get("reasoning_content", "").strip()
            data = json.loads(raw)
            animations = data.get("animations", [])

            # 应用动效参数到元素
            for anim in animations:
                sc_idx = anim.get("scene", -1)
                if 0 <= sc_idx < len(decomp.scenes):
                    sc = decomp.scenes[sc_idx]
                    spring_name = anim.get("spring", "snappy")
                    idle = anim.get("idle", "none")
                    out = anim.get("out", "fade")
                    direction = anim.get("direction", "")

                    spring_vals = SPRING_PRESETS.get(spring_name, SPRING_PRESETS["snappy"])

                    for elem in sc.elements:
                        # 注入动效属性（渲染器会读取）
                        elem.effect_type = idle if idle != "none" else ""
                        # 通过 timing.entrance 传递 spring 和 direction
                        if elem.timing.entrance:
                            if direction:
                                elem.timing.entrance.direction = direction
                        # 通过 timing.exit 传递出场方式
                        if elem.timing.exit:
                            exit_map = {"fade": "fade", "fade_scale": "scale", "slide_left": "slide", "slide_right": "slide", "slide_up": "slide"}
                            elem.timing.exit.type = exit_map.get(out, "fade")

                        # 文字动画（Kinetic Typography）
                        if elem.type == "text":
                            from scene_description import TextAnimationSpec
                            text_entrance = anim.get("text_entrance", "")
                            text_exit = anim.get("text_exit", "")
                            if text_entrance:
                                split_mode = "char" if text_entrance == "char_pop" else "word"
                                if text_entrance == "mask_reveal":
                                    split_mode = "line"
                                elem.text_animation = TextAnimationSpec(
                                    entrance=text_entrance,
                                    exit=text_exit or "fade_up",
                                    split_mode=split_mode,
                                    direction=direction or "center",
                                    zone="focus",
                                )

                    # 设置场景转场（transition_out）
                    transition = anim.get("transition", "fade")
                    trans_dir = anim.get("transition_direction", "")
                    sc.transition_out = {"type": transition, "direction": trans_dir}

                    logger.info(f"场景{sc_idx}: spring={spring_name} idle={idle} out={out} dir={direction} trans={transition}")

            logger.info(f"LLM 作曲家: {len(animations)} 场景动效已注入")
        else:
            logger.warning(f"LLM 作曲家 HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"LLM 作曲家失败: {e}")

    return decomp


def decomposition_to_orchestrator_template(
    decomp: VideoDecomposition,
    topic: str = "",
    max_components_per_beat: int = 4,
) -> dict:
    """将 VideoDecomposition 转为 orchestrator 需要的 template 格式。

    核心原则: 只提取参考视频的**结构骨架**（节奏/时长/布局/元素数量），
    不传任何原文内容。LLM 根据新主题 + 结构骨架生成全新内容。

    Returns:
        template dict with beat_sheet
    """
    n_scenes = len(decomp.scenes)
    if n_scenes == 0:
        return {"beat_sheet": {"beats": []}}

    # 分配 phase: 按位置
    def _phase(i: int) -> str:
        if i == 0 or i <= n_scenes * 0.25:
            return "hook"
        elif i >= n_scenes * 0.75:
            return "cta"
        else:
            return "build"

    # D4: 每个场景一个 beat（不压缩到 3 个 phase，避免 LLM 只产几条文案）
    beats: list[dict] = []
    for i, sc in enumerate(decomp.scenes):
        phase = _phase(i)
        duration_s = max(0.8, round(sc.duration_frames / max(decomp.fps or 30, 1), 2))
        beat = {
            "id": f"s{i}",
            "beat": i,
            "role": phase,
            "layout": sc.vlm_layout or sc.layout_type or "grid",
            "duration_s": duration_s,
            "transition_in": "cut",
            "pattern": "",
            # 只提供 KineticText 文字槽位，下游风格迁移只取文字
            "components": [
                {"ref": "KineticText", "role": "hero_text", "position": "center"},
            ],
        }
        beats.append(beat)

    return {
        "template_id": f"decomp_{int(__import__('time').time())}",
        "topic": topic,
        "text": {
            "on_screen_text": [topic],
            "narration": f"关于{topic}的短视频",
        },
        "category": topic,
        "beat_sheet": {
            "canvas": {"width": decomp.canvas_width, "height": decomp.canvas_height, "fps": decomp.fps},
            "global_palette": decomp.global_color_palette,
            "beats": beats,
        },
    }


# ── motion_path 生成：VLM 动画类型 → 关键帧 ──────────────────────────────

def generate_motion_paths_for_decomp(d: dict, scene_motions: list[dict], fps: int = 30):
    """根据 VLM 运动分析结果，为每个元素生成 motion_path 关键帧。

    VLM 识别的动画类型 → 生成对应的连续运动轨迹。
    这解决了 RAFT 光流抓不到场景级动画（淡入/平移/缩放）的问题。
    """
    import math

    # D3: 相对关键帧生成器（契约 2）
    # 格式: {"frame": int, "dx": float, "dy": float, "scale": float, "opacity": float, "easing": str}
    # dx/dy = 画布百分比偏移（振幅 ≤8），scale = 缩放倍数（0.9~1.1），opacity 0~1
    # 渲染端靠 "dx" 键名识别新格式。

    def _kf(frame: int, dx: float = 0.0, dy: float = 0.0, scale: float = 1.0,
            opacity: float = 1.0, easing: str = "ease-out") -> dict:
        """构造标准相对关键帧（含全部 6 个必要键）。"""
        return {"frame": frame, "dx": round(dx, 3), "dy": round(dy, 3),
                "scale": round(scale, 3), "opacity": round(opacity, 3), "easing": easing}

    def _gen_pan(duration_f: int, direction: str = "right") -> list[dict]:
        """平移：dx 从 ±6 收敛到 0（画布百分比偏移）。"""
        amp = 6.0
        start_dx = {"right": amp, "left": -amp, "top": 0.0, "bottom": 0.0}.get(direction, amp)
        start_dy = {"top": -amp, "bottom": amp}.get(direction, 0.0) if direction in ("top", "bottom") else 0.0
        kfs = []
        for ratio in [0, 0.3, 0.7, 1.0]:
            frame = int(duration_f * ratio)
            dx = start_dx * (1 - ratio)
            dy = start_dy * (1 - ratio)
            kfs.append(_kf(frame, dx=dx, dy=dy))
        return kfs

    def _gen_scale(duration_f: int) -> list[dict]:
        """缩放：scale 0.94→1.0 配 opacity 0→1。"""
        kfs = []
        for ratio in [0, 0.2, 0.5, 1.0]:
            frame = int(duration_f * ratio)
            s = 0.94 + 0.06 * ratio
            kfs.append(_kf(frame, scale=s, opacity=ratio))
        return kfs

    def _gen_fade(duration_f: int) -> list[dict]:
        """淡入：仅 opacity 0→1，位置/缩放不变。"""
        kfs = []
        for ratio in [0, 0.2, 0.5, 1.0]:
            frame = int(duration_f * ratio)
            kfs.append(_kf(frame, opacity=ratio))
        return kfs

    def _gen_float(duration_f: int) -> list[dict]:
        """飘浮：dy 正弦 ±1.2（8 个关键帧）。"""
        kfs = []
        for i in range(8):
            ratio = i / 7
            frame = int(duration_f * ratio)
            dy = 1.2 * math.sin(ratio * math.pi * 2)
            kfs.append(_kf(frame, dy=dy, easing="linear"))
        return kfs

    def _gen_elastic(duration_f: int) -> list[dict]:
        """弹性：scale 1±0.06 衰减。"""
        kfs = []
        for i in range(8):
            ratio = i / 7
            frame = int(duration_f * ratio)
            s = 1.0 + 0.06 * math.sin(ratio * math.pi * 3) * math.exp(-ratio * 2)
            s = round(max(0.9, min(1.1, s)), 3)
            kfs.append(_kf(frame, scale=s))
        return kfs

    def _gen_cascade(duration_f: int, n_elements: int, el_idx: int) -> list[dict]:
        """级联：按 el_idx 延迟的 opacity 0→1 配 dy 4→0。"""
        delay_ratio = el_idx / max(n_elements, 1) * 0.3
        kfs = []
        for ratio in [0, delay_ratio, delay_ratio + 0.1, 1.0]:
            ratio = min(ratio, 1.0)
            frame = int(duration_f * ratio)
            opacity = 0.0 if ratio < delay_ratio else min(1.0, (ratio - delay_ratio) / max(0.1, 0.001))
            dy = 4.0 * (1 - opacity)
            kfs.append(_kf(frame, dy=dy, opacity=opacity))
        return kfs

    # VLM 描述 → 动画类型映射
    MOTION_MAP = {
        "平移": "pan", "移动": "pan", "滑入": "pan",
        "缩放": "scale", "放大": "scale",
        "淡入": "fade", "淡出": "fade", "淡入淡出": "fade",
        "飘浮": "float", "浮动": "float",
        "弹性": "elastic", "回弹": "elastic",
        "级联": "cascade", "依次": "cascade",
        "旋转": "rotate",
    }

    for i, sc in enumerate(d["scenes"]):
        # 获取该场景的 VLM 运动描述
        motion_desc = ""
        if i < len(scene_motions):
            motion_desc = scene_motions[i].get("desc", "")

        # 解析动画类型
        detected_types = []
        for keyword, anim_type in MOTION_MAP.items():
            if keyword in motion_desc:
                detected_types.append(anim_type)

        if not detected_types:
            detected_types = ["fade"]  # 默认淡入

        duration_f = sc.get("duration_frames", 90)
        imgs = [el for el in sc["elements"] if el.get("type") == "image" and el.get("content_src")]

        for el_idx, el in enumerate(imgs):
            # 为每个元素选择动画类型（轮转分配，增加多样性）
            anim_type = detected_types[el_idx % len(detected_types)]

            if anim_type == "pan":
                direction = ["right", "left", "top", "bottom"][el_idx % 4]
                el["motion_path"] = _gen_pan(duration_f, direction)
            elif anim_type == "scale":
                el["motion_path"] = _gen_scale(duration_f)
            elif anim_type == "fade":
                el["motion_path"] = _gen_fade(duration_f)
            elif anim_type == "float":
                el["motion_path"] = _gen_float(duration_f)
            elif anim_type == "elastic":
                el["motion_path"] = _gen_elastic(duration_f)
            elif anim_type == "cascade":
                el["motion_path"] = _gen_cascade(duration_f, len(imgs), el_idx)
            else:
                el["motion_path"] = _gen_fade(duration_f)
