#!/usr/bin/env python3
"""
measure_structure.py — 从 recipe.json 提取结构指标集 M

用于迁移验证实验：对比原始 recipe 和迁移后 recipe 的结构保真度。

用法:
    python scripts/measure_structure.py recipe.json
    python scripts/measure_structure.py recipe.json --output metrics.json
    python scripts/measure_structure.py recipe1.json recipe2.json --compare

指标集 M:
    1. beat_timing_distribution  — 各 beat 占总时长比例
    2. motion_density            — 每秒动效事件数
    3. attention_curve            — 各 beat 元素密度 (组件数/秒)
    4. motion_type_diversity      — 使用的 motion primitive 种类数
    5. transition_interval_variance — 相邻 beat 切换间隔方差
    6. head_tail_ratio            — 首段/末段元素密度比
"""

import json
import sys
import math
from pathlib import Path
from typing import Any


def load_recipe(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def count_components_recursive(obj: Any) -> int:
    """递归统计 timeline 节点中的组件数（含嵌套 children/phases）。"""
    count = 0
    if isinstance(obj, dict):
        if "ref" in obj:
            count += 1
        if "children" in obj:
            for child in obj["children"]:
                count += count_components_recursive(child)
        if "components" in obj:
            for comp in obj["components"]:
                count += count_components_recursive(comp)
        if "phases" in obj:
            for phase in obj["phases"]:
                count += count_components_recursive(phase)
    elif isinstance(obj, list):
        for item in obj:
            count += count_components_recursive(item)
    return count


def collect_motion_refs(obj: Any) -> set[str]:
    """递归收集 timeline 中所有组件 ref 名称。"""
    refs: set[str] = set()
    if isinstance(obj, dict):
        if "ref" in obj:
            refs.add(obj["ref"])
        for key in ("children", "components", "phases"):
            if key in obj:
                items = obj[key] if isinstance(obj[key], list) else [obj[key]]
                for item in items:
                    refs.update(collect_motion_refs(item))
    elif isinstance(obj, list):
        for item in obj:
            refs.update(collect_motion_refs(item))
    return refs


def measure(recipe: dict) -> dict:
    """从 recipe.json 计算结构指标集 M。"""
    meta = recipe["meta"]
    timeline = recipe["timeline"]
    motion = recipe.get("motion", {})

    fps = meta["fps"]
    total_frames = meta["durationFrames"]
    total_seconds = total_frames / fps

    # ── 1. beat timing distribution ──
    beat_timings = []
    for beat in timeline:
        beat_timings.append({
            "id": beat.get("id", f"beat_{beat['beat']}"),
            "startFrame": beat["startFrame"],
            "durationFrames": beat["durationFrames"],
            "ratio": beat["durationFrames"] / total_frames,
        })

    # ── 2. motion density ──
    # 统计 motion 原语定义数（recipe.motion 的 key 数量，排除 $comment）
    motion_primitives = [k for k in motion if not k.startswith("$")]
    motion_primitive_count = len(motion_primitives)

    # 统计 timeline 中实际使用的组件实例数
    total_component_instances = count_components_recursive(timeline)
    motion_density = total_component_instances / total_seconds

    # ── 3. attention curve (per-beat element density) ──
    attention_curve = []
    for beat in timeline:
        beat_seconds = beat["durationFrames"] / fps
        component_count = count_components_recursive(beat)
        density = component_count / beat_seconds if beat_seconds > 0 else 0
        attention_curve.append({
            "id": beat.get("id", f"beat_{beat['beat']}"),
            "components": component_count,
            "seconds": beat_seconds,
            "density": round(density, 3),
        })

    # ── 4. motion type diversity ──
    # 用到的组件类型（去重）
    used_refs = collect_motion_refs(timeline)
    # 映射到 motion 原语（组件名 camelCase → motion key camelCase）
    # 简单统计 ref 种类数即可
    motion_diversity = len(used_refs)

    # ── 5. transition interval variance ──
    starts = [beat["startFrame"] for beat in timeline]
    intervals = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    if len(intervals) > 1:
        mean_interval = sum(intervals) / len(intervals)
        variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
        interval_std = math.sqrt(variance)
    else:
        mean_interval = intervals[0] if intervals else 0
        interval_std = 0

    # ── 6. head/tail ratio ──
    first_beat = attention_curve[0] if attention_curve else {"density": 0}
    last_beat = attention_curve[-1] if attention_curve else {"density": 0}
    head_tail_ratio = (
        round(first_beat["density"] / last_beat["density"], 3)
        if last_beat["density"] > 0
        else float("inf")
    )

    return {
        "source": meta.get("sourceReference", "unknown"),
        "templateId": meta.get("templateId", "unknown"),
        "totalFrames": total_frames,
        "totalSeconds": total_seconds,
        "beatCount": len(timeline),

        "beatTimingDistribution": beat_timings,

        "motionDensity": {
            "instancesPerSecond": round(motion_density, 3),
            "totalInstances": total_component_instances,
            "motionPrimitivesDefined": motion_primitive_count,
        },

        "attentionCurve": attention_curve,

        "motionDiversity": {
            "uniqueComponentTypes": motion_diversity,
            "types": sorted(used_refs),
        },

        "transitionInterval": {
            "intervals": intervals,
            "meanFrames": round(mean_interval, 1),
            "stdFrames": round(interval_std, 1),
            "coefficientOfVariation": round(
                interval_std / mean_interval, 3
            ) if mean_interval > 0 else 0,
        },

        "headTailRatio": head_tail_ratio,
    }


def compare(m1: dict, m2: dict, threshold: float = 0.2) -> dict:
    """对比两个结构指标集，计算 ΔM。"""
    deltas: dict[str, Any] = {}

    # beat timing distribution delta
    timings1 = {b["id"]: b["ratio"] for b in m1["beatTimingDistribution"]}
    timings2 = {b["id"]: b["ratio"] for b in m2["beatTimingDistribution"]}
    common_beats = set(timings1.keys()) & set(timings2.keys())
    beat_deltas = {}
    for bid in common_beats:
        d = abs(timings1[bid] - timings2[bid])
        beat_deltas[bid] = {
            "original": round(timings1[bid], 4),
            "migrated": round(timings2[bid], 4),
            "delta": round(d, 4),
            "pass": d < threshold,
        }
    deltas["beatTiming"] = beat_deltas

    # motion density delta
    d1 = m1["motionDensity"]["instancesPerSecond"]
    d2 = m2["motionDensity"]["instancesPerSecond"]
    density_delta = abs(d1 - d2) / d1 if d1 > 0 else 0
    deltas["motionDensity"] = {
        "original": d1,
        "migrated": d2,
        "relativeDelta": round(density_delta, 4),
        "pass": density_delta < threshold,
    }

    # attention curve delta (per-beat density)
    curve1 = {a["id"]: a["density"] for a in m1["attentionCurve"]}
    curve2 = {a["id"]: a["density"] for a in m2["attentionCurve"]}
    curve_deltas = {}
    for bid in common_beats:
        c1, c2 = curve1.get(bid, 0), curve2.get(bid, 0)
        d = abs(c1 - c2) / c1 if c1 > 0 else (0 if c2 == 0 else 1.0)
        curve_deltas[bid] = {
            "original": c1,
            "migrated": c2,
            "relativeDelta": round(d, 4),
            "pass": d < threshold,
        }
    deltas["attentionCurve"] = curve_deltas

    # motion diversity delta
    types1 = set(m1["motionDiversity"]["types"])
    types2 = set(m2["motionDiversity"]["types"])
    jaccard = (
        len(types1 & types2) / len(types1 | types2)
        if (types1 | types2)
        else 1.0
    )
    deltas["motionDiversity"] = {
        "original": sorted(types1),
        "migrated": sorted(types2),
        "jaccard": round(jaccard, 4),
        "pass": jaccard > (1 - threshold),
    }

    # transition interval delta
    std1 = m1["transitionInterval"]["stdFrames"]
    std2 = m2["transitionInterval"]["stdFrames"]
    std_delta = abs(std1 - std2) / std1 if std1 > 0 else 0
    deltas["transitionInterval"] = {
        "originalStd": std1,
        "migratedStd": std2,
        "relativeDelta": round(std_delta, 4),
        "pass": std_delta < threshold,
    }

    # head/tail ratio delta
    r1 = m1["headTailRatio"]
    r2 = m2["headTailRatio"]
    ratio_delta = abs(r1 - r2) / r1 if r1 > 0 and r1 != float("inf") else 0
    deltas["headTailRatio"] = {
        "original": r1,
        "migrated": r2,
        "relativeDelta": round(ratio_delta, 4),
        "pass": ratio_delta < threshold,
    }

    # overall verdict
    all_pass = all(
        v.get("pass", True)
        for v in deltas.values()
        if isinstance(v, dict)
    )
    # per-beat checks
    for section in ("beatTiming", "attentionCurve"):
        for bid, v in deltas[section].items():
            if not v["pass"]:
                all_pass = False

    # Count all individual pass/fail checks (including per-beat)
    passed_count = 0
    total_checks = 0
    for v in deltas.values():
        if isinstance(v, dict):
            if "pass" in v:
                total_checks += 1
                if v["pass"]:
                    passed_count += 1
            else:
                # Nested dict like beatTiming/attentionCurve with per-beat entries
                for sub in v.values():
                    if isinstance(sub, dict) and "pass" in sub:
                        total_checks += 1
                        if sub["pass"]:
                            passed_count += 1

    if all_pass:
        grade = "A"
    elif passed_count >= total_checks * 0.7:
        grade = "B"
    elif passed_count >= total_checks * 0.4:
        grade = "C"
    else:
        grade = "D"

    return {
        "threshold": threshold,
        "grade": grade,
        "passed": passed_count,
        "total": total_checks,
        "verdict": all_pass,
        "deltas": deltas,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="从 recipe.json 提取结构指标集 M"
    )
    parser.add_argument(
        "recipes", nargs="+", help="recipe.json 文件路径（2 个时自动 compare）"
    )
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径")
    parser.add_argument(
        "--compare", action="store_true", help="对比模式（需要恰好 2 个 recipe）"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.2, help="对比阈值（默认 0.2 = 20%）"
    )
    args = parser.parse_args()

    if len(args.recipes) == 2 or args.compare:
        if len(args.recipes) != 2:
            print("对比模式需要恰好 2 个 recipe.json", file=sys.stderr)
            sys.exit(1)
        m1 = measure(load_recipe(args.recipes[0]))
        m2 = measure(load_recipe(args.recipes[1]))
        result = {
            "mode": "compare",
            "recipe1": args.recipes[0],
            "recipe2": args.recipes[1],
            "metrics1": m1,
            "metrics2": m2,
            "comparison": compare(m1, m2, args.threshold),
        }
    else:
        results = []
        for path in args.recipes:
            recipe = load_recipe(path)
            m = measure(recipe)
            results.append({"path": path, "metrics": m})
        result = {
            "mode": "measure",
            "count": len(results),
            "results": results,
        }

    output = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"✅ 输出写入 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
