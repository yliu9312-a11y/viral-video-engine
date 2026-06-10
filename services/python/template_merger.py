"""Merge multiple StructureTemplates into one representative template.

When multiple reference videos are provided, each is analyzed independently
and the resulting templates are merged here. The merge strategy:
- Phase boundaries: median of all templates
- Shot types: union per phase
- Category: majority vote
- Visual: merge color palettes, take first layout/style
- Text: concatenate on-screen text, deduplicate
- Audio: average BPM ranges
- Rhythm: average shot durations
"""
from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger(__name__)


def merge_templates(templates: list[dict]) -> dict:
    """Merge multiple StructureTemplate dicts into one.

    Args:
        templates: List of StructureTemplate dicts (at least 1).

    Returns:
        Merged StructureTemplate dict.
    """
    if not templates:
        raise ValueError("At least one template is required")
    if len(templates) == 1:
        return templates[0]

    logger.info(f"Merging {len(templates)} templates")

    # Use first template as base
    base = templates[0].copy()

    # Category: majority vote
    categories = [t.get("category", "通用") for t in templates]
    cat_counter = Counter(categories)
    base["category"] = cat_counter.most_common(1)[0][0]

    # Duration range: union (min of mins, max of maxs)
    dur_ranges = [t.get("duration_range", [15, 30]) for t in templates]
    base["duration_range"] = [
        min(r[0] for r in dur_ranges),
        max(r[1] for r in dur_ranges),
    ]

    # Narrative: majority vote per field
    for field in ["hook_type", "build_pattern", "cta_type"]:
        values = [t.get("narrative", {}).get(field, "") for t in templates]
        values = [v for v in values if v]
        if values:
            base["narrative"][field] = Counter(values).most_common(1)[0][0]

    # Timeline: merge phase boundaries (median)
    base["timeline"] = _merge_timelines(templates)

    # Visual: merge color palettes, take first layout/style
    base["visual"] = _merge_visual(templates)

    # Text: concatenate and deduplicate
    base["text"] = _merge_text(templates)

    # Rhythm: average
    base["rhythm"] = _merge_rhythm(templates)

    # Audio: average BPM ranges
    base["audio_template"] = _merge_audio(templates)

    # Source videos: collect all
    base["source_videos"] = []
    for t in templates:
        base["source_videos"].extend(t.get("source_videos", []))

    # Provenance
    base["provenance"]["pipeline"] = "v2_multi_video_merge"
    base["provenance"]["merged_from"] = len(templates)

    return base


def _merge_timelines(templates: list[dict]) -> list[dict]:
    """Merge timelines by taking median phase boundaries."""
    from statistics import median

    # Collect all phase names
    phase_names = set()
    for t in templates:
        for p in t.get("timeline", []):
            phase_names.add(p["phase"])

    merged = []
    for phase_name in sorted(phase_names):
        # Collect data from all templates that have this phase
        phase_data_list = []
        for t in templates:
            for p in t.get("timeline", []):
                if p["phase"] == phase_name:
                    phase_data_list.append(p)

        if not phase_data_list:
            continue

        # Median boundaries
        starts = [p["duration_pct"][0] for p in phase_data_list]
        ends = [p["duration_pct"][1] for p in phase_data_list]

        # Union of shot types
        all_shot_types = set()
        for p in phase_data_list:
            all_shot_types.update(p.get("required_shot_types", []))

        # Average shot length
        avg_lens = [p.get("avg_shot_length_s", 3.0) for p in phase_data_list]

        merged.append({
            "phase": phase_name,
            "duration_pct": [round(median(starts), 2), round(median(ends), 2)],
            "shot_count_range": [
                min(p.get("shot_count_range", [1, 3])[0] for p in phase_data_list),
                max(p.get("shot_count_range", [1, 3])[1] for p in phase_data_list),
            ],
            "avg_shot_length_s": round(median(avg_lens), 2),
            "required_shot_types": list(all_shot_types),
            "caption_style": phase_data_list[0].get("caption_style", {}),
            "audio_energy": phase_data_list[0].get("audio_energy", "medium"),
            "bgm_role": phase_data_list[0].get("bgm_role", "节奏推进"),
            "asr_text": " ".join(p.get("asr_text", "") for p in phase_data_list if p.get("asr_text")),
        })

    return merged


def _merge_visual(templates: list[dict]) -> dict:
    """Merge visual dimensions: union palettes, first layout/style."""
    all_colors = set()
    layouts = []
    styles = []

    for t in templates:
        vis = t.get("visual", {})
        all_colors.update(vis.get("color_palette", []))
        if vis.get("layout_pattern") and vis["layout_pattern"] != "unknown":
            layouts.append(vis["layout_pattern"])
        if vis.get("design_style") and vis["design_style"] != "unknown":
            styles.append(vis["design_style"])

    from collections import Counter
    style_counter = Counter(styles)

    return {
        "color_palette": list(all_colors) or ["#000000", "#FFFFFF"],
        "layout_pattern": layouts[0] if layouts else "unknown",
        "design_style": style_counter.most_common(1)[0][0] if styles else "unknown",
    }


def _merge_text(templates: list[dict]) -> dict:
    """Merge text dimensions: deduplicate on-screen text."""
    all_text = []
    seen = set()
    asr_parts = []
    languages = set()

    for t in templates:
        txt = t.get("text", {})
        for word in txt.get("on_screen_text", []):
            if word not in seen:
                seen.add(word)
                all_text.append(word)
        asr = txt.get("asr_text", "")
        if asr:
            asr_parts.append(asr)
        lang = txt.get("language", "")
        if lang:
            languages.add(lang)

    return {
        "on_screen_text": all_text,
        "asr_text": " ".join(asr_parts),
        "language": "+".join(sorted(languages)) if languages else "unknown",
    }


def _merge_rhythm(templates: list[dict]) -> dict:
    """Merge rhythm: average shot durations."""
    from statistics import median

    avg_durs = []
    shot_counts = []
    frequencies = []
    all_peaks = []

    for t in templates:
        r = t.get("rhythm", {})
        if r.get("avg_shot_duration_s"):
            avg_durs.append(r["avg_shot_duration_s"])
        if r.get("shot_count"):
            shot_counts.append(r["shot_count"])
        if r.get("switch_frequency"):
            frequencies.append(r["switch_frequency"])
        all_peaks.extend(r.get("energy_peaks_s", []))

    freq_counter = Counter(frequencies)

    return {
        "avg_shot_duration_s": round(median(avg_durs), 2) if avg_durs else 3.0,
        "switch_frequency": freq_counter.most_common(1)[0][0] if frequencies else "medium",
        "shot_count": round(median(shot_counts)) if shot_counts else 0,
        "segments": [],
        "energy_peaks_s": sorted(set(all_peaks)),
    }


def _merge_audio(templates: list[dict]) -> dict:
    """Merge audio: average BPM ranges."""
    bpm_mins = []
    bpm_maxs = []

    for t in templates:
        audio = t.get("audio_template", {})
        bpm_range = audio.get("bpm_range", [120, 120])
        bpm_mins.append(bpm_range[0])
        bpm_maxs.append(bpm_range[1])

    return {
        "bpm_range": [round(sum(bpm_mins) / len(bpm_mins)), round(sum(bpm_maxs) / len(bpm_maxs))],
        "beat_align_strength": "medium",
        "energy_curve": "rising",
        "visual_energy_curve": [],
    }
