"""SceneDescription — 完整场景描述 schema。

用于从参考视频中提取每个元素的精确属性（位置、颜色、文字、动画），
实现真正的视觉风格迁移。

与 StyleToken 的区别：
- StyleToken: 22 个全局值，只能描述 "mood"
- SceneDescription: 每元素 50+ 属性，描述完整场景结构
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


def _get_mimo_env():
    """懒加载 MIMO 环境变量（避免模块加载时 .env 未就绪）。"""
    return (
        os.environ.get("MIMO_API_KEY", ""),
        os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"),
        os.environ.get("MIMO_VLM_MODEL", "mimo-v2.5"),
    )


# ── Schema ────────────────────────────────────────────────────────────────

@dataclass
class SpatialProps:
    """空间属性。"""
    x: float = 50.0           # % 相对于画布
    y: float = 50.0
    width: float = 100.0      # % 相对于画布
    height: float = 100.0
    anchor_x: float = 0.5     # 锚点 0-1
    anchor_y: float = 0.5
    rotation: float = 0.0     # 度
    scale_x: float = 1.0
    scale_y: float = 1.0
    z_index: int = 0


@dataclass
class AppearanceProps:
    """外观属性。"""
    opacity: float = 1.0      # 0-1
    fill: str = "#000000"     # 颜色/渐变
    stroke: str = ""
    stroke_width: float = 0.0
    border_radius: float = 0.0
    shadow: str = ""          # CSS shadow 字符串
    blend_mode: str = "normal"
    blur: float = 0.0


@dataclass
class TypographyProps:
    """排版属性（仅 text 类型）。"""
    font_family: str = "sans-serif"
    font_size: float = 4.0    # % 相对于画布高度
    font_weight: int = 400
    line_height: float = 1.2
    letter_spacing: float = 0.0
    text_align: str = "left"
    color: str = "#000000"
    gradient: str = ""
    text_transform: str = "none"  # uppercase/lowercase/none


@dataclass
class TextAnimationSpec:
    """文字动画规格（Kinetic Typography）。

    Staging 原则：同一时刻焦点区只揭示一个文字。
    入场技法选自封闭表：word_stagger / char_pop / mask_reveal / blur_in / typewriter / line_split
    """
    entrance: str = "word_stagger"   # word_stagger/char_pop/mask_reveal/blur_in/typewriter/line_split/scroll_list_pointer/none
    exit: str = "fade_up"            # fade_up/mask_out/scale_down/none
    split_mode: str = "word"         # char/word/line — 切分粒度
    direction: str = "center"        # left/right/center/top/bottom — 引导视线
    zone: str = "focus"              # focus（焦点区，串行）/ corner（常驻区，不竞争）


@dataclass
class Keyframe:
    """单个关键帧 — 从视频测量得到的真实运动数据。"""
    frame: int                # 帧号（绝对）
    x: float | None = None    # 位置 %（None = 不变）
    y: float | None = None
    rotation: float | None = None     # 度
    scale_x: float | None = None
    scale_y: float | None = None
    opacity: float | None = None      # 0-1
    easing: str = "ease-out"          # 到此关键帧的缓动


@dataclass
class MotionTrack:
    """一个元素的完整运动轨迹 — CV 测量 + VLM 语义标注。"""
    element_id: str = ""
    keyframes: list[Keyframe] = field(default_factory=list)
    z_order: int = 0                  # 从遮挡关系测量
    role: str = "unknown"             # VLM 语义标签: title/card/background/icon/text
    pattern: str = ""                 # 命中的模式名: cascade_stack/orbit/parallax/...
    pattern_params: dict = field(default_factory=dict)  # 模式参数
    source: str = "measured"          # measured / vlm_fallback
    confidence: float = 1.0           # 追踪质量


@dataclass
class AnimationSpec:
    """动画规格。"""
    type: str = "none"        # fade/slide/scale/rotate/clip/3d/blur/none
    direction: str = ""       # left/right/top/bottom/center
    duration: int = 15        # 帧数
    easing: str = "ease-out"  # linear/ease-in/ease-out/ease-in-out/spring/bounce
    start_value: float = 0.0
    end_value: float = 1.0


@dataclass
class TimingProps:
    """时间属性。"""
    in_point: int = 0         # 入场帧
    out_point: int = 30       # 出场帧
    entrance: AnimationSpec = field(default_factory=AnimationSpec)
    exit: AnimationSpec = field(default_factory=lambda: AnimationSpec(type="fade", start_value=1.0, end_value=0.0))
    stagger_index: int = 0
    stagger_delay: int = 0


@dataclass
class SceneElement:
    """场景中的一个元素。"""
    id: str = ""
    type: str = "text"        # text/image/shape/group
    content_text: str = ""    # 文字内容
    content_src: str = ""     # 图片路径
    spatial: SpatialProps = field(default_factory=SpatialProps)
    appearance: AppearanceProps = field(default_factory=AppearanceProps)
    typography: TypographyProps = field(default_factory=TypographyProps)
    timing: TimingProps = field(default_factory=TimingProps)

    # 连续运动（从视频测量得到，渲染时逐帧插值）
    motion_path: list[Keyframe] = field(default_factory=list)
    z_order: int = 0                  # 可测量的层级（遮挡顺序）
    role: str = "unknown"             # VLM 语义标签: title/card/background/icon/text
    source: str = "measured"          # measured / vlm_fallback（审计用）
    track_confidence: float = 1.0     # 追踪质量，低于阈值降级
    effect_type: str = ""             # 动效标签: pop_in/scatter/flip/scale_pulse/rotate_180/...
    effect_tier: str = ""             # A/B/C
    text_animation: TextAnimationSpec | None = None  # 文字动画规格（仅 text 类型）


@dataclass
class TransitionSpec:
    """转场规格。"""
    type: str = "cut"         # cut/fade/wipe/slide/morph
    duration: int = 10        # 帧数
    direction: str = ""       # left/right/top/bottom
    easing: str = "ease-out"


@dataclass
class SceneDescription:
    """完整场景描述。"""
    canvas_width: int = 1080
    canvas_height: int = 1920
    fps: int = 30
    duration: int = 0         # 总帧数
    background_color: str = "#000000"
    background_gradient: str = ""

    elements: list[SceneElement] = field(default_factory=list)
    transitions: list[TransitionSpec] = field(default_factory=list)
    motion_patterns: list[dict] = field(default_factory=list)  # 检测到的运动模式
    motion_tracks: list[MotionTrack] = field(default_factory=list)  # CV 测量的运动轨迹

    # 提取元数据
    source_video: str = ""
    extraction_method: str = ""  # "cv_motion_fusion" / "vlm" / "opencv_fallback"
    style_profile: StyleProfile | None = None  # 提取的视觉风格


# ── 风格迁移: StyleProfile ──────────────────────────────────────────────────

# 封闭风格家族集（像布局家族一样，可控、可入 KB）
STYLE_FAMILIES = {
    "dark_neon_ui":   "暗色背景 + 霓虹光效 + 高对比 + UI/科技感",
    "bright_airy":    "明亮通透 + 柔和色彩 + 自然光 + 生活/美食",
    "retro_film":     "胶片质感 + 暖色调 + 颗粒 + 暗角 + 复古",
    "minimal_tech":   "极简 + 大量留白 + 冷色调 + 几何线条",
    "vibrant_social": "高饱和 + 对比色 + 活力 + 社交媒体风",
    "dark_cinematic": "暗色调 + 电影质感 + 浅景深 + 戏剧光",
}

# 风格家族 → AIGC prompt 修饰词
STYLE_AIGC_PROMPTS = {
    "dark_neon_ui": {
        "prefix": "dark moody background, neon-lit, high contrast, UI overlay aesthetic, tech interface,",
        "suffix": "dark theme, glowing accents, digital art style, cinematic lighting",
        "negative": "bright cheerful, realistic daytime photo, warm natural light, pastel colors",
    },
    "bright_airy": {
        "prefix": "bright airy natural light, soft pastel colors, lifestyle photography, warm tones,",
        "suffix": "clean minimal, soft shadows, natural daylight, editorial style",
        "negative": "dark moody, neon, high contrast, cyberpunk, heavy shadows",
    },
    "retro_film": {
        "prefix": "retro film photography, warm amber tones, film grain texture, vintage color grading,",
        "suffix": "analog film look, soft focus, nostalgic atmosphere, 35mm film",
        "negative": "digital clean, sharp modern, cold blue, sterile",
    },
    "minimal_tech": {
        "prefix": "minimalist clean design, white space, cool blue tones, geometric, tech aesthetic,",
        "suffix": "crisp lines, flat design, modern, sophisticated",
        "negative": "busy, cluttered, warm, vintage, organic, hand-drawn",
    },
    "vibrant_social": {
        "prefix": "vibrant saturated colors, bold contrast, social media aesthetic, energetic, dynamic,",
        "suffix": "eye-catching, pop art influence, high saturation, trending style",
        "negative": "muted, desaturated, minimalist, monochrome, subtle",
    },
    "dark_cinematic": {
        "prefix": "dark cinematic, dramatic lighting, shallow depth of field, film color grading,",
        "suffix": "movie still quality, anamorphic lens, teal and orange grade, atmospheric",
        "negative": "flat lighting, amateur, overexposed, washed out",
    },
}


@dataclass
class StyleProfile:
    """可迁移的视觉风格 token 集。

    从参考视频提取，应用到新内容的两个点:
    1. AIGC 生成时注入 prompt（最高杠杆）
    2. 渲染时叠风格图层栈（调色 + FX + overlay）
    """
    style_family: str = "dark_neon_ui"   # STYLE_FAMILIES 的 key

    # 调色板
    palette: dict = field(default_factory=lambda: {
        "bg_color": "#000000",
        "bg_gradient": "",
        "accent": "#3B82F6",
        "accent2": "#FFD60A",
        "text_color": "#FFFFFF",
    })

    # 调色/影调
    grade: dict = field(default_factory=lambda: {
        "brightness": 1.0,     # CSS filter 倍数
        "contrast": 1.0,
        "saturate": 1.0,
        "hue_rotate": 0,       # 度
        "temperature": "neutral",  # warm / cool / neutral
        "mood": "dark",         # dark / light
    })

    # 视觉特效（有/无 + 强度 0-1）
    fx: dict = field(default_factory=lambda: {
        "vignette": 0.0,
        "film_grain": 0.0,
        "light_leak": 0.0,
        "glow": 0.0,
        "gradient_mesh": 0.0,
    })

    # 叠加层
    overlay: dict = field(default_factory=lambda: {
        "has_logo": False,
        "logo_pos": "top_right",
        "has_frame": False,
        "ui_chrome": False,
    })

    # 排版风格
    typography: dict = field(default_factory=lambda: {
        "font_style": "sans",    # sans / serif / mono
        "weight": "bold",        # regular / medium / bold / heavy
        "case": "normal",        # upper / normal / lower
        "text_color": "#FFFFFF",
        "glow_text": False,
    })

    def to_aigc_prompt(self, base_prompt: str) -> str:
        """将 StyleProfile 注入 AIGC prompt。"""
        style = STYLE_AIGC_PROMPTS.get(self.style_family, STYLE_AIGC_PROMPTS["dark_neon_ui"])
        # 将 palette 颜色加入 prompt
        colors = f"color palette: {self.palette.get('bg_color','#000')}, {self.palette.get('accent','#3B82F6')}"
        return f"{style['prefix']} {base_prompt}, {colors}, {style['suffix']}"

    def to_css_filter(self) -> str:
        """生成 CSS filter 字符串（渲染时调色）。"""
        parts = []
        if self.grade["brightness"] != 1.0:
            parts.append(f"brightness({self.grade['brightness']})")
        if self.grade["contrast"] != 1.0:
            parts.append(f"contrast({self.grade['contrast']})")
        if self.grade["saturate"] != 1.0:
            parts.append(f"saturate({self.grade['saturate']})")
        if self.grade["hue_rotate"] != 0:
            parts.append(f"hue-rotate({self.grade['hue_rotate']}deg)")
        return " ".join(parts) if parts else "none"

    def to_dict(self) -> dict:
        """序列化。"""
        return {
            "style_family": self.style_family,
            "palette": self.palette,
            "grade": self.grade,
            "fx": self.fx,
            "overlay": self.overlay,
            "typography": self.typography,
        }

    @classmethod
    def from_dict(cls, d: dict) -> StyleProfile:
        """反序列化。"""
        return cls(
            style_family=d.get("style_family", "dark_neon_ui"),
            palette=d.get("palette", {}),
            grade=d.get("grade", {}),
            fx=d.get("fx", {}),
            overlay=d.get("overlay", {}),
            typography=d.get("typography", {}),
        )


# ── VLM 提取 ──────────────────────────────────────────────────────────────

def _vlm_call(frames_b64: list[str], prompt: str, max_tokens: int = 3000, retries: int = 3) -> str | None:
    """调用 VLM 分析帧。

    可靠性保障:
    - 图片压缩到 640px 宽（减少 payload → 减少超时）
    - 3 次重试 + 指数退避（1s, 2s, 4s）
    - 连接复用（httpx.Client）
    """
    import time as _time
    import base64 as _base64

    api_key, api_url, vlm_model = _get_mimo_env()
    if not api_key:
        logger.warning("MIMO_API_KEY 未设置，跳过 VLM 调用")
        return None

    # 压缩图片：缩放到 640px 宽，JPEG quality 70 → payload 减少 ~70%
    compressed_b64 = []
    for b64 in frames_b64:
        try:
            import cv2, numpy as np
            img_bytes = _base64.b64decode(b64)
            arr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                h, w = frame.shape[:2]
                if w > 640:
                    scale = 640 / w
                    frame = cv2.resize(frame, (640, int(h * scale)))
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                compressed_b64.append(_base64.b64encode(buf).decode())
            else:
                compressed_b64.append(b64)
        except Exception:
            compressed_b64.append(b64)

    content = []
    for b64 in compressed_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    content.append({"type": "text", "text": prompt})

    # 重试 + 指数退避
    for attempt in range(retries):
        try:
            resp = httpx.post(
                api_url,
                json={
                    "model": vlm_model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                },
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=120.0,
            )
            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                logger.info(f"VLM 限流，等待 {wait}s 重试 ({attempt+1}/{retries})")
                _time.sleep(wait)
                continue
            if resp.status_code != 200:
                logger.warning(f"VLM 调用失败: {resp.status_code} {resp.text[:200]}")
                if attempt < retries - 1:
                    _time.sleep(2 ** attempt)
                    continue
                return None
            msg = resp.json()["choices"][0]["message"]
            text = msg.get("content", "").strip()
            if not text:
                text = msg.get("reasoning_content", "").strip()
            return text if text else None
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            wait = 2 ** (attempt + 1)
            logger.warning(f"VLM 超时/连接失败 ({attempt+1}/{retries}): {e}, 等待 {wait}s")
            _time.sleep(wait)
        except Exception as e:
            logger.warning(f"VLM 异常: {e}")
            return None

    logger.warning(f"VLM 调用失败（已重试 {retries} 次）")
    return None


def _parse_json(text: str) -> dict | None:
    """从 VLM 输出中提取 JSON。"""
    import re
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def extract_scene_description(video_path: str, output_dir: str = "") -> SceneDescription:
    """从参考视频提取完整 SceneDescription。

    流程 (CV 测量 + VLM 语义):
    1. MotionAnalyzer: SAM2 元素发现 + RAFT/光流逐帧追踪 → MotionTrack 轨迹
    2. EasyOCR: 文字检测 + TextTracker 跨帧追踪
    3. 轨迹→关键帧: RDP 简化 MotionSample 为 Keyframe 序列
    4. VLM: 仅做 OCR 更正 + 语义角色标签（不出坐标）
    5. 运动模式分类: 从测量轨迹自动分类 cascade_stack/orbit/parallax
    6. 融合为 SceneDescription
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    scene = SceneDescription(
        canvas_width=width,
        canvas_height=height,
        fps=int(fps),
        duration=int(total_frames),
        source_video=video_path,
    )

    # ── Step 1: MotionAnalyzer — CV 测量运动轨迹 ──
    from motion_analyzer import MotionAnalyzer

    analyzer = MotionAnalyzer.create(video_path)
    timeline = analyzer.analyze(video_path)

    logger.info(f"MotionAnalyzer: {len(timeline.tracks)} 元素轨迹, "
                f"{len(timeline.motion_events)} 运动事件")

    # 背景色：第一帧主色调
    from vision_analyzer import extract_dominant_colors
    cap = cv2.VideoCapture(video_path)
    ret, first_frame = cap.read()
    if ret:
        colors = extract_dominant_colors(first_frame, k=3)
        if colors:
            scene.background_color = colors[0].hex
    cap.release()

    # ── Step 2: EasyOCR 文字检测 ──
    from vision_analyzer import detect_text_regions, TextTracker, adaptive_sample_frames

    sampled_frames = adaptive_sample_frames(video_path, target_frames=16)
    text_tracker = TextTracker()

    cap = cv2.VideoCapture(video_path)
    for frame_idx, ts in sampled_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue
        elements = detect_text_regions(frame)
        detections = [(e.bbox, e.text, e.color) for e in elements]
        text_tracker.update(frame_idx, detections)
    cap.release()

    text_tracks = text_tracker.get_final_elements()
    logger.info(f"EasyOCR: {len(text_tracks)} 个文字追踪")

    # ── Step 3: MotionSample → Keyframe 转换（RDP 简化）──
    motion_tracks = []
    for track in timeline.tracks:
        keyframes = _samples_to_keyframes(track.samples, fps)
        if not keyframes:
            continue
        mt = MotionTrack(
            element_id=f"motion_{track.element_id}",
            keyframes=keyframes,
            z_order=0,  # 后续由遮挡分析确定
            role="unknown",  # 后续由 VLM 标注
            source="measured",
            confidence=track.confidence,
        )
        motion_tracks.append(mt)

    logger.info(f"运动轨迹转换: {len(motion_tracks)} 个元素, "
                f"共 {sum(len(m.keyframes) for m in motion_tracks)} 个关键帧")

    # ── Step 4: VLM — 仅语义标注（OCR 更正 + 角色标签）──
    import base64
    frames_b64 = []
    cap = cv2.VideoCapture(video_path)
    for frame_idx, ts in sampled_frames[:8]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
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

    # OCR 结果
    ocr_lines = []
    for track in text_tracks:
        text = track.get("text", "")
        if text:
            ocr_lines.append(f'  "{text}"')
    ocr_text_block = "\n".join(ocr_lines[:20])

    # 运动轨迹摘要（给 VLM 看，不让它出坐标）
    motion_summary = []
    for i, mt in enumerate(motion_tracks[:10]):
        kfs = mt.keyframes
        if len(kfs) < 2:
            continue
        start = kfs[0]
        end = kfs[-1]
        dx = (end.x or 50) - (start.x or 50)
        dy = (end.y or 50) - (start.y or 50)
        dur = end.frame - start.frame
        direction = "left" if dx < -5 else "right" if dx > 5 else "up" if dy < -5 else "down" if dy > 5 else "static"
        motion_summary.append(
            f'  元素{i}: {direction}移动 dx={dx:.1f}% dy={dy:.1f}%, {dur}帧'
        )

    motion_block = "\n".join(motion_summary[:10]) if motion_summary else "无显著运动"

    # VLM prompt：只做语义分类，不出坐标
    vlm_prompt = f"""分析这些视频帧，完成以下任务：

【OCR 更正】
以下是 OCR 检测到的文字，请根据画面修正错误：
{ocr_text_block}

【运动元素角色标注】
以下是检测到的运动元素：
{motion_block}

对每个运动元素，判断它的角色（从以下选项选一个）：
- title: 标题文字
- card: 卡片/图片
- background: 背景
- icon: 图标/小装饰
- text: 正文文字
- logo: Logo

【运动模式判断】
整体运动模式是什么？（从以下选一个或多个）：
- cascade_stack: 元素依次入场后堆叠
- orbit: 元素环绕运动
- parallax: 前后层不同速度移动
- grid_pop: 网格弹出
- slide_swap: 滑动替换
- stagger: 交错入场
- none: 无明显模式

返回 JSON（只返回 JSON）：
{{
  "corrected_texts": [
    {{"ocr": "原始", "corrected": "修正后"}}
  ],
  "element_roles": [
    {{"index": 0, "role": "card"}}
  ],
  "motion_pattern": "cascade_stack",
  "transitions": [{{"type": "cut", "direction": ""}}]
}}"""

    vlm_result = _vlm_call(frames_b64, vlm_prompt) if frames_b64 else None
    vlm_structured = _parse_vlm_json(vlm_result) if vlm_result else None

    # ── Step 5: 融合 ──

    # OCR 更正
    corrected_map = {}
    if vlm_structured:
        for item in vlm_structured.get("corrected_texts", []):
            ocr = item.get("ocr", "")
            corrected = item.get("corrected", "")
            if ocr and corrected and ocr != corrected:
                corrected_map[ocr.lower()] = corrected

    # 角色标注
    role_map = {}
    if vlm_structured:
        for item in vlm_structured.get("element_roles", []):
            idx = item.get("index", -1)
            role = item.get("role", "unknown")
            if 0 <= idx < len(motion_tracks):
                role_map[idx] = role

    # 运动模式
    detected_pattern = ""
    if vlm_structured:
        detected_pattern = vlm_structured.get("motion_pattern", "")

    # 应用角色标注到运动轨迹
    for i, mt in enumerate(motion_tracks):
        mt.role = role_map.get(i, "unknown")
        mt.pattern = detected_pattern

    # ── Step 6: 构建 SceneElement ──

    elem_idx = 0

    # 6a: 从运动轨迹创建元素（图片/卡片/图形等非文字元素）
    for i, mt in enumerate(motion_tracks):
        # 跳过已被 EasyOCR 识别为文字的轨迹（避免重复）
        is_text = _is_text_track(mt, text_tracks, width, height)
        if is_text:
            continue

        kfs = mt.keyframes
        if not kfs:
            continue

        # 用第一个关键帧确定初始位置
        start_kf = kfs[0]
        x_pct = start_kf.x if start_kf.x is not None else 50.0
        y_pct = start_kf.y if start_kf.y is not None else 50.0

        # 估算尺寸（从 MotionSample）
        samples = timeline.tracks[i].samples if i < len(timeline.tracks) else []
        w_pct = samples[0].w * 100 if samples else 20.0
        h_pct = samples[0].h * 100 if samples else 20.0

        elem = SceneElement(
            id=f"elem_{elem_idx}",
            type="image",
            content_src="",
            spatial=SpatialProps(
                x=x_pct, y=y_pct,
                width=w_pct, height=h_pct,
                rotation=start_kf.rotation or 0.0,
            ),
            appearance=AppearanceProps(opacity=1.0),
            timing=TimingProps(
                in_point=int(kfs[0].frame),
                out_point=int(kfs[-1].frame),
                entrance=AnimationSpec(type="slide", direction="left", duration=15),
                exit=AnimationSpec(type="fade", duration=15, start_value=1.0, end_value=0.0),
            ),
            motion_path=kfs,
            z_order=mt.z_order,
            role=mt.role,
            source=mt.source,
            track_confidence=mt.confidence,
        )
        scene.elements.append(elem)
        elem_idx += 1

    # 6b: 从 EasyOCR 文字追踪创建文字元素
    for i, track in enumerate(text_tracks):
        matched_text = track.get("text", "")
        if not matched_text:
            continue

        # OCR 更正
        if matched_text.lower() in corrected_map:
            matched_text = corrected_map[matched_text.lower()]
        else:
            for ocr_key, corrected_val in corrected_map.items():
                from difflib import SequenceMatcher
                if SequenceMatcher(None, matched_text.lower(), ocr_key).ratio() > 0.8:
                    matched_text = corrected_val
                    break

        bx, by, bx2, by2 = track["bbox"]
        x_pct = round((bx + bx2) / 2 / width * 100, 1)
        y_pct = round((by + by2) / 2 / height * 100, 1)
        w_pct = round((bx2 - bx) / width * 100, 1)
        h_pct = round((by2 - by) / height * 100, 1)
        text_color = track.get("color", "#000000")

        # 为文字元素生成 motion_path（从 EasyOCR 追踪的位置变化）
        text_motion = _text_track_to_keyframes(track, fps)

        elem = SceneElement(
            id=f"elem_{elem_idx}",
            type="text",
            content_text=matched_text,
            spatial=SpatialProps(
                x=x_pct, y=y_pct,
                width=w_pct, height=h_pct,
            ),
            appearance=AppearanceProps(opacity=1.0, fill=text_color),
            typography=TypographyProps(
                font_family="sans-serif",
                font_size=round(h_pct * 0.8, 1),
                font_weight=700 if h_pct > 5 else 400,
                color=text_color,
            ),
            timing=TimingProps(
                in_point=track["first_frame"],
                out_point=track["last_frame"],
                entrance=AnimationSpec(type="fade", duration=15),
                exit=AnimationSpec(type="fade", duration=15, start_value=1.0, end_value=0.0),
                stagger_index=i,
                stagger_delay=i * 3,
            ),
            motion_path=text_motion,
            role="text",
            source="measured",
        )
        scene.elements.append(elem)
        elem_idx += 1

    # 转场
    for trans in (vlm_structured.get("transitions", []) if vlm_structured else []):
        scene.transitions.append(TransitionSpec(
            type=trans.get("type", "cut"),
            direction=trans.get("direction", ""),
        ))

    # 写入运动模式
    if detected_pattern:
        scene.motion_patterns.append({
            "name": detected_pattern,
            "element_ids": [mt.element_id for mt in motion_tracks],
            "confidence": min(mt.confidence for mt in motion_tracks) if motion_tracks else 0,
        })

    scene.motion_tracks = motion_tracks
    scene.extraction_method = "cv_motion_fusion"

    # ── Step 6: 提取 StyleProfile（CV + VLM）──
    try:
        scene.style_profile = extract_style_profile(video_path, first)
    except Exception as e:
        logger.warning(f"StyleProfile 提取失败: {e}")

    logger.info(
        f"SceneDescription 完成: {len(scene.elements)} 元素, "
        f"{len(scene.motion_tracks)} 运动轨迹, "
        f"{len(scene.motion_patterns)} 运动模式, "
        f"风格: {scene.style_profile.style_family if scene.style_profile else 'N/A'}, "
        f"模式: {detected_pattern or 'none'}"
    )

    return scene


def extract_style_profile(video_path: str, frame=None) -> StyleProfile:
    """从参考视频提取 StyleProfile（CV 测可量 + VLM 判语义）。

    CV: extract_dominant_colors → palette, 亮度/对比/饱和 → grade
    VLM: 判 style_family, fx (glow/grain/vignette), overlay (logo/UI)
    """
    import cv2
    import numpy as np
    from vision_analyzer import extract_dominant_colors

    profile = StyleProfile()

    # ── CV: 提取调色板和影调 ──
    if frame is None:
        cap = cv2.VideoCapture(video_path)
        # 取 3 个采样帧
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frames = []
        for ratio in [0.2, 0.5, 0.8]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * ratio))
            ret, f = cap.read()
            if ret:
                frames.append(f)
        cap.release()
        if frames:
            frame = frames[len(frames) // 2]  # 取中间帧
        else:
            return profile

    # 提取主色调
    colors = extract_dominant_colors(frame, k=5)
    if colors:
        # 按占比排序
        colors.sort(key=lambda c: c.percentage, reverse=True)
        c0, c1 = colors[0], colors[1] if len(colors) > 1 else colors[0]
        profile.palette["bg_color"] = c0.hex
        profile.palette["accent"] = c1.hex
        if len(colors) > 2:
            profile.palette["accent2"] = colors[2].hex

        # 文字颜色：与背景对比度最高的
        best_text = "#FFFFFF"
        best_ratio = 0
        for tc in ["#FFFFFF", "#000000", "#F0F0F0"]:
            from aesthetic_linter import _contrast_ratio
            ratio = _contrast_ratio(tc, c0.hex)
            if ratio > best_ratio:
                best_ratio = ratio
                best_text = tc
        profile.palette["text_color"] = best_text
        profile.typography["text_color"] = best_text

    # 亮度/对比/饱和 → grade
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray)) / 255.0
    contrast = float(np.std(gray)) / 128.0
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    saturation = float(np.mean(hsv[:, :, 1])) / 255.0

    profile.grade["brightness"] = round(brightness, 2)
    profile.grade["contrast"] = round(min(contrast, 2.0), 2)
    profile.grade["saturate"] = round(saturation, 2)
    profile.grade["mood"] = "dark" if brightness < 0.4 else "light"

    # 暖冷判断：红蓝通道比
    b_mean = float(np.mean(frame[:, :, 0]))
    r_mean = float(np.mean(frame[:, :, 2]))
    if r_mean > b_mean * 1.2:
        profile.grade["temperature"] = "warm"
    elif b_mean > r_mean * 1.2:
        profile.grade["temperature"] = "cool"
    else:
        profile.grade["temperature"] = "neutral"

    # ── VLM: 判风格家族 + FX + overlay ──
    _, buf = cv2.imencode('.jpg', frame)
    import base64
    b64 = base64.b64encode(buf).decode()

    vlm_prompt = (
        "分析这个视频截图的视觉风格，返回 JSON：\n"
        '{"style_family": "从以下选一个: dark_neon_ui / bright_airy / retro_film / minimal_tech / vibrant_social / dark_cinematic",\n'
        ' "has_glow": true/false, 是否有霓虹/发光效果\n'
        ' "has_grain": true/false, 是否有胶片颗粒\n'
        ' "has_vignette": true/false, 是否有暗角\n'
        ' "has_logo": true/false, 是否有品牌Logo叠加\n'
        ' "has_ui_chrome": true/false, 是否有UI边框/按钮等\n'
        ' "glow_text": true/false, 文字是否有发光效果}\n'
        "只返回 JSON。"
    )

    vlm_result = _vlm_call([b64], vlm_prompt)
    if vlm_result:
        import re
        match = re.search(r'\{[\s\S]*\}', vlm_result)
        if match:
            try:
                data = json.loads(match.group())
                profile.style_family = data.get("style_family", profile.style_family)
                if data.get("has_glow"):
                    profile.fx["glow"] = 0.6
                if data.get("has_grain"):
                    profile.fx["film_grain"] = 0.08
                if data.get("has_vignette"):
                    profile.fx["vignette"] = 0.5
                if data.get("has_logo"):
                    profile.overlay["has_logo"] = True
                if data.get("has_ui_chrome"):
                    profile.overlay["ui_chrome"] = True
                if data.get("glow_text"):
                    profile.typography["glow_text"] = True
            except json.JSONDecodeError:
                pass

    return profile


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _samples_to_keyframes(samples, fps: float, eps: float = 2.0) -> list[Keyframe]:
    """将 MotionSample 序列转换为稀疏关键帧（RDP 简化）。

    Args:
        samples: MotionSample 列表（含 t, x, y, rotation 等）
        fps: 帧率
        eps: RDP 简化容差（像素百分比），越大越稀疏
    Returns:
        简化后的 Keyframe 列表
    """
    if not samples:
        return []

    # 原始采样点 → 绝对帧号 + 位置
    raw_points = []
    for s in samples:
        frame = int(s.t * fps)
        raw_points.append({
            "frame": frame,
            "x": s.x * 100,  # 转为百分比
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

    # RDP 简化（基于 x, y 路径）
    simplified_indices = _rdp_simplify(
        [(p["x"], p["y"]) for p in raw_points], eps
    )

    keyframes = []
    for idx in simplified_indices:
        p = raw_points[idx]
        keyframes.append(Keyframe(
            frame=p["frame"],
            x=round(p["x"], 2),
            y=round(p["y"], 2),
            rotation=round(p["rotation"], 1),
            scale_x=p["scale_x"],
            scale_y=p["scale_y"],
            opacity=round(p["opacity"], 2),
            easing="ease-out",
        ))

    # 确保首尾帧存在
    if keyframes and keyframes[0].frame != raw_points[0]["frame"]:
        p = raw_points[0]
        keyframes.insert(0, Keyframe(frame=p["frame"], x=p["x"], y=p["y"],
                                     rotation=p["rotation"], opacity=p["opacity"]))
    if keyframes and keyframes[-1].frame != raw_points[-1]["frame"]:
        p = raw_points[-1]
        keyframes.append(Keyframe(frame=p["frame"], x=p["x"], y=p["y"],
                                  rotation=p["rotation"], opacity=p["opacity"]))

    return keyframes


def _rdp_simplify(points: list[tuple], eps: float, offset: int = 0) -> list[int]:
    """Ramer-Douglas-Peucker 轨迹简化，返回保留点在原始数组中的索引。"""
    if len(points) <= 2:
        return [offset + i for i in range(len(points))]

    # 找距离起点-终点连线最远的点
    start = points[0]
    end = points[-1]
    max_dist = 0.0
    max_idx = 0

    for i in range(1, len(points) - 1):
        d = _point_line_distance(points[i], start, end)
        if d > max_dist:
            max_dist = d
            max_idx = i

    if max_dist > eps:
        left = _rdp_simplify(points[:max_idx + 1], eps, offset)
        right = _rdp_simplify(points[max_idx:], eps, offset + max_idx)
        return left[:-1] + right
    else:
        return [offset, offset + len(points) - 1]


def _point_line_distance(point, line_start, line_end) -> float:
    """点到直线的距离。"""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end

    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5

    t = max(0, min(1, ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return ((x0 - proj_x) ** 2 + (y0 - proj_y) ** 2) ** 0.5


def _is_text_track(mt: MotionTrack, text_tracks: list, width: int, height: int) -> bool:
    """判断运动轨迹是否对应一个已检测到的文字区域。"""
    if not mt.keyframes or not text_tracks:
        return False

    kf = mt.keyframes[0]
    cx = (kf.x or 50) / 100 * width
    cy = (kf.y or 50) / 100 * height

    for tt in text_tracks:
        bx, by, bx2, by2 = tt["bbox"]
        if bx <= cx <= bx2 and by <= cy <= by2:
            return True
    return False


def _text_track_to_keyframes(track: dict, fps: float) -> list[Keyframe]:
    """从 EasyOCR 文字追踪生成 motion_path。"""
    first_frame = track.get("first_frame", 0)
    last_frame = track.get("last_frame", 0)
    bbox = track.get("bbox", (0, 0, 0, 0))
    x = (bbox[0] + bbox[2]) / 2
    y = (bbox[1] + bbox[3]) / 2

    # 文字通常是静态的，只保留首尾关键帧
    return [
        Keyframe(frame=first_frame, x=x, y=y, opacity=0.0),
        Keyframe(frame=min(first_frame + 15, last_frame), x=x, y=y, opacity=1.0),
    ]


def _parse_vlm_json(text: str) -> dict | None:
    """从 VLM 输出中提取 JSON（处理 markdown 代码块等）。"""
    import re
    if not text:
        return None

    # 尝试直接解析
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and parsed:
            return parsed[0] if isinstance(parsed[0], dict) else None
        return None
    except json.JSONDecodeError:
        pass

    # 从 markdown 代码块提取
    code_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if code_match:
        try:
            parsed = json.loads(code_match.group(1))
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list) and parsed:
                return parsed[0] if isinstance(parsed[0], dict) else None
        except json.JSONDecodeError:
            pass

    # 最后尝试正则匹配
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def extract_roi_color_cv(video_path: str, bbox: tuple, frame_idx: int) -> str:
    """从指定帧的指定区域提取颜色。"""
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return "#000000"
    x1, y1, x2, y2 = bbox
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return "#000000"
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    avg_lab = lab.reshape(-1, 3).mean(axis=0)
    avg_bgr = cv2.cvtColor(np.uint8([[avg_lab]]), cv2.COLOR_LAB2BGR)[0][0]
    return '#%02x%02x%02x' % (int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0]))


def scene_to_dict(scene: SceneDescription) -> dict:
    """将 SceneDescription 序列化为 dict。"""
    from dataclasses import asdict
    return asdict(scene)


def scene_from_dict(d: dict) -> SceneDescription:
    """从 dict 反序列化 SceneDescription。"""
    scene = SceneDescription(
        canvas_width=d.get("canvas_width", 1080),
        canvas_height=d.get("canvas_height", 1920),
        fps=d.get("fps", 30),
        duration=d.get("duration", 0),
        background_color=d.get("background_color", "#000000"),
        background_gradient=d.get("background_gradient", ""),
        source_video=d.get("source_video", ""),
        extraction_method=d.get("extraction_method", ""),
    )
    scene.motion_patterns = d.get("motion_patterns", [])

    # 反序列化 motion_tracks
    for mt_d in d.get("motion_tracks", []):
        kfs = []
        for kf_d in mt_d.get("keyframes", []):
            kfs.append(Keyframe(
                frame=kf_d.get("frame", 0),
                x=kf_d.get("x"),
                y=kf_d.get("y"),
                rotation=kf_d.get("rotation"),
                scale_x=kf_d.get("scale_x"),
                scale_y=kf_d.get("scale_y"),
                opacity=kf_d.get("opacity"),
                easing=kf_d.get("easing", "ease-out"),
            ))
        scene.motion_tracks.append(MotionTrack(
            element_id=mt_d.get("element_id", ""),
            keyframes=kfs,
            z_order=mt_d.get("z_order", 0),
            role=mt_d.get("role", "unknown"),
            pattern=mt_d.get("pattern", ""),
            pattern_params=mt_d.get("pattern_params", {}),
            source=mt_d.get("source", "measured"),
            confidence=mt_d.get("confidence", 1.0),
        ))

    for elem_d in d.get("elements", []):
        # 解析 motion_path
        motion_path = []
        for kf_d in elem_d.get("motion_path", []):
            motion_path.append(Keyframe(
                frame=kf_d.get("frame", 0),
                x=kf_d.get("x"),
                y=kf_d.get("y"),
                rotation=kf_d.get("rotation"),
                scale_x=kf_d.get("scale_x"),
                scale_y=kf_d.get("scale_y"),
                opacity=kf_d.get("opacity"),
                easing=kf_d.get("easing", "ease-out"),
            ))

        elem = SceneElement(
            id=elem_d.get("id", ""),
            type=elem_d.get("type", "text"),
            content_text=elem_d.get("content_text", ""),
            content_src=elem_d.get("content_src", ""),
            spatial=SpatialProps(**{k: elem_d.get("spatial", {}).get(k, v)
                                   for k, v in SpatialProps().__dict__.items()}),
            appearance=AppearanceProps(**{k: elem_d.get("appearance", {}).get(k, v)
                                         for k, v in AppearanceProps().__dict__.items()}),
            typography=TypographyProps(**{k: elem_d.get("typography", {}).get(k, v)
                                         for k, v in TypographyProps().__dict__.items()}),
            timing=TimingProps(**{k: elem_d.get("timing", {}).get(k, v)
                                 for k, v in TimingProps().__dict__.items()}),
            motion_path=motion_path,
            z_order=elem_d.get("z_order", 0),
            role=elem_d.get("role", "unknown"),
            source=elem_d.get("source", "measured"),
            track_confidence=elem_d.get("track_confidence", 1.0),
            effect_type=elem_d.get("effect_type", ""),
            effect_tier=elem_d.get("effect_tier", ""),
        )
        scene.elements.append(elem)
    for trans_d in d.get("transitions", []):
        scene.transitions.append(TransitionSpec(**trans_d))
    # 反序列化 StyleProfile
    sp_d = d.get("style_profile")
    if sp_d:
        scene.style_profile = StyleProfile.from_dict(sp_d)
    return scene
