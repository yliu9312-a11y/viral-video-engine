"""VideoSpec Pydantic Schema — 两步 LLM 编排的强约束输出格式。

所有枚举值与以下文件保持同步：
- web/src/design-tokens/index.ts (FontSize, PaletteName, CaptionStyle)
- web/src/remotion/compositions/ScriptDrivenVideo.tsx (COMPONENT_MAP)

新增 Remotion 组件时：同步更新 ComponentName + 对应 Props 类 + _PROPS_MAP
"""
from __future__ import annotations

import json
from typing import Literal, Union

from pydantic import BaseModel, Field, model_validator


# ══════════════════════════════════════════════════════════
# Design Token 枚举 (与 design-tokens/index.ts 同步)
# ══════════════════════════════════════════════════════════

FontSize = Literal["display", "headline", "body", "caption"]

# 像素值映射 — LLM 填语义名，代码转成数字
FONT_SIZE_MAP: dict[str, int] = {
    "display": 96,
    "headline": 64,
    "body": 40,
    "caption": 28,
}

PaletteName = Literal["beauty", "digital", "food", "viral", "promo"]

# 调色板映射 — 供组件使用
PALETTE_MAP: dict[str, dict[str, str]] = {
    "beauty": {"primary": "#F5E6E0", "secondary": "#1F1B1A", "accent": "#E8746B"},
    "digital": {"primary": "#0A0E1A", "secondary": "#FFFFFF", "accent": "#3DE0FF"},
    "food": {"primary": "#FAF5E8", "secondary": "#2C1A0E", "accent": "#E8B04D"},
    "viral": {"primary": "#000000", "secondary": "#FFFFFF", "accent": "#FFD60A"},
    "promo": {"primary": "#050510", "secondary": "#FFFFFF", "accent": "#3B82F6"},
}

Phase = Literal["hook", "build", "cta"]

Position = Literal["center", "upper", "lower"]

# KineticText 的 mode (与组件 props 同步)
TextMode = Literal["bounce", "slide", "typewriter", "shake"]

# ParticleBg 的 style (与组件 props 同步)
ParticleStyle = Literal["float", "burst", "drift", "stars"]


# ══════════════════════════════════════════════════════════
# 每个 Remotion 组件的 Props
# 字段名、类型、默认值必须与 ScriptDrivenVideo.tsx COMPONENT_MAP 一致
# ══════════════════════════════════════════════════════════

class KineticTextProps(BaseModel):
    text: str = Field(description="屏幕上显示的完整文字，直接可渲染，不超过20字")
    mode: TextMode = "bounce"
    font_size: FontSize = Field(default="headline", description="字号档位")
    color: str = Field(default="#FFFFFF", description="文字颜色 hex")
    stroke_color: str = Field(default="#000000", description="描边颜色 hex")
    stroke_width: int = Field(default=3, ge=0, le=10)


class ProductShowcaseProps(BaseModel):
    product_image: str = Field(default="", description="产品图片文件名，无图片时留空")
    product_name: str = Field(description="产品名称，≤10字")
    price: str = Field(default="", description="价格字符串如'¥199'，无价格时空字符串")
    cta: str = Field(default="了解更多", description="行动号召文字，≤6字")


class CountdownTimerProps(BaseModel):
    countdown: int = Field(default=3, ge=1, le=5, description="倒计时起始数字")
    color: str = Field(default="#FF416C", description="主色 hex")
    go_text: str = Field(default="GO!", description="倒计时结束后显示的文字")


class PriceRevealProps(BaseModel):
    original_price: str = Field(description="原价，如'¥199'")
    current_price: str = Field(description="现价，如'¥39.9'")
    badge: str = Field(default="限时特价", description="角标文字，≤6字")
    color: str = Field(default="#FF416C", description="强调色 hex")


class BeforeAfterProps(BaseModel):
    before_image: str = Field(default="", description="before 图片文件名")
    after_image: str = Field(default="", description="after 图片文件名")
    before_label: str = Field(default="Before", description="左侧标签，≤6字")
    after_label: str = Field(default="After", description="右侧标签，≤6字")


class DataItem(BaseModel):
    label: str
    value: float
    color: str | None = None


class BarChartProps(BaseModel):
    data: list[DataItem] = Field(min_length=1, max_length=6, description="柱状图数据")


class NumberRollProps(BaseModel):
    value: int = Field(description="目标数字")
    prefix: str = Field(default="", description="数字前缀，如'¥'")
    suffix: str = Field(default="+", description="数字后缀，如'+'、'万'")
    color: str = Field(default="#FFD700", description="数字颜色 hex")
    font_size: FontSize = Field(default="display", description="字号档位")


class DonutChartProps(BaseModel):
    segments: list[DataItem] = Field(min_length=1, max_length=6, description="环形图数据")


class ParticleBgProps(BaseModel):
    count: int = Field(default=25, ge=5, le=100, description="粒子数量")
    color: str = Field(default="#FFD60A", description="主色 hex")
    secondary_color: str = Field(default="#FF416C", description="副色 hex")
    style: ParticleStyle = "float"
    opacity: float = Field(default=0.3, ge=0.0, le=1.0)


class GradientTextProps(BaseModel):
    text: str = Field(description="渐变文字内容，≤20字")
    gradient: str | None = Field(default=None, description="CSS gradient 字符串，None 用默认蓝白渐变")
    font_size: FontSize = Field(default="headline", description="字号档位")
    font_weight: int = Field(default=800, ge=100, le=900)
    shimmer_speed: float = Field(default=0.02, ge=0.005, le=0.1, description="shimmer 动画速度")
    delay: int = Field(default=0, ge=0, le=300, description="延迟帧数")


class WordRevealProps(BaseModel):
    text: str = Field(description="逐词揭示文字，英文按空格分词，中文按字分词")
    font_size: FontSize = Field(default="display", description="字号档位")
    color: str = Field(default="#FFFFFF", description="文字颜色 hex")
    gradient: str | None = Field(default=None, description="CSS gradient，None 用纯色")
    stagger_frames: int = Field(default=3, ge=1, le=10, description="每词间隔帧数")
    delay: int = Field(default=0, ge=0, le=300)


class TypewriterPromptProps(BaseModel):
    text: str = Field(description="打字机输入的文字内容")
    char_interval: int = Field(default=1, ge=1, le=5, description="每字间隔帧数")
    show_cursor: bool = Field(default=True, description="是否显示光标")
    glow_color: str = Field(default="#3B82F6", description="发光颜色 hex")
    delay: int = Field(default=0, ge=0, le=300)


class GlassCardProps(BaseModel):
    text: str = Field(default="", description="卡片内文字内容")
    width: int = Field(default=280, ge=100, le=800, description="卡片宽度 px")
    height: int = Field(default=200, ge=80, le=600, description="卡片高度 px")
    glow_color: str = Field(default="rgba(59, 130, 246, 0.3)", description="边框发光色")
    float: bool = Field(default=False, description="是否开启浮动动画")
    delay: int = Field(default=0, ge=0, le=300)


class FloatingMockupProps(BaseModel):
    text: str = Field(default="", description="mockup 内文字/描述")
    src: str = Field(default="", description="图片路径（staticFile 相对路径）")
    width: int = Field(default=300, ge=100, le=800)
    height: int = Field(default=200, ge=80, le=600)
    float_speed: float = Field(default=0.02, ge=0.005, le=0.1)
    perspective: int = Field(default=1000, ge=200, le=3000)
    rotate_y: float = Field(default=5.0, ge=0.0, le=30.0)
    delay: int = Field(default=0, ge=0, le=300)


MarqueeDirection = Literal["left", "right"]


class MarqueeTextProps(BaseModel):
    text: str = Field(description="跑马灯文字内容")
    speed: float = Field(default=3.3, ge=0.5, le=10.0, description="滚动速度 px/帧")
    font_size: FontSize = Field(default="caption", description="字号档位")
    color: str = Field(default="rgba(255, 255, 255, 0.35)", description="文字颜色")
    direction: MarqueeDirection = "left"


class FeatureItem(BaseModel):
    label: str = Field(description="功能标签，≤6字")
    icon: str = Field(default="", description="emoji 或图标字符")
    description: str = Field(default="", description="简短描述，≤15字")


class FeatureGridProps(BaseModel):
    features: list[FeatureItem] = Field(min_length=1, max_length=8, description="功能列表")
    columns: int = Field(default=2, ge=1, le=4, description="网格列数")
    card_width: int = Field(default=280, ge=100, le=500)
    card_height: int = Field(default=180, ge=80, le=400)
    delay: int = Field(default=0, ge=0, le=300)


class LogoRevealProps(BaseModel):
    logo_text: str = Field(default="Brand", description="Logo 文字")
    logo_icon: str | None = Field(default=None, description="Logo 图标 emoji")
    glow_color: str = Field(default="#3B82F6", description="辉光颜色 hex")
    delay: int = Field(default=0, ge=0, le=300)


class GlowTrailProps(BaseModel):
    path_d: str = Field(
        default="M 100 960 Q 300 200 540 280 T 980 200",
        description="SVG path d 属性"
    )
    color: str = Field(default="#3B82F6", description="粒子颜色 hex")
    trail_length: int = Field(default=5, ge=2, le=12, description="拖尾粒子数")
    dot_size: int = Field(default=6, ge=2, le=20, description="粒子半径 px")
    delay: int = Field(default=0, ge=0, le=300)


# ══════════════════════════════════════════════════════════
# ComponentName + Props Union + 映射表
# ══════════════════════════════════════════════════════════

ComponentName = Literal[
    "KineticText",
    "ProductShowcase",
    "CountdownTimer",
    "PriceReveal",
    "BeforeAfter",
    "BarChart",
    "NumberRoll",
    "DonutChart",
    "ParticleBg",
    "GradientText",
    "WordReveal",
    "TypewriterPrompt",
    "GlassCard",
    "FloatingMockup",
    "MarqueeText",
    "FeatureGrid",
    "LogoReveal",
    "GlowTrail",
]

ComponentProps = Union[
    KineticTextProps,
    ProductShowcaseProps,
    CountdownTimerProps,
    PriceRevealProps,
    BeforeAfterProps,
    BarChartProps,
    NumberRollProps,
    DonutChartProps,
    ParticleBgProps,
    GradientTextProps,
    WordRevealProps,
    TypewriterPromptProps,
    GlassCardProps,
    FloatingMockupProps,
    MarqueeTextProps,
    FeatureGridProps,
    LogoRevealProps,
    GlowTrailProps,
]

_PROPS_MAP: dict[str, type[BaseModel]] = {
    "KineticText": KineticTextProps,
    "ProductShowcase": ProductShowcaseProps,
    "CountdownTimer": CountdownTimerProps,
    "PriceReveal": PriceRevealProps,
    "BeforeAfter": BeforeAfterProps,
    "BarChart": BarChartProps,
    "NumberRoll": NumberRollProps,
    "DonutChart": DonutChartProps,
    "ParticleBg": ParticleBgProps,
    "GradientText": GradientTextProps,
    "WordReveal": WordRevealProps,
    "TypewriterPrompt": TypewriterPromptProps,
    "GlassCard": GlassCardProps,
    "FloatingMockup": FloatingMockupProps,
    "MarqueeText": MarqueeTextProps,
    "FeatureGrid": FeatureGridProps,
    "LogoReveal": LogoRevealProps,
    "GlowTrail": GlowTrailProps,
}


def _sanitize_props(component: str, props: dict) -> dict:
    """修复 LLM 输出的常见 schema 错误。

    策略: 宽进严出 — 尽量从 LLM 输出中提取有效数据，
    对无法修复的字段用默认值替代，而不是直接报错。
    """
    props = dict(props)  # shallow copy

    props_cls = _PROPS_MAP.get(component)
    if not props_cls:
        return props

    valid_fields = set(props_cls.model_fields.keys())

    # 1. 去掉未知字段
    props = {k: v for k, v in props.items() if k in valid_fields}

    # 2. BarChart/DonutChart: data/segments 格式修复
    if component in ("BarChart", "DonutChart"):
        key = "data" if component == "BarChart" else "segments"
        val = props.get(key)
        if isinstance(val, dict):
            # 单个 dict → list
            props[key] = [val] if "label" in val else []
        elif isinstance(val, list):
            props[key] = [v for v in val if isinstance(v, dict) and "label" in v]
        else:
            props[key] = []
        # 如果修复后为空，填默认数据
        if not props[key]:
            props[key] = [{"label": "数据", "value": 80}]

    # 3. NumberRoll: value 必须是 int
    if component == "NumberRoll":
        val = props.get("value")
        if not isinstance(val, (int, float)):
            # 尝试从 dict 或字符串中提取
            if isinstance(val, dict):
                props["value"] = 10000
            elif isinstance(val, str):
                import re
                nums = re.findall(r"\d+", val)
                props["value"] = int(nums[0]) if nums else 10000
            else:
                props["value"] = 10000

    # 4. CountdownTimer: countdown 必须是 int
    if component == "CountdownTimer":
        val = props.get("countdown")
        if not isinstance(val, (int, float)):
            props["countdown"] = 3

    # 5. FeatureGrid: features 格式修复
    if component == "FeatureGrid":
        val = props.get("features")
        if isinstance(val, list):
            fixed = []
            for item in val:
                if isinstance(item, str):
                    fixed.append({"label": item})
                elif isinstance(item, dict) and "label" in item:
                    fixed.append(item)
            props["features"] = fixed if fixed else [{"label": "Feature"}]
        elif not val:
            props["features"] = [{"label": "Feature"}]

    # 6. GlowTrail: path_d 为空时给默认值
    if component == "GlowTrail":
        if not props.get("path_d") and not props.get("pathD"):
            props["path_d"] = "M 100 960 Q 300 200 540 280 T 980 200"

    # 7. gradient: 数组 → CSS 字符串
    if "gradient" in props:
        g = props["gradient"]
        if isinstance(g, list):
            props["gradient"] = f"linear-gradient(90deg, {', '.join(str(c) for c in g)})"

    # 8. speed: 字符串描述 → 数值
    if "speed" in props:
        s = props["speed"]
        if isinstance(s, str):
            speed_map = {"slow": 1.5, "medium": 3.3, "fast": 6.0}
            props["speed"] = speed_map.get(s.lower(), 3.3)

    # 9. 补全缺失的必填字段 (用组件默认值)
    for field_name, field_info in props_cls.model_fields.items():
        if field_name not in props:
            if field_info.default is not None and field_info.default is not ...:
                props[field_name] = field_info.default
            elif field_info.is_required():
                # 必填但没默认值 — 用类型对应的零值
                ann = field_info.annotation
                if ann is str:
                    props[field_name] = ""
                elif ann is int:
                    props[field_name] = 0
                elif ann is float:
                    props[field_name] = 0.0
                elif ann is bool:
                    props[field_name] = False

    return props


# ══════════════════════════════════════════════════════════
# ShotSpec：单个镜头 (LLM 填这个)
# ══════════════════════════════════════════════════════════

TransitionType = Literal["none", "crossfade"]

class ShotSpec(BaseModel):
    component: ComponentName
    props: dict = Field(description="组件 props，由 validate_props 校验")
    duration_frames: int = Field(
        ge=30, le=240,
        description="帧数。30fps下：60=2s，90=3s，120=4s，180=6s。建议60-180。",
    )
    phase: Phase
    position: Position = "center"
    transition: TransitionType = Field(
        default="crossfade",
        description="转场类型：crossfade=交叉淡入淡出, none=硬切",
    )

    @model_validator(mode="before")
    @classmethod
    def clip_duration(cls, data):
        """Clip duration_frames to valid range before Pydantic validation."""
        if isinstance(data, dict) and "duration_frames" in data:
            df = data["duration_frames"]
            if isinstance(df, (int, float)):
                data["duration_frames"] = max(30, min(240, int(df)))
        return data

    @model_validator(mode="after")
    def validate_props(self) -> "ShotSpec":
        props_cls = _PROPS_MAP.get(self.component)
        if props_cls is None:
            raise ValueError(f"未知组件: {self.component}")
        # 宽进：sanitize LLM 常见错误后再校验
        sanitized = _sanitize_props(self.component, self.props)
        props_cls.model_validate(sanitized)
        self.props = sanitized
        return self


# ══════════════════════════════════════════════════════════
# VideoSpec：完整视频规格 (LLM 最终输出)
# ══════════════════════════════════════════════════════════

class VideoSpec(BaseModel):
    shots: list[ShotSpec] = Field(
        min_length=1,
        max_length=12,
        description="镜头序列，按时间顺序排列",
    )
    fps: int = Field(default=30)
    palette: PaletteName = Field(description="全片统一色板")
    total_duration_frames: int = Field(
        description="总帧数，必须等于所有 shots 的 duration_frames 之和",
    )

    @model_validator(mode="before")
    @classmethod
    def fix_total_frames(cls, data):
        """Auto-correct total_duration_frames to match actual shots sum."""
        if isinstance(data, dict) and "shots" in data:
            shots = data["shots"]
            if isinstance(shots, list):
                actual = sum(
                    s.get("duration_frames", 60) for s in shots if isinstance(s, dict)
                )
                if actual > 0:
                    data["total_duration_frames"] = actual
        return data

    @model_validator(mode="after")
    def validate_total_frames(self) -> "VideoSpec":
        actual = sum(s.duration_frames for s in self.shots)
        if actual != self.total_duration_frames:
            self.total_duration_frames = actual
        return self

    def to_render_input(self) -> dict:
        """转换为 render_script.ts 期望的格式。

        render_script.ts 读 JSON 后包装成 { script: <json> }，ScriptDrivenVideo
        期望 VideoSpec { shots[], globalStyle?, fps? }。
        """
        return {
            "fps": self.fps,
            "globalStyle": {
                "bgColor": PALETTE_MAP[self.palette]["primary"],
                "palette": self.palette,
            },
            "shots": [
                {
                    "id": f"{shot.phase}_{i}",
                    "role": shot.phase,
                    "component": shot.component,
                    "props": _resolve_props(shot),
                    "start": _calc_start(self.shots, i),
                    "duration": shot.duration_frames,
                    "position": shot.position,
                    "transition": shot.transition,
                }
                for i, shot in enumerate(self.shots)
            ],
        }


# ══════════════════════════════════════════════════════════
# 辅助函数：概念层 → 实际值转换
# ══════════════════════════════════════════════════════════

def _resolve_props(shot: ShotSpec) -> dict:
    """将 LLM 填的语义值转成组件期望的实际值。

    - font_size: "headline" → 64
    - palette 颜色: 由组件自行处理，这里只透传
    - snake_case → camelCase 转换 (Python schema 用 snake_case，
      但 JS 组件用 camelCase)
    """
    props = dict(shot.props)

    # font_size 语义名 → 像素值
    if "font_size" in props:
        fs = props.pop("font_size")
        props["fontSize"] = FONT_SIZE_MAP.get(fs, 64)

    # snake_case → camelCase (与 JS 组件对齐)
    _SNAKE_TO_CAMEL = {
        "product_image": "productImage",
        "product_name": "productName",
        "stroke_color": "strokeColor",
        "stroke_width": "strokeWidth",
        "go_text": "goText",
        "original_price": "originalPrice",
        "current_price": "currentPrice",
        "before_image": "beforeImage",
        "after_image": "afterImage",
        "before_label": "beforeLabel",
        "after_label": "afterLabel",
        "secondary_color": "secondaryColor",
        "font_weight": "fontWeight",
        "shimmer_speed": "shimmerSpeed",
        "stagger_frames": "staggerFrames",
        "char_interval": "charInterval",
        "show_cursor": "showCursor",
        "glow_color": "glowColor",
        "float_speed": "floatSpeed",
        "rotate_y": "rotateY",
        "card_width": "cardWidth",
        "card_height": "cardHeight",
        "logo_text": "logoText",
        "logo_icon": "logoIcon",
        "trail_length": "trailLength",
        "dot_size": "dotSize",
        "path_d": "pathD",
    }
    for snake, camel in _SNAKE_TO_CAMEL.items():
        if snake in props:
            props[camel] = props.pop(snake)

    return props


def _calc_start(shots: list[ShotSpec], index: int) -> int:
    """计算第 index 个 shot 的起始帧。"""
    return sum(s.duration_frames for s in shots[:index])


# ══════════════════════════════════════════════════════════
# Schema 导出 (供 json_object 模式下的 prompt 使用)
# ══════════════════════════════════════════════════════════

def get_schema_json() -> str:
    """返回 VideoSpec 的 JSON Schema 字符串，嵌入到 LLM prompt 中。"""
    return json.dumps(VideoSpec.model_json_schema(), ensure_ascii=False, indent=2)
