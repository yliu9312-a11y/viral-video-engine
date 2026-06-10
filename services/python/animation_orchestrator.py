"""Animation Orchestrator — LLM 编排动画脚本。

v2 架构 (旧): LLM → 浅 schema 创意决策 → 正则解析 idea → VideoSpec
v3 架构 (新): Step1 LLM 自由推理 → Step2 LLM 强约束填 Pydantic → VideoSpec

v3 彻底删除正则解析，两步调用分离创意与格式化。
"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from video_spec_schema import VideoSpec as VideoSpecV3, ShotSpec as ShotSpecV3, get_schema_json

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_API_URL = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

# ── v3: OpenAI SDK 客户端 ─────────────────────────────────
_MIMO_CLIENT: OpenAI | None = None


def _get_client() -> OpenAI:
    global _MIMO_CLIENT
    if _MIMO_CLIENT is None:
        # MIMO_API_URL 可能是完整 endpoint (含 /chat/completions)，需要去掉
        base = MIMO_API_URL.replace("/chat/completions", "")
        # 确保是 /v1 结尾 (OpenAI SDK 会自动拼 /chat/completions)
        if not base.endswith("/v1"):
            base = base.rstrip("/") + "/v1"
        _MIMO_CLIENT = OpenAI(
            api_key=MIMO_API_KEY,
            base_url=base,
        )
    return _MIMO_CLIENT

# ───────────────────────────────────────────────────
# 1. 组件目录 (给 LLM 看的简化版)
# ───────────────────────────────────────────────────

COMPONENT_CATALOG = {
    # ── 基础组件 ──
    "KineticText": "动感文字(bounce/slide/typewriter/shake)，用于标题/卖点/CTA",
    "ProductShowcase": "产品展示卡片(图片+价格+CTA)，用于产品特写",
    "CountdownTimer": "3-2-1-GO倒计时，用于开场紧迫感",
    "PriceReveal": "价格揭示(原价划掉→现价弹出)，用于限时优惠",
    "BeforeAfter": "前后对比分屏，用于效果对比",
    "BarChart": "柱状图动画，用于数据展示/参数对比",
    "NumberRoll": "数字滚动到目标值，用于销量/粉丝数",
    "DonutChart": "环形图动画，用于占比/好评率展示",
    "ParticleBg": "粒子背景(float/burst/drift/stars)，用于氛围",
    # ── MG 高级组件 (Layout.dev 风格) ──
    "GradientText": "渐变文字+shimmer光效，适合大标题、品牌slogan。自带spring入场+shimmer循环",
    "WordReveal": "逐词交错fade+slide揭示，适合英文hook、金句、标语。自带stagger动效",
    "TypewriterPrompt": "圆角搜索栏+打字机输入+光标闪烁+发光边框，适合展示AI prompt、代码、指令",
    "GlassCard": "玻璃拟态容器(blur+蓝色边框发光+可选浮动)，适合功能卡片、特性展示",
    "FloatingMockup": "浮动UI截图+透视倾斜+跟随阴影，适合展示app/网站界面截图",
    "MarqueeText": "水平滚动文字+边缘渐变遮罩，适合底部信息流、标签列表、品牌关键词",
    "FeatureGrid": "功能标签卡片网格布局，适合展示产品特性矩阵(4-8个功能点)",
    "LogoReveal": "Logo spring弹入+蓝色辉光脉冲，适合品牌收尾、片尾logo展示",
    "GlowTrail": "SVG路径上移动的发光粒子拖尾，适合装饰性转场、引导视线流动",
}

VIRAL_PATTERNS = {
    "hook": [
        "悬念反问: 逐词渐变揭示 → WordReveal + GlowTrail(弧线引导)",
        "打字机提问: 搜索栏打字 → TypewriterPrompt + ParticleBg(float)",
        "渐变大字: shimmer渐变标题 → GradientText + ParticleBg(stars)",
        "痛点反问: 大字'你还在XXX？' → KineticText(shake)",
        "数字冲击: 数字滚到大数 → NumberRoll + KineticText(bounce)",
        "倒计时开场: 3-2-1-GO → CountdownTimer + ParticleBg(burst)",
    ],
    "build": [
        "功能矩阵: 玻璃卡片网格 → FeatureGrid(4功能) + MarqueeText(底部标签)",
        "产品展示: 浮动UI截图 → FloatingMockup + GlassCard(描述卡片)",
        "特性卡片: 玻璃拟态卡片 → GlassCard x3 + GlowTrail(连接线)",
        "卖点列表: 编号卡片逐个弹入 → KineticText(slide) x3",
        "数据说话: 柱状图+数字 → BarChart + NumberRoll",
        "使用演示: 产品图+文字 → ProductShowcase + KineticText",
    ],
    "cta": [
        "品牌收尾: Logo弹入+辉光 → LogoReveal + GradientText(标语)",
        "渐变收尾: shimmer大字 → GradientText + MarqueeText(底部信息)",
        "限时优惠: 价格+倒计时+CTA → PriceReveal + CountdownTimer + KineticText",
        "行动号召: 大字CTA+粒子 → KineticText(shake) + ParticleBg(burst)",
    ],
}

# ── Layout 语法: phase → 组件角色模板 ──
# 基于 Layout.dev 参考视频的视觉层次结构
LAYOUT_SYNTAX = {
    "hook": {
        "roles": ["hero_text", "decorative"],
        "hero_text": ["WordReveal", "GradientText", "TypewriterPrompt", "KineticText"],
        "decorative": ["GlowTrail", "ParticleBg"],
        "position": "center",
        "description": "Hook: 大字标签居中，可选装饰性动效(GlowTrail弧线/粒子)。视觉焦点=文字",
    },
    "build": {
        "roles": ["content_cards", "bottom_ticker", "background"],
        "content_cards": ["FeatureGrid", "GlassCard", "FloatingMockup", "ProductShowcase"],
        "bottom_ticker": ["MarqueeText"],
        "background": ["ParticleBg"],
        "position": "center",
        "description": "Build: 内容卡片居中(玻璃拟态/功能网格)，底部跑马灯标签，粒子背景。层次=卡片>跑马灯>背景",
    },
    "cta": {
        "roles": ["hero_text", "logo", "decorative"],
        "hero_text": ["GradientText", "WordReveal", "KineticText"],
        "logo": ["LogoReveal"],
        "decorative": ["MarqueeText", "ParticleBg"],
        "position": "center",
        "description": "CTA: 渐变大字slogan + Logo弹入收尾。底部可选跑马灯。视觉焦点=文字+Logo",
    },
}

# ───────────────────────────────────────────────────
# 2. 创意决策 schema (LLM 输出这个，很浅)
# ───────────────────────────────────────────────────

DECISION_SCHEMA_EXAMPLE = """{
  "concept": "痛点反问 → 产品特写 → 限时优惠",
  "shots": [
    {"component": "KineticText", "idea": "大字弹出'你还在为耳机掉落烦恼？'", "emphasis": "high"},
    {"component": "ProductShowcase", "idea": "防脱落运动耳机特写，¥299", "emphasis": "medium"},
    {"component": "PriceReveal", "idea": "原价¥599划掉，现价¥299弹出", "emphasis": "high"}
  ]
}"""

# ───────────────────────────────────────────────────
# 3. Pydantic 校验模型
# ───────────────────────────────────────────────────


class ShotDecision(BaseModel):
    """LLM 输出的单个 shot 决策。"""
    component: str
    idea: str = ""
    emphasis: str = "medium"  # high / medium / low

    @field_validator("component")
    @classmethod
    def validate_component(cls, v):
        if v not in COMPONENT_CATALOG:
            raise ValueError(f"Unknown component: {v}. Valid: {list(COMPONENT_CATALOG.keys())}")
        return v


class CreativeDecision(BaseModel):
    """LLM 输出的创意决策。"""
    concept: str = ""
    shots: list[ShotDecision] = Field(min_length=1, max_length=8)


class ShotSpec(BaseModel):
    """转换后的单个 shot (Video Spec 格式)。"""
    id: str
    role: str
    component: str
    props: dict
    start: int
    duration: int
    position: str = "center"
    transition: str = "crossfade"


class VideoSpec(BaseModel):
    """最终 Video Spec (Remotion 可直接渲染)。"""
    shots: list[ShotSpec]
    globalStyle: dict = Field(default_factory=lambda: {"bgColor": "#0A0A0A", "palette": "viral"})


# ───────────────────────────────────────────────────
# 4. 确定性转换：决策 → Video Spec
# ───────────────────────────────────────────────────

# 每个组件的默认 props
COMPONENT_DEFAULTS = {
    "KineticText": {"text": "默认文字", "mode": "bounce", "fontSize": 64, "color": "#FFFFFF", "strokeColor": "#000000", "strokeWidth": 3},
    "ProductShowcase": {"productImage": "", "productName": "精选好物", "price": "", "cta": "了解更多"},
    "CountdownTimer": {"countdown": 3, "color": "#FF416C", "goText": "GO!"},
    "PriceReveal": {"originalPrice": "¥199", "currentPrice": "¥39.9", "badge": "限时特价", "color": "#FF416C"},
    "BeforeAfter": {"beforeImage": "", "afterImage": "", "beforeLabel": "Before", "afterLabel": "After"},
    "BarChart": {"data": [{"label": "效果", "value": 85}, {"label": "性价比", "value": 92}]},
    "NumberRoll": {"value": 10000, "prefix": "", "suffix": "+", "color": "#FFD700", "fontSize": 96},
    "ParticleBg": {"count": 25, "color": "#FFD60A", "secondaryColor": "#FF416C", "style": "float", "opacity": 0.3},
    # MG 高级组件
    "GradientText": {"text": "默认渐变文字", "fontSize": 64, "fontWeight": 800, "shimmerSpeed": 0.02},
    "WordReveal": {"text": "Default Word Reveal", "fontSize": 96, "color": "#FFFFFF", "staggerFrames": 3},
    "TypewriterPrompt": {"text": "echo 'hello world'", "charInterval": 1, "showCursor": True, "glowColor": "#3B82F6"},
    "GlassCard": {"text": "特性展示", "width": 280, "height": 200, "glowColor": "rgba(59, 130, 246, 0.3)", "float": False},
    "FloatingMockup": {"text": "App Preview", "width": 300, "height": 200, "floatSpeed": 0.02, "rotateY": 5},
    "MarqueeText": {"text": "关键词 • 标签 • 品牌", "speed": 3.3, "fontSize": 32, "color": "rgba(255, 255, 255, 0.35)", "direction": "left"},
    "FeatureGrid": {"features": [{"label": "功能A"}, {"label": "功能B"}, {"label": "功能C"}, {"label": "功能D"}], "columns": 2, "cardWidth": 280, "cardHeight": 180},
    "LogoReveal": {"logoText": "Brand", "glowColor": "#3B82F6"},
    "GlowTrail": {"pathD": "M 100 960 Q 300 200 540 280 T 980 200", "color": "#3B82F6", "trailLength": 5, "dotSize": 6},
}

# emphasis → 帧数分配权重
EMPHASIS_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.7}

# emphasis → position 偏好
EMPHASIS_POSITION = {"high": "center", "medium": "center", "low": "upper"}


def _extract_props_from_idea(idea: str, component: str) -> dict:
    """从 LLM 的 idea 文本中提取具体 props (启发式 + LLM 友好)。"""
    props = {}
    idea_lower = idea.lower()

    # 提取引号中的文字作为 text
    import re
    quoted = re.findall(r"['‘“\"](.+?)['’”\"]", idea)
    if quoted and component == "KineticText":
        props["text"] = quoted[0]

    # 提取价格
    prices = re.findall(r"¥(\d+(?:\.\d+)?)", idea)
    if prices:
        if component == "PriceReveal":
            if len(prices) >= 2:
                props["originalPrice"] = f"¥{prices[0]}"
                props["currentPrice"] = f"¥{prices[1]}"
            elif len(prices) == 1:
                props["currentPrice"] = f"¥{prices[0]}"
        elif component == "ProductShowcase":
            props["price"] = f"¥{prices[0]}"

    # 提取产品名 (在"特写"、"展示"之前的内容)
    product_match = re.search(r"([一-龥]+(?:耳机|手机|手表|包包|口红|面膜|精华|面霜|产品|好物))", idea)
    if product_match and component == "ProductShowcase":
        props["productName"] = product_match.group(1)

    # 提取模式词
    mode_map = {"弹出": "bounce", "滑入": "slide", "打字": "typewriter", "抖动": "shake", "晃动": "shake"}
    for keyword, mode in mode_map.items():
        if keyword in idea and component == "KineticText":
            props["mode"] = mode
            break

    # 提取粒子风格
    style_map = {"爆发": "burst", "浮动": "float", "漂移": "drift", "星星": "stars"}
    for keyword, style in style_map.items():
        if keyword in idea and component == "ParticleBg":
            props["style"] = style
            break

    # 提取数字
    nums = re.findall(r"(\d+)", idea)
    if component == "NumberRoll" and nums:
        props["value"] = int(nums[0])
    if component == "CountdownTimer" and nums:
        props["countdown"] = min(int(nums[0]), 5)

    return props


# ═══════════════════════════════════════════════════════════
# v3: 两步 LLM 调用 — Step1 自由推理 + Step2 强约束填表
# ═══════════════════════════════════════════════════════════

def _build_context_block(
    phase: str,
    gap: dict,
    kb_atoms: list,
    materials: list,
    template: dict,
    control_vector: dict | None = None,
) -> str:
    """拼装所有上下文信息，供两步调用共用。

    包含: 节奏约束 + 可用素材 + 组件注册表 + 布局语法 + 主题色板 + 爆款模式 + ControlVector。
    """
    atom_lines = [f"  - {a.get('remotion_component', '?')}: {a.get('description', '')}" for a in kb_atoms[:6]]
    atoms_text = "\n".join(atom_lines) or "  无"

    mat_lines = []
    for m in materials[:5]:
        fname = m.get("path", "").split("/")[-1] if isinstance(m.get("path"), str) else ""
        if fname:
            mat_lines.append(f"  - {fname}")
    mats_text = "\n".join(mat_lines) or "  无素材"

    patterns = VIRAL_PATTERNS.get(phase, [])
    pat_text = "\n".join(f"  - {p}" for p in patterns[:4])

    narrative = template.get("narrative", {})
    missing = gap.get("missing_shot_types", [])

    # Phase duration constraints from template
    phase_info = next((p for p in template.get("timeline", []) if p["phase"] == phase), {})
    dur_pct = phase_info.get("duration_pct", [0, 1])
    total_dur = template.get("duration_range", [15, 30])
    avg_total = (total_dur[0] + total_dur[1]) / 2
    phase_dur = (dur_pct[1] - dur_pct[0]) * avg_total
    n_shots = phase_info.get("shot_count_range", [1, 3])
    avg_shots = (n_shots[0] + n_shots[1]) / 2
    avg_shot_dur = phase_dur / max(avg_shots, 1)

    # 组件注册表 (分类)
    basic_comps = {k: v for k, v in COMPONENT_CATALOG.items() if k in
                   ("KineticText", "ProductShowcase", "CountdownTimer", "PriceReveal",
                    "BeforeAfter", "BarChart", "NumberRoll", "DonutChart", "ParticleBg")}
    mg_comps = {k: v for k, v in COMPONENT_CATALOG.items() if k not in basic_comps}
    basic_text = "\n".join(f"  {name}: {desc}" for name, desc in basic_comps.items())
    mg_text = "\n".join(f"  {name}: {desc}" for name, desc in mg_comps.items())

    # 布局语法
    layout = LAYOUT_SYNTAX.get(phase, {})
    layout_roles = layout.get("description", "")
    role_options = []
    for role, comps in layout.items():
        if isinstance(comps, list):
            role_options.append(f"  {role}: {' / '.join(comps)}")
    layout_text = "\n".join(role_options) if role_options else "  无特殊布局要求"

    # 主题色板 (确定性，LLM 不应自行选色)
    palette_name = template.get("packaging", {}).get("color_palette_name", "promo")
    theme_text = (
        f"  palette: {palette_name}\n"
        f"  背景色: #050510 (深蓝黑)\n"
        f"  主文字: #FFFFFF\n"
        f"  强调色: #3B82F6 (蓝色)\n"
        f"  渐变: 从灰(#9CA3AF)到白到蓝\n"
        f"  玻璃拟态: rgba(15,23,42,0.6) + 蓝色边框发光\n"
        f"  注意: 颜色已确定，不要自行选择其他颜色"
    )

    return (
        f"阶段: {phase}\n"
        f"缺失镜头: {', '.join(missing) or '无'}\n"
        f"钩子类型: {narrative.get('hook_type', '')}\n"
        f"构建模式: {narrative.get('build_pattern', '')}\n"
        f"CTA类型: {narrative.get('cta_type', '')}\n\n"
        f"【节奏约束】\n"
        f"  本阶段总时长: ~{phase_dur:.0f}s ({int(phase_dur*30)}帧)\n"
        f"  建议 shot 数: {n_shots[0]}-{n_shots[1]}个\n"
        f"  每个 shot 平均: ~{avg_shot_dur:.1f}s ({int(avg_shot_dur*30)}帧)\n"
        f"  最短 shot 不低于: 2s (60帧) — 文字需要阅读时间\n"
        f"  最长 shot 不超过: 8s (240帧) — 避免拖沓\n"
        f"  读文字规则: 中文每字~0.3s, 英文每词~0.4s, 加 1s 缓冲\n\n"
        f"【主题色板 — 确定性，不要自行选色】\n{theme_text}\n\n"
        f"【布局语法 — {phase} 阶段】\n"
        f"  {layout_roles}\n"
        f"  组件角色选择:\n{layout_text}\n\n"
        f"【MG 高级组件 — 视觉丰富度核心】\n{mg_text}\n\n"
        f"【基础组件】\n{basic_text}\n\n"
        f"【可用素材】\n{mats_text}\n\n"
        f"【KB 推荐组件】\n{atoms_text}\n\n"
        f"【爆款参考模式】\n{pat_text}"
        + _build_cv_section(control_vector, phase)
    )


def _build_cv_section(cv: dict | None, phase: str) -> str:
    """构建 ControlVector 上下文段落。"""
    if not cv:
        return ""

    scale = cv.get("shot_duration_scale", 1.0)
    text_d = cv.get("text_density", 0.5)
    cta_e = cv.get("cta_emphasis", 0.5)
    easing = cv.get("easing_profile", "smooth")
    priority = cv.get("component_priority", {}).get(phase, [])

    pace_hint = "快切" if scale < 0.8 else ("慢镜" if scale > 1.2 else "标准")
    text_hint = "少字" if text_d < 0.3 else ("多字" if text_d > 0.7 else "适中")
    content_order = cv.get("content_order", [])

    section = (
        f"\n\n【ControlVector 控制参数】\n"
        f"  节奏: {pace_hint} (时长缩放 {scale:.1f}x)\n"
        f"  文字密度: {text_hint} ({text_d:.0%})\n"
        f"  CTA 强度: {cta_e:.0%}\n"
        f"  缓动风格: {easing}\n"
        f"  {phase} 阶段优先组件: {', '.join(priority) if priority else '无特殊偏好'}\n"
        f"  注意: 以上参数必须遵守，不要自行调整节奏/文字量"
    )
    if content_order:
        section += f"\n  内容顺序 (用户指定): {' → '.join(content_order)}"
    return section


def _step1_creative_reasoning(context_block: str) -> str:
    """Step1: 让 MiMo 自由思考创意方案 (thinking enabled)。

    返回自然语言推理文本。thinking 模式下 temperature 锁 1.0。
    """
    system_prompt = (
        "你是剪映爆款短视频 Motion Graphics 导演。\n"
        "根据下方信息，为这段短视频设计完整镜头序列。\n\n"
        "请按顺序思考（输出自然语言，不要输出 JSON）：\n"
        "1. 爆款参考结构的核心节奏是什么？hook 怎么抓眼球？\n"
        "2. 哪些 phase 用户素材充足？哪些需要 Remotion 组件补充视觉张力？\n"
        "3. 逐 shot 决定：用哪个组件？屏幕上显示什么文字/数据？什么视觉风格？\n"
        "4. palette 已确定为 promo（深蓝黑背景+蓝白强调色），不要选其他 palette。\n"
        "5. 每个 shot 的帧数必须满足下方【节奏约束】，不能随意定。\n"
        "6. 按照【布局语法】选择组件角色，确保视觉层次正确。\n\n"
        "【节奏铁律】\n"
        "- 有文字的 shot: 文字字数×0.3s(中文)或词数×0.4s(英文) + 1s 缓冲\n"
        "- 纯画面 shot (BeforeAfter/ProductShowcase): 最少 2s\n"
        "- 过渡 shot (ParticleBg/CountdownTimer): 最少 1.5s\n"
        "- 所有 shot: 最短 2s (60帧), 最长 8s (240帧)\n"
        "- 总时长必须符合下方【节奏约束】中的阶段时长\n\n"
        "【组件选择优先级】\n"
        "- Hook 阶段优先: WordReveal / GradientText / TypewriterPrompt\n"
        "- Build 阶段优先: FeatureGrid / GlassCard / FloatingMockup + MarqueeText(底部)\n"
        "- CTA 阶段优先: GradientText + LogoReveal\n"
        "- 动效内建在组件里，不需要写动效参数，只需选组件+填文字内容\n\n"
        "可用组件见下方【MG 高级组件】和【基础组件】列表。\n\n"
        "把推理过程完整写出来，越详细越好。"
    )

    client = _get_client()
    resp = client.chat.completions.create(
        model=MIMO_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_block},
        ],
        max_completion_tokens=1500,
        extra_body={"thinking": {"type": "enabled"}},
    )
    return resp.choices[0].message.content


def _step2_structured_fill(context_block: str, reasoning: str) -> VideoSpecV3:
    """Step2: 把 Step1 推理结果转成强约束 VideoSpec JSON。

    thinking 关闭，temperature 低，json_object 模式 + Pydantic 校验。
    """
    schema_json = get_schema_json()

    system_prompt = (
        "你是 JSON 填表专员。只输出合法 JSON，不要其他文字。\n\n"
        "创意设计方案已在下方给出，你只需把它转成严格的 VideoSpec JSON 格式。\n\n"
        f"VideoSpec JSON Schema:\n{schema_json}\n\n"
        "填表规则（必须遵守）：\n"
        "• text / product_name / badge / go_text 等文字字段：填最终要在屏幕上显示的完整文字\n"
        "• font_size 只能是：display / headline / body / caption\n"
        "• palette 固定为 promo（深蓝黑背景），不要选其他值\n"
        "• mode 只能是：bounce / slide / typewriter / shake\n"
        "• phase 只能是：hook / build / cta\n"
        "• position 只能是：center / upper / lower\n"
        "• duration_frames：单个 shot 范围 30-240，建议 60-120（2-4秒）\n"
        "• total_duration_frames 必须等于所有 shots 的 duration_frames 之和\n"
        "• shots 数量 1-12 个（hook 阶段 1-2 个即可）\n"
        "• color 字段填 hex 色值如 '#FFFFFF'，默认用 '#FFFFFF'\n"
        "• glow_color 默认用 '#3B82F6' (蓝色)\n"
        "• 不要改变创意决策，只做格式转换\n"
        "• 只输出 JSON 对象，不要 markdown 代码块"
    )

    user_content = f"【创意推理方案】\n{reasoning}\n\n【原始上下文】\n{context_block}"

    client = _get_client()
    resp = client.chat.completions.create(
        model=MIMO_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=2000,
        temperature=0.1,
        extra_body={"thinking": {"type": "disabled"}},
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content

    return VideoSpecV3.model_validate_json(raw)


def _enforce_pacing(spec, phase: str, template: dict):
    """Post-process: enforce minimum/maximum shot durations for readable pacing.

    Works with both v2 ShotSpec (duration) and v3 ShotSpec (duration_frames).
    """
    MIN_FRAMES = 60   # 2s minimum
    MAX_FRAMES = 240  # 8s maximum

    # Detect v2 vs v3 by checking if first shot has 'duration' or 'duration_frames'
    is_v3 = hasattr(spec.shots[0], 'duration_frames') if spec.shots else True

    # Get phase duration budget from template
    phase_info = next((p for p in template.get("timeline", []) if p["phase"] == phase), {})
    dur_pct = phase_info.get("duration_pct", [0, 1])
    total_dur = template.get("duration_range", [15, 30])
    avg_total = (total_dur[0] + total_dur[1]) / 2
    target_frames = int((dur_pct[1] - dur_pct[0]) * avg_total * 30)

    def get_dur(shot):
        return shot.duration_frames if is_v3 else shot.duration

    def set_dur(shot, val):
        if is_v3:
            shot.duration_frames = val
        else:
            shot.duration = val

    shots = list(spec.shots)
    changed = False

    # Enforce minimum duration per shot
    for shot in shots:
        if get_dur(shot) < MIN_FRAMES:
            set_dur(shot, MIN_FRAMES)
            changed = True

    # Enforce maximum duration per shot
    for shot in shots:
        if get_dur(shot) > MAX_FRAMES:
            set_dur(shot, MAX_FRAMES)
            changed = True

    # Re-sequence v2 shots (v2 has 'start' field)
    if changed and not is_v3:
        current_frame = 0
        for shot in shots:
            shot.start = current_frame
            current_frame += get_dur(shot)

    # If total exceeds budget, scale down proportionally
    total = sum(get_dur(s) for s in shots)
    if total > target_frames * 1.2 and target_frames > 0:
        scale = target_frames / total
        for shot in shots:
            set_dur(shot, max(MIN_FRAMES, int(get_dur(shot) * scale)))
        # Re-sequence v2 again after scaling
        if not is_v3:
            current_frame = 0
            for shot in shots:
                shot.start = current_frame
                current_frame += get_dur(shot)

    # Update v3 total_duration_frames
    if is_v3:
        spec.total_duration_frames = sum(s.duration_frames for s in shots)

    spec.shots = shots
    return spec


def _apply_cv_deterministic(spec: VideoSpecV3, cv: dict, phase: str) -> VideoSpecV3:
    """将 ControlVector 的确定性旋钮强制应用到 VideoSpec。

    这是"控制真生效"的兜底 — LLM 输出后再 enforce 一遍。
    确定性旋钮: shot_duration_scale, transition_density, text_density, easing_profile, phase_weights。
    """
    scale = cv.get("shot_duration_scale", 1.0)
    trans_density = cv.get("transition_density", 0.5)
    text_density = cv.get("text_density", 0.5)
    easing = cv.get("easing_profile", "smooth")
    phase_weights = cv.get("phase_weights", {})
    cta_emphasis = cv.get("cta_emphasis", 0.5)

    # 1. shot_duration_scale: 缩放所有 shot 时长，然后重排 start
    if abs(scale - 1.0) > 0.05:
        for shot in spec.shots:
            shot.duration_frames = max(30, min(240, int(shot.duration_frames * scale)))
        # 重排 start — 保证无缝衔接，无 gap 无重叠
        current = 0
        for shot in spec.shots:
            shot.start = current  # type: ignore[attr-defined]
            current += shot.duration_frames
        spec.total_duration_frames = sum(s.duration_frames for s in spec.shots)

    # 2. transition_density: 控制 crossfade 比例
    if trans_density < 0.3:
        # 低转场密度 → 大部分 shot 用 none (硬切)
        for i, shot in enumerate(spec.shots):
            if i > 0:  # 第一个 shot 保持 crossfade
                shot.transition = "none"
    elif trans_density > 0.7:
        # 高转场密度 → 全部 crossfade
        for shot in spec.shots:
            shot.transition = "crossfade"

    # 3. text_density: 降低文字类组件的 fontSize (视觉上减少文字量)
    if text_density < 0.3:
        text_components = {"WordReveal", "GradientText", "KineticText", "TypewriterPrompt"}
        for shot in spec.shots:
            if shot.component in text_components:
                fs = shot.props.get("font_size", "headline")
                # 降一档字号
                size_map = {"display": "headline", "headline": "body", "body": "caption", "caption": "caption"}
                shot.props["font_size"] = size_map.get(fs, fs)

    # 4. easing_profile: 注入到 shot props
    if easing in ("snappy", "smooth", "premium"):
        for shot in spec.shots:
            shot.props["_easing_profile"] = easing

    return spec


def _validate_spec_semantic(spec: VideoSpecV3, phase: str) -> list[str]:
    """语义校验：Pydantic 管结构，这里管「有意义」。

    返回错误列表。空 = 通过。
    拒绝条件:
      1. 引用了不在 COMPONENT_CATALOG 的组件 (Pydantic Literal 已兜底，这里是双保险)
      2. 文字类组件的 text 为空
      3. FeatureGrid 的 features 为空
      4. phase 不匹配 (hook shot 不该用 LogoReveal，cta shot 不该用 CountdownTimer 开场)
    """
    errors: list[str] = []
    valid_components = set(COMPONENT_CATALOG.keys())

    # Phase→不合适组件映射
    phase_blacklist = {
        "hook": {"LogoReveal", "PriceReveal"},  # hook 不该放 logo/价格
        "cta": {"CountdownTimer"},               # cta 不该倒计时开场
    }
    blacklisted = phase_blacklist.get(phase, set())

    text_components = {
        "KineticText", "GradientText", "WordReveal", "TypewriterPrompt",
        "GlassCard", "MarqueeText",
    }
    logo_components = {"LogoReveal"}

    for i, shot in enumerate(spec.shots):
        # 1. 组件名合法性 (双保险)
        if shot.component not in valid_components:
            errors.append(
                f"shot[{i}]: 组件 '{shot.component}' 不在注册表中。"
                f"可用: {sorted(valid_components)}"
            )
            continue

        # 2. 文字类组件 text 不能为空
        if shot.component in text_components:
            text_val = shot.props.get("text", "")
            if not text_val or (isinstance(text_val, str) and not text_val.strip()):
                errors.append(
                    f"shot[{i}]: {shot.component} 的 text 不能为空"
                )

        # 2b. LogoReveal 用 logo_text
        if shot.component in logo_components:
            logo_val = shot.props.get("logo_text", "")
            if not logo_val or (isinstance(logo_val, str) and not logo_val.strip()):
                errors.append(
                    f"shot[{i}]: LogoReveal 的 logo_text 不能为空"
                )

        # 3. FeatureGrid features 不能为空
        if shot.component == "FeatureGrid":
            features = shot.props.get("features", [])
            if not features or not isinstance(features, list):
                errors.append(f"shot[{i}]: FeatureGrid 的 features 不能为空")

        # 4. Phase 黑名单
        if shot.component in blacklisted:
            errors.append(
                f"shot[{i}]: {shot.component} 不适合 {phase} 阶段"
            )

    return errors


def _fallback_spec_for_phase(phase: str, template: dict) -> VideoSpecV3:
    """安全默认 VideoSpec — 当 LLM 反复失败时使用。

    每个 phase 用最稳的组件组合，确保不黑屏。
    """
    phase_info = next((p for p in template.get("timeline", []) if p["phase"] == phase), {})
    dur_pct = phase_info.get("duration_pct", [0, 1])
    total_dur = template.get("duration_range", [15, 30])
    avg_total = (total_dur[0] + total_dur[1]) / 2
    phase_frames = int((dur_pct[1] - dur_pct[0]) * avg_total * 30)
    # Cap individual shots at 180 frames (6s)
    shot_frames = min(180, max(60, phase_frames))

    if phase == "hook":
        shots = [
            ShotSpecV3(component="ParticleBg", props={"count": 20, "style": "float", "color": "#3B82F6", "opacity": 0.2}, duration_frames=shot_frames, phase="hook"),
            ShotSpecV3(component="WordReveal", props={"text": "What if a friend was always there?", "fontSize": 96, "color": "#FFFFFF"}, duration_frames=shot_frames, phase="hook", position="center"),
        ]
    elif phase == "build":
        shots = [
            ShotSpecV3(component="ParticleBg", props={"count": 15, "style": "float", "color": "#3B82F6", "opacity": 0.15}, duration_frames=shot_frames, phase="build"),
            ShotSpecV3(component="FeatureGrid", props={"features": [{"label": "陪伴"}, {"label": "分享"}, {"label": "成长"}, {"label": "温暖"}], "columns": 2}, duration_frames=shot_frames, phase="build", position="center"),
            ShotSpecV3(component="MarqueeText", props={"text": "Friendship • Connection • Together", "speed": 3, "fontSize": 28}, duration_frames=shot_frames, phase="build", position="lower"),
        ]
    else:  # cta
        shots = [
            ShotSpecV3(component="ParticleBg", props={"count": 20, "style": "stars", "color": "#3B82F6", "opacity": 0.2}, duration_frames=shot_frames, phase="cta"),
            ShotSpecV3(component="GradientText", props={"text": "Stop scrolling, start connecting.", "fontSize": 64}, duration_frames=shot_frames, phase="cta", position="center"),
            ShotSpecV3(component="LogoReveal", props={"logo_text": "Friendship", "glow_color": "#3B82F6"}, duration_frames=max(60, shot_frames // 3), phase="cta", position="center"),
        ]

    total = sum(s.duration_frames for s in shots)
    spec = VideoSpecV3(shots=shots, palette="promo", total_duration_frames=total)
    return _enforce_pacing(spec, phase, template)


def generate_video_spec(
    phase: str,
    gap: dict,
    kb_atoms: list,
    materials: list,
    template: dict,
    max_retries: int = 2,
    control_vector: dict | None = None,
) -> VideoSpecV3:
    """v3 公开入口：两步 LLM 调用 + 校验修复环 + 安全默认兜底。

    流程:
      1. Step1 推理 (只跑一次)
      2. Step2 填表 + Pydantic 校验
      3. 语义校验 (组件合法性 + text 非空 + phase 匹配)
      4. 语义失败 → 带错误重提示一次
      5. 仍失败 → 退到安全默认 VideoSpec
    """
    context_block = _build_context_block(phase, gap, kb_atoms, materials, template, control_vector)
    reasoning = _step1_creative_reasoning(context_block)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            spec = _step2_structured_fill(context_block, reasoning)

            # 语义校验 (在 pacing 之前，因为 pacing 会改帧数)
            semantic_errors = _validate_spec_semantic(spec, phase)
            if semantic_errors:
                error_msg = "语义校验失败:\n" + "\n".join(f"  - {e}" for e in semantic_errors)
                print(f"[校验修复环] 第{attempt+1}次: {error_msg}")
                reasoning += (
                    f"\n\n【第{attempt + 1}次填表的语义错误，请修正后重新填写】\n"
                    f"{error_msg}\n"
                    f"请确保: 1) 所有组件来自注册表 2) 文字类组件的 text 非空 3) 组件与 phase 匹配"
                )
                last_error = ValueError(error_msg)
                continue

            spec = _enforce_pacing(spec, phase, template)
            if control_vector:
                spec = _apply_cv_deterministic(spec, control_vector, phase)
            return spec

        except Exception as e:
            last_error = e
            print(f"[校验修复环] 第{attempt+1}次失败: {e}")
            reasoning += f"\n\n【第{attempt + 1}次填表的错误，请修正后重新填写】\n{e}"

    # 所有重试失败 → 安全默认
    print(f"[校验修复环] {max_retries + 1}次尝试全部失败，退到安全默认 VideoSpec")
    return _fallback_spec_for_phase(phase, template)


# ═══════════════════════════════════════════════════════════
# Beat-Level Generation — 结构确定 + LLM 只填内容
# ═══════════════════════════════════════════════════════════

def _load_composition_rules() -> str:
    """加载组合纪律（常驻 system prompt）。"""
    rules_path = Path(__file__).parent.parent.parent / ".claude" / "skills" / "composition-rules.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8").strip()
    return ""


def _load_fewshot_pairings() -> list[dict]:
    """加载 few-shot 好搭配示例。"""
    path = Path(__file__).parent.parent.parent / "fewshot_pairings.json"
    if path.exists():
        import json as _json
        return _json.loads(path.read_text(encoding="utf-8"))
    return []


def _build_rich_candidate_card(catalog, phase: str, need: dict | None = None, already_used: list[str] | None = None) -> str:
    """L2+L3: 硬过滤 → 多因子排序 → 富候选卡。

    每个候选带 description/when_to_use/when_not/example_effect/char_limits。
    """
    # L1: 硬过滤
    char_len = need.get("content_len") if need else None
    candidates = catalog.filter_candidates(phase=phase, char_len=char_len)
    if not candidates:
        return ""

    # L2: 多因子排序
    if need:
        query = catalog.need_to_query(need)
        ranked = catalog.rank(candidates, query, need=need, already_used=already_used, top_k=8)
    else:
        ranked = [(e, 0.5) for e in candidates[:8]]

    # L3: 富候选卡
    lines = [f"可用组件（{phase} 阶段，按适配度排序）:"]
    for entry, score in ranked:
        limits = entry.char_limits or {}
        limit_str = f" [≤{limits.get('max_chars', '无')}字]" if limits else ""
        lines.append(f"  ★ {entry.id}: {entry.description}{limit_str}")
        lines.append(f"    何时用: {entry.when_to_use}")
        if entry.when_not:
            lines.append(f"    不要用在: {entry.when_not}")
        if entry.example_effect:
            lines.append(f"    效果: {entry.example_effect}")

    return "\n".join(lines)


def _format_fewshot(pairings: list[dict], topic: str) -> str:
    """L3: 格式化 few-shot 好搭配示例。"""
    if not pairings:
        return ""
    lines = ["【好搭配示例 — 学习这些选择逻辑】"]
    for p in pairings[:3]:  # 最多 3 条
        need = p["need"]
        lines.append(f"  需求: {need['phase']}阶段, {need['kind']}, {need['content_lang']}, {need['content_len']}字, {need.get('style_family','')}")
        lines.append(f"  选择: {p['choice']} → {json.dumps(p['params'], ensure_ascii=False)}")
        lines.append(f"  理由: {p['why']}")
        lines.append("")
    return "\n".join(lines)


def _fill_beat_content(beats: list[dict], topic: str) -> dict:
    """让 LLM 为每个 beat 填充内容 + 选择动效参数。

    L3: 注入 few-shot 好搭配 + 富候选卡 + 要求 why。
    L2: 用多因子排序的候选（不只 filter）。
    """
    # 加载资源
    composition_rules = _load_composition_rules()
    fewshot = _load_fewshot_pairings()

    try:
        from component_catalog import get_catalog
        catalog = get_catalog()
    except Exception:
        catalog = None

    # 构建 beat 描述（含富候选卡）
    beat_descs = []
    already_used = []
    for b in beats:
        comp_descs = []
        for i, c in enumerate(b.get("components", [])):
            hint = c.get("content_hint", "")
            items = c.get("items_hint", [])
            comp_descs.append(f"  [{i}] {c['ref']} ({c['role']}): {hint}")
            if items:
                for item in items:
                    comp_descs.append(f"       示例: {json.dumps(item, ensure_ascii=False)}")

        # L2+L3: 富候选卡（硬过滤 → 多因子排序 → 带 when_to_use/when_not/example_effect）
        phase = b.get("role", b.get("id", "build"))
        if catalog:
            need = catalog.build_need(
                phase=phase,
                kind="text" if any(c.get("role") in ("hero_text", "title") for c in b.get("components", [])) else "composition",
                content_lang="zh",
            )
            catalog_info = _build_rich_candidate_card(catalog, phase, need=need, already_used=already_used)
            if catalog_info:
                comp_descs.append(f"\n{catalog_info}")

        beat_descs.append(
            f"Beat {b['beat']} ({b['id']}, {b['duration_s']}s):\n"
            + "\n".join(comp_descs)
        )

    beats_text = "\n\n".join(beat_descs)

    # L3: few-shot 好搭配
    fewshot_section = _format_fewshot(fewshot, topic)

    # 组合纪律
    rules_section = ""
    if composition_rules:
        rules_section = f"\n\n【组合纪律 — 必须遵守】\n{composition_rules}\n"

    system_prompt = (
        f"你是短视频内容策划师兼动画导演。主题: {topic}\n"
        f"下方是 beat 结构定义，每个 beat 已有组件类型和可用组件候选。\n"
        f"你的任务：\n"
        f"1. 根据主题为每个 beat 生成**与主题相关的**具体内容\n"
        f"2. 为每个 beat 选择动效参数\n\n"
        f"内容要求：\n"
        f"- 所有文字必须与主题「{topic}」直接相关\n"
        f"- hook (开场): 用一句吸引人的话引出主题，制造悬念或共鸣\n"
        f"- build (主体): 展示主题的核心内容（景点/特色/故事），每个组件一个亮点\n"
        f"- cta (结尾): 总结或号召行动，留下深刻印象\n"
        f"- 如果主题是中文的，文字用中文；如果是英文的，用英文\n"
        f"- 文字要有画面感和节奏感，适合短视频观看\n\n"
        f"- marquee 用英文关键词，• 分隔\n"
        f"- 不要改变组件类型或结构，只填内容\n\n"
        f"【严格字数限制 — 超出会截断！】\n"
        f"- WordReveal text: ≤8个英文单词, ≤50字符\n"
        f"- TypewriterPrompt text: ≤5个英文单词, ≤25字符 (搜索栏很窄!)\n"
        f"- GradientText text: ≤6个英文单词, ≤35字符\n"
        f"- GlassCard title: ≤4个中文字, ≤12字符\n"
        f"- FeatureGrid label: ≤2个英文单词, ≤8字符\n"
        f"- LogoReveal logo_text: ≤2个英文单词, ≤15字符\n"
        f"- MarqueeText: ≤80字符, 关键词用 • 分隔\n\n"
        f"{fewshot_section}\n"
        f"{rules_section}"
        f"输出 JSON 格式 — 用实际的 beat ID 作为 key:\n"
        f'{{\n'
        f'  "hook": {{"0": {{"text": "开场文字", "why": "选择理由"}}}},\n'
        f'  "build": {{"0": {{"text": "主体内容1", "why": "理由"}}, "1": {{"text": "内容2", "why": "理由"}}}},\n'
        f'  "cta": {{"0": {{"text": "结尾文字", "why": "理由"}}}},\n'
        f'  "_animations": {{\n'
        f'    "hook": {{"stagger": 3, "spring": "snappy", "direction": "bottom", "idle": "float", "out": "fade"}},\n'
        f'    "build": {{"stagger": 5, "spring": "bouncy", "direction": "left", "idle": "breathe", "out": "slide_right"}},\n'
        f'    "cta": {{"stagger": 0, "spring": "smooth", "direction": "center", "idle": "none", "out": "fade_scale"}}\n'
        f'  }}\n'
        f'}}\n'
        f"每个组件的 text 必须附带 why 字段，说明为什么选择这个组件和这些参数。\n"
        f"_animations 每个 beat 可选：stagger/spring/snappy/bouncy/smooth/direction/idle/out/text_entrance/text_exit\n"
        f"只输出 JSON，不要其他文字。"
    )

    user_content = f"【Beat 结构】\n{beats_text}\n\n主题: {topic}"

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=MIMO_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=1500,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        result = json.loads(raw)

        # L4: 选择校验 — 检查 LLM 的组件选择是否合理
        if catalog:
            result = _validate_and_fix_choices(result, beats, catalog)

        return result
    except Exception as e:
        print(f"[Beat内容填充] LLM 失败: {e}，使用默认内容")
        return {}


def _validate_and_fix_choices(result: dict, beats: list[dict], catalog) -> dict:
    """L4: 校验 LLM 的选择，不合理则用排序候选替换。"""
    from render_validator import validate_choice

    for b in beats:
        beat_id = b["id"]
        beat_data = result.get(beat_id, {})
        if not isinstance(beat_data, dict):
            continue

        phase = b.get("role", beat_id)
        for comp_idx, comp_data in beat_data.items():
            if comp_idx == "_animation":
                continue
            if not isinstance(comp_data, dict):
                continue

            # 检查 why 字段（L3 要求）
            why = comp_data.get("why", "")
            if not why:
                # 没给理由 — 不拒绝，但记录
                pass

            # L4: 用 catalog 的 filter_candidates 做硬校验
            need = catalog.build_need(phase=phase, kind="text", content_len=len(comp_data.get("text", "")))
            candidates = catalog.filter_candidates(phase=phase, kind="text")
            if not candidates:
                continue

            # 检查当前选择是否在候选列表里
            # （LLM 没有输出 catalog_id，用组件名推断）
            # 这里暂时跳过，因为当前 LLM 输出的是 props 而不是 catalog_id
            # 完整 L4 需要 LLM 输出 catalog_id 后才能做选择校验
            pass

    return result


def generate_video_spec_from_beats(
    template: dict,
    topic: str = "friendship",
    verify: bool = False,
) -> VideoSpecV3:
    """从 beat_sheet 生成 VideoSpec — 结构确定 + LLM 只填内容。

    核心思路:
    - beat 结构 (组件类型、时序、层叠) 完全由 beat_sheet 确定
    - LLM 只填充每个组件的文字内容
    - 同一 beat 内的组件 start 相同 (实现同时渲染)
    - position 用于 z-ordering: center=主内容, lower=底部元素
    """
    beat_sheet = template.get("beat_sheet")
    if not beat_sheet:
        raise ValueError("模板缺少 beat_sheet 字段")

    beats = beat_sheet.get("beats", [])
    if not beats:
        raise ValueError("beat_sheet 为空")

    # LLM 填充内容
    content_map = _fill_beat_content(beats, topic)

    # 知识验证: 搜索验证 LLM 生成内容的事实准确性
    if verify:
        try:
            from knowledge_verifier import verify_knowledge
            verify_result = verify_knowledge(topic, content_map)
            if verify_result.corrected > 0:
                print(f"[知识验证] 修正 {verify_result.corrected} 条声明 "
                      f"(verified={verify_result.verified}, unverifiable={verify_result.unverifiable})")
                for c in verify_result.corrections:
                    print(f"  - {c.claim.source_key}: {c.claim.text[:30]}... → {c.corrected_text[:30]}... ({c.reason})")
                content_map = verify_result.corrected_content
            else:
                print(f"[知识验证] 全部通过 (verified={verify_result.verified})")
        except Exception as e:
            print(f"[知识验证] 失败，使用原始内容: {e}")

    # 提取 LLM 的动效参数
    animations = content_map.get("_animations", {})

    # 组装 shots
    all_shots: list[ShotSpecV3] = []
    current_frame = 0

    for beat in beats:
        beat_id = beat["id"]
        beat_duration = int(beat["duration_s"] * 30)  # s → frames
        beat_content = content_map.get(beat_id, {})
        beat_anim = animations.get(beat_id, {})

        components = beat.get("components", [])
        comp_llm_idx = 0
        for comp in components:
            ref = comp["ref"]
            role = comp.get("role", "hero")
            position = comp.get("position", "center")
            props_hint = dict(comp.get("props_hint", {}))
            repeat = comp.get("repeat", 1)
            items_hint = comp.get("items_hint", [])

            # 从 LLM 内容覆盖 (LLM 可能跳过某些 beat)
            # 保留原始 src（LLM 不知道图片路径，会丢弃它）
            _orig_src = props_hint.get("src", "")
            comp_content = beat_content.get(str(comp_llm_idx), {})
            if comp_content:
                if "items" in comp_content:
                    items_hint = comp_content["items"]
                props_hint.update(comp_content)
            # 恢复 src（LLM 不应覆盖图片路径）
            if _orig_src and not props_hint.get("src"):
                props_hint["src"] = _orig_src
            comp_llm_idx += 1

            # 根据 repeat 生成多个 shot (如 GlassCard×3)
            for r in range(max(1, repeat)):
                item = items_hint[r] if r < len(items_hint) else (items_hint[0] if items_hint else {})
                props = _build_component_props(ref, props_hint, comp, item_override=item)
                props = _enforce_text_limits(props, ref)

                # 应用 LLM 动效参数
                SPRING_PRESETS = {
                    "snappy": {"stiffness": 200, "damping": 18},
                    "bouncy": {"stiffness": 180, "damping": 10},
                    "smooth": {"stiffness": 90, "damping": 20},
                }
                if beat_anim:
                    # 入场 stagger（2-5 帧利落级联）
                    stagger = beat_anim.get("stagger", 0)
                    if stagger > 0 and repeat > 1:
                        props["stagger_delay"] = r * min(stagger, 5)
                    # spring 弹性（命名预设）
                    spring_name = beat_anim.get("spring", "snappy")
                    spring_vals = SPRING_PRESETS.get(spring_name, SPRING_PRESETS["snappy"])
                    props["spring_stiffness"] = spring_vals["stiffness"]
                    props["spring_damping"] = spring_vals["damping"]
                    # 入场方向
                    direction = beat_anim.get("direction", "")
                    if direction:
                        props["entrance_direction"] = direction
                    # 持续微动（idle）：元素在屏上时的次级动作
                    idle = beat_anim.get("idle", "none")
                    props["idle_animation"] = idle
                    # 出场方式（比入场快，Material: outgoing 90ms vs incoming 210ms）
                    out = beat_anim.get("out", "fade")
                    props["exit_animation"] = out

                    # 文字动画（Kinetic Typography）
                    text_entrance = beat_anim.get("text_entrance", "")
                    text_exit = beat_anim.get("text_exit", "")
                    if text_entrance or text_exit:
                        props["text_animation"] = {
                            "entrance": text_entrance or "word_stagger",
                            "exit": text_exit or "fade_up",
                        }

                shot = ShotSpecV3(
                    component=ref,
                    props=props,
                    duration_frames=beat_duration,
                    phase=_beat_to_phase(beat_id),
                    position=position,
                    transition="crossfade",
                )
                all_shots.append(shot)

        current_frame += beat_duration

    total = sum(s.duration_frames for s in all_shots)
    spec = VideoSpecV3(shots=all_shots, palette="promo", total_duration_frames=total)
    return spec


# ── 文本长度约束 ──
# canvas: 1080×1920, safe zone: left=60, right=120 → 可用宽 900px
# 中文字宽 ≈ fontSize, 英文字宽 ≈ fontSize × 0.6 (比例字体)

CHAR_LIMITS = {
    "WordReveal":       {"max_chars": 50,  "max_words": 8,  "note": "逐词揭示, 大字, 可 wrap"},
    "TypewriterPrompt": {"max_chars": 25,  "max_words": 5,  "note": "搜索栏 700px, 单行 nowrap"},
    "GradientText":     {"max_chars": 35,  "max_words": 6,  "note": "渐变大字, 单行, 64px"},
    "GlassCard":        {"max_chars": 20,  "max_words": 4,  "note": "卡片 260px, 内部文字"},
    "MarqueeText":      {"max_chars": 80,  "max_words": 15, "note": "跑马灯, 滚动显示, 长度不限但要可读"},
    "FeatureGrid":      {"max_chars": 8,   "max_words": 2,  "note": "标签 ≤2词, description ≤10字"},
    "LogoReveal":       {"max_chars": 15,  "max_words": 2,  "note": "Logo 文字, 短"},
    "KineticText":      {"max_chars": 20,  "max_words": 4,  "note": "动感文字, 大字"},
}


def _truncate_en(text: str, max_chars: int) -> str:
    """截断英文文本到 max_chars, 在词边界断开。"""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # 在最后一个空格断开
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.5:
        truncated = truncated[:last_space]
    return truncated.rstrip(' .,;:!?') + '...'


def _truncate_zh(text: str, max_chars: int) -> str:
    """截断中文文本到 max_chars。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + '…'


def _enforce_text_limits(props: dict, component: str) -> dict:
    """确保组件的 text 字段不超过显示限制。

    处理: text, logo_text, items[].title, items[].description
    """
    limits = CHAR_LIMITS.get(component)
    if not limits:
        return props

    props = dict(props)
    max_c = limits["max_chars"]

    # 处理 text 字段
    for key in ("text", "logoText", "logo_text"):
        val = props.get(key, "")
        if isinstance(val, str) and len(val) > max_c:
            # 判断中英文
            zh_count = sum(1 for c in val if '一' <= c <= '鿿')
            if zh_count > len(val) * 0.3:
                props[key] = _truncate_zh(val, max_c)
            else:
                props[key] = _truncate_en(val, max_c)
            print(f"[文本截断] {component}.{key}: {len(val)}→{len(props[key])} chars")

    # 处理 features/items 列表
    for key in ("features", "items"):
        items = props.get(key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if "label" in item and len(item["label"]) > 8:
                        item["label"] = item["label"][:7] + "…"
                    if "title" in item and len(item["title"]) > 12:
                        item["title"] = item["title"][:11] + "…"
                    if "description" in item and len(item["description"]) > 15:
                        item["description"] = item["description"][:14] + "…"

    return props


def _beat_to_phase(beat_id: str) -> str:
    """beat id → phase 名称。"""
    if beat_id in ("hook", "typewriter"):
        return "hook"
    if beat_id in ("build", "features", "payoff", "grid"):
        return "build"
    return "cta"


def _build_component_props(ref: str, props_hint: dict, comp_def: dict, item_override: dict | None = None) -> dict:
    """从 props_hint + items_hint 构建组件 props。"""
    props = dict(props_hint)

    if ref == "WordReveal":
        return {
            "text": props.get("text", "What if a friend was always there?"),
            "font_size": "headline",
            "stagger_frames": props.get("stagger_frames", 4),
            "gradient": props.get("gradient", "linear-gradient(90deg, #9CA3AF, #FFFFFF, #3B82F6)"),
            "color": "#FFFFFF",
        }

    if ref == "TypewriterPrompt":
        return {
            "text": props.get("text", "Remember that time we stayed up all night talking?"),
            "char_interval": props.get("char_interval", 1),
            "show_cursor": True,
            "glow_color": "#3B82F6",
            "delay": props.get("delay", 10),
        }

    if ref == "GlassCard":
        item = item_override or {}
        if not item:
            items = props.get("items", comp_def.get("items_hint", []))
            if items:
                item = items[0] if isinstance(items, list) else items
        icon = item.get("icon", "")
        title = item.get("title", item.get("label", ""))
        desc = item.get("desc", item.get("description", ""))
        text = f"{icon} {title}\n{desc}" if title else props.get("text", "")
        return {
            "text": text,
            "width": props.get("width", 260),
            "height": props.get("height", 200),
            "float": props.get("float", True),
            "glow_color": "rgba(59, 130, 246, 0.3)",
        }

    if ref == "MarqueeText":
        return {
            "text": props.get("text", "Laugh • Share • Grow • Support • Memories • Together"),
            "speed": props.get("speed", 2.5),
            "font_size": "caption",
            "color": "rgba(255, 255, 255, 0.35)",
            "direction": "left",
        }

    if ref == "GradientText":
        return {
            "text": props.get("text", "From strangers to soulmates"),
            "font_size": "headline",
            "font_weight": 800,
            "gradient": props.get("gradient", "linear-gradient(90deg, #9CA3AF, #FFFFFF, #3B82F6)"),
        }

    if ref == "FeatureGrid":
        items = props.get("items", comp_def.get("items_hint", []))
        features = [
            {"label": it.get("label", ""), "icon": it.get("icon", ""), "description": it.get("description", "")}
            for it in items
        ] if items else [{"label": "Trust"}, {"label": "Loyalty"}, {"label": "Growth"}, {"label": "Joy"}]
        return {
            "features": features,
            "columns": props.get("columns", 2),
        }

    if ref == "LogoReveal":
        logo_text = (
            props.get("logo_text")
            or props.get("logoText")
            or item_override.get("logo_text", "SoulCircle")
        )
        logo_icon = (
            props.get("logo_icon")
            or props.get("logoIcon")
            or "💛"
        )
        return {
            "logo_text": logo_text,
            "logo_icon": logo_icon,
            "glow_color": "#3B82F6",
        }

    if ref == "GlowTrail":
        return {
            "path_d": "M 100,800 Q 300,200 540,300",
            "color": "#3B82F6",
            "trail_length": 5,
            "dot_size": 6,
            "delay": props.get("delay", 30),
        }

    if ref == "FloatingMockup":
        # 从 props_hint 保留 src（LLM 可能丢弃它）
        original_src = props_hint.get("src", "")
        return {
            "src": props.get("src", "") or original_src,
            "text": props.get("text", ""),
            "width": props.get("width", 400),
            "height": props.get("height", 300),
            "floatSpeed": props.get("floatSpeed", 0.02),
            "perspective": props.get("perspective", 1000),
            "rotateY": props.get("rotateY", 5),
            "delay": props.get("delay", 0),
        }

    if ref == "ParticleBg":
        return {
            "count": props.get("count", 15),
            "color": "#3B82F6",
            "secondary_color": "#60A5FA",
            "style": props.get("style", "float"),
            "opacity": props.get("opacity", 0.15),
        }

    return props


# DEPRECATED: 已被 generate_video_spec() 两步调用替代，保留用于回滚
# 所有正则解析逻辑在此函数内，新代码不再调用
def decisions_to_spec(decision: CreativeDecision, phase: str, materials: list, fps: int = 30, total_seconds: float = 3.0) -> VideoSpec:
    """将 LLM 创意决策转换为 Video Spec JSON。确定性、可预测。"""
    shots = decision.shots
    if not shots:
        return VideoSpec(shots=[])

    total_frames = int(fps * total_seconds)
    min_dur = max(fps, 10)  # 每个 shot 至少 10 帧

    # 计算帧数分配 (按 emphasis 权重)
    weights = [EMPHASIS_WEIGHT.get(s.emphasis, 1.0) for s in shots]
    total_weight = sum(weights)
    frame_allocations = [max(int(total_frames * w / total_weight), min_dur) for w in weights]

    # 标准化确保总帧数正确
    diff = total_frames - sum(frame_allocations)
    if diff != 0:
        max_idx = frame_allocations.index(max(frame_allocations))
        frame_allocations[max_idx] += diff

    # 确保没有 0 帧的 shot
    for i in range(len(frame_allocations)):
        if frame_allocations[i] < 1:
            frame_allocations[i] = min_dur

    # 生成 mat_names 用于图片匹配
    mat_names = [m.get("path", "").split("/")[-1] for m in materials if isinstance(m.get("path"), str)]

    # 转换每个 shot
    spec_shots = []
    current_frame = 0

    for i, (shot_decision, duration) in enumerate(zip(shots, frame_allocations)):
        component = shot_decision.component
        defaults = COMPONENT_DEFAULTS.get(component, {}).copy()

        # 从 idea 中提取具体 props
        idea_props = _extract_props_from_idea(shot_decision.idea, component)
        defaults.update(idea_props)

        # 填充图片素材
        for img_key in ("productImage", "beforeImage", "afterImage"):
            if img_key in defaults and (not defaults[img_key] or defaults[img_key] == ""):
                if mat_names:
                    defaults[img_key] = mat_names[0]

        # 处理换行
        if "text" in defaults and isinstance(defaults["text"], str):
            defaults["text"] = defaults["text"].replace("\n", " ")

        spec_shot = ShotSpec(
            id=f"{phase}_{i+1}",
            role=phase,
            component=component,
            props=defaults,
            start=current_frame,
            duration=duration,
            position=EMPHASIS_POSITION.get(shot_decision.emphasis, "center"),
        )
        spec_shots.append(spec_shot)
        current_frame += duration

    # 如果第一个 shot 不是 ParticleBg，插入一个背景
    if spec_shots and spec_shots[0].component != "ParticleBg":
        bg = ShotSpec(
            id=f"{phase}_bg",
            role=phase,
            component="ParticleBg",
            props=COMPONENT_DEFAULTS["ParticleBg"].copy(),
            start=0,
            duration=total_frames,
            position="center",
        )
        spec_shots.insert(0, bg)

    return VideoSpec(shots=spec_shots)


# ───────────────────────────────────────────────────
# 5. Fallback (无 LLM 时)
# ───────────────────────────────────────────────────


def _fallback_decision(phase: str) -> CreativeDecision:
    """无 LLM 时的默认决策。"""
    if phase == "hook":
        return CreativeDecision(
            concept="痛点反问开场",
            shots=[
                ShotDecision(component="KineticText", idea="大字'你还在为运动时耳机总掉而烦恼？'", emphasis="high"),
            ],
        )
    elif phase == "build":
        return CreativeDecision(
            concept="产品展示+数据说话",
            shots=[
                ShotDecision(component="ProductShowcase", idea="精选好物展示", emphasis="medium"),
                ShotDecision(component="BarChart", idea="效果评分数据", emphasis="medium"),
            ],
        )
    else:
        return CreativeDecision(
            concept="限时优惠促转化",
            shots=[
                ShotDecision(component="PriceReveal", idea="原价¥199，现价¥39.9限时特价", emphasis="high"),
                ShotDecision(component="KineticText", idea="大字'立即抢购'", emphasis="high"),
            ],
        )


# ───────────────────────────────────────────────────
# 6. Prompt 构建 (简单、自由、不约束格式)
# ───────────────────────────────────────────────────


def build_prompt(phase: str, gap: dict, kb_atoms: list, materials: list, template: dict) -> str:
    """构建创意决策 prompt — 只要求 LLM 做选择题，不做格式化。"""
    # KB 推荐
    atom_lines = [f"  - {a.get('remotion_component','?')}: {a.get('description','')}" for a in kb_atoms[:6]]
    atoms_text = "\n".join(atom_lines) or "  无"

    # 素材
    mat_lines = []
    for m in materials[:5]:
        fname = m.get("path", "").split("/")[-1] if isinstance(m.get("path"), str) else ""
        if fname:
            mat_lines.append(f"  - {fname}")
    mats_text = "\n".join(mat_lines) or "  无素材"

    # 爆款模式
    patterns = VIRAL_PATTERNS.get(phase, [])
    pat_text = "\n".join(f"  - {p}" for p in patterns[:4])

    # 组件目录 (简化版，优先推荐 MG 组件)
    cat_text = "\n".join(f"  {name}: {desc}" for name, desc in COMPONENT_CATALOG.items())

    # 模板信息
    narrative = template.get("narrative", {})
    missing = gap.get("missing_shot_types", [])

    return f"""你是短视频 Motion Graphics 导演。为 {phase} 阶段选择创意方案。

## 你的任务
选择用哪些组件、按什么顺序、表达什么创意。不需要管帧数、具体参数——这些由代码自动处理。

## 输入信息
- 阶段: {phase}
- 缺失镜头: {', '.join(missing) or '无'}
- 钩子类型: {narrative.get('hook_type', '')}
- 构建模式: {narrative.get('build_pattern', '')}
- CTA类型: {narrative.get('cta_type', '')}

## 可用素材
{mats_text}

## KB 推荐组件
{atoms_text}

## 爆款参考模式
{pat_text}

## 可用组件
{cat_text}

## 输出格式 (严格按此 JSON 格式)
{DECISION_SCHEMA_EXAMPLE}

## 规则
1. shots 数组 2-4 个元素
2. component 必须是上面列出的组件名
3. idea 用中文描述创意意图，包含关键信息(如文字内容、价格、产品名)
4. emphasis: high=重点镜头, medium=普通, low=过渡
5. 只返回 JSON，不要其他文字"""


# ───────────────────────────────────────────────────
# 7. 校验 + 重试
# ───────────────────────────────────────────────────


def _validate_decision(raw: dict) -> Optional[CreativeDecision]:
    """校验 LLM 输出的决策。"""
    try:
        return CreativeDecision(**raw)
    except Exception as e:
        print(f"Decision validation failed: {e}")
        return None


def _build_retry_prompt(original_prompt: str, raw_output: str, error: str) -> str:
    """构建重试 prompt，附带具体错误信息。"""
    return f"""{original_prompt}

---
你上次的输出有问题，请修正：

你的输出:
{raw_output[:500]}

错误信息: {error}

请重新输出正确的 JSON。"""


# ───────────────────────────────────────────────────
# 8. 主入口
# ───────────────────────────────────────────────────


async def orchestrate_animation(
    phase: str,
    gap: dict,
    kb_atoms: list,
    materials: list,
    template: dict,
    fps: int = 30,
    total_seconds: float = 3.0,
    control_vector: dict | None = None,
) -> dict:
    """完整编排流程：v3 两步 LLM 调用，失败时 fallback 到 v2。"""

    # Compute phase duration from template
    phase_info = next((p for p in template.get("timeline", []) if p["phase"] == phase), {})
    dur_pct = phase_info.get("duration_pct", [0, 1])
    total_dur = template.get("duration_range", [15, 30])
    avg_total = (total_dur[0] + total_dur[1]) / 2
    phase_seconds = (dur_pct[1] - dur_pct[0]) * avg_total

    # 无 API key → v2 fallback
    if not MIMO_API_KEY:
        decision = _fallback_decision(phase)
        spec = decisions_to_spec(decision, phase, materials, fps, phase_seconds)
        spec = _enforce_pacing(spec, phase, template)
        return spec.model_dump()

    # ── v3: 两步调用 ──────────────────────────────────────
    try:
        spec_v3 = generate_video_spec(phase, gap, kb_atoms, materials, template, control_vector=control_vector)
        return spec_v3.to_render_input()
    except Exception as e:
        print(f"v3 两步调用失败，fallback 到 v2: {e}")

    # ── v2 fallback: 浅 schema + 正则解析 ─────────────────
    prompt = build_prompt(phase, gap, kb_atoms, materials, template)
    decision = None
    raw_output = ""

    try:
        headers = {"Authorization": f"Bearer {MIMO_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MIMO_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
            "max_tokens": 800,
        }
        resp = httpx.post(MIMO_API_URL, json=payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        raw_output = msg.get("content", "").strip()
        if not raw_output:
            raw_output = msg.get("reasoning_content", "").strip()

        if raw_output:
            raw_dict = json.loads(raw_output)
            decision = _validate_decision(raw_dict)

            if decision is None:
                error_msg = f"shots 组件名必须是: {list(COMPONENT_CATALOG.keys())}"
                retry_prompt = _build_retry_prompt(prompt, raw_output, error_msg)
                payload["messages"] = [{"role": "user", "content": retry_prompt}]
                resp2 = httpx.post(MIMO_API_URL, json=payload, headers=headers, timeout=120.0)
                resp2.raise_for_status()
                raw2 = resp2.json()["choices"][0]["message"].get("content", "").strip()
                if raw2:
                    decision = _validate_decision(json.loads(raw2))

    except json.JSONDecodeError as e:
        print(f"v2 JSON parse error: {e}")
    except Exception as e:
        print(f"v2 LLM call failed: {e}")

    if decision is None:
        decision = _fallback_decision(phase)

    spec = decisions_to_spec(decision, phase, materials, fps, phase_seconds)
    spec = _enforce_pacing(spec, phase, template)
    return spec.model_dump()


async def orchestrate_from_beats(
    template: dict,
    topic: str = "friendship",
    verify: bool = False,
) -> dict:
    """Beat-level 编排入口 — 结构确定 + LLM 只填内容。

    当 template 含 beat_sheet 时使用此函数。
    返回完整 VideoSpec render input (所有 beats 的 shots)。
    同一 beat 内的组件 start 相同 → 同时渲染。
    """
    beat_sheet = template.get("beat_sheet")
    if not beat_sheet:
        raise ValueError("模板缺少 beat_sheet")

    if not MIMO_API_KEY:
        print("[Beat编排] 无 API key，使用 beat sheet 默认内容")

    try:
        spec = generate_video_spec_from_beats(template, topic, verify=verify)
    except Exception as e:
        print(f"[Beat编排] 失败: {e}")
        raise

    # Build render input with beat-level start times
    # (not sequential like to_render_input)
    beats = beat_sheet.get("beats", [])
    beat_starts = {}
    frame = 0
    for beat in beats:
        beat_id = beat["id"]
        beat_dur = int(beat["duration_s"] * 30)
        beat_starts[beat_id] = frame
        frame += beat_dur

    # Map each shot to its beat start
    # Account for repeat: one comp with repeat=3 generates 3 shots
    shot_beat_map = {}
    shot_idx = 0
    for beat in beats:
        beat_id = beat["id"]
        for comp in beat.get("components", []):
            repeat = max(1, comp.get("repeat", 1))
            for _ in range(repeat):
                if shot_idx < len(spec.shots):
                    shot_beat_map[shot_idx] = beat_starts[beat_id]
                    shot_idx += 1

    from video_spec_schema import _resolve_props

    # First pass: build shots with beat starts
    render_shots = []
    for i, shot in enumerate(spec.shots):
        render_shots.append({
            "id": f"beat_{shot.phase}_{i}",
            "role": shot.phase,
            "component": shot.component,
            "props": _resolve_props(shot),
            "start": shot_beat_map.get(i, 0),
            "duration": shot.duration_frames,
            "position": shot.position,
            "transition": shot.transition,
        })

    # Second pass: re-sequence beats to be contiguous (no gaps)
    # Group by beat start, then recompute starts from actual max durations
    beat_groups: dict[int, list[dict]] = {}
    for shot in render_shots:
        s = shot["start"]
        if s not in beat_groups:
            beat_groups[s] = []
        beat_groups[s].append(shot)

    new_start = 0
    for old_start in sorted(beat_groups.keys()):
        group = beat_groups[old_start]
        max_dur = max(s["duration"] for s in group)
        for shot in group:
            shot["start"] = new_start
        new_start += max_dur

    return {
        "fps": 30,
        "globalStyle": {"bgColor": "#050510", "palette": "promo"},
        "shots": render_shots,
    }


async def orchestrate_full_video(assignment, template, kb_atoms_per_phase, materials):
    """为完整视频的每个 phase 生成动画脚本。"""
    scripts = {}
    for phase_data in assignment.get("phases", []):
        phase_name = phase_data.get("phase", "")
        strategy = phase_data.get("strategy_id", "")
        if strategy not in ("C", "D", "F"):
            continue
        gap = {"phase": phase_name, "missing_shot_types": [], "severity": "LOW"}
        atoms = kb_atoms_per_phase.get(phase_name, [])
        script = await orchestrate_animation(phase_name, gap, atoms, materials, template)
        scripts[phase_name] = script
    return scripts
