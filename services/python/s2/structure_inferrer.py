"""Stage B: 规则 + ASR/Caption 结构推断 — 零 VLM 成本。

对纯音乐 MG（无旁白），用 S1 VLM caption 里的屏幕文字替代 ASR。
"""
from __future__ import annotations

import re

from .schemas import ASRSegment, PhaseDraft


def compute_initial_phases(duration: float) -> dict[str, float]:
    """位置百分比先验，按视频时长分档。

    来源: 业界 118k+ 爆款视频验证的 Hook/Build/CTA 框架。
    hook_end 保守估计为前 20%（MG 视频 hook 通常较长）。
    """
    if duration <= 15:
        return {"hook_end": min(3.0, duration * 0.25), "build_end": max(3, duration - 2), "cta_end": duration}
    elif duration <= 45:
        return {"hook_end": duration * 0.2, "build_end": duration - 4, "cta_end": duration}
    else:
        return {"hook_end": duration * 0.15, "build_end": duration * 0.85, "cta_end": duration}


# ── Hook 类型匹配 ──────────────────────────────────────────

HOOK_PATTERNS: dict[str, list[str]] = {
    "悬念反问": [r"你.{0,5}知道", r"猜猜", r"为什么", r"怎么", r"\?", r"？"],
    "数字震惊": [r"\d+(块|元|岁|年|天|个|次|倍|万|亿)", r"前\d+名", r"第\d+", r"\d+%"],
    "否定常识": [r"千万别", r"不要", r"错了", r"误区", r"别再", r"停止"],
    "利益直接": [r"教你", r"学会", r"省钱", r"免费", r"分享", r"推荐", r"必看"],
    "前后对比": [r"以前.{0,10}现在", r"原来.{0,10}变成", r"之前.{0,10}之后", r"对比"],
    "社会认同": [r"\d+万人", r"爆卖", r"断货", r"火了", r"刷屏", r"全网"],
}

# ── Build pattern 匹配 ────────────────────────────────────

BUILD_PATTERNS: dict[str, list[str]] = {
    "教程步骤": [r"第[一二三1-9]步", r"步骤", r"首先", r"然后", r"接着", r"最后"],
    "对比展示": [r"对比", r"vs", r"区别", r"不同", r"哪个好"],
    "痛点列举": [r"烦恼", r"困扰", r"问题", r"痛点", r"难受"],
    "故事叙述": [r"有一天", r"朋友.{0,5}说", r"发现", r"经历"],
    "清单罗列": [r"第[一二三四五]", r"个方法", r"个技巧", r"个原因"],
}

# ── CTA 类型匹配 ───────────────────────────────────────────

CTA_PATTERNS: dict[str, list[str]] = {
    "限时优惠": [r"限时", r"最后\d+[天小时]", r"优惠", r"折扣", r"特价", r"半价"],
    "社会认同": [r"评论", r"点赞", r"关注", r"收藏", r"转发", r"告诉我"],
    "直接索取": [r"链接", r"购物车", r"小黄车", r"下单", r"购买", r"点击"],
    "悬念留白": [r"下期", r"下次", r"揭晓", r"未完待续", r"敬请期待"],
}


def _match_patterns(text: str, patterns: dict[str, list[str]]) -> list[tuple[str, float]]:
    """返回按置信度排序的 (类型, 置信度) 列表，取 top-3。"""
    candidates = []
    for type_name, regexes in patterns.items():
        hits = sum(1 for r in regexes if re.search(r, text))
        if hits > 0:
            candidates.append((type_name, round(hits / len(regexes), 3)))
    return sorted(candidates, key=lambda x: -x[1])[:3]


def infer_hook_candidates(asr: list[ASRSegment], hook_end: float,
                          captions: list[dict] | None = None) -> list[tuple[str, float]]:
    """从 ASR 前 N 秒文本中推断 hook 类型候选。

    如果 ASR 为空（无旁白），用 VLM caption 里的屏幕文字。
    """
    hook_text = " ".join(s.text for s in asr if s.start < hook_end)
    if not hook_text and captions:
        hook_text = " ".join(c["caption"] for c in captions if c.get("start_time", 999) < hook_end)
    return _match_patterns(hook_text, HOOK_PATTERNS) if hook_text else [("利益直接", 0.5)]


def infer_build_candidates(asr: list[ASRSegment], build_start: float, build_end: float,
                           captions: list[dict] | None = None) -> list[tuple[str, float]]:
    """从 ASR build 阶段文本中推断 build pattern 候选。"""
    build_text = " ".join(s.text for s in asr if build_start <= s.start < build_end)
    if not build_text and captions:
        build_text = " ".join(
            c["caption"] for c in captions
            if build_start <= c.get("start_time", 999) < build_end
        )
    return _match_patterns(build_text, BUILD_PATTERNS) if build_text else [("教程步骤", 0.5)]


def infer_cta_candidates(asr: list[ASRSegment], cta_start: float,
                         captions: list[dict] | None = None) -> list[tuple[str, float]]:
    """从 ASR 末尾文本中推断 CTA 类型候选。"""
    cta_text = " ".join(s.text for s in asr if s.start >= cta_start)
    if not cta_text and captions:
        cta_text = " ".join(c["caption"] for c in captions if c.get("start_time", 0) >= cta_start)
    return _match_patterns(cta_text, CTA_PATTERNS) if cta_text else [("社会认同", 0.5)]


def build_phase_drafts(
    asr: list[ASRSegment],
    phases: dict[str, float],
    captions: list[dict] | None = None,
) -> tuple[PhaseDraft, PhaseDraft, PhaseDraft]:
    """构建三个 phase 的初始草案。

    captions: S1 的 Shot 列表 (dict 格式, 含 start_time/end_time/caption),
              作为无旁白 MG 的文本来源替代 ASR。
    """
    hook_end = phases["hook_end"]
    build_end = phases["build_end"]

    # 合并 ASR + caption 文本
    hook_asr = " ".join(s.text for s in asr if s.start < hook_end)
    build_asr = " ".join(s.text for s in asr if hook_end <= s.start < build_end)
    cta_asr = " ".join(s.text for s in asr if s.start >= build_end)

    if captions:
        if not hook_asr:
            hook_asr = " ".join(c["caption"] for c in captions if c.get("start_time", 999) < hook_end)
        if not build_asr:
            build_asr = " ".join(
                c["caption"] for c in captions
                if hook_end <= c.get("start_time", 999) < build_end
            )
        if not cta_asr:
            cta_asr = " ".join(c["caption"] for c in captions if c.get("start_time", 0) >= build_end)

    hook_draft = PhaseDraft(
        phase="hook", start=0, end=hook_end,
        asr_text=hook_asr,
        type_candidates=infer_hook_candidates(asr, hook_end, captions),
    )
    build_draft = PhaseDraft(
        phase="build", start=hook_end, end=build_end,
        asr_text=build_asr,
        type_candidates=infer_build_candidates(asr, hook_end, build_end, captions),
    )
    cta_draft = PhaseDraft(
        phase="cta", start=build_end, end=phases["cta_end"],
        asr_text=cta_asr,
        type_candidates=infer_cta_candidates(asr, build_end, captions),
    )

    return hook_draft, build_draft, cta_draft
