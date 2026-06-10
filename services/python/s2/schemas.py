"""S2 VLM 增强方案 — 数据结构定义。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ASRSegment(BaseModel):
    start: float
    end: float
    text: str
    no_speech_prob: float = 0.0


class PhaseDraft(BaseModel):
    """Stage B 的输出，VLM 的输入。"""
    phase: str  # "hook" / "build" / "cta"
    start: float
    end: float
    asr_text: str = ""
    type_candidates: list[tuple[str, float]] = Field(default_factory=list)


class HookAnalysis(BaseModel):
    hook_type: str = "利益直接"
    visual_technique: str = ""
    text_on_screen: str = ""
    confidence: str = "medium"  # low / medium / high


class BuildAnalysis(BaseModel):
    build_pattern: str = "教程步骤"
    pacing: str = "medium"  # fast_cuts / medium / steady
    key_moments: list[dict] = Field(default_factory=list)


class CTAAnalysis(BaseModel):
    cta_type: str = "社会认同"
    urgency_cues: list[str] = Field(default_factory=list)
    text_on_screen: str = ""
    confidence: str = "medium"


class VLMRefinement(BaseModel):
    """Stage C 的输出。"""
    category_primary: str = "通用"
    category_secondary: list[str] = Field(default_factory=list)
    hook_end_adjusted: float | None = None
    cta_start_adjusted: float | None = None
    narrative_arc: str = ""
    hook: HookAnalysis = Field(default_factory=HookAnalysis)
    build: BuildAnalysis = Field(default_factory=BuildAnalysis)
    cta: CTAAnalysis = Field(default_factory=CTAAnalysis)
