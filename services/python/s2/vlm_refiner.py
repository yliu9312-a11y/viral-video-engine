"""Stage C: VLM 微调 — 用 MiMo-V2.5 在候选中判定 + 边界微调。"""
from __future__ import annotations

import base64
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import httpx

from .schemas import ASRSegment, HookAnalysis, BuildAnalysis, CTAAnalysis, VLMRefinement

logger = logging.getLogger(__name__)

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_API_URL = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
VLM_MODEL = os.environ.get("MIMO_VLM_MODEL", "mimo-v2.5")


def _extract_frames(video_path: str, timestamps: list[float]) -> list[str]:
    """从视频中提取指定时间戳的帧，返回 base64 JPEG 列表。"""
    cap = cv2.VideoCapture(video_path)
    frames_b64 = []
    for ts in timestamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ret, frame = cap.read()
        if not ret:
            continue
        h, w = frame.shape[:2]
        if h > 720:
            scale = 720 / h
            frame = cv2.resize(frame, (int(w * scale), 720))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frames_b64.append(base64.b64encode(buf).decode("utf-8"))
    cap.release()
    return frames_b64


def _vlm_call(messages: list[dict], max_tokens: int = 500) -> str | None:
    """单次 VLM 调用，返回 content 文本。失败返回 None。"""
    if not MIMO_API_KEY:
        return None
    try:
        resp = httpx.post(
            MIMO_API_URL,
            json={
                "model": VLM_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
            },
            headers={"Authorization": f"Bearer {MIMO_API_KEY}"},
            timeout=90.0,
        )
        if resp.status_code != 200:
            logger.warning(f"VLM 调用失败: {resp.status_code}")
            return None
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content", "").strip()
        if not content:
            content = msg.get("reasoning_content", "").strip()
        return content if content else None
    except Exception as e:
        logger.warning(f"VLM 调用异常: {e}")
        return None


def _parse_json(text: str) -> dict | None:
    """从 VLM 输出中提取 JSON。"""
    import re
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试提取 JSON 块
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ═══════════════════════════════════════════════════════════
# Call 1: 粗结构 + 类别（看完整视频，1fps 采样）
# ═══════════════════════════════════════════════════════════

def _call1_category_structure(
    video_path: str, duration: float,
    hook_end: float, cta_start: float,
) -> dict | None:
    """VLM Call 1: 粗判类别 + 边界微调。"""
    # 1fps 采样，最多 30 帧
    n_frames = min(30, max(8, int(duration)))
    timestamps = [duration * i / n_frames for i in range(n_frames)]
    frames_b64 = _extract_frames(video_path, timestamps)
    if len(frames_b64) < 3:
        return None

    # 构造 multi-image prompt
    content = []
    for i, (ts, b64) in enumerate(zip(timestamps, frames_b64)):
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    content.append({"type": "text", "text": (
        f"这是 {duration:.1f}s 短视频的 {len(frames_b64)} 个关键帧（按时间顺序，每帧约 {duration/n_frames:.1f}s）。\n\n"
        f"当前初始 phase 划分: hook 结束于 {hook_end:.1f}s, CTA 开始于 {cta_start:.1f}s。\n\n"
        "请分析并返回 JSON（只返回 JSON）:\n"
        "{\n"
        '  "category_primary": "好物推荐/美妆/美食/数码/生活/健身/知识/宠物/母婴/家居/旅行 选一个",\n'
        '  "category_secondary": ["可选第二类别"],\n'
        f'  "hook_end_adjusted": {hook_end},  // 在 [{max(0, hook_end-2):.1f}, {hook_end+2:.1f}] 内微调\n'
        f'  "cta_start_adjusted": {cta_start},  // 在 [{cta_start-2:.1f}, {min(duration, cta_start+2):.1f}] 内微调\n'
        '  "narrative_arc": "用箭头描述叙事节奏，如 hook→pain→solution→proof→cta"\n'
        "}"
    )})

    result = _vlm_call([{"role": "user", "content": content}])
    return _parse_json(result) if result else None


# ═══════════════════════════════════════════════════════════
# Call 2: Hook 细分类（只看前 5s）
# ═══════════════════════════════════════════════════════════

def _call2_hook_classify(
    video_path: str, hook_end: float,
    hook_candidates: list[tuple[str, float]],
    hook_asr: str,
) -> dict | None:
    """VLM Call 2: Hook 细分类。"""
    # 前 5s 采样 3fps = 15 帧
    timestamps = [i / 3.0 for i in range(15) if i / 3.0 <= min(5, hook_end)]
    frames_b64 = _extract_frames(video_path, timestamps)
    if not frames_b64:
        return None

    candidate_str = " / ".join(f"{t}" for t, _ in hook_candidates) if hook_candidates else "未知"
    asr_line = f"前 {hook_end:.1f}s 的口语: \"{hook_asr}\"" if hook_asr else "无口语数据"

    content = []
    for i, (ts, b64) in enumerate(zip(timestamps, frames_b64)):
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    content.append({"type": "text", "text": (
        f"这是短视频开头 {min(5, hook_end):.1f}s 的关键帧。\n\n"
        f"口语内容: {asr_line}\n"
        f"候选 hook 类型: {candidate_str}\n\n"
        "镜头类型枚举: 人脸特写 / 产品展示 / 场景建立 / 分屏对比 / 文字冲击 / 开箱 / 反应\n\n"
        "返回 JSON（只返回 JSON）:\n"
        "{\n"
        '  "hook_type": "从候选中选一个，如果没有匹配的可自行判断",\n'
        '  "visual_technique": "从镜头类型枚举中选",\n'
        '  "text_on_screen": "画面中的关键文字（无则空字符串）",\n'
        '  "confidence": "low / medium / high"\n'
        "}"
    )})

    result = _vlm_call([{"role": "user", "content": content}])
    return _parse_json(result) if result else None


# ═══════════════════════════════════════════════════════════
# Call 3: CTA 细分类（只看末 5s）
# ═══════════════════════════════════════════════════════════

def _call3_cta_classify(
    video_path: str, duration: float, cta_start: float,
    cta_candidates: list[tuple[str, float]],
    cta_asr: str,
) -> dict | None:
    """VLM Call 3: CTA 细分类。"""
    start_ts = max(0, duration - 5)
    timestamps = [start_ts + i / 3.0 for i in range(15) if start_ts + i / 3.0 <= duration]
    frames_b64 = _extract_frames(video_path, timestamps)
    if not frames_b64:
        return None

    candidate_str = " / ".join(f"{t}" for t, _ in cta_candidates) if cta_candidates else "未知"
    asr_line = f"末尾口语: \"{cta_asr}\"" if cta_asr else "无口语数据"

    content = []
    for i, (ts, b64) in enumerate(zip(timestamps, frames_b64)):
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    content.append({"type": "text", "text": (
        f"这是短视频最后 5s 的关键帧。\n\n"
        f"口语内容: {asr_line}\n"
        f"候选 CTA 类型: {candidate_str}\n\n"
        "返回 JSON（只返回 JSON）:\n"
        "{\n"
        '  "cta_type": "从候选中选一个，如果没有匹配的可自行判断",\n'
        '  "urgency_cues": ["画面中的紧迫感元素，如倒计时、限时标签等"],\n'
        '  "text_on_screen": "画面中的关键文字",\n'
        '  "confidence": "low / medium / high"\n'
        "}"
    )})

    result = _vlm_call([{"role": "user", "content": content}])
    return _parse_json(result) if result else None


# ═══════════════════════════════════════════════════════════
# 公开入口
# ═══════════════════════════════════════════════════════════

def vlm_refine_structure(
    video_path: str,
    duration: float,
    phases: dict[str, float],
    hook_candidates: list[tuple[str, float]],
    cta_candidates: list[tuple[str, float]],
    hook_asr: str = "",
    cta_asr: str = "",
) -> VLMRefinement:
    """Stage C 入口: 3 个并发 VLM 调用。

    任何一个失败都不影响其他，失败项用 Stage B 的默认值。
    """
    hook_end = phases["hook_end"]
    cta_start = phases["build_end"]

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_call1_category_structure, video_path, duration, hook_end, cta_start): "call1",
            executor.submit(_call2_hook_classify, video_path, hook_end, hook_candidates, hook_asr): "call2",
            executor.submit(_call3_cta_classify, video_path, duration, cta_start, cta_candidates, cta_asr): "call3",
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                logger.warning(f"VLM {key} 异常: {e}")
                results[key] = None

    # 组装结果，失败项用默认值
    call1 = results.get("call1") or {}
    call2 = results.get("call2") or {}
    call3 = results.get("call3") or {}

    return VLMRefinement(
        category_primary=call1.get("category_primary", "通用"),
        category_secondary=call1.get("category_secondary", []),
        hook_end_adjusted=call1.get("hook_end_adjusted"),
        cta_start_adjusted=call1.get("cta_start_adjusted"),
        narrative_arc=call1.get("narrative_arc", ""),
        hook=HookAnalysis(
            hook_type=call2.get("hook_type", hook_candidates[0][0] if hook_candidates else "利益直接"),
            visual_technique=call2.get("visual_technique", ""),
            text_on_screen=call2.get("text_on_screen", ""),
            confidence=call2.get("confidence", "medium"),
        ),
        build=BuildAnalysis(
            build_pattern=call1.get("build_pattern", "教程步骤"),
            pacing=call1.get("pacing", "medium"),
        ),
        cta=CTAAnalysis(
            cta_type=call3.get("cta_type", cta_candidates[0][0] if cta_candidates else "社会认同"),
            urgency_cues=call3.get("urgency_cues", []),
            text_on_screen=call3.get("text_on_screen", ""),
            confidence=call3.get("confidence", "medium"),
        ),
    )
