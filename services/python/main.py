"""VST Python Service: S1 video analysis + S2 structure extraction + S3 gap detection."""

import json
import math
import os
import uuid
from pathlib import Path

# Load .env from project root (works regardless of how uvicorn is started)
from dotenv import load_dotenv
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.is_file():
    load_dotenv(_env_path, override=False)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from s1_analyzer import run_s1
from s2_extractor import run_s2
from s3_gap_detector import run_gap_detection
from s3_strategist import run_strategist
from video_utils import ensure_compatible

app = FastAPI(title="VST Python Service")

PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_BASE = PROJECT_ROOT / "data" / "output"


class HealthResponse(BaseModel):
    status: str
    service: str


class ExtractRequest(BaseModel):
    video_path: str = ""  # single video (backward compatible)
    video_paths: list[str] = []  # multiple videos


class ShotInfo(BaseModel):
    index: int
    start_time: float
    end_time: float
    duration: float
    caption: str
    clip_path: str = ""
    thumbnail_path: str = ""


class ExtractResponse(BaseModel):
    success: bool
    template_id: str = ""
    shots: list[ShotInfo] = []
    structure_template: dict = {}
    output_dir: str = ""
    converted: bool = False
    error: str = ""
    video_infos: list[dict] = []  # basic info per video


class GapRequest(BaseModel):
    structure_template: dict
    material_dir: str


class GapResponse(BaseModel):
    success: bool
    gap_report: dict = {}
    output_dir: str = ""
    error: str = ""


class AssignRequest(BaseModel):
    gap_report_path: str
    template_path: str
    material_dir: str


class AssignResponse(BaseModel):
    success: bool
    assignment: dict = {}
    output_dir: str = ""
    error: str = ""


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", service="vst-python")


@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest):
    """S1+S2 pipeline: video path(s) → shots + StructureTemplate JSON.

    Supports single or multiple reference videos. When multiple videos are
    provided, each is analyzed independently and the templates are merged.
    """
    # Resolve video paths (support both single and multi)
    video_paths = req.video_paths if req.video_paths else ([req.video_path] if req.video_path else [])
    video_paths = [p for p in video_paths if p]  # filter empty strings

    if not video_paths:
        raise HTTPException(status_code=400, detail="video_path or video_paths is required")
    for p in video_paths:
        if not Path(p).is_file():
            raise HTTPException(status_code=400, detail=f"Video not found: {p}")

    try:
        job_id = uuid.uuid4().hex[:8]
        output_dir = str(OUTPUT_BASE / job_id)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        templates = []
        all_shots = []
        video_infos = []
        shot_offset = 0

        for idx, vpath in enumerate(video_paths):
            usable_path = ensure_compatible(vpath)
            s1_output = run_s1(usable_path, output_dir=output_dir)
            template = run_s2(s1_output)
            templates.append(template)

            # Collect video info
            video_infos.append({
                "index": idx,
                "path": vpath,
                "duration": round(s1_output.total_duration, 2),
                "fps": round(s1_output.fps, 1),
                "width": s1_output.width,
                "height": s1_output.height,
                "shot_count": len(s1_output.shots),
                "has_audio": s1_output.audio.has_audio,
                "bpm": round(s1_output.audio.bpm, 1) if s1_output.audio.has_audio else 0,
            })

            # Collect shots with global index offset
            for s in s1_output.shots:
                all_shots.append(ShotInfo(
                    index=s.index + shot_offset,
                    start_time=round(s.start_time, 3),
                    end_time=round(s.end_time, 3),
                    duration=round(s.duration, 3),
                    caption=s.caption,
                    clip_path=s.clip_path,
                    thumbnail_path=s.thumbnail_path,
                ))
            shot_offset += len(s1_output.shots)

        # Merge templates if multiple
        if len(templates) > 1:
            from template_merger import merge_templates
            template = merge_templates(templates)
        else:
            template = templates[0]

        # Save StructureTemplate to disk
        template_path = str(Path(output_dir) / "structure_template.json")
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)

        return ExtractResponse(
            success=True,
            template_id=template["template_id"],
            shots=all_shots,
            structure_template=template,
            output_dir=output_dir,
            video_infos=video_infos,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return ExtractResponse(success=False, error=str(e))


@app.post("/extract_style")
async def extract_style(req: ExtractRequest):
    """从参考视频提取完整 SceneDescription（逐元素属性）。

    与 /extract 的区别：
    - /extract: 提取 StructureTemplate（泛化的叙事结构）
    - /extract_style: 提取 SceneDescription（每个元素的精确位置/颜色/动画）
    """
    video_paths = req.video_paths if req.video_paths else ([req.video_path] if req.video_path else [])
    video_paths = [p for p in video_paths if p]
    if not video_paths:
        raise HTTPException(status_code=400, detail="video_path or video_paths is required")
    for p in video_paths:
        if not Path(p).is_file():
            raise HTTPException(status_code=400, detail=f"Video not found: {p}")

    try:
        from scene_description import extract_scene_description, scene_to_dict

        job_id = uuid.uuid4().hex[:8]
        output_dir = str(OUTPUT_BASE / job_id)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        scenes = []
        for vpath in video_paths:
            scene = extract_scene_description(vpath, output_dir=output_dir)
            scenes.append(scene_to_dict(scene))

        # 保存到文件
        scene_path = str(Path(output_dir) / "scene_description.json")
        with open(scene_path, "w", encoding="utf-8") as f:
            json.dump(scenes[0] if len(scenes) == 1 else scenes, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "scene": scenes[0] if len(scenes) == 1 else scenes,
            "output_dir": output_dir,
            "scene_path": scene_path,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/gap", response_model=GapResponse)
async def gap(req: GapRequest):
    """S3 gap detection: StructureTemplate + material_dir → gap_report.json."""
    material_dir = req.material_dir
    if not Path(material_dir).is_dir():
        raise HTTPException(status_code=400, detail=f"Material directory not found: {material_dir}")

    try:
        job_id = uuid.uuid4().hex[:8]
        output_dir = str(OUTPUT_BASE / f"gap_{job_id}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        report = run_gap_detection(
            template=req.structure_template,
            material_dir=material_dir,
            output_dir=output_dir,
        )

        return GapResponse(
            success=True,
            gap_report=report,
            output_dir=output_dir,
        )
    except Exception as e:
        return GapResponse(success=False, error=str(e))


@app.post("/assign", response_model=AssignResponse)
async def assign(req: AssignRequest):
    """S3 strategy: gap_report + template → material_assignment.json."""
    if not Path(req.gap_report_path).is_file():
        raise HTTPException(status_code=400, detail=f"Gap report not found: {req.gap_report_path}")
    if not Path(req.template_path).is_file():
        raise HTTPException(status_code=400, detail=f"Template not found: {req.template_path}")
    if not Path(req.material_dir).is_dir():
        raise HTTPException(status_code=400, detail=f"Material directory not found: {req.material_dir}")

    try:
        job_id = uuid.uuid4().hex[:8]
        output_dir = str(OUTPUT_BASE / f"assign_{job_id}")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        result = run_strategist(
            gap_report_path=req.gap_report_path,
            template_path=req.template_path,
            material_dir=req.material_dir,
            output_dir=output_dir,
        )

        return AssignResponse(
            success=True,
            assignment=result,
            output_dir=output_dir,
        )
    except Exception as e:
        return AssignResponse(success=False, error=str(e))


class PhaseOverride(BaseModel):
    phase: str
    strategy_id: str | None = None  # A/B/C/D/E
    material_paths: list[str] | None = None  # replacement material paths


class UpdateAssignRequest(BaseModel):
    assignment_path: str
    overrides: list[PhaseOverride]
    template_path: str
    material_dir: str


@app.post("/assign/update", response_model=AssignResponse)
async def update_assign(req: UpdateAssignRequest):
    """Apply manual overrides to an existing assignment and re-save."""
    if not Path(req.assignment_path).is_file():
        raise HTTPException(status_code=400, detail=f"Assignment not found: {req.assignment_path}")

    try:
        with open(req.assignment_path, "r", encoding="utf-8") as f:
            assignment = json.load(f)

        with open(req.template_path, "r", encoding="utf-8") as f:
            template = json.load(f)

        # Build override map
        override_map = {o.phase: o for o in req.overrides}

        # Apply overrides to each phase
        strategy_names = {"A": "结构重排", "B": "字幕补全", "C": "包装补全", "D": "AIGC 生成", "E": "素材重组"}
        for phase in assignment.get("phases", []):
            phase_name = phase.get("phase", "")
            if phase_name not in override_map:
                continue

            override = override_map[phase_name]

            # Override strategy
            if override.strategy_id and override.strategy_id in strategy_names:
                phase["strategy_id"] = override.strategy_id
                phase["strategy_name"] = strategy_names[override.strategy_id]

                # Re-run strategy to get new completion_actions
                from s3_strategist import STRATEGY_MAP, _assign_materials_to_phase
                gap = {"phase": phase_name, "missing_shot_types": [], "severity": "LOW", "recommended_strategies": [{"id": override.strategy_id, "name": strategy_names[override.strategy_id]}]}
                timeline = template.get("timeline", [])
                phase_data = next((p for p in timeline if p["phase"] == phase_name), {})
                materials = assignment.get("phases", [])

                strategy_fn = STRATEGY_MAP.get(override.strategy_id)
                if strategy_fn:
                    if override.strategy_id == "A":
                        new_phase = strategy_fn(gap, timeline, [])
                    else:
                        new_phase = strategy_fn(gap, template, [])
                    phase["completion_actions"] = [
                        {"action_type": a.action_type, "component": a.component, "params": a.params, "duration_s": a.duration_s}
                        for a in new_phase.completion_actions
                    ]

            # Override materials
            if override.material_paths:
                existing = phase.get("materials", [])
                for i, path in enumerate(override.material_paths):
                    if i < len(existing):
                        existing[i]["path"] = path
                    else:
                        existing.append({"path": path, "type": "image", "role": "manual", "duration_s": 3.0})
                phase["materials"] = existing

        # Update total duration
        assignment["total_duration_s"] = sum(p.get("total_duration_s", 0) for p in assignment.get("phases", []))

        # Save updated assignment
        output_dir = str(Path(req.assignment_path).parent)
        with open(req.assignment_path, "w", encoding="utf-8") as f:
            json.dump(assignment, f, ensure_ascii=False, indent=2)

        return AssignResponse(
            success=True,
            assignment=assignment,
            output_dir=output_dir,
        )
    except Exception as e:
        return AssignResponse(success=False, error=str(e))


@app.get("/")
async def root():
    return {"message": "VST Python FastAPI service"}


# ─── Orchestrator + ControlVector endpoints ──────────────────────────────────


class OrchestrateRequest(BaseModel):
    assignment_path: str = ""
    template_path: str
    material_dir: str = ""
    profile: str = "standard"  # "standard" / "ctr" / "conversion" / "pace" / "premium"
    control_vector: dict | None = None  # 直接传 CV，优先于 profile
    topic: str = ""  # 用户输入的主题/卖点，空则从 template 推断
    verify: bool = True  # 是否启用知识验证（搜索验证 LLM 生成内容的事实准确性）


@app.post("/orchestrate")
async def orchestrate(req: OrchestrateRequest):
    """运行 orchestrator 生成 VideoSpec，支持 ControlVector。

    优先使用 beat-level orchestrator (模板有 beat_sheet 时)，
    否则回退到 phase-level orchestrator。
    """
    import json
    from control_vector import get_profile, ControlVector, apply_edit_ops, EditOp

    if not Path(req.template_path).is_file():
        raise HTTPException(status_code=400, detail=f"Template not found: {req.template_path}")

    try:
        with open(req.template_path) as f:
            template = json.load(f)

        # Determine ControlVector
        if req.control_vector:
            cv = ControlVector.from_dict(req.control_vector)
        else:
            cv = get_profile(req.profile) if req.profile != "standard" else ControlVector()
        cv = cv.clamp()
        cv_dict = cv.to_dict()

        # ── Beat-level path (优先) ──
        if template.get("beat_sheet"):
            from animation_orchestrator import orchestrate_from_beats

            # Apply CV: shot_duration_scale → beat duration adjustment
            beat_sheet = template["beat_sheet"]
            scale = cv.shot_duration_scale
            if abs(scale - 1.0) > 0.05:
                for beat in beat_sheet.get("beats", []):
                    beat["duration_s"] = max(1.5, beat["duration_s"] * scale)

            # Derive topic: user input > template text > template category
            topic = req.topic
            if not topic:
                text_data = template.get("text", {})
                on_screen = text_data.get("on_screen_text", []) if isinstance(text_data, dict) else []
                topic = on_screen[0] if on_screen else template.get("category", "通用")
            result = await orchestrate_from_beats(template, topic=topic, verify=req.verify)

            # QA validation + auto-fix
            from render_validator import validate_and_fix
            result, qa_issues = validate_and_fix(result)

            # Save spec
            output_dir = str(Path(req.template_path).parent)
            spec_path = str(Path(output_dir) / f"video_spec_{req.profile}.json")
            with open(spec_path, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            total = max(s["start"] + s["duration"] for s in result.get("shots", [])) if result.get("shots") else 0
            return {
                "success": True,
                "video_spec": result,
                "spec_path": spec_path,
                "control_vector": cv_dict,
                "profile": req.profile,
                "shot_count": len(result.get("shots", [])),
                "total_frames": total,
                "mode": "beat-level",
                "qa_issues": [{"severity": i.severity, "category": i.category, "message": i.message} for i in qa_issues],
            }

        # ── Phase-level fallback ──
        from animation_orchestrator import orchestrate_animation

        if not Path(req.assignment_path).is_file():
            raise HTTPException(status_code=400, detail=f"Assignment not found: {req.assignment_path}")

        with open(req.assignment_path) as f:
            assignment = json.load(f)

        scripts = {}
        for phase_data in assignment.get("phases", []):
            phase_name = phase_data.get("phase", "")
            strategy = phase_data.get("strategy_id", "")
            if strategy not in ("C", "D", "F"):
                continue

            gap = phase_data.get("gap", {"phase": phase_name, "missing_shot_types": [], "severity": "LOW"})
            kb_atoms = []
            for action in phase_data.get("completion_actions", []):
                if action.get("action_type") == "animation_script":
                    kb_atoms = action.get("params", {}).get("kb_atoms", [])

            try:
                render_input = await orchestrate_animation(
                    phase_name, gap, kb_atoms, phase_data.get("materials", []), template,
                    control_vector=cv_dict,
                )
                scripts[phase_name] = render_input
            except Exception as e:
                print(f"[orchestrate] {phase_name} failed: {e}")
                scripts[phase_name] = {"error": str(e)}

        all_shots = []
        frame_offset = 0
        for phase_name in ["hook", "build", "cta"]:
            if phase_name not in scripts or "error" in scripts[phase_name]:
                continue
            phase_script = scripts[phase_name]
            for shot in phase_script.get("shots", []):
                merged = dict(shot)
                merged["start"] = shot["start"] + frame_offset
                merged["id"] = f"cv_{phase_name}_{len(all_shots)}"
                all_shots.append(merged)
            phase_info = next((p for p in template.get("timeline", []) if p["phase"] == phase_name), {})
            dur_pct = phase_info.get("duration_pct", [0, 1])
            total_dur = template.get("duration_range", [15, 30])
            avg_total = (total_dur[0] + total_dur[1]) / 2
            frame_offset += int((dur_pct[1] - dur_pct[0]) * avg_total * 30)

        full_spec = {
            "fps": 30,
            "globalStyle": {"bgColor": "#050510", "palette": "promo"},
            "shots": all_shots,
        }

        output_dir = str(Path(req.assignment_path).parent)
        spec_path = str(Path(output_dir) / f"video_spec_{req.profile}.json")
        with open(spec_path, "w") as f:
            json.dump(full_spec, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "video_spec": full_spec,
            "spec_path": spec_path,
            "control_vector": cv_dict,
            "profile": req.profile,
            "shot_count": len(all_shots),
            "total_frames": max((s["start"] + s["duration"]) for s in all_shots) if all_shots else 0,
            "mode": "phase-level",
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ─── ControlVector endpoints (Task 10/12/13) ────────────────────────────────


@app.get("/profiles")
async def get_profiles():
    """返回所有可用的内容策略 profile。"""
    from control_vector import PROFILES, get_profile
    return {
        name: cv.to_dict() for name, cv in PROFILES.items()
    }


class ProfileApplyRequest(BaseModel):
    assignment_path: str
    profile: str  # "ctr" / "conversion" / "pace" / "premium"


@app.post("/profiles/apply")
async def apply_profile(req: ProfileApplyRequest):
    """将命名 profile 应用到 assignment，返回 ControlVector。"""
    from control_vector import get_profile
    cv = get_profile(req.profile)
    return {"success": True, "control_vector": cv.to_dict(), "profile": req.profile}


class NLEditRequest(BaseModel):
    assignment_path: str
    instruction: str  # 自然语言指令，如 "开头更抓人一些"


@app.post("/edit/nl")
async def nl_edit(req: NLEditRequest):
    """自然语言编辑 → EditOp → ControlVector delta。

    流程: LLM 解析指令 → EditOp 枚举 → 校验 → 应用到 ControlVector → 回显 diff。
    """
    import os
    from openai import OpenAI
    from control_vector import (
        ControlVector, EditOp, VALID_OPS, apply_edit_ops, get_profile
    )

    api_key = os.environ.get("MIMO_API_KEY", "")
    api_url = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        return {"success": False, "error": "MIMO_API_KEY not set"}

    # Read current assignment to get current CV (or use default)
    import json
    cv = ControlVector()
    try:
        with open(req.assignment_path, "r") as f:
            assignment = json.load(f)
        if "control_vector" in assignment:
            cv = ControlVector.from_dict(assignment["control_vector"])
    except Exception:
        pass

    # LLM: parse instruction into EditOps
    ops_json_schema = """{
      "ops": [
        {"op": "<合法操作>", "amount": 0.0-1.0, "target": "", "value": ""}
      ]
    }"""

    system_prompt = (
        "你是视频编辑助手。把用户的编辑指令解析成 JSON 操作列表。\n\n"
        f"合法操作: {', '.join(sorted(VALID_OPS))}\n"
        "- strengthen_hook: 开头更抓人 (amount: 0-1)\n"
        "- reduce_text: 减少字幕/文字 (amount: 0-1)\n"
        "- increase_pace: 增强节奏感/更快 (amount: 0-1)\n"
        "- reorder_content: 重排内容顺序 (value: 要提前的内容)\n"
        "- change_packaging: 换包装风格 (target: snappy/smooth/premium)\n"
        "- adjust_ending: 调整结尾 (amount: 正=更强, 负=更弱)\n"
        "- slow_down: 慢下来 (amount: 0-1)\n"
        "- add_transition: 加转场 (amount: 0-1)\n"
        "- simplify: 简洁一些 (amount: 0-1)\n\n"
        "输出格式:\n"
        f"{ops_json_schema}\n\n"
        "只输出 JSON，不要其他文字。每个操作的 amount 在 0-1 之间。"
    )

    try:
        client = OpenAI(api_key=api_key, base_url=api_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.instruction},
            ],
            max_completion_tokens=500,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)

        ops = []
        skipped = []
        for item in parsed.get("ops", []):
            op_name = item.get("op", "")
            if op_name in VALID_OPS:
                ops.append(EditOp(
                    op=op_name,
                    amount=float(item.get("amount", 0.5)),
                    target=str(item.get("target", "")),
                    value=str(item.get("value", "")),
                ))
            else:
                skipped.append(op_name)

        if not ops:
            return {
                "success": False,
                "error": f"无法理解指令中的操作: {', '.join(skipped) if skipped else '无有效操作'}",
                "raw": raw,
                "hint": f"合法操作: {', '.join(sorted(VALID_OPS))}",
            }

        # Apply ops to CV
        new_cv = apply_edit_ops(cv, ops)

        # Build human-readable diff
        diff_lines = []
        if new_cv.shot_duration_scale != cv.shot_duration_scale:
            diff_lines.append(f"镜头时长: {cv.shot_duration_scale:.1f}x → {new_cv.shot_duration_scale:.1f}x")
        if new_cv.text_density != cv.text_density:
            diff_lines.append(f"文字密度: {cv.text_density:.0%} → {new_cv.text_density:.0%}")
        if new_cv.transition_density != cv.transition_density:
            diff_lines.append(f"转场密度: {cv.transition_density:.0%} → {new_cv.transition_density:.0%}")
        if new_cv.cta_emphasis != cv.cta_emphasis:
            diff_lines.append(f"CTA强度: {cv.cta_emphasis:.0%} → {new_cv.cta_emphasis:.0%}")
        if new_cv.easing_profile != cv.easing_profile:
            diff_lines.append(f"缓动风格: {cv.easing_profile} → {new_cv.easing_profile}")
        if new_cv.phase_weights != cv.phase_weights:
            diff_lines.append(f"Phase权重: {cv.phase_weights} → {new_cv.phase_weights}")

        result = {
            "success": True,
            "ops": [o.to_dict() for o in ops],
            "control_vector": new_cv.to_dict(),
            "diff": diff_lines,
            "instruction": req.instruction,
        }
        if skipped:
            result["warnings"] = [f"无法理解: '{s}'，已跳过" for s in skipped]
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── NL Scene Editor ────────────────────────────────────────────────────────


class SceneEditRequest(BaseModel):
    spec_path: str      # VideoSpec JSON 文件路径
    instruction: str    # 自然语言指令


@app.post("/edit/scene")
async def scene_edit(req: SceneEditRequest):
    """自然语言编辑 VideoSpec 的具体场景/组件。

    与 /edit/nl 的区别:
    - /edit/nl → ControlVector 全局参数 (节奏/密度/风格)
    - /edit/scene → VideoSpec shot 级别 (组件/文字/时长/位置)

    流程: LLM 解析指令 → SceneEditOp[] → 校验 → 应用 → 返回 diff + 新 spec 路径。
    """
    from scene_editor import edit_scene
    result = await edit_scene(req.spec_path, req.instruction)
    return result


# ─── Scene Decomposition endpoint ──────────────────────────────────────────


class DecomposeRequest(BaseModel):
    video_path: str


@app.post("/decompose")
async def decompose(req: DecomposeRequest):
    """场景级视频分解: 参考视频 → 多场景 + beat_sheet。

    流程:
    1. PySceneDetect shot 检测 → shot = scene
    2. 逐场景窗口化提取 (SAM2 + EasyOCR + VLM)
    3. 元素融合去重 (SAM2 ∪ OCR)
    4. beat_sheet 自动抽取
    """
    if not Path(req.video_path).is_file():
        raise HTTPException(status_code=400, detail=f"Video not found: {req.video_path}")

    try:
        from scene_decomposer import decompose_video, decomposition_to_dict

        job_id = uuid.uuid4().hex[:8]
        output_dir = str(OUTPUT_BASE / job_id)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        decomp = decompose_video(req.video_path)
        d = decomposition_to_dict(decomp)

        json_path = str(Path(output_dir) / "decomposition.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "decomposition": d,
            "json_path": json_path,
            "scene_count": len(decomp.scenes),
            "element_count": sum(len(s.elements) for s in decomp.scenes),
            "beat_count": len(decomp.beat_structure.beats) if decomp.beat_structure else 0,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ─── Style Migration endpoint ──────────────────────────────────────────────


class StyleMigrateRequest(BaseModel):
    video_path: str
    topic: str
    allow_reference_pixels: bool = False


def _style_migrate_blocking(video_path: str, topic: str, allow_reference_pixels: bool = False) -> dict:
    """同步阻塞版本的风格迁移，供 run_in_executor 调用。"""
    import time as _time
    import shutil
    from scene_decomposer import (
        decompose_video, decomposition_to_dict, decomposition_from_dict,
        decomposition_to_orchestrator_template, generate_motion_paths_for_decomp,
        _clamp_to_safe_zone,
    )
    from scene_description import extract_style_profile
    from render_validator import validate_and_fix_decomposition

    job_id = uuid.uuid4().hex[:8]
    output_dir = OUTPUT_BASE / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    t_start = _time.time()

    print(f"[style_migrate] job={job_id} 开始分解...", flush=True)

    # 1. 分解
    decomp = decompose_video(video_path, output_dir=str(output_dir))
    d = decomposition_to_dict(decomp)
    print(f"[style_migrate] 分解完成: {len(d.get('scenes', []))} 场景 ({_time.time()-t_start:.0f}s)", flush=True)

    # 2. 槽位化 — 在任何内容写入前把图片槽位定好、OCR 文字全部清空
    _slotify_scenes(d, allow_reference_pixels=allow_reference_pixels)
    print(f"[style_migrate] 槽位化完成 ({_time.time()-t_start:.0f}s)", flush=True)

    # 3. 提取场景参考帧（只用作 Gemini 风格条件输入，绝不写 content_src）
    ref_frames = _extract_scene_ref_frames(video_path, d, str(output_dir))
    print(f"[style_migrate] 参考帧提取完成: {len(ref_frames)} 帧 ({_time.time()-t_start:.0f}s)", flush=True)

    # 4. StyleProfile
    style_profile = extract_style_profile(video_path)
    print(f"[style_migrate] 风格: {style_profile.style_family} ({_time.time()-t_start:.0f}s)", flush=True)

    # 4.5 用 style_profile.palette 刷新槽位占位 fill 渐变（比初始填色更精准）
    if hasattr(style_profile, "palette") and style_profile.palette:
        palette = style_profile.palette
        bg_color = palette[0] if palette else "#1a1a2e"
        accent_color = palette[1] if len(palette) > 1 else "#4b78c7"
        for sc in d["scenes"]:
            for el in sc.get("elements", []):
                if el.get("type") == "image" and not el.get("content_src"):
                    el.setdefault("appearance", {})["fill"] = (
                        f"linear-gradient(135deg, {bg_color} 0%, {accent_color} 100%)"
                    )

    # 5. VLM 运动分析
    scene_motions = _vlm_analyze_motion(video_path, d["scenes"])
    print(f"[style_migrate] 运动分析完成 ({_time.time()-t_start:.0f}s)", flush=True)

    # 6. LLM 内容计划（文案 + 生图 prompt 前置，与 StyleProfile 对齐）
    plan = _llm_content_plan(topic, d) or _fallback_content_plan(topic, d)
    print(f"[style_migrate] 内容计划完成: {len(plan)} 场景 ({_time.time()-t_start:.0f}s)", flush=True)

    # 7. Gemini 图片生成（按计划 prompt + 图像条件 + 图库复用）
    scene_images = _generate_scene_images(
        topic, d["scenes"], str(output_dir), style_profile, plan, ref_frames, aspect_ratio="16:9"
    )
    print(f"[style_migrate] 图片生成完成 ({_time.time()-t_start:.0f}s)", flush=True)

    # 替换图片路径 — 成功填生成图，失败留空 content_src（appearance.fill 已设占位渐变）
    for i, sc in enumerate(d["scenes"]):
        imgs = scene_images.get(i, [])
        img_slot_idx = 0
        for el in sc["elements"]:
            if el.get("type") != "image":
                continue
            if img_slot_idx < len(imgs):
                el["content_src"] = f"data/output/{job_id}/generated/{imgs[img_slot_idx]}"
                img_slot_idx += 1
            else:
                # 失败兜底：保持空 src（appearance.fill 占位渐变已设置）
                # allow_reference_pixels=True 时保留裁剪图旧行为
                if allow_reference_pixels:
                    orig = el.get("content_src", "")
                    if orig and os.path.isabs(orig):
                        fname = os.path.basename(orig)
                        el["content_src"] = f"data/output/{job_id}/{fname}"
                else:
                    el["content_src"] = ""

    # 8. 逐场景文案注入（文案已由 plan 规划，与图片同步）
    _inject_texts_per_scene(d, [p["text"] for p in plan])

    # 9. 注入动效（文字已注入，llm_texts={} 保证文字分支不被覆盖）
    _inject_text_and_effects(d, {}, scene_motions)

    # 10. motion_path 关键帧
    generate_motion_paths_for_decomp(d, scene_motions, fps=d.get("fps", 30))

    # 11. safe-zone clamp（保留）
    for sc in d["scenes"]:
        for el in sc.get("elements", []):
            sp = el.get("spatial", {})
            x = sp.get("x", 50)
            y = sp.get("y", 50)
            w = sp.get("width", 30)
            h = sp.get("height", 30)
            x, y = _clamp_to_safe_zone(x, y, w, h)
            sp["x"] = x
            sp["y"] = y

    # 12. QA 校验 + 自动修复
    d, qa_issues = validate_and_fix_decomposition(d)
    if qa_issues:
        print(f"[style_migrate] QA 发现 {len(qa_issues)} 个问题（已自动修复）", flush=True)

    # 13. 重算场景边界
    frame = 0
    for sc in d["scenes"]:
        sc["start_frame"] = frame
        sc["end_frame"] = frame + sc["duration_frames"]
        frame += sc["duration_frames"]
    d["total_frames"] = frame

    # C5: 转场接线
    VALID_TRANSITIONS = {"cut", "fade", "slide"}
    scenes_list = d["scenes"]
    for si, sc in enumerate(scenes_list):
        if si < len(scenes_list) - 1:
            next_sc = scenes_list[si + 1]
            ent = next_sc.get("entrance_transition", {})
            t_type = ent.get("type", "fade")
            if t_type not in VALID_TRANSITIONS:
                t_type = "fade"
            t_dir = ent.get("direction", "")
            sc["transition_out"] = {"type": t_type, "direction": t_dir}
        else:
            sc["transition_out"] = {"type": "fade", "direction": ""}

    # C6: BGM
    BGM_MAP = {
        "dark_neon_ui": "bgm_dark.m4a",
        "dark_cinematic": "bgm_dark.m4a",
        "retro_film": "bgm_dark.m4a",
        "bright_airy": "bgm_bright.m4a",
        "vibrant_social": "bgm_bright.m4a",
    }
    bgm_file = BGM_MAP.get(style_profile.style_family, "bgm_neutral.m4a")
    d["bgm"] = {"src": f"bgm/{bgm_file}", "volume": 0.22}

    # 保存 StyleProfile
    d["style_profile"] = style_profile.to_dict()

    # 保存 decomposition JSON
    decomp_path = str(output_dir / "decomposition.json")
    with open(decomp_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    # 复制图片到 web/public — generated png 始终复制；裁剪 jpg 仅 allow_reference_pixels=True 时复制
    public_out_dir = PROJECT_ROOT / "web" / "public" / "data" / "output" / job_id
    public_gen_dir = public_out_dir / "generated"
    public_gen_dir.mkdir(parents=True, exist_ok=True)
    gen_dir = output_dir / "generated"
    if gen_dir.exists():
        for img in gen_dir.glob("*.png"):
            shutil.copy2(img, public_gen_dir / img.name)
    if allow_reference_pixels:
        for img in output_dir.glob("*.jpg"):
            shutil.copy2(img, public_out_dir / img.name)

    return {
        "success": True,
        "decomposition": d,
        "decomp_path": decomp_path,
        "job_id": job_id,
        "style_family": style_profile.style_family,
        "scene_count": len(decomp.scenes),
        "element_count": sum(len(s.elements) for s in decomp.scenes),
    }


@app.post("/style_migrate")
async def style_migrate(req: StyleMigrateRequest):
    """风格迁移: 参考视频 + 新主题 → 带风格的 decomposition JSON。

    流程:
    1. 分解参考视频 (SAM2 + OCR + VLM)
    2. 提取 StyleProfile (CV + VLM)
    3. VLM 运动分析
    4. Gemini 生成主题图片（注入风格）
    5. LLM 编排文字
    6. 注入文字 + 动效 + 风格
    返回完整 decomposition JSON 供 MultiSceneVideo 渲染。
    """
    if not Path(req.video_path).is_file():
        raise HTTPException(status_code=400, detail=f"Video not found: {req.video_path}")

    try:
        import asyncio
        loop = asyncio.get_event_loop()

        # 在线程池中运行阻塞工作（内容计划 + 生图 + 文案注入已在 blocking 内完成）
        import functools
        result = await loop.run_in_executor(
            None,
            functools.partial(
                _style_migrate_blocking,
                req.video_path,
                req.topic,
                req.allow_reference_pixels,
            ),
        )

        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ─── Slot table: layout_type → number of image slots ─────────────────────────

_SLOT_TABLE: dict[str, int] = {
    "full_bleed": 1,
    "centered": 3,
    "split": 2,
    "grid": 4,
    "radial": 5,
    "stack": 3,
}


def _slotify_scenes(d: dict, allow_reference_pixels: bool = False) -> None:
    """将每个场景的元素裁剪为槽位数，并清空所有文字内容。

    图片：按视觉重要性保留 top-N（N 由 layout_type 查 _SLOT_TABLE），
          依序标注 slot_role="hero"(第1个) / "satellite"(其余)。
    文字：只保留第 1 个元素，content_text 立即清空 ""（OCR 使命已完成）。
    allow_reference_pixels=False（默认）：所有图片 content_src 清空，
          同时设置 appearance.fill 渐变占位（style_profile 刷新前的临时颜色）。
    """

    _DEFAULT_BG = "#1a1a2e"
    _DEFAULT_ACCENT = "#4b78c7"

    for sc in d.get("scenes", []):
        layout = sc.get("layout_type", "centered")
        n_slots = _SLOT_TABLE.get(layout, 3)

        elements = sc.get("elements", [])

        # — 图片元素：按重要性排序取 top-N，保留原相对顺序 ——————————————————————
        img_elements = [el for el in elements if el.get("type") == "image"]
        other_elements = [el for el in elements if el.get("type") != "image"]

        def _img_score(el: dict) -> float:
            sp = el.get("spatial", {})
            x = sp.get("x", 50.0)
            y = sp.get("y", 50.0)
            w = sp.get("width", 30.0)
            h = sp.get("height", 30.0)
            return (w * h) * (1.0 - min(1.0, math.hypot(x - 50, y - 50) / 70.0))

        if len(img_elements) > n_slots:
            # 确定保留的 indices（在原 img_elements 列表中）
            ranked = sorted(range(len(img_elements)), key=lambda i: _img_score(img_elements[i]), reverse=True)
            keep_set = set(ranked[:n_slots])
            # 保持原相对顺序
            img_elements = [el for i, el in enumerate(img_elements) if i in keep_set]

        # 标注 slot_role + 清空 src（如需）
        for slot_i, el in enumerate(img_elements):
            el["slot_role"] = "hero" if slot_i == 0 else "satellite"
            if not allow_reference_pixels:
                el["content_src"] = ""
                el.setdefault("appearance", {})["fill"] = (
                    f"linear-gradient(135deg, {_DEFAULT_BG} 0%, {_DEFAULT_ACCENT} 100%)"
                )

        # — 文字元素：只保留第 1 个，清空 content_text ————————————————————————
        text_elements = [el for el in other_elements if el.get("type") == "text"]
        non_text_non_img = [el for el in other_elements if el.get("type") != "text"]

        kept_texts: list[dict] = []
        for i, el in enumerate(text_elements):
            el["content_text"] = ""  # OCR 使命已完成，清空
            if i == 0:
                kept_texts.append(el)
            # i > 0：丢弃（多余文字槽位删除）

        # 重组 elements：图片 + 保留文字 + 其他（保持图片在前）
        sc["elements"] = img_elements + kept_texts + non_text_non_img


def _extract_scene_ref_frames(
    video_path: str, d: dict, output_dir: str
) -> dict:
    """为每个场景取中点帧，缩放到宽 640，存为 ref/s{i}_ref.jpg。

    返回 {scene_idx: 绝对路径}。
    这些图像**只作为 Gemini 的风格参考条件输入，绝不写进任何 content_src**。
    """
    import cv2  # noqa: PLC0415

    ref_dir = Path(output_dir) / "ref"
    ref_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    result: dict = {}
    for i, sc in enumerate(d.get("scenes", [])):
        start_f = sc.get("start_frame", 0)
        end_f = sc.get("end_frame", total_frames)
        mid_f = start_f + (end_f - start_f) // 2

        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_f)
        ret, frame = cap.read()
        if not ret:
            continue

        # 缩到宽 640，保持宽高比
        h_orig, w_orig = frame.shape[:2]
        scale = 640.0 / w_orig if w_orig > 0 else 1.0
        new_w = 640
        new_h = max(1, int(h_orig * scale))
        frame_small = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

        out_path = str(ref_dir / f"s{i}_ref.jpg")
        cv2.imwrite(out_path, frame_small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        result[i] = os.path.abspath(out_path)

    cap.release()
    return result


def _llm_content_plan(topic: str, d: dict) -> list[dict] | None:
    """LLM 内容规划：逐场景生成主文案 + 生图 prompt。

    输入：场景骨架摘要（序号/phase/时长/layout_type/图片槽位数），不含任何 OCR 文字。
    输出：[{"text": "中文屏幕主文案≤12字", "image_prompt": "英文生图prompt"}] × 场景数。
    失败返回 None，调用方用 _fallback_content_plan 兜底。
    """
    import httpx  # noqa: PLC0415

    api_key = os.environ.get("MIMO_API_KEY", "")
    api_url = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        return None

    scenes = d.get("scenes", [])
    n = len(scenes)
    if n == 0:
        return None

    # 构建场景骨架摘要（绝不包含 OCR 内容）
    scene_summaries = []
    for i, sc in enumerate(scenes):
        if i == 0 or i <= n * 0.25:
            phase = "hook"
        elif i >= n * 0.75:
            phase = "cta"
        else:
            phase = "build"
        layout = sc.get("layout_type", "centered")
        n_slots = _SLOT_TABLE.get(layout, 3)
        dur_s = round(sc.get("duration_frames", 90) / max(1, d.get("fps", 30)), 1)
        scene_summaries.append(
            f"场景{i}(phase={phase},时长={dur_s}s,layout={layout},图片槽位={n_slots})"
        )

    system_prompt = (
        "你是短视频文案专家。根据主题和场景结构，为每个场景生成屏幕文案和生图指令。\n"
        "要求：\n"
        "- text：中文主文案，≤12字，与 topic 强相关，各场景不重复；hook 场景要抓人；cta 场景有号召力\n"
        "- image_prompt：英文生图 prompt，具体名词，与 text 呼应，不含任何参考视频信息\n"
        "输出格式（JSON object）：\n"
        '{"scenes": [{"text": "...", "image_prompt": "..."}, ...]}\n'
        "长度必须与输入场景数完全一致。只输出 JSON，不要其他文字。"
    )
    user_msg = f"主题: {topic}\n\n场景结构:\n" + "\n".join(scene_summaries)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 2000,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(2):
        try:
            resp = httpx.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw)
            scenes_out = parsed.get("scenes", [])
            if len(scenes_out) != n:
                print(
                    f"[_llm_content_plan] 长度不符: 期望 {n} 场景, 得到 {len(scenes_out)}",
                    flush=True,
                )
                return None
            # 校验每条都有必要字段
            result: list[dict] = []
            for item in scenes_out:
                text = str(item.get("text", "")).strip()
                image_prompt = str(item.get("image_prompt", "")).strip()
                if not text or not image_prompt:
                    return None
                result.append({"text": text[:12], "image_prompt": image_prompt})
            return result
        except Exception as exc:
            print(f"[_llm_content_plan] attempt {attempt+1} failed: {exc}", flush=True)
            if attempt == 0:
                import time as _t
                _t.sleep(2)

    return None


def _fallback_content_plan(topic: str, d: dict) -> list[dict]:
    """内容计划兜底函数 — 不依赖任何外部 API，不含参考视频文字。

    所有文案纯粹基于 topic 生成。
    """
    scenes = d.get("scenes", [])
    n = len(scenes)

    BUILD_TEXTS = ["走近{t}", "发现{t}", "{t}印象", "感受{t}", "探索{t}", "品味{t}"]
    HOOK_TEMPLATES = [
        "wide cinematic opening shot, dramatic sky, golden hour, 4K",
        "iconic establishing shot, strong silhouette, warm tones",
        "vibrant scene, wide angle, sense of scale, dusk lighting",
    ]
    BUILD_TEMPLATES = [
        "detail shot, natural light, shallow depth of field, lifestyle",
        "process shot, warm ambient light, authentic feel",
        "environmental portrait, candid moment, outdoor setting",
        "architectural detail, geometric pattern, clean lines",
    ]
    CTA_TEMPLATES = [
        "sweeping panorama, dramatic clouds, high vantage point",
        "night scene, warm lights, long exposure, reflective surfaces",
        "final wide shot, golden hour, sense of scale, cinematic",
    ]

    result: list[dict] = []
    build_idx = 0
    for i, sc in enumerate(scenes):
        if i == 0 or i <= n * 0.25:
            phase = "hook"
        elif i >= n * 0.75:
            phase = "cta"
        else:
            phase = "build"

        t_short = topic[:10]  # guard against very long topics

        if phase == "hook":
            text = t_short
            img_tmpl = HOOK_TEMPLATES[i % len(HOOK_TEMPLATES)]
        elif phase == "cta":
            raw = f"{t_short},等你来"
            text = raw[:12]
            img_tmpl = CTA_TEMPLATES[i % len(CTA_TEMPLATES)]
        else:
            raw = BUILD_TEXTS[build_idx % len(BUILD_TEXTS)].format(t=t_short)
            text = raw[:12]
            img_tmpl = BUILD_TEMPLATES[build_idx % len(BUILD_TEMPLATES)]
            build_idx += 1

        image_prompt = f"{topic}, {img_tmpl}"
        result.append({"text": text, "image_prompt": image_prompt})

    return result


def _vlm_analyze_motion(video_path: str, scenes: list[dict]) -> list[dict]:
    """VLM 运动分析（简化版，供 style_migrate 使用）。"""
    import cv2, base64
    from scene_description import _vlm_call

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    MOTION_MAP = {
        "平移": {"type": "slide", "idle": "float"},
        "旋转": {"type": "3d", "idle": "rotate"},
        "缩放": {"type": "scale", "idle": "breathe"},
        "淡入淡出": {"type": "fade", "idle": "float"},
        "弹性": {"type": "scale", "idle": "elastic_pop"},
        "级联": {"type": "slide", "idle": "float"},
        "飘浮": {"type": "fade", "idle": "float"},
    }

    results = []
    # 只对部分场景做 VLM 运动分析（避免 13 个场景 × 75s 超时 = 16 分钟）
    sample_indices = set(range(0, len(scenes), max(1, len(scenes) // 6)))  # 最多 6 个
    for si, sc in enumerate(scenes):
        start_f = sc.get("start_frame", 0)
        end_f = sc.get("end_frame", total)
        mid_f = start_f + int((end_f - start_f) * 0.3)
        gap = max(2, int(fps * 0.15))

        frames_b64 = []
        for pos in [mid_f, min(mid_f + gap, end_f - 1)]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if ret:
                _, buf = cv2.imencode('.jpg', frame)
                frames_b64.append(base64.b64encode(buf).decode())

        motion_desc = ""
        if si in sample_indices and len(frames_b64) == 2:
            motion_desc = _vlm_call(
                frames_b64,
                "分析两帧运动：平移/旋转/缩放/淡入淡出/弹性/级联/飘浮，用/分隔，30字以内。"
            ) or ""

        matched = []
        for kw, params in MOTION_MAP.items():
            if kw in motion_desc:
                matched.append(params)
        if not matched:
            matched = [{"type": "fade", "idle": "float"}]

        results.append({"desc": motion_desc, "effects": matched})

    cap.release()
    return results


def _generate_scene_images(
    topic: str,
    scenes: list,
    output_dir: str,
    style_profile,
    plan: list[dict],
    ref_frames: dict,
    aspect_ratio: str = "16:9",
) -> dict:
    """Gemini 图片生成（按计划 prompt + 图像条件 + 图库复用）。

    每场景只真实生成 hero 1 张（+ satellite 如槽位≥2 则再生 1 张 alternate）。
    全局图库复用：第 3 个及以后的 satellite 槽位从已生成图轮转，不再调用 API。
    失败兜底链：同场景其他生成图 → 全局图库 → 留空（不回填参考裁剪图）。
    并发=3 保留。
    """
    from gemini_imager import generate_image  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: PLC0415

    n = len(scenes)
    img_dir = Path(output_dir) / "generated"
    img_dir.mkdir(parents=True, exist_ok=True)

    # 构建实际生成任务：hero + 可能的 alternate（每场景最多 2 次 API 调用）
    # task = (scene_idx, slot_label, fname, prompt, ref_path)
    tasks: list[tuple[int, str, str, str, str]] = []

    for i, sc in enumerate(scenes):
        layout = sc.get("layout_type", "centered")
        n_slots = _SLOT_TABLE.get(layout, 3)
        base_prompt = plan[i]["image_prompt"] if i < len(plan) else f"{topic}, cinematic scene"
        ref_path = ref_frames.get(i, "")

        # hero — 1 张主图
        hero_fname = f"s{i}_hero.png"
        hero_fpath = str(img_dir / hero_fname)
        if not Path(hero_fpath).exists():
            tasks.append((i, "hero", hero_fname, base_prompt, ref_path))
        else:
            tasks.append((i, "hero", hero_fname, "", ref_path))  # 已存在，跳过生成

        # alternate — 若槽位≥2，再生 1 张
        if n_slots >= 2:
            alt_fname = f"s{i}_alt.png"
            alt_fpath = str(img_dir / alt_fname)
            alt_prompt = base_prompt + ", alternate angle, detail shot"
            if not Path(alt_fpath).exists():
                tasks.append((i, "alt", alt_fname, alt_prompt, ref_path))
            else:
                tasks.append((i, "alt", alt_fname, "", ref_path))

    # 分组：需要生成 vs 已存在
    to_generate = [(si, sl, fn, pr, rp) for si, sl, fn, pr, rp in tasks if pr]
    already_done = [(si, sl, fn) for si, sl, fn, pr, rp in tasks if not pr]

    # scene_images: {scene_idx: [fname, ...]} — 成功生成/已存在的文件名列表
    scene_images: dict[int, list[str]] = {}
    for si, sl, fn in already_done:
        scene_images.setdefault(si, []).append(fn)

    # 全局图库（用于 satellite 复用）
    global_library: list[str] = []

    def _gen_one(args: tuple[int, str, str, str, str]):
        si, slot_label, fname, prompt, ref_path = args
        fpath = str(img_dir / fname)
        res = generate_image(
            prompt, fpath,
            width=1280, height=720,
            style_profile=style_profile,
            aspect_ratio=aspect_ratio,
            reference_image_path=ref_path,
        )
        return si, slot_label, fname, bool(res)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_gen_one, t): t for t in to_generate}
        for fut in as_completed(futures):
            si, slot_label, fname, ok = fut.result()
            if ok:
                scene_images.setdefault(si, []).append(fname)
                global_library.append(fname)

    # 补充全局图库（已存在的图也算）
    for si, imgs in scene_images.items():
        for fn in imgs:
            if fn not in global_library:
                global_library.append(fn)

    # 为每个场景按槽位数填满图片列表
    # satellite 第 3+ 张从全局图库轮转，不重复使用本场景已有图
    gl_cycle_idx = 0
    final_images: dict[int, list[str]] = {}
    for i, sc in enumerate(scenes):
        layout = sc.get("layout_type", "centered")
        n_slots = _SLOT_TABLE.get(layout, 3)
        got = list(scene_images.get(i, []))
        filled: list[str] = list(got)  # hero + alt（如果生成成功）

        # 补 satellite 槽（第 3+ 个，从全局图库轮转）
        for _ in range(len(filled), n_slots):
            # 找一张本场景尚未使用的全局图
            picked = ""
            tried = 0
            total_gl = len(global_library)
            while tried < total_gl:
                candidate = global_library[gl_cycle_idx % max(1, total_gl)]
                gl_cycle_idx += 1
                tried += 1
                if candidate not in filled:
                    picked = candidate
                    break
            filled.append(picked)  # picked="" 表示留空（渲染端画占位块）

        final_images[i] = filled

    return final_images


def _inject_texts_per_scene(d: dict, texts: list[str]) -> None:
    """C7: 逐场景文案注入 — 第 i 个场景的第一个 text 元素分配 texts[i]。

    - 超 16 字截断
    - 该场景其余 text 元素 content_text 置 ""
    - font_size 自适应、最短显示帧数、text_animation 复用旧逻辑
    """
    for sc_idx, sc in enumerate(d["scenes"]):
        scene_text = texts[sc_idx] if sc_idx < len(texts) else ""
        if scene_text and len(scene_text) > 16:
            scene_text = scene_text[:16]
        first_text = True
        for el in sc["elements"]:
            if el.get("type") != "text":
                continue
            if first_text and scene_text:
                new_text = scene_text
                el["content_text"] = new_text
                typo = el.get("typography", {})
                n = len(new_text)
                typo["font_size"] = 6 if n <= 4 else (4.5 if n <= 8 else 3.5)
                el["typography"] = typo
                timing = el.get("timing", {})
                min_frames = max(15, len(new_text) * 3)
                if timing.get("out_point", 0) - timing.get("in_point", 0) < min_frames:
                    timing["out_point"] = timing.get("in_point", 0) + min_frames
                el["timing"] = timing
                if len(new_text) <= 10:
                    entrance, split = "typewriter", "char"
                else:
                    entrance, split = "blur_in", "word"
                el["text_animation"] = {
                    "entrance": entrance, "exit": "fade_up",
                    "split_mode": split, "direction": "center", "zone": "focus",
                }
                first_text = False
            else:
                # 该场景其余 text 元素清空（不让旧内容残留）
                el["content_text"] = ""


def _inject_text_and_effects(d, llm_texts, scene_motions):
    """注入 LLM 文字 + VLM 动效 + 文字动画。"""
    ROLE_TO_PHASE = {"unknown": "build", "hook": "hook", "feature": "build", "cta": "cta"}
    IDLE_POOL = ["float", "breathe", "rotate", "elastic_pop", "2_5d_push"]

    phase_idx = {"hook": 0, "build": 0, "cta": 0}
    for sc_idx, sc in enumerate(d["scenes"]):
        phase = ROLE_TO_PHASE.get(sc.get("scene_role", "unknown"), "build")
        texts = llm_texts.get(phase, [])
        idx = phase_idx.get(phase, 0)
        motion = scene_motions[sc_idx] if sc_idx < len(scene_motions) else {}

        for el_idx, el in enumerate(sc["elements"]):
            if el.get("type") == "text" and texts:
                if idx >= len(texts):
                    el["content_text"] = ""
                    continue
                new_text = texts[idx]
                if len(new_text) > 14:
                    new_text = new_text[:14]
                el["content_text"] = new_text
                typo = el.get("typography", {})
                n = len(new_text)
                typo["font_size"] = 6 if n <= 4 else (4.5 if n <= 8 else 3.5)
                el["typography"] = typo
                timing = el.get("timing", {})
                min_frames = max(15, len(new_text) * 3)
                if timing.get("out_point", 0) - timing.get("in_point", 0) < min_frames:
                    timing["out_point"] = timing.get("in_point", 0) + min_frames
                el["timing"] = timing
                # 文字动画：typewriter/blur_in（匹配原视频风格）
                if len(new_text) <= 10:
                    entrance, split = "typewriter", "char"
                else:
                    entrance, split = "blur_in", "word"
                el["text_animation"] = {
                    "entrance": entrance, "exit": "fade_up",
                    "split_mode": split, "direction": "center", "zone": "focus",
                }
                idx += 1
                phase_idx[phase] = idx

            if el.get("type") == "image":
                # C8: 同一场景所有图片用同一 idle（按 sc_idx 确定），收敛动效池
                IDLE_POOL_IMG = ["float", "breathe"]
                el["effect_type"] = IDLE_POOL_IMG[sc_idx % len(IDLE_POOL_IMG)]
                timing = el.get("timing", {})
                if not timing.get("entrance"):
                    # 同一场景统一一种入场（按 sc_idx 选），direction 统一 "bottom"
                    entrance_types = ["scale", "slide", "fade"]
                    timing["entrance"] = {
                        "type": entrance_types[sc_idx % len(entrance_types)],
                        "direction": "bottom",
                        "duration": 6,
                    }
                if not timing.get("exit"):
                    timing["exit"] = {"type": "fade", "duration": 3}


# ─── Knowledge Base endpoints ───────────────────────────────────────────────


class KBRecommendRequest(BaseModel):
    shot_types: list[str]
    phase: str


class KBRecommendResponse(BaseModel):
    success: bool
    atoms: list[dict] = []
    error: str = ""


@app.post("/kb/recommend", response_model=KBRecommendResponse)
async def kb_recommend(req: KBRecommendRequest):
    """Query knowledge base for atoms that fill the given shot types."""
    try:
        from kb.graph_backend import GraphBackend
        from kb.template_store import TemplateStore

        db_path = str(Path(__file__).parent.parent.parent / "data" / "graph.db")
        if not Path(db_path).exists():
            return KBRecommendResponse(success=True, atoms=[], error="KB not initialized")

        gb = GraphBackend(f"file://{db_path}")
        await gb.connect()
        store = TemplateStore(gb)

        all_atoms = []
        for shot_type in req.shot_types:
            results = await store.find_atoms_for_gap(shot_type, req.phase, top_k=3)
            for r in results:
                atom_id = str(r.get("id", ""))
                if ":" in atom_id:
                    atom_id = atom_id.split(":")[-1]
                all_atoms.append({
                    "atom_id": atom_id,
                    "description": r.get("description", ""),
                    "remotion_component": r.get("remotion_component", ""),
                    "fills_shot_types": r.get("fills_shot_types", []),
                    "visual_impact_score": r.get("visual_impact_score", 0),
                    "distance": round(r.get("dist", 0), 4),
                    "matched_type": shot_type,
                })

        await gb.close()
        return KBRecommendResponse(success=True, atoms=all_atoms)
    except Exception as e:
        return KBRecommendResponse(success=False, error=str(e))


class KBSubgraphResponse(BaseModel):
    success: bool
    nodes: list[dict] = []
    edges: list[dict] = []
    pattern: dict = {}
    error: str = ""


@app.get("/kb/subgraph/{pattern_id}", response_model=KBSubgraphResponse)
async def kb_subgraph(pattern_id: str):
    """Get full subgraph for a pattern: pattern → modules → atoms."""
    try:
        from kb.graph_backend import GraphBackend
        from kb.template_store import TemplateStore

        db_path = str(Path(__file__).parent.parent.parent / "data" / "graph.db")
        if not Path(db_path).exists():
            return KBSubgraphResponse(success=False, error="KB not initialized")

        gb = GraphBackend(f"file://{db_path}")
        await gb.connect()
        store = TemplateStore(gb)

        full = await store.get_pattern_full(pattern_id)
        if not full:
            await gb.close()
            return KBSubgraphResponse(success=False, error=f"Pattern {pattern_id} not found")

        nodes = []
        edges = []

        # Pattern node
        pid = str(full.get("id", pattern_id))
        if ":" in pid:
            pid = pid.split(":")[-1]
        nodes.append({
            "id": f"pattern:{pid}",
            "type": "pattern",
            "label": full.get("category", pid),
            "description": full.get("description", ""),
            "category": full.get("category", ""),
            "hook_type": full.get("hook_type", ""),
            "build_pattern": full.get("build_pattern", ""),
            "cta_type": full.get("cta_type", ""),
            "appearance_count": full.get("appearance_count", 1),
        })

        for mod in full.get("modules", []):
            mid = str(mod.get("id", ""))
            if ":" in mid:
                mid = mid.split(":")[-1]
            nodes.append({
                "id": f"module:{mid}",
                "type": "module",
                "label": mod.get("narrative_pattern", mid),
                "description": mod.get("description", ""),
                "phase": mod.get("phase", ""),
                "narrative_pattern": mod.get("narrative_pattern", ""),
                "duration_min_s": mod.get("duration_min_s", 0),
                "duration_max_s": mod.get("duration_max_s", 0),
                "appearance_count": mod.get("appearance_count", 1),
            })
            edges.append({
                "source": f"pattern:{pid}",
                "target": f"module:{mid}",
                "type": "composed_of",
                "position": mod.get("_position", 0),
            })

            for atom in mod.get("atoms", []):
                aid = str(atom.get("id", ""))
                if ":" in aid:
                    aid = aid.split(":")[-1]
                nodes.append({
                    "id": f"atom:{aid}",
                    "type": "atom",
                    "label": atom.get("remotion_component", aid),
                    "description": atom.get("description", ""),
                    "category": atom.get("category", ""),
                    "atom_type": atom.get("type", ""),
                    "remotion_component": atom.get("remotion_component", ""),
                    "fills_shot_types": atom.get("fills_shot_types", []),
                    "visual_impact_score": atom.get("visual_impact_score", 0),
                    "tech_stack": atom.get("tech_stack", []),
                })
                edges.append({
                    "source": f"module:{mid}",
                    "target": f"atom:{aid}",
                    "type": "built_from",
                    "weight": atom.get("_weight", 0.5),
                    "optional": atom.get("_optional", False),
                })

        await gb.close()
        return KBSubgraphResponse(
            success=True, nodes=nodes, edges=edges,
            pattern={"id": pid, "category": full.get("category", ""), "description": full.get("description", "")},
        )
    except Exception as e:
        return KBSubgraphResponse(success=False, error=str(e))


class KBPatternItem(BaseModel):
    pattern_id: str
    category: str
    description: str
    hook_type: str
    build_pattern: str
    appearance_count: int


class KBPatternsResponse(BaseModel):
    success: bool
    patterns: list[dict] = []
    error: str = ""


@app.get("/kb/patterns", response_model=KBPatternsResponse)
async def kb_patterns():
    """List all patterns in the knowledge base."""
    try:
        from kb.graph_backend import GraphBackend
        from kb.template_store import TemplateStore

        db_path = str(Path(__file__).parent.parent.parent / "data" / "graph.db")
        if not Path(db_path).exists():
            return KBPatternsResponse(success=True, patterns=[], error="KB not initialized")

        gb = GraphBackend(f"file://{db_path}")
        await gb.connect()
        store = TemplateStore(gb)

        patterns = await store.list_patterns(limit=50)
        result = []
        for p in patterns:
            pid = str(p.get("id", ""))
            if ":" in pid:
                pid = pid.split(":")[-1]
            result.append({
                "pattern_id": pid,
                "category": p.get("category", ""),
                "description": p.get("description", ""),
                "hook_type": p.get("hook_type", ""),
                "build_pattern": p.get("build_pattern", ""),
                "appearance_count": p.get("appearance_count", 1),
            })

        await gb.close()
        return KBPatternsResponse(success=True, patterns=result)
    except Exception as e:
        return KBPatternsResponse(success=False, error=str(e))


class KBIngestRequest(BaseModel):
    template: dict
    vertical: str = "通用"


class KBIngestResponse(BaseModel):
    success: bool
    decision: str = ""
    reason: str = ""
    target_tid: str = ""
    new_tids: list[str] = []
    similar_count: int = 0
    error: str = ""


@app.post("/kb/ingest", response_model=KBIngestResponse)
async def kb_ingest(req: KBIngestRequest):
    """Ingest a new template into the knowledge base with LLM-powered merge/create/split decision."""
    try:
        from kb.graph_backend import GraphBackend
        from kb.template_store import TemplateStore
        from kb.agent.ingestion_agent import ingest_template

        db_path = str(Path(__file__).parent.parent.parent / "data" / "graph.db")
        if not Path(db_path).exists():
            return KBIngestResponse(success=False, error="KB not initialized")

        gb = GraphBackend(f"file://{db_path}")
        await gb.connect()
        store = TemplateStore(gb)

        result = await ingest_template(req.template, vertical=req.vertical, gb=gb, store=store)

        await gb.close()
        return KBIngestResponse(
            success=True,
            decision=result.decision,
            reason=result.reason,
            target_tid=result.target_tid,
            new_tids=result.new_tids,
            similar_count=len(result.similar_patterns),
        )
    except Exception as e:
        return KBIngestResponse(success=False, error=str(e))
