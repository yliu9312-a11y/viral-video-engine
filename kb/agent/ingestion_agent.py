"""Ingestion Agent: decide merge/create_new/split when adding new templates to KB.

Flow:
1. Find similar existing patterns via vector search
2. Compare structure (timeline phases, shot types)
3. LLM decides: merge_existing / create_new / split
4. Execute decision on the graph
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Literal

import httpx


MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_API_URL = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")


@dataclass
class IngestionResult:
    """Result of an ingestion decision."""
    decision: str = "pending"  # "merge_existing" | "create_new" | "split"
    target_tid: str = ""  # for merge
    reason: str = ""
    new_tids: list[str] = field(default_factory=list)  # for create_new or split
    similar_patterns: list[dict] = field(default_factory=list)


def _structural_similarity(a: dict, b: dict) -> float:
    """Compute structural similarity between two templates based on timeline phases and shot types."""
    a_phases = {p.get("phase", ""): set(p.get("required_shot_types", [])) for p in a.get("timeline", [])}
    b_phases = {p.get("phase", ""): set(p.get("required_shot_types", [])) for p in b.get("timeline", [])}

    if not a_phases or not b_phases:
        return 0.0

    all_phases = set(a_phases.keys()) | set(b_phases.keys())
    if not all_phases:
        return 0.0

    score = 0.0
    for phase in all_phases:
        a_types = a_phases.get(phase, set())
        b_types = b_phases.get(phase, set())
        if a_types and b_types:
            overlap = len(a_types & b_types) / max(len(a_types | b_types), 1)
            score += overlap
        elif not a_types and not b_types:
            score += 1.0

    return score / len(all_phases)


async def _llm_decide(candidate: dict, similar: list[dict]) -> dict:
    """Ask LLM to decide merge/create_new/split."""
    if not MIMO_API_KEY:
        # Fallback: simple heuristic
        if similar and similar[0].get("dist", 1.0) < 0.15:
            return {"type": "merge_existing", "target_tid": similar[0].get("tid", ""), "reason": "high vector similarity"}
        return {"type": "create_new", "reason": "no close match found"}

    similar_summary = []
    for s in similar[:3]:
        similar_summary.append({
            "tid": s.get("tid", ""),
            "category": s.get("category", ""),
            "description": s.get("description", "")[:100],
            "distance": round(s.get("dist", 0), 4),
            "timeline_phases": [p.get("phase", "") for p in s.get("template", {}).get("timeline", [])],
        })

    prompt = f"""你是一个知识图谱入库决策专家。新样例模板需要入库，请判断应该如何处理。

新模板:
- 类目: {candidate.get('category', '未知')}
- 描述: {json.dumps(candidate.get('narrative', {}), ensure_ascii=False)}
- 时间线: {json.dumps([{'phase': p.get('phase'), 'shots': p.get('required_shot_types', [])} for p in candidate.get('timeline', [])], ensure_ascii=False)}

已有的相似模板:
{json.dumps(similar_summary, ensure_ascii=False, indent=2)}

请判断:
1. 如果新模板与某个已有模板结构高度重叠(>85%相似), 返回 {{"type":"merge_existing", "target_tid":"...", "reason":"..."}}
2. 如果新模板结构差异显著, 返回 {{"type":"create_new", "reason":"..."}}
3. 如果新模板应该被拆成多个独立模板, 返回 {{"type":"split", "reason":"...", "split_descriptions":["..."]}}

只返回 JSON，不要其他文字。"""

    try:
        headers = {"Authorization": f"Bearer {MIMO_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": MIMO_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500,
        }
        resp = httpx.post(MIMO_API_URL, json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Extract JSON from response
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content)
    except Exception as e:
        print(f"LLM decision failed: {e}, falling back to heuristic")
        if similar and similar[0].get("dist", 1.0) < 0.15:
            return {"type": "merge_existing", "target_tid": similar[0].get("tid", ""), "reason": "fallback: high similarity"}
        return {"type": "create_new", "reason": f"fallback: {e}"}


async def _extract_modules_atoms(template: dict, store) -> list[str]:
    """Auto-extract modules and atoms from template timeline, build full subgraph.

    Returns list of module IDs for composed_of linking.
    """
    timeline = template.get("timeline", [])
    category = template.get("category", "通用")
    module_ids = []

    for i, phase_data in enumerate(timeline):
        phase = phase_data.get("phase", f"phase_{i}")
        shot_types = phase_data.get("required_shot_types", [])
        dur_range = phase_data.get("duration_pct", [0.2, 0.4])

        # Build atoms for each shot type
        atom_refs = []
        for st in shot_types:
            # Check if atom already exists for this shot type
            existing = await store.gb.execute(
                f"SELECT * FROM atom WHERE '{st}' IN fills_shot_types LIMIT 1"
            )
            if existing and len(existing) > 0:
                atom_id = str(existing[0]["id"]).split(":")[-1]
            else:
                # Create new atom
                atom_id = f"atom_{st}_{uuid.uuid4().hex[:6]}"
                atom_desc = _shot_type_to_description(st, phase)
                atom_type = _shot_type_to_atom_type(st)
                component = _shot_type_to_component(st)

                await store.store_atom({
                    "atom_id": atom_id,
                    "type": atom_type,
                    "category": phase,
                    "remotion_component": component,
                    "description": atom_desc,
                    "required_inputs": [_shot_type_to_input(st)],
                    "fills_shot_types": [st],
                    "duration_min_s": phase_data.get("avg_shot_length_s", 2.0) * 0.7,
                    "duration_max_s": phase_data.get("avg_shot_length_s", 3.0) * 1.5,
                    "visual_impact_score": 0.7,
                    "tech_stack": ["remotion"],
                })

            atom_refs.append({"atom_id": atom_id, "weight": 0.5, "optional": False})

        # Create module for this phase
        module_id = f"mod_{phase}_{uuid.uuid4().hex[:6]}"
        narrative = phase_data.get("caption_style", {})
        module_desc = f"{phase}阶段: {', '.join(shot_types)}"

        await store.store_module({
            "module_id": module_id,
            "phase": phase,
            "narrative_pattern": template.get("narrative", {}).get("build_pattern", ""),
            "script_template": module_desc,
            "duration_min_s": dur_range[0] * template.get("duration_range", [15, 30])[0],
            "duration_max_s": dur_range[1] * template.get("duration_range", [15, 30])[1],
            "description": module_desc,
            "atoms": atom_refs,
        })

        # Create composed_of edge from pattern to module (done later by caller)
        module_ids.append(module_id)

    return module_ids


def _shot_type_to_description(shot_type: str, phase: str) -> str:
    """Generate human-readable description from shot type."""
    descriptions = {
        "face_closeup": "面部特写镜头，展示真实人物表情",
        "text_overlay": "文字覆盖层，用于标题或字幕展示",
        "product_closeup": "产品特写镜头，展示细节和质感",
        "product_usage": "产品使用场景，展示实际使用过程",
        "before_after": "前后对比镜头，展示使用前后效果",
        "unboxing": "开箱镜头，展示拆包过程",
        "ingredients": "成分/材料特写，展示核心成分",
        "cooking_process": "制作过程镜头，展示烹饪或制作步骤",
        "step_demo": "步骤演示镜头，分步展示操作方法",
        "comparison": "对比镜头，竞品或效果对比",
        "outdoor_scene": "户外场景，自然环境画面",
        "indoor_scene": "室内场景，生活化画面",
        "reaction_shot": "反应镜头，展示使用后的惊喜或反馈",
        "data_display": "数据展示画面，图表或数字呈现",
        "lifestyle_broll": "生活方式空镜，展示日常场景",
        "hand_gesture": "手势动作镜头，展示手部操作",
        "screen_recording": "屏幕录制画面，展示软件或界面",
        "tutorial_step": "教程步骤画面，教学内容展示",
        "hook_attention_grabber": "高能量开场，快速抓住注意力",
    }
    return descriptions.get(shot_type, f"{phase}阶段的{shot_type}镜头")


def _shot_type_to_atom_type(shot_type: str) -> str:
    """Map shot type to atom type."""
    if "text" in shot_type or "overlay" in shot_type:
        return "caption"
    if "transition" in shot_type or "effect" in shot_type:
        return "transition"
    if "3d" in shot_type:
        return "3d"
    return "shot"


def _shot_type_to_component(shot_type: str) -> str:
    """Map shot type to Remotion component name."""
    components = {
        "face_closeup": "FaceCloseupFrame",
        "text_overlay": "TitleBar",
        "product_closeup": "ProductZoomFrame",
        "product_usage": "UsageDemoFrame",
        "before_after": "BeforeAfterSplit",
        "unboxing": "UnboxingFrame",
        "ingredients": "IngredientDetail",
        "cooking_process": "ProcessStepFrame",
        "step_demo": "TutorialStepFrame",
        "comparison": "ComparisonDemo",
        "outdoor_scene": "BrollFrame",
        "indoor_scene": "BrollFrame",
        "reaction_shot": "ReactionFrame",
        "data_display": "DataGraphic",
        "lifestyle_broll": "LifestyleFrame",
        "hand_gesture": "HandGestureFrame",
        "screen_recording": "ScreenRecordFrame",
        "tutorial_step": "TutorialStepFrame",
        "hook_attention_grabber": "AttentionGrabber",
    }
    return components.get(shot_type, "GenericFrame")


def _shot_type_to_input(shot_type: str) -> str:
    """Map shot type to required input type."""
    if "text" in shot_type:
        return "text_content"
    if "product" in shot_type or "unboxing" in shot_type:
        return "product_image_or_video"
    if "face" in shot_type or "reaction" in shot_type:
        return "face_video_or_image"
    if "screen" in shot_type:
        return "screen_recording"
    return "bg_video_or_image"


async def ingest_template(
    template: dict,
    vertical: str = "通用",
    gb=None,
    store=None,
) -> IngestionResult:
    """Main ingestion entry point.

    Args:
        template: StructureTemplate dict to ingest
        vertical: product/content category
        gb: GraphBackend instance
        store: TemplateStore instance

    Returns:
        IngestionResult with decision and actions taken
    """
    # Build description for embedding search
    narrative = template.get("narrative", {})
    timeline = template.get("timeline", [])
    desc_parts = [
        f"类别:{template.get('category', '通用')}",
        f"钩子:{narrative.get('hook_type', '')}",
        f"结构:{narrative.get('build_pattern', '')}",
        f"CTA:{narrative.get('cta_type', '')}",
    ]
    for phase in timeline:
        desc_parts.append(f"{phase.get('phase', '')}:{','.join(phase.get('required_shot_types', []))}")
    search_query = "|".join(desc_parts)

    # Step 1: Find similar patterns via vector search
    similar = await store.search_similar(search_query, top_k=5)

    # Enrich with structural similarity
    for s in similar:
        s_tpl = s.get("template", {})
        s["structural_sim"] = _structural_similarity(template, s_tpl)
        s["tid"] = str(s.get("id", ""))
        if ":" in s["tid"]:
            s["tid"] = s["tid"].split(":")[-1]

    # Sort by combined score (vector distance + structural)
    similar.sort(key=lambda s: s.get("dist", 1.0) * 0.6 + (1 - s.get("structural_sim", 0)) * 0.4)

    result = IngestionResult(similar_patterns=similar)

    # Step 2: LLM decides
    decision = await _llm_decide(template, similar)
    result.decision = decision.get("type", "create_new")
    result.reason = decision.get("reason", "")

    # Step 3: Execute decision
    if result.decision == "merge_existing":
        target_tid = decision.get("target_tid", "")
        if not target_tid and similar:
            target_tid = similar[0].get("tid", "")
        result.target_tid = target_tid

        if target_tid:
            # Increment appearance_count
            await store.gb.execute(
                f"UPDATE pattern:{target_tid} SET appearance_count += 1"
            )
            print(f"Merged into existing pattern:{target_tid}")

    elif result.decision == "create_new":
        # Auto-extract modules and atoms from template timeline
        module_ids = await _extract_modules_atoms(template, store)
        tid = await store.store_template(template, vertical=vertical, module_ids=module_ids)
        result.new_tids = [tid]
        print(f"Created new pattern:{tid} with {len(module_ids)} modules")

    elif result.decision == "split":
        split_descs = decision.get("split_descriptions", [])
        if split_descs:
            for i, desc in enumerate(split_descs):
                # Create a sub-template for each split
                sub_template = {
                    **template,
                    "template_id": f"{template.get('template_id', 'tpl')}_split_{i}",
                    "narrative": {**template.get("narrative", {}), "split_description": desc},
                }
                module_ids = await _extract_modules_atoms(sub_template, store)
                tid = await store.store_template(sub_template, vertical=vertical, module_ids=module_ids)
                result.new_tids.append(tid)
                print(f"Split part {i}: created pattern:{tid} with {len(module_ids)} modules")
        else:
            # Fallback: just create as new
            module_ids = await _extract_modules_atoms(template, store)
            tid = await store.store_template(template, vertical=vertical, module_ids=module_ids)
            result.new_tids = [tid]

    return result
