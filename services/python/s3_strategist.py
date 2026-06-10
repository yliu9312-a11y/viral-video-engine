"""S3 Strategy Engine: gap_report + StructureTemplate → material_assignment.json.

Reads identified gaps, selects completion strategies (A-E), and produces a concrete
material assignment plan with specific paths and actions for Remotion rendering.
Optionally queries the knowledge base for atom recommendations per gap.
"""

import json
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime


def _query_kb_atoms(missing_shot_types: list[str], phase: str) -> list[dict]:
    """Query SurrealDB knowledge base for atom recommendations. Returns [] if KB unavailable."""
    try:
        from kb.graph_backend import GraphBackend
        from kb.template_store import TemplateStore

        db_path = str(Path(__file__).parent.parent.parent / "data" / "graph.db")
        if not Path(db_path).exists():
            return []

        async def _search():
            gb = GraphBackend(f"file://{db_path}")
            await gb.connect()
            store = TemplateStore(gb)
            results = []
            for shot_type in missing_shot_types:
                atoms = await store.find_atoms_for_gap(shot_type, phase, top_k=3)
                for atom in atoms:
                    atom["_matched_shot_type"] = shot_type
                results.extend(atoms)
            await gb.close()
            return results

        return asyncio.run(_search())
    except Exception:
        return []


# ─── Completion actions ──────────────────────────────────────────────────────

@dataclass
class CompletionAction:
    """A single action to fill a gap."""
    action_type: str  # "remotion_component" | "subtitle_overlay" | "aigc_image" | "material_transform" | "skip_phase"
    component: str = ""  # Remotion component name (e.g. "TitleBar", "StickerPack")
    params: dict = field(default_factory=dict)
    duration_s: float = 0.0


@dataclass
class PhaseAssignment:
    """Material assignment for a single phase."""
    phase: str
    strategy_id: str  # A / B / C / D / E
    strategy_name: str
    materials: list[dict] = field(default_factory=list)  # {path, type, role, duration_s}
    completion_actions: list[CompletionAction] = field(default_factory=list)
    total_duration_s: float = 0.0
    kb_atoms: list[dict] = field(default_factory=list)  # KB-recommended atoms for this gap


@dataclass
class MaterialAssignment:
    """Full material assignment plan."""
    template_id: str
    generated_at: str
    phases: list[PhaseAssignment] = field(default_factory=list)
    total_duration_s: float = 0.0
    warnings: list[str] = field(default_factory=list)


# ─── Strategy selectors ─────────────────────────────────────────────────────

def _pick_best_strategy(gap: dict) -> dict:
    """Pick the highest-priority strategy from gap's recommended list."""
    strategies = gap.get("recommended_strategies", [])
    if not strategies:
        # Fallback: always suggest caption fill
        return {"id": "B", "name": "字幕补全"}
    # Already sorted by priority (lower = higher priority)
    return strategies[0]


def _strategy_a_restructure(gap: dict, timeline: list, available_materials: list[dict]) -> PhaseAssignment:
    """Strategy A: Restructure - skip phase or merge into adjacent."""
    phase = gap["phase"]
    return PhaseAssignment(
        phase=phase,
        strategy_id="A",
        strategy_name="结构重排",
        materials=[],
        completion_actions=[CompletionAction(
            action_type="skip_phase",
            component="",
            params={"reason": f"severe gap in {phase}, merging content into adjacent phase"},
            duration_s=0.0,
        )],
        total_duration_s=0.0,
    )


def _strategy_b_caption(gap: dict, template: dict, available_materials: list[dict]) -> PhaseAssignment:
    """Strategy B: Caption/subtitle fill - text-heavy overlays to carry semantic load."""
    phase = gap["phase"]
    timeline = template.get("timeline", [])
    phase_data = next((p for p in timeline if p["phase"] == phase), {})

    dur_pct = phase_data.get("duration_pct", [0, 0.3])
    dur_range = template.get("duration_range", [15, 30])
    target_duration = (dur_pct[1] - dur_pct[0]) * dur_range[1]

    # Use available materials for this phase
    phase_materials = _assign_materials_to_phase(available_materials, phase_data, gap)
    material_duration = sum(m["duration_s"] for m in phase_materials)
    fill_duration = max(0, target_duration - material_duration)

    # Generate caption overlay actions
    actions = []
    missing_types = gap.get("missing_shot_types", [])
    caption_texts = _generate_caption_texts(phase, missing_types, template)

    if fill_duration > 0:
        actions.append(CompletionAction(
            action_type="subtitle_overlay",
            component="CaptionOverlay",
            params={
                "texts": caption_texts,
                "style": phase_data.get("caption_style", {}),
                "fill_mode": "semantic_text",
            },
            duration_s=fill_duration,
        ))

    return PhaseAssignment(
        phase=phase,
        strategy_id="B",
        strategy_name="字幕补全",
        materials=phase_materials,
        completion_actions=actions,
        total_duration_s=target_duration,
    )


def _strategy_c_packaging(gap: dict, template: dict, available_materials: list[dict], kb_atoms: list[dict] | None = None) -> PhaseAssignment:
    """Strategy C: Packaging fill - Remotion components (title bars, stickers, cards).

    When kb_atoms are provided, uses KB-recommended remotion_component instead of hardcoded defaults.
    """
    phase = gap["phase"]
    timeline = template.get("timeline", [])
    phase_data = next((p for p in timeline if p["phase"] == phase), {})

    dur_pct = phase_data.get("duration_pct", [0, 0.3])
    dur_range = template.get("duration_range", [15, 30])
    target_duration = (dur_pct[1] - dur_pct[0]) * dur_range[1]

    phase_materials = _assign_materials_to_phase(available_materials, phase_data, gap)
    material_duration = sum(m["duration_s"] for m in phase_materials)
    fill_duration = max(0, target_duration - material_duration)

    actions = []

    # Use KB-recommended components when available (highest visual_impact_score first)
    kb_components = []
    if kb_atoms:
        kb_components = sorted(
            [a for a in kb_atoms if a.get("remotion_component")],
            key=lambda a: a.get("visual_impact_score", 0),
            reverse=True,
        )

    # Always generate at least one action per phase (even if fill_duration is 0)
    from atom_component_map import get_components_for_phase
    min_actions = 1

    if kb_components:
        # Map KB atoms to actual Remotion components
        mapped = get_components_for_phase(kb_components, phase, max_components=3)
        for comp in mapped:
            dur = max(min(fill_duration, 4.0), 1.0)  # at least 1s per action
            actions.append(CompletionAction(
                action_type="remotion_component",
                component=comp["component"],
                params=comp["params"],
                duration_s=dur,
            ))
            fill_duration = max(0, fill_duration - dur)
    else:
        # Fallback: use actual Remotion components
        from atom_component_map import PHASE_TEXT_DEFAULTS, PHASE_PRICE_DEFAULTS, PHASE_CHART_DEFAULTS

        if phase == "hook" and fill_duration > 0:
            text_defaults = PHASE_TEXT_DEFAULTS.get("hook", {})
            actions.append(CompletionAction(
                action_type="remotion_component",
                component="KineticText",
                params=text_defaults,
                duration_s=min(fill_duration, 3.0),
            ))
            fill_duration -= min(fill_duration, 3.0)

        if phase == "build" and fill_duration > 0:
            actions.append(CompletionAction(
                action_type="remotion_component",
                component="BarChart",
                params={"data": PHASE_CHART_DEFAULTS.get("build", [])},
                duration_s=min(fill_duration, 4.0),
            ))
            fill_duration -= min(fill_duration, 4.0)

        if phase == "payoff_cta" and fill_duration > 0:
            price_defaults = PHASE_PRICE_DEFAULTS.get("payoff_cta", {})
            actions.append(CompletionAction(
                action_type="remotion_component",
                component="PriceReveal",
                params=price_defaults,
                duration_s=min(fill_duration, 3.0),
            ))
            fill_duration -= min(fill_duration, 3.0)

    # Sticker fills for remaining
    if fill_duration > 0:
        actions.append(CompletionAction(
            action_type="remotion_component",
            component="StickerPack",
            params={"density": "medium"},
            duration_s=fill_duration,
        ))

    return PhaseAssignment(
        phase=phase,
        strategy_id="C",
        strategy_name="包装补全",
        materials=phase_materials,
        completion_actions=actions,
        total_duration_s=target_duration,
    )


def _strategy_d_aigc(gap: dict, template: dict, available_materials: list[dict], kb_atoms: list[dict] | None = None) -> PhaseAssignment:
    """Strategy D: AIGC generation with KB-enhanced prompts.

    When kb_atoms are provided, uses their descriptions to enrich the AIGC prompt
    for more contextually accurate image generation.
    """
    phase = gap["phase"]
    timeline = template.get("timeline", [])
    phase_data = next((p for p in timeline if p["phase"] == phase), {})

    dur_pct = phase_data.get("duration_pct", [0, 0.3])
    dur_range = template.get("duration_range", [15, 30])
    target_duration = (dur_pct[1] - dur_pct[0]) * dur_range[1]

    phase_materials = _assign_materials_to_phase(available_materials, phase_data, gap)

    # AIGC actions with KB-enhanced prompts
    actions = []
    missing_types = gap.get("missing_shot_types", [])
    for shot_type in missing_types:
        prompt = _build_aigc_prompt(shot_type, template, kb_atoms)
        actions.append(CompletionAction(
            action_type="aigc_image",
            component="AIGCFrame",
            params={
                "prompt": prompt,
                "shot_type": shot_type,
                "model": "gemini_imagen",
                "output_placeholder": f"aigc_{phase}_{shot_type}.png",
                "kb_enhanced": bool(kb_atoms),
            },
            duration_s=target_duration / max(len(missing_types), 1),
        ))

    return PhaseAssignment(
        phase=phase,
        strategy_id="D",
        strategy_name="AIGC 生成",
        materials=phase_materials,
        completion_actions=actions,
        total_duration_s=target_duration,
    )


def _strategy_e_recombine(gap: dict, template: dict, available_materials: list[dict]) -> PhaseAssignment:
    """Strategy E: Material recombination - Ken Burns, speed changes, reverse, crop."""
    phase = gap["phase"]
    timeline = template.get("timeline", [])
    phase_data = next((p for p in timeline if p["phase"] == phase), {})

    dur_pct = phase_data.get("duration_pct", [0, 0.3])
    dur_range = template.get("duration_range", [15, 30])
    target_duration = (dur_pct[1] - dur_pct[0]) * dur_range[1]

    phase_materials = _assign_materials_to_phase(available_materials, phase_data, gap)
    shortfall = gap.get("shot_count_shortfall", 0)

    # Apply transforms to existing materials to create "new" shots
    actions = []
    transforms = ["ken_burns_zoom_in", "ken_burns_pan", "speed_2x", "reverse", "crop_center"]
    for i in range(shortfall):
        transform = transforms[i % len(transforms)]
        actions.append(CompletionAction(
            action_type="material_transform",
            component="TransformedClip",
            params={
                "source": phase_materials[i % len(phase_materials)]["path"] if phase_materials else "",
                "transform": transform,
            },
            duration_s=phase_materials[i % len(phase_materials)]["duration_s"] if phase_materials else 3.0,
        ))

    return PhaseAssignment(
        phase=phase,
        strategy_id="E",
        strategy_name="素材重组",
        materials=phase_materials,
        completion_actions=actions,
        total_duration_s=target_duration,
    )


def _strategy_f_orchestrate(gap: dict, template: dict, available_materials: list[dict], kb_atoms: list[dict] | None = None) -> PhaseAssignment:
    """Strategy F: LLM-orchestrated animation script.

    Uses the animation orchestrator to generate a detailed animation script
    that the Remotion ScriptDrivenVideo composition can render directly.
    """
    phase = gap["phase"]
    timeline = template.get("timeline", [])
    phase_data = next((p for p in timeline if p["phase"] == phase), {})

    dur_pct = phase_data.get("duration_pct", [0, 0.3])
    dur_range = template.get("duration_range", [15, 30])
    target_duration = (dur_pct[1] - dur_pct[0]) * dur_range[1]

    phase_materials = _assign_materials_to_phase(available_materials, phase_data, gap)

    # Store the animation script as a completion action
    actions = []
    if kb_atoms:
        actions.append(CompletionAction(
            action_type="animation_script",
            component="ScriptDrivenVideo",
            params={
                "kb_atoms": [
                    {
                        "atom_id": a.get("atom_id", ""),
                        "remotion_component": a.get("remotion_component", ""),
                        "description": a.get("description", ""),
                        "fills_shot_types": a.get("fills_shot_types", []),
                        "visual_impact_score": a.get("visual_impact_score", 0),
                    }
                    for a in (kb_atoms or [])
                ],
                "gap": gap,
                "template_category": template.get("category", "通用"),
            },
            duration_s=target_duration,
        ))

    return PhaseAssignment(
        phase=phase,
        strategy_id="F",
        strategy_name="LLM 编排",
        materials=phase_materials,
        completion_actions=actions,
        total_duration_s=target_duration,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _assign_materials_to_phase(
    available_materials: list[dict],
    phase_data: dict,
    gap: dict,
) -> list[dict]:
    """Assign available materials to a phase based on shot type matching."""
    required_types = set(phase_data.get("required_shot_types", []))
    assigned = []
    used_paths = set()

    # First pass: match by tagged type
    for mat in available_materials:
        if mat["path"] in used_paths:
            continue
        mat_types = set(mat.get("tagged_types", []))
        if mat_types & required_types:
            assigned.append({
                "path": mat["path"],
                "type": mat["type"],
                "role": "primary",
                "duration_s": min(mat.get("duration", 3.0), 5.0),
            })
            used_paths.add(mat["path"])

    # Second pass: fill with general materials if short
    for mat in available_materials:
        if mat["path"] in used_paths:
            continue
        if len(assigned) >= phase_data.get("shot_count_range", [1, 3])[1]:
            break
        assigned.append({
            "path": mat["path"],
            "type": mat["type"],
            "role": "fill",
            "duration_s": min(mat.get("duration", 3.0), 3.0),
        })
        used_paths.add(mat["path"])

    return assigned


def _generate_caption_texts(phase: str, missing_types: list[str], template: dict) -> list[str]:
    """Generate caption text suggestions based on phase and missing types."""
    hook_type = template.get("narrative", {}).get("hook_type", "")
    build_pattern = template.get("narrative", {}).get("build_pattern", "")
    cta_type = template.get("narrative", {}).get("cta_type", "")

    if phase == "hook":
        if "悬念" in hook_type:
            return ["你知道吗？", "99%的人都不知道的秘密"]
        if "数字" in hook_type:
            return ["3个方法让你...", "震惊！原来可以这样"]
        return ["想要改变？", "这个方法太好用了"]
    elif phase == "build":
        if "对比" in build_pattern:
            return ["使用前 vs 使用后", "效果一目了然"]
        if "教程" in build_pattern:
            return ["第一步：准备材料", "第二步：开始操作", "第三步：完成"]
        return ["核心卖点", "为什么选择我们", "真实效果展示"]
    else:  # payoff_cta
        if "限时" in cta_type:
            return ["限时优惠！", "点击下方链接抢购"]
        if "社会认同" in cta_type:
            return ["10万+用户的选择", "好评如潮，你也试试"]
        return ["立即行动", "点击获取更多信息"]


def _extract_selling_points(template: dict) -> list[str]:
    """Extract selling points from template for card display."""
    build_pattern = template.get("narrative", {}).get("build_pattern", "")
    if "痛点" in build_pattern:
        return ["解决核心痛点", "效果立竿见影", "用户真实反馈"]
    return ["产品特色", "使用便捷", "性价比高"]


def _build_aigc_prompt(shot_type: str, template: dict, kb_atoms: list[dict] | None = None) -> str:
    """Build a detailed prompt for Gemini image generation.

    Includes aesthetic constraints from design tokens:
    - Color palette consistency (60-30-10 rule)
    - Vertical 9:16 composition with safe zone awareness
    - Professional lighting and quality
    """
    category = template.get("category", "通用")

    # Palette-specific color guidance
    palette_guides = {
        "beauty": "warm soft tones, coral pink accents, cream white background, gentle lighting",
        "digital": "cool dark tones, cyan electric blue accents, deep navy background, dramatic lighting",
        "food": "warm golden tones, honey amber accents, cream yellow background, appetizing warm light",
        "viral": "high contrast black and white, bold yellow accent, dramatic shadows, punchy colors",
    }
    # Guess palette from category
    palette_map = {"美妆": "beauty", "护肤": "beauty", "数码": "digital", "科技": "digital", "美食": "food", "生活": "food"}
    palette = palette_map.get(category, "viral")
    color_guide = palette_guides.get(palette, palette_guides["viral"])

    base_prompts = {
        "face_closeup": f"professional portrait photo, person smiling naturally, soft studio lighting, shallow depth of field, {category} context, {color_guide}, centered composition with space for text overlay at top and bottom, vertical 9:16, 4k quality",
        "product_closeup": f"commercial product photography, {category} product as hero subject, {color_guide}, clean background with subtle gradient, dramatic side lighting, sharp details, centered with 20% margin on all sides, vertical 9:16",
        "product_usage": f"lifestyle photo of person using {category} product, natural authentic moment, {color_guide}, modern clean environment, subject in center third of frame, vertical 9:16",
        "before_after": f"split comparison photo, left side showing before and right side showing after, {category} results, {color_guide}, clean symmetric layout, vertical 9:16",
        "hook_attention_grabber": f"eye-catching creative photo for social media, {category} theme, {color_guide}, dynamic composition, bold and energetic, vertical 9:16",
        "text_overlay": f"clean minimalist background with subtle gradient, {color_guide}, generous negative space in center 60% for text overlay, {category} theme, vertical 9:16",
        "transition": f"abstract smooth gradient background, {color_guide}, clean and modern, subtle texture, vertical 9:16",
    }
    base = base_prompts.get(shot_type, f"high quality {category} {shot_type} photo, {color_guide}, professional photography, centered composition, vertical 9:16")

    # Enrich with KB atom descriptions
    if kb_atoms:
        relevant = [a for a in kb_atoms if shot_type in a.get("fills_shot_types", [])]
        if relevant:
            best = relevant[0]
            kb_desc = best.get("description", "")
            if kb_desc:
                base += f", inspired by: {kb_desc}"

    # Anti-patterns (avoid common AI image failures)
    base += ", avoid: plastic skin, oversaturated colors, watermarks, text artifacts, blurry details"

    return base


def _generate_aigc_images(
    phase_assignment: PhaseAssignment,
    gap: dict,
    template: dict,
    output_dir: str,
) -> None:
    """Generate AIGC images for Strategy D and add to phase materials."""
    try:
        from gemini_imager import generate_for_gap
    except ImportError:
        print("Warning: gemini_imager not available, skipping AIGC generation")
        return

    aigc_dir = str(Path(output_dir) / "aigc")
    Path(aigc_dir).mkdir(parents=True, exist_ok=True)

    missing_types = gap.get("missing_shot_types", [])
    for shot_type in missing_types:
        prompt = _build_aigc_prompt(shot_type, template)
        print(f"Generating AIGC image for {shot_type}: {prompt[:60]}...")

        img_path = generate_for_gap(
            prompt=prompt,
            phase=gap["phase"],
            shot_type=shot_type,
            output_dir=aigc_dir,
        )

        if img_path:
            phase_assignment.materials.append({
                "path": img_path,
                "type": "image",
                "role": "aigc_generated",
                "duration_s": 3.0,
            })
            print(f"  → Saved: {img_path}")
        else:
            print(f"  → Failed to generate for {shot_type}")


# ─── Main entry point ────────────────────────────────────────────────────────

STRATEGY_MAP = {
    "A": _strategy_a_restructure,
    "B": _strategy_b_caption,
    "C": _strategy_c_packaging,
    "D": _strategy_d_aigc,
    "E": _strategy_e_recombine,
    "F": _strategy_f_orchestrate,
}


def generate_assignment(
    gap_report: dict,
    template: dict,
    material_dir: str,
    output_dir: str = "",
) -> MaterialAssignment:
    """Generate a concrete material assignment plan from gap report.

    Args:
        gap_report: gap_report dict from S3 gap detector
        template: StructureTemplate dict from S2
        material_dir: path to user's materials directory

    Returns:
        MaterialAssignment with per-phase strategies and actions
    """
    gaps = gap_report.get("gaps", [])
    materials = gap_report.get("materials", [])
    timeline = template.get("timeline", [])

    assignment = MaterialAssignment(
        template_id=template.get("template_id", ""),
        generated_at=datetime.now().isoformat(),
    )

    assigned_phases = set()

    for gap in gaps:
        phase = gap["phase"]
        strategy = _pick_best_strategy(gap)
        strategy_id = strategy["id"]

        # Query KB BEFORE strategy execution so strategies can use the results
        missing_types = gap.get("missing_shot_types", [])
        kb_atoms: list[dict] = []
        if missing_types:
            kb_results = _query_kb_atoms(missing_types, phase)
            if kb_results:
                kb_atoms = [
                    {
                        "atom_id": str(r.get("id", "")).split(":")[-1] if ":" in str(r.get("id", "")) else str(r.get("id", "")),
                        "description": r.get("description", ""),
                        "remotion_component": r.get("remotion_component", ""),
                        "fills_shot_types": r.get("fills_shot_types", []),
                        "visual_impact_score": r.get("visual_impact_score", 0),
                        "distance": round(r.get("dist", 0), 4),
                        "matched_type": r.get("_matched_shot_type", ""),
                    }
                    for r in kb_results
                ]

        # Get strategy function
        strategy_fn = STRATEGY_MAP.get(strategy_id)
        if not strategy_fn:
            strategy_fn = _strategy_b_caption  # fallback

        # Execute strategy (pass kb_atoms to C and D)
        if strategy_id == "A":
            phase_assignment = strategy_fn(gap, timeline, materials)
        elif strategy_id in ("C", "D"):
            phase_assignment = strategy_fn(gap, template, materials, kb_atoms=kb_atoms)
        else:
            phase_assignment = strategy_fn(gap, template, materials)

        # Attach KB atoms to phase for frontend display
        phase_assignment.kb_atoms = kb_atoms

        # Strategy D: actually generate images via Gemini
        if strategy_id == "D" and output_dir:
            _generate_aigc_images(phase_assignment, gap, template, output_dir)

        assignment.phases.append(phase_assignment)
        assigned_phases.add(phase)

    # Add non-gap phases as pass-through (use available materials as-is)
    for phase_data in timeline:
        phase = phase_data["phase"]
        if phase not in assigned_phases:
            phase_materials = _assign_materials_to_phase(materials, phase_data, {"missing_shot_types": []})
            dur_pct = phase_data.get("duration_pct", [0, 0.3])
            dur_range = template.get("duration_range", [15, 30])
            target_duration = (dur_pct[1] - dur_pct[0]) * dur_range[1]

            assignment.phases.append(PhaseAssignment(
                phase=phase,
                strategy_id="PASS",
                strategy_name="直接使用",
                materials=phase_materials,
                completion_actions=[],
                total_duration_s=target_duration,
            ))

    # Sort phases by template order
    phase_order = {p["phase"]: i for i, p in enumerate(timeline)}
    assignment.phases.sort(key=lambda pa: phase_order.get(pa.phase, 99))

    # Compute total
    assignment.total_duration_s = sum(pa.total_duration_s for pa in assignment.phases)

    # Warnings
    if not gaps:
        assignment.warnings.append("No gaps identified - all materials sufficient")
    high_gaps = [g for g in gaps if g.get("severity") == "HIGH"]
    if high_gaps:
        assignment.warnings.append(f"{len(high_gaps)} HIGH severity gaps - video quality may be impacted")

    return assignment


def run_strategist(
    gap_report_path: str,
    template_path: str,
    material_dir: str,
    output_dir: str = "",
) -> dict:
    """Full S3 strategy pipeline.

    Args:
        gap_report_path: path to gap_report.json
        template_path: path to StructureTemplate JSON
        material_dir: path to user's materials directory
        output_dir: where to save material_assignment.json

    Returns:
        material_assignment dict
    """
    with open(gap_report_path, "r", encoding="utf-8") as f:
        gap_report = json.load(f)

    with open(template_path, "r", encoding="utf-8") as f:
        template = json.load(f)

    assignment = generate_assignment(gap_report, template, material_dir, output_dir)
    result = asdict(assignment)

    # Convert CompletionAction dataclasses
    for phase in result["phases"]:
        phase["completion_actions"] = [asdict(a) if hasattr(a, "__dataclass_fields__") else a for a in phase["completion_actions"]]

    # Aesthetic lint + auto-fix
    from aesthetic_linter import lint_and_fix
    result, lint_result = lint_and_fix(result, template)
    if lint_result.auto_fixes:
        print(f"Aesthetic linter: {lint_result.summary()}")
    for err in lint_result.errors:
        if err.severity == "error":
            print(f"  ❌ [{err.rule}] {err.message}")

    # Save to file
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        assignment_path = str(Path(output_dir) / "material_assignment.json")
        with open(assignment_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        result["saved_to"] = assignment_path

    return result
