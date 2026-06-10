"""S2 Structure Extraction: S1 output → StructureTemplate JSON.

v2 pipeline (新): ASR → 规则推断 → VLM 微调 → 模板组装
v0 pipeline (旧): 位置百分比 + 关键词匹配 + VLM 补丁
"""
import logging

logger = logging.getLogger(__name__)

import base64
import json
import os
import uuid
from datetime import datetime

import cv2
import httpx

from s1_analyzer import S1Output, Shot
from motion_analyzer import MotionTimeline

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_API_URL = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
MIMO_MODEL = os.environ.get("MIMO_VLM_MODEL", "mimo-v2.5")

CATEGORIES = ["好物推荐", "美妆", "美食", "数码", "生活", "健身", "知识", "宠物", "母婴", "家居", "旅行"]


def classify_phase(shot: Shot, total_duration: float) -> str:
    """Classify a shot into hook/build/payoff_cta based on position and duration."""
    position_pct = shot.start_time / total_duration if total_duration > 0 else 0
    if position_pct < 0.15:
        return "hook"
    elif position_pct < 0.75:
        return "build"
    else:
        return "payoff_cta"


def infer_hook_type(shots: list[Shot], captions: list[str]) -> str:
    """Infer hook type from first shot characteristics."""
    if not shots:
        return "利益_直接"
    first_caption = captions[0] if captions else ""
    if "？" in first_caption or "?" in first_caption:
        return "悬念_反问句"
    if any(w in first_caption for w in ["震惊", "居然", "没想到", "竟然"]):
        return "数字_震惊"
    if any(w in first_caption for w in ["不要", "别", "千万别"]):
        return "否定_常识"
    return "利益_直接"


def infer_build_pattern(shots: list[Shot], captions: list[str]) -> str:
    """Infer build pattern from middle shots."""
    if len(shots) <= 2:
        return "教程演示_步骤拆解"
    middle_captions = " ".join(captions[1:-1]) if len(captions) > 2 else ""
    if any(w in middle_captions for w in ["对比", "之前", "之后", "vs"]):
        return "对比展示_揭示原因"
    if any(w in middle_captions for w in ["步骤", "第一", "第二", "然后"]):
        return "教程演示_步骤拆解"
    if any(w in middle_captions for w in ["痛点", "问题", "烦恼"]):
        return "痛点列举_方案展示_效果对比"
    return "教程演示_步骤拆解"


def infer_cta_type(shots: list[Shot], captions: list[str]) -> str:
    """Infer CTA type from last shot."""
    last_caption = captions[-1] if captions else ""
    if any(w in last_caption for w in ["限时", "优惠", "折扣"]):
        return "限时优惠"
    if any(w in last_caption for w in ["评论", "点赞", "关注", "收藏"]):
        return "社会认同"
    if any(w in last_caption for w in ["链接", "购买", "下单"]):
        return "直接索取"
    return "社会认同"


def infer_shot_type(caption: str) -> str:
    """Infer shot type from caption content."""
    if any(w in caption for w in ["人脸", "面部", "特写", "脸"]):
        return "face_closeup"
    if any(w in caption for w in ["产品", "商品", "特写", "展示"]):
        return "product_zoom_in"
    if any(w in caption for w in ["场景", "环境", "全景"]):
        return "usage_scenario"
    if any(w in caption for w in ["文字", "标题", "字幕"]):
        return "text_overlay"
    return "general"


def infer_caption_style(captions: list[str]) -> dict:
    """Infer caption style from caption content."""
    has_chinese = any(any("一" <= c <= "鿿" for c in c) for c in captions)
    return {
        "font": "思源黑体" if has_chinese else "Arial",
        "color": "#FFFFFF",
        "size": "large",
        "position": "bottom_third",
        "animation": "typewriter_fast",
    }


def infer_audio_energy(audio_rms: float) -> str:
    """Map audio energy level to category."""
    if audio_rms < 0.02:
        return "low"
    elif audio_rms < 0.05:
        return "medium"
    elif audio_rms < 0.1:
        return "medium_rising"
    else:
        return "high"


def group_shots_into_phases(shots: list[Shot], total_duration: float) -> dict:
    """Group shots into hook/build/payoff_cta phases."""
    phases = {"hook": [], "build": [], "payoff_cta": []}
    for shot in shots:
        phase = classify_phase(shot, total_duration)
        phases[phase].append(shot)
    return phases


def _build_motion_summary(motion: MotionTimeline, n_audio_segments: int = 10) -> dict:
    """Build compact motion summary for template (S4 consumption)."""
    track_summaries = []
    for t in motion.tracks[:10]:  # cap at 10 tracks
        track_summaries.append({
            "id": t.element_id,
            "label": t.label,
            "motion_type": t.motion_type,
            "path": t.path_summary,
            "enter_t": round(t.enter_t, 2),
            "exit_t": round(t.exit_t, 2),
        })
    return {
        "event_count": len(motion.motion_events),
        "energy_peak_times": [round(e["peak_t"], 2) for e in motion.motion_events[:10]],
        "visual_energy_resampled": motion.resample_energy(n_audio_segments),
        "tracks": track_summaries,
    }


def build_structure_template(s1: S1Output) -> dict:
    """Convert S1 output into a StructureTemplate JSON."""
    captions = [s.caption for s in s1.shots]
    phases = group_shots_into_phases(s1.shots, s1.total_duration)

    # Calculate phase durations
    phase_durations = {}
    for phase_name, phase_shots in phases.items():
        phase_durations[phase_name] = sum(s.duration for s in phase_shots)

    timeline = []
    for phase_name in ["hook", "build", "payoff_cta"]:
        phase_shots = phases[phase_name]
        if not phase_shots:
            continue
        dur = phase_durations[phase_name]
        dur_pct = dur / s1.total_duration if s1.total_duration > 0 else 0

        shot_types = list(set(infer_shot_type(s.caption) for s in phase_shots))
        avg_shot_len = dur / len(phase_shots) if phase_shots else 0

        timeline.append({
            "phase": phase_name,
            "duration_pct": [round(max(0, dur_pct - 0.05), 2), round(min(1, dur_pct + 0.05), 2)],
            "shot_count_range": [max(1, len(phase_shots) - 1), len(phase_shots) + 1],
            "avg_shot_length_s": round(avg_shot_len, 2),
            "required_shot_types": shot_types,
            "caption_style": infer_caption_style(captions),
            "audio_energy": infer_audio_energy(s1.audio.rms_mean),
            "bgm_role": "背景铺垫" if phase_name == "hook" else "节奏推进" if phase_name == "build" else "高潮收尾",
        })

    # Infer narrative dimensions
    hook_type = infer_hook_type(s1.shots, captions)
    build_pattern = infer_build_pattern(s1.shots, captions)
    cta_type = infer_cta_type(s1.shots, captions)

    # Parse visual language from captions
    visual_info = _parse_visual_from_captions(s1.shots)
    rhythm_info = _build_rhythm_from_s1(s1)

    # Transitions
    transitions = ["cut"] * max(1, len(s1.shots) - 1)

    template = {
        "template_id": f"tpl_{uuid.uuid4().hex[:8]}",
        "source_videos": [s1.video_path],
        "category": "通用",
        "duration_range": [round(max(5, s1.total_duration - 5), 1), round(s1.total_duration + 5, 1)],
        "narrative": {
            "hook_type": hook_type,
            "build_pattern": build_pattern,
            "cta_type": cta_type,
        },
        "timeline": timeline,
        "visual": {
            "color_palette": visual_info["color_palette"],
            "layout_pattern": visual_info["layout_pattern"],
            "design_style": visual_info["design_style"],
        },
        "text": {
            "on_screen_text": visual_info["on_screen_text"],
            "asr_text": "",
            "language": visual_info["language"],
        },
        "rhythm": rhythm_info,
        "audio_template": {
            "bpm_range": [round(s1.audio.bpm * 0.8), round(s1.audio.bpm * 1.2)] if s1.audio.has_audio else [120, 120],
            "beat_align_strength": "medium" if s1.audio.has_audio else "none",
            "energy_curve": "rising" if s1.audio.has_audio and s1.audio.avg_energy > 0.05 else "flat",
            "visual_energy_curve": s1.motion.visual_energy_curve if s1.motion else [],
        },
        "motion_summary": _build_motion_summary(s1.motion) if s1.motion else {},
        "packaging": {
            "transitions": transitions,
            "sticker_density_per_sec": 0.0,
            "title_bar": {
                "style": "minimal",
                "appears_at_phases": ["hook"],
            },
            "cover_style": "default",
            "use_3d_elements": False,
        },
        "transferability": {
            "best_for_verticals": ["通用"],
            "avoid_verticals": [],
        },
        "provenance": {
            "extracted_from": [s1.video_path],
            "extraction_date": datetime.now().isoformat(),
            "version": 1,
            "times_used": 0,
        },
    }

    return template


def _extract_key_frame_base64(video_path: str, timestamp: float) -> str:
    """Extract a single frame from video at given timestamp, return base64 JPEG."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return ""
    # Resize to 540x960 for faster VLM processing
    h, w = frame.shape[:2]
    if h > 960:
        scale = 960 / h
        frame = cv2.resize(frame, (int(w * scale), 960))
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return base64.b64encode(buf).decode("utf-8")


def vlm_enhance_template(template: dict, s1: S1Output) -> dict:
    """Use MiMo VLM to enhance a template with meaningful category and shot types.

    Analyzes one key frame per phase, then updates the template.
    Falls back to original template if VLM is unavailable.
    """
    if not MIMO_API_KEY:
        print("VLM: no API key, using algorithmic template")
        return template

    # Collect one representative frame per phase
    phase_frames = {}
    for phase_data in template.get("timeline", []):
        phase_name = phase_data["phase"]
        dur_pct = phase_data.get("duration_pct", [0, 0.3])
        mid_pct = (dur_pct[0] + dur_pct[1]) / 2
        timestamp = mid_pct * s1.total_duration
        b64 = _extract_key_frame_base64(s1.video_path, timestamp)
        if b64:
            phase_frames[phase_name] = b64

    if not phase_frames:
        return template

    # Build multi-image VLM prompt (simplified for reliability)
    content = []
    for phase_name, b64 in phase_frames.items():
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    content.append({"type": "text", "text": (
        "分析这些视频截图，返回 JSON，只返回 JSON 不要其他文字：\n"
        '{"category": "好物推荐/美妆/美食/数码/生活/健身/知识/宠物/母婴/家居/旅行 选一个", '
        '"hook_shots": ["镜头类型"], '
        '"build_shots": ["镜头类型"], '
        '"payoff_shots": ["镜头类型"]}\n\n'
        "镜头类型从以下选：face_closeup / product_closeup / product_usage / before_after / text_overlay / step_demo / comparison / data_display / lifestyle_broll / indoor_scene / outdoor_scene"
    )})

    try:
        resp = httpx.post(
            MIMO_API_URL,
            json={
                "model": MIMO_MODEL,
                "messages": [{"role": "user", "content": content}],
                "temperature": 0.1,
                "max_tokens": 800,
            },
            headers={"Authorization": f"Bearer {MIMO_API_KEY}"},
            timeout=30.0,
        )
        if resp.status_code == 200:
            msg = resp.json()["choices"][0]["message"]
            text = msg.get("content", "").strip()
            # Fallback: check reasoning_content if content is empty
            if not text:
                text = msg.get("reasoning_content", "").strip()
            # Extract JSON
            import re
            match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())

                # Update template with VLM insights
                if data.get("category") in CATEGORIES:
                    template["category"] = data["category"]
                if data.get("hook_type"):
                    template["narrative"]["hook_type"] = data["hook_type"]
                if data.get("build_pattern"):
                    template["narrative"]["build_pattern"] = data["build_pattern"]
                if data.get("cta_type"):
                    template["narrative"]["cta_type"] = data["cta_type"]

                # Update shot types per phase
                shot_map = {
                    "hook": data.get("hook_shots", []),
                    "build": data.get("build_shots", []),
                    "payoff_cta": data.get("payoff_shots", []),
                }
                for phase_data in template.get("timeline", []):
                    phase_name = phase_data["phase"]
                    vlm_shots = shot_map.get(phase_name, [])
                    if vlm_shots:
                        phase_data["required_shot_types"] = vlm_shots

                print(f"VLM enhanced: category={template['category']}, "
                      f"hook={template['narrative']['hook_type']}, "
                      f"build={template['narrative']['build_pattern']}")
            else:
                print(f"VLM: could not parse response: {text[:100]}")
        else:
            print(f"VLM: request failed with status {resp.status_code}")
    except Exception as e:
        print(f"VLM enhancement failed: {e}")

    return template


def run_s2_v0(s1: S1Output) -> dict:
    """v0 pipeline: 位置百分比 + 关键词匹配 + VLM 补丁。保留用于 fallback。"""
    template = build_structure_template(s1)
    template = vlm_enhance_template(template, s1)
    return template


def _parse_visual_from_captions(shots: list[Shot]) -> dict:
    """从 S1 caption 中解析视觉语言信息（布局/色彩/排版/风格）。"""
    import re

    all_text = []
    layouts = []
    colors = []
    styles = []

    for shot in shots:
        cap = shot.caption or ""

        # 提取屏幕文字
        m = re.search(r'【屏幕文字】(.+?)(?:\n|【|$)', cap)
        if m:
            all_text.extend(re.findall(r'[一-鿿]+|[A-Za-z]+|\d+', m.group(1)))

        # 提取布局
        m = re.search(r'【布局】(.+?)(?:\n|【|$)', cap)
        if m:
            layouts.append(m.group(1).strip())

        # 提取色彩
        m = re.search(r'【色彩】(.+?)(?:\n|【|$)', cap)
        if m:
            colors.append(m.group(1).strip())

        # 提取风格
        m = re.search(r'【风格】(.+?)(?:\n|【|$)', cap)
        if m:
            styles.append(m.group(1).strip())

    # 合并色彩：提取所有十六进制色号
    hex_colors = list(set(re.findall(r'#[0-9a-fA-F]{3,8}', ' '.join(colors)))) or ["#000000", "#FFFFFF"]

    # 主布局模式（取第一个非空）
    layout_pattern = layouts[0] if layouts else "unknown"

    # 设计风格（众数）
    from collections import Counter
    style_counter = Counter(styles)
    design_style = style_counter.most_common(1)[0][0] if styles else "unknown"

    # 去重文字
    seen = set()
    unique_text = []
    for t in all_text:
        if t not in seen and len(t) > 1:
            seen.add(t)
            unique_text.append(t)

    return {
        "color_palette": hex_colors,
        "layout_pattern": layout_pattern,
        "design_style": design_style,
        "on_screen_text": unique_text,
        "language": "zh+en" if any('一' <= c <= '鿿' for c in ' '.join(unique_text)) else "en",
    }


def _build_rhythm_from_s1(s1: S1Output) -> dict:
    """从 S1 数据中提取节奏结构信息。"""
    shots = s1.shots
    if not shots:
        return {}

    # 镜头切换频率
    avg_shot_len = sum(s.duration for s in shots) / len(shots)
    switch_freq = "fast" if avg_shot_len < 2 else "medium" if avg_shot_len < 5 else "slow"

    # 快慢段落
    segments = []
    for i, shot in enumerate(shots):
        speed = "fast" if shot.duration < 2 else "medium" if shot.duration < 5 else "slow"
        segments.append({
            "shot_index": i,
            "duration_s": round(shot.duration, 2),
            "speed": speed,
        })

    # 高潮位置（从 motion energy 推断）
    peak_times = []
    if s1.motion and s1.motion.visual_energy_curve:
        # Find peaks in energy curve
        curve = s1.motion.visual_energy_curve
        if len(curve) > 2:
            avg = sum(curve) / len(curve)
            for i in range(1, len(curve) - 1):
                if curve[i] > avg * 1.2 and curve[i] > curve[i-1] and curve[i] > curve[i+1]:
                    peak_times.append(round(i * s1.total_duration / len(curve), 2))

    return {
        "avg_shot_duration_s": round(avg_shot_len, 2),
        "switch_frequency": switch_freq,
        "shot_count": len(shots),
        "segments": segments,
        "energy_peaks_s": peak_times,
    }


def _build_template_from_pipeline(
    s1: S1Output,
    asr_segments: list,
    phases: dict[str, float],
    hook_draft, build_draft, cta_draft,
    vlm_result=None,
) -> dict:
    """Stage D: 用 pipeline 结果组装 StructureTemplate。"""
    # VLM 边界微调（限制在 ±2s 内）
    hook_end = phases["hook_end"]
    cta_start = phases["build_end"]

    if vlm_result and vlm_result.hook_end_adjusted is not None:
        adjusted = vlm_result.hook_end_adjusted
        hook_end = max(phases["hook_end"] - 2, min(phases["hook_end"] + 2, adjusted))

    if vlm_result and vlm_result.cta_start_adjusted is not None:
        adjusted = vlm_result.cta_start_adjusted
        cta_start = max(phases["build_end"] - 2, min(phases["build_end"] + 2, adjusted))

    # 分类结果（VLM 优先，否则用 Stage B 候选 top-1）
    category = "通用"
    hook_type = "利益直接"
    build_pattern = "教程步骤"
    cta_type = "社会认同"
    narrative_arc = ""

    if vlm_result:
        category = vlm_result.category_primary or "通用"
        hook_type = vlm_result.hook.hook_type
        build_pattern = vlm_result.build.build_pattern
        cta_type = vlm_result.cta.cta_type
        narrative_arc = vlm_result.narrative_arc
    else:
        hook_type = hook_draft.type_candidates[0][0] if hook_draft.type_candidates else "利益直接"
        build_pattern = build_draft.type_candidates[0][0] if build_draft.type_candidates else "教程步骤"
        cta_type = cta_draft.type_candidates[0][0] if cta_draft.type_candidates else "社会认同"

    # 组装 timeline
    captions = [s.caption for s in s1.shots]

    def _make_phase_timeline(name, start, end, asr_text):
        dur = end - start
        dur_pct = dur / s1.total_duration if s1.total_duration > 0 else 0
        phase_shots = [s for s in s1.shots if start <= (s.start_time + s.end_time) / 2 < end]
        shot_types = list(set(infer_shot_type(s.caption) for s in phase_shots)) or ["general"]
        avg_len = dur / len(phase_shots) if phase_shots else dur
        return {
            "phase": name,
            "duration_pct": [round(max(0, start / s1.total_duration), 2), round(min(1, end / s1.total_duration), 2)],
            "shot_count_range": [max(1, len(phase_shots) - 1), len(phase_shots) + 1],
            "avg_shot_length_s": round(avg_len, 2),
            "required_shot_types": shot_types,
            "caption_style": infer_caption_style(captions),
            "audio_energy": infer_audio_energy(s1.audio.rms_mean),
            "bgm_role": "背景铺垫" if name == "hook" else "节奏推进" if name == "build" else "高潮收尾",
            "asr_text": asr_text,
        }

    timeline = [
        _make_phase_timeline("hook", 0, hook_end, hook_draft.asr_text),
        _make_phase_timeline("build", hook_end, cta_start, build_draft.asr_text),
        _make_phase_timeline("payoff_cta", cta_start, s1.total_duration, cta_draft.asr_text),
    ]

    # 解析视觉语言信息
    visual_info = _parse_visual_from_captions(s1.shots)
    rhythm_info = _build_rhythm_from_s1(s1)

    return {
        "template_id": f"tpl_{uuid.uuid4().hex[:8]}",
        "source_videos": [s1.video_path],
        "category": category,
        "duration_range": [round(max(5, s1.total_duration - 5), 1), round(s1.total_duration + 5, 1)],
        "narrative": {
            "hook_type": hook_type,
            "build_pattern": build_pattern,
            "cta_type": cta_type,
            "narrative_arc": narrative_arc,
        },
        "timeline": timeline,
        "visual": {
            "color_palette": visual_info["color_palette"],
            "layout_pattern": visual_info["layout_pattern"],
            "design_style": visual_info["design_style"],
        },
        "text": {
            "on_screen_text": visual_info["on_screen_text"],
            "asr_text": " ".join(p.get("asr_text", "") for p in timeline if p.get("asr_text")),
            "language": visual_info["language"],
        },
        "rhythm": rhythm_info,
        "audio_template": {
            "bpm_range": [round(s1.audio.bpm * 0.8), round(s1.audio.bpm * 1.2)] if s1.audio.has_audio else [120, 120],
            "beat_align_strength": "medium" if s1.audio.has_audio else "none",
            "energy_curve": "rising" if s1.audio.has_audio and s1.audio.avg_energy > 0.05 else "flat",
            "visual_energy_curve": s1.motion.visual_energy_curve if s1.motion else [],
        },
        "motion_summary": _build_motion_summary(s1.motion) if s1.motion else {},
        "packaging": {
            "transitions": ["cut"] * max(1, len(s1.shots) - 1),
            "sticker_density_per_sec": 0.0,
            "title_bar": {"style": "minimal", "appears_at_phases": ["hook"]},
            "cover_style": "default",
            "use_3d_elements": False,
        },
        "transferability": {"best_for_verticals": [category], "avoid_verticals": []},
        "provenance": {
            "extracted_from": [s1.video_path],
            "extraction_date": datetime.now().isoformat(),
            "version": 2,
            "times_used": 0,
            "pipeline": "v2_asr_vlm",
        },
    }


def run_s2(s1: S1Output, enable_vlm: bool = True) -> dict:
    """v2 pipeline: ASR → 规则推断 → VLM 微调 → 模板组装。

    每个 stage 独立降级：
    - ASR 失败 → 纯位置百分比
    - VLM 失败 → 用 Stage B 候选
    - 全部失败 → 退回 v0 pipeline
    """
    from s2.structure_inferrer import compute_initial_phases, build_phase_drafts
    from s2.asr_extractor import extract_asr
    from s2.vlm_refiner import vlm_refine_structure

    # Stage A: ASR
    asr_segments = extract_asr(s1.video_path)
    if asr_segments:
        logger.info(f"ASR 提取 {len(asr_segments)} 段")
    else:
        logger.info("ASR 无语音（纯音乐/字幕型视频），将用 VLM caption 补充")

    # Stage B: 规则推断（ASR + VLM caption 文本合并）
    phases = compute_initial_phases(s1.total_duration)
    caption_dicts = [
        {"start_time": s.start_time, "end_time": s.end_time, "caption": s.caption}
        for s in s1.shots if s.caption
    ]
    hook_draft, build_draft, cta_draft = build_phase_drafts(asr_segments, phases, caption_dicts)

    logger.info(f"Stage B: hook={hook_draft.type_candidates}, build={build_draft.type_candidates}, cta={cta_draft.type_candidates}")

    # Stage C: VLM 微调
    vlm_result = None
    if enable_vlm and MIMO_API_KEY:
        try:
            vlm_result = vlm_refine_structure(
                video_path=s1.video_path,
                duration=s1.total_duration,
                phases=phases,
                hook_candidates=hook_draft.type_candidates,
                cta_candidates=cta_draft.type_candidates,
                hook_asr=hook_draft.asr_text,
                cta_asr=cta_draft.asr_text,
            )
            logger.info(f"VLM: category={vlm_result.category_primary}, hook={vlm_result.hook.hook_type}, cta={vlm_result.cta.cta_type}")
        except Exception as e:
            logger.warning(f"VLM 失败, 退回 Stage B: {e}")
            vlm_result = None

    # Stage D: 模板组装
    template = _build_template_from_pipeline(
        s1, asr_segments, phases,
        hook_draft, build_draft, cta_draft,
        vlm_result,
    )

    return template
