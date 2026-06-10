"""ControlVector — 类型化控制向量，三任务共用地基。

Task 10 (多版本): 预设 profile → ControlVector
Task 12 (人工可调): 用户直接改 ControlVector 字段
Task 13 (NL 编辑): LLM 解析指令 → EditOp delta → 打在 ControlVector 上

所有数值 clamp 在合法区间，orchestrator 消费时叠加 theme + registry 校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal
import copy


# ═══════════════════════════════════════════════════════════
# ControlVector 定义
# ═══════════════════════════════════════════════════════════

EasingProfile = Literal["snappy", "smooth", "premium"]


@dataclass
class ControlVector:
    """类型化控制向量 — orchestrator 的输入参数。"""

    # Phase 时长权重 (相对值，会被归一化)
    phase_weights: dict[str, float] = field(
        default_factory=lambda: {"hook": 1.0, "build": 1.0, "cta": 1.0}
    )

    # 镜头时长缩放: 0.7=更快, 1.0=标准, 1.4=更慢
    shot_duration_scale: float = 1.0

    # 转场密度: 0=硬切, 0.5=适度, 1=每 shot 转场
    transition_density: float = 0.5

    # 踩点同步
    beat_sync: bool = False

    # 每 phase 组件偏好顺序 (引用 COMPONENT_REGISTRY)
    component_priority: dict[str, list[str]] = field(default_factory=lambda: {
        "hook": ["WordReveal", "GradientText", "TypewriterPrompt", "KineticText"],
        "build": ["FeatureGrid", "GlassCard", "FloatingMockup", "ProductShowcase"],
        "cta": ["GradientText", "LogoReveal", "KineticText"],
    })

    # 文字密度: 0=纯画面, 0.5=适度, 1=满屏字幕
    text_density: float = 0.5

    # CTA 强度: 0=弱收尾, 1=强 CTA
    cta_emphasis: float = 0.5

    # 缓动风格
    easing_profile: EasingProfile = "smooth"

    # 内容/卖点顺序 (可被 "把商品提前" 重排)
    content_order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ControlVector":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    def clamp(self) -> "ControlVector":
        """确保所有数值在合法区间。"""
        v = copy.deepcopy(self)
        v.shot_duration_scale = max(0.5, min(2.0, v.shot_duration_scale))
        v.transition_density = max(0.0, min(1.0, v.transition_density))
        v.text_density = max(0.0, min(1.0, v.text_density))
        v.cta_emphasis = max(0.0, min(1.0, v.cta_emphasis))
        for k in v.phase_weights:
            v.phase_weights[k] = max(0.1, min(3.0, v.phase_weights[k]))
        if v.easing_profile not in ("snappy", "smooth", "premium"):
            v.easing_profile = "smooth"
        return v


# ═══════════════════════════════════════════════════════════
# 命名 Profile (Task 10: 4 个内容策略变体)
# ═══════════════════════════════════════════════════════════

PROFILES: dict[str, ControlVector] = {
    "ctr": ControlVector(
        phase_weights={"hook": 2.0, "build": 0.8, "cta": 0.8},
        shot_duration_scale=0.8,       # 前 3 秒抓人，镜头快
        transition_density=0.7,        # 高密度转场
        component_priority={
            "hook": ["WordReveal", "GradientText", "TypewriterPrompt"],
            "build": ["GlassCard", "FeatureGrid", "FloatingMockup"],
            "cta": ["GradientText", "LogoReveal"],
        },
        text_density=0.6,              # 中高文字密度
        cta_emphasis=0.4,              # CTA 不用太强，靠 hook 抓
        easing_profile="snappy",
    ),

    "conversion": ControlVector(
        phase_weights={"hook": 0.8, "build": 1.5, "cta": 1.5},
        shot_duration_scale=1.2,       # 信息量大，镜头较长
        transition_density=0.3,        # 低转场，少干扰
        component_priority={
            "hook": ["WordReveal", "KineticText"],
            "build": ["FeatureGrid", "GlassCard", "ProductShowcase"],
            "cta": ["GradientText", "LogoReveal", "PriceReveal"],
        },
        text_density=0.7,              # 高文字，卖点清晰
        cta_emphasis=0.9,              # 强 CTA
        easing_profile="smooth",
    ),

    "pace": ControlVector(
        phase_weights={"hook": 1.0, "build": 1.0, "cta": 1.0},
        shot_duration_scale=0.6,       # 快切
        transition_density=0.9,        # 高转场密度
        beat_sync=True,                # 踩点
        component_priority={
            "hook": ["WordReveal", "GradientText"],
            "build": ["GlassCard", "MarqueeText", "FeatureGrid"],
            "cta": ["GradientText", "LogoReveal"],
        },
        text_density=0.3,              # 少字，靠画面节奏
        cta_emphasis=0.5,
        easing_profile="snappy",
    ),

    "premium": ControlVector(
        phase_weights={"hook": 1.2, "build": 1.0, "cta": 0.8},
        shot_duration_scale=1.4,       # 慢镜头
        transition_density=0.2,        # 少转场，留白
        component_priority={
            "hook": ["GradientText", "WordReveal"],
            "build": ["GlassCard", "FloatingMockup"],
            "cta": ["LogoReveal", "GradientText"],
        },
        text_density=0.3,              # 少字，质感
        cta_emphasis=0.4,              # 淡收尾
        easing_profile="premium",
    ),
}


def get_profile(name: str) -> ControlVector:
    """获取命名 profile，不存在则返回默认。"""
    return copy.deepcopy(PROFILES.get(name, ControlVector()))


def list_profiles() -> list[str]:
    return list(PROFILES.keys())


# ═══════════════════════════════════════════════════════════
# EditOp — Task 13 NL 编辑操作 (枚举)
# ═══════════════════════════════════════════════════════════

@dataclass
class EditOp:
    """单个编辑操作 — LLM 从自然语言解析出的 delta。"""
    op: str       # 操作类型
    amount: float = 0.0  # 幅度 (0-1)
    target: str = ""     # 目标 (phase/component/style)
    value: str = ""      # 值

    def to_dict(self) -> dict:
        return asdict(self)


# 合法 op 枚举
VALID_OPS = {
    "strengthen_hook",     # "开头更抓人"
    "reduce_text",         # "减少字幕"
    "increase_pace",       # "增强节奏感"
    "reorder_content",     # "把商品信息提前"
    "change_packaging",    # "换包装风格"
    "adjust_ending",       # "结尾更有力"
    "slow_down",           # "慢一点"
    "add_transition",      # "加转场"
    "simplify",            # "简洁一些"
}


def apply_edit_ops(cv: ControlVector, ops: list[EditOp]) -> ControlVector:
    """将 EditOp delta 应用到 ControlVector。返回新实例。"""
    v = copy.deepcopy(cv)

    for op in ops:
        if op.op not in VALID_OPS:
            continue

        a = max(0.0, min(1.0, op.amount))  # clamp

        if op.op == "strengthen_hook":
            v.phase_weights["hook"] = min(3.0, v.phase_weights["hook"] + a * 1.0)
            v.shot_duration_scale = max(0.5, v.shot_duration_scale - a * 0.3)
            if a > 0.5:
                v.component_priority["hook"] = ["WordReveal", "GradientText", "TypewriterPrompt"]

        elif op.op == "reduce_text":
            v.text_density = max(0.0, v.text_density - a * 0.5)

        elif op.op == "increase_pace":
            v.shot_duration_scale = max(0.5, v.shot_duration_scale - a * 0.4)
            v.transition_density = min(1.0, v.transition_density + a * 0.3)
            v.beat_sync = a > 0.5

        elif op.op == "reorder_content":
            if op.value and op.value in v.content_order:
                v.content_order.remove(op.value)
                v.content_order.insert(0, op.value)
            elif op.value:
                v.content_order.insert(0, op.value)

        elif op.op == "change_packaging":
            if op.target in ("snappy", "smooth", "premium"):
                v.easing_profile = op.target  # type: ignore

        elif op.op == "adjust_ending":
            v.cta_emphasis = min(1.0, v.cta_emphasis + a * 0.5)

        elif op.op == "slow_down":
            v.shot_duration_scale = min(2.0, v.shot_duration_scale + a * 0.4)

        elif op.op == "add_transition":
            v.transition_density = min(1.0, v.transition_density + a * 0.3)

        elif op.op == "simplify":
            v.text_density = max(0.0, v.text_density - a * 0.3)
            v.transition_density = max(0.0, v.transition_density - a * 0.2)

    return v.clamp()
