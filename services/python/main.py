"""VST Python Service: S1 video analysis + S2 structure extraction + S3 gap detection."""

import json
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
                    phase_name, gap, kb_atoms, [], template,
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


def _style_migrate_blocking(video_path: str, topic: str) -> dict:
    """同步阻塞版本的风格迁移，供 run_in_executor 调用。"""
    from scene_decomposer import (
        decompose_video, decomposition_to_dict, decomposition_from_dict,
        decomposition_to_orchestrator_template, generate_motion_paths_for_decomp,
    )
    from scene_description import extract_style_profile

    job_id = uuid.uuid4().hex[:8]
    output_dir = OUTPUT_BASE / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[style_migrate] job={job_id} 开始分解...", flush=True)

    # 1. 分解
    decomp = decompose_video(video_path, output_dir=str(output_dir))
    d = decomposition_to_dict(decomp)
    print(f"[style_migrate] 分解完成: {len(d.get('scenes', []))} 场景", flush=True)

    # 2. StyleProfile
    style_profile = extract_style_profile(video_path)
    print(f"[style_migrate] 风格: {style_profile.style_family}", flush=True)

    # 3. VLM 运动分析
    scene_motions = _vlm_analyze_motion(video_path, d["scenes"])
    print(f"[style_migrate] 运动分析完成", flush=True)

    # 4. Gemini 图片生成（注入风格）
    scene_images = _generate_scene_images(topic, d["scenes"], str(output_dir), style_profile)
    print(f"[style_migrate] 图片生成完成", flush=True)

    # 替换图片路径
    for i, sc in enumerate(d["scenes"]):
        imgs = scene_images.get(i, [])
        img_idx = 0
        for el in sc["elements"]:
            if el.get("type") == "image":
                if img_idx < len(imgs):
                    el["content_src"] = f"data/output/{job_id}/generated/{imgs[img_idx]}"
                    img_idx += 1
                else:
                    el["content_src"] = ""

    # 5. motion_path 关键帧
    generate_motion_paths_for_decomp(d, scene_motions, fps=d.get("fps", 30))

    # 6. 注入文字 + 动效（先用默认文字，LLM 编排在 async 层做）
    _inject_text_and_effects(d, {}, scene_motions)

    # 7. 重算场景边界
    frame = 0
    for sc in d["scenes"]:
        sc["start_frame"] = frame
        sc["end_frame"] = frame + sc["duration_frames"]
        frame += sc["duration_frames"]
    d["total_frames"] = frame

    # 保存 StyleProfile
    d["style_profile"] = style_profile.to_dict()

    # 保存 decomposition JSON
    decomp_path = str(output_dir / "decomposition.json")
    with open(decomp_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    # 复制图片到 web/public
    import shutil
    public_gen_dir = PROJECT_ROOT / "web" / "public" / "data" / "output" / job_id / "generated"
    public_gen_dir.mkdir(parents=True, exist_ok=True)
    gen_dir = output_dir / "generated"
    if gen_dir.exists():
        for img in gen_dir.glob("*.png"):
            shutil.copy2(img, public_gen_dir / img.name)

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

        # 在线程池中运行阻塞工作，不阻塞 uvicorn 事件循环
        result = await loop.run_in_executor(
            None, _style_migrate_blocking, req.video_path, req.topic
        )

        # LLM 文字编排（async，可以在事件循环中跑）
        if result.get("success"):
            try:
                from animation_orchestrator import orchestrate_from_beats
                from scene_decomposer import decomposition_to_orchestrator_template, decomposition_from_dict
                # 重新加载 decomposition 做 LLM 编排
                decomp_path = result.get("decomp_path", "")
                if decomp_path and Path(decomp_path).is_file():
                    with open(decomp_path) as f:
                        d = json.load(f)
                    decomp_obj = decomposition_from_dict(d)
                    template = decomposition_to_orchestrator_template(decomp_obj, topic=req.topic)
                    spec = await orchestrate_from_beats(template, topic=req.topic, verify=False)
                    llm_texts = {}
                    for shot in spec.get("shots", []):
                        role = shot.get("role", "")
                        text = shot.get("props", {}).get("text", "")
                        if role and text:
                            llm_texts.setdefault(role, []).append(text)
                    if llm_texts:
                        _inject_text_and_effects(d, llm_texts, [])
                        with open(decomp_path, "w", encoding="utf-8") as f:
                            json.dump(d, f, ensure_ascii=False, indent=2)
                        result["decomposition"] = d
                    print(f"[style_migrate] LLM 编排完成", flush=True)
            except Exception as e:
                print(f"[style_migrate] LLM 编排失败（不影响主流程）: {e}", flush=True)

        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


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
    for sc in scenes:
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
        if len(frames_b64) == 2:
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


def _generate_scene_images(topic, scenes, output_dir, style_profile):
    """Gemini 图片生成（注入风格）。"""
    from gemini_imager import generate_image
    import shutil

    PROMPTS = {
        "hook": [
            "cinematic aerial view, dramatic sky, golden hour, 4K",
            "iconic landmark, sunset, city skyline, warm tones",
            "street food close-up, steam rising, warm lighting",
            "city skyline at blue hour, rivers, modern buildings",
            "cherry blossoms, pink petals, dreamy spring",
            "food street at night, neon lights, vibrant",
        ],
        "build": [
            "scenic greenway, spring sunlight, serene 4K",
            "food street night, neon signs, bustling",
            "ferry crossing, city lights on water, blue hour",
            "university campus, cherry blossoms, students",
            "engineering marvel bridge, double decker",
            "historic temple architecture, golden light",
            "pedestrian street, historic buildings, modern shops",
            "panoramic river view, green bridge, golden hour",
        ],
        "cta": [
            "panorama from tower, rivers merging, dramatic clouds",
            "morning street life, breakfast culture, warm daily scene",
            "night skyline, colorful lights, river reflection",
            "tower at night, illuminated, golden glow, majestic",
        ],
    }

    n = len(scenes)
    img_dir = Path(output_dir) / "generated"
    img_dir.mkdir(parents=True, exist_ok=True)

    scene_images = {}
    for i, sc in enumerate(scenes):
        if i == 0 or i <= n * 0.25:
            phase = "hook"
        elif i >= n * 0.75:
            phase = "cta"
        else:
            phase = "build"

        prompts = PROMPTS.get(phase, PROMPTS["build"])
        n_imgs = max(2, min(len(sc.get("elements", [])), 6))
        paths = []

        for j in range(n_imgs):
            fname = f"s{i}_gen_{j}.png"
            fpath = str(img_dir / fname)
            if Path(fpath).exists():
                paths.append(fname)
                continue
            prompt = prompts[j % len(prompts)]
            result = generate_image(prompt, fpath, width=1280, height=720, style_profile=style_profile)
            if result:
                paths.append(fname)

        scene_images[i] = paths

    return scene_images


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
                # 混搭 idle 动画，避免同步
                el["effect_type"] = IDLE_POOL[(sc_idx + el_idx) % len(IDLE_POOL)]
                timing = el.get("timing", {})
                if not timing.get("entrance"):
                    timing["entrance"] = {
                        "type": ["scale", "slide", "3d", "fade"][el_idx % 4],
                        "direction": ["left", "right", "top", "bottom"][el_idx % 4],
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
