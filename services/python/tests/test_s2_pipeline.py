"""S2 V2 Pipeline 单元测试
运行: cd services/python && pytest tests/test_s2_pipeline.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from s2.schemas import ASRSegment, PhaseDraft, VLMRefinement, HookAnalysis, CTAAnalysis
from s2.structure_inferrer import (
    compute_initial_phases,
    infer_hook_candidates,
    infer_cta_candidates,
    build_phase_drafts,
    _match_patterns,
)


# ── Stage B: compute_initial_phases ─────────────────────

def test_short_video():
    p = compute_initial_phases(10.0)
    assert p["hook_end"] == 2.5
    assert p["cta_end"] == 10.0


def test_medium_video():
    p = compute_initial_phases(28.0)
    assert p["hook_end"] == 3.0
    assert p["cta_end"] == 28.0


def test_long_video():
    p = compute_initial_phases(60.0)
    assert p["hook_end"] == 4.0
    assert p["build_end"] == 51.0  # 60 * 0.85


# ── Stage B: hook candidates ────────────────────────────

def test_hook_question():
    asr = [ASRSegment(start=0, end=2, text="你们知道吗这个东西有多好用？")]
    candidates = infer_hook_candidates(asr, 3.0)
    types = [c[0] for c in candidates]
    assert "悬念反问" in types


def test_hook_number():
    asr = [ASRSegment(start=0, end=2, text="99%的人都不知道这个方法")]
    candidates = infer_hook_candidates(asr, 3.0)
    types = [c[0] for c in candidates]
    assert "数字震惊" in types


def test_hook_negation():
    asr = [ASRSegment(start=0, end=2, text="千万别这样洗脸")]
    candidates = infer_hook_candidates(asr, 3.0)
    types = [c[0] for c in candidates]
    assert "否定常识" in types


def test_hook_benefit():
    asr = [ASRSegment(start=0, end=2, text="教你3天瘦5斤的方法")]
    candidates = infer_hook_candidates(asr, 3.0)
    types = [c[0] for c in candidates]
    assert "利益直接" in types


def test_hook_empty_asr():
    candidates = infer_hook_candidates([], 3.0)
    assert candidates == [("利益直接", 0.5)]


# ── Stage B: CTA candidates ─────────────────────────────

def test_cta_urgency():
    asr = [ASRSegment(start=20, end=23, text="限时优惠最后3天")]
    candidates = infer_cta_candidates(asr, 20.0)
    types = [c[0] for c in candidates]
    assert "限时优惠" in types


def test_cta_social():
    asr = [ASRSegment(start=20, end=23, text="评论区告诉我点赞收藏")]
    candidates = infer_cta_candidates(asr, 20.0)
    types = [c[0] for c in candidates]
    assert "社会认同" in types


def test_cta_direct():
    asr = [ASRSegment(start=20, end=23, text="链接在小黄车点击购买")]
    candidates = infer_cta_candidates(asr, 20.0)
    types = [c[0] for c in candidates]
    assert "直接索取" in types


# ── Stage B: build_phase_drafts ─────────────────────────

def test_phase_drafts_structure():
    asr = [
        ASRSegment(start=0, end=2, text="你知道吗？"),
        ASRSegment(start=3, end=6, text="第一步洁面"),
        ASRSegment(start=7, end=10, text="第二步护肤"),
        ASRSegment(start=20, end=23, text="限时优惠"),
    ]
    phases = compute_initial_phases(25.0)
    hook, build, cta = build_phase_drafts(asr, phases)

    assert hook.phase == "hook"
    assert build.phase == "build"
    assert cta.phase == "cta"
    assert hook.end == phases["hook_end"]
    assert build.start == phases["hook_end"]
    assert cta.start == phases["build_end"]


# ── VLMRefinement schema ───────────────────────────────

def test_vlm_refinement_defaults():
    ref = VLMRefinement()
    assert ref.category_primary == "通用"
    assert ref.hook.hook_type == "利益直接"
    assert ref.cta.cta_type == "社会认同"


def test_vlm_refinement_with_data():
    ref = VLMRefinement(
        category_primary="美妆",
        hook=HookAnalysis(hook_type="悬念反问", confidence="high"),
        cta=CTAAnalysis(cta_type="限时优惠", urgency_cues=["倒计时"]),
    )
    assert ref.category_primary == "美妆"
    assert ref.hook.hook_type == "悬念反问"
    assert ref.hook.confidence == "high"
    assert "倒计时" in ref.cta.urgency_cues
