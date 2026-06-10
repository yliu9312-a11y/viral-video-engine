"""S3 Gap Identification: StructureTemplate + user materials → gap_report."""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict


@dataclass
class Material:
    path: str
    file_type: str  # "image" | "video"
    tagged_types: list[str] = field(default_factory=list)
    usable_duration: float = 0.0
    quality_score: float = 1.0
    palette_hint: str = ""  # beauty/digital/food/viral from VLM
    width: int = 0
    height: int = 0
    description: str = ""
    # Task 11: role-fit scores from VLM (0-10)
    hook_fit: float = 5.0
    build_fit: float = 5.0
    cta_fit: float = 5.0
    # Composite scores (computed by score_and_assign)
    scores: dict = field(default_factory=dict)  # {phase: composite_score}


@dataclass
class PhaseGap:
    phase: str
    missing_shot_types: list[str]
    duration_shortfall: float
    shot_count_shortfall: int
    low_quality_count: int
    severity: str  # HIGH / MEDIUM / LOW
    impact_on_video: str
    recommended_strategies: list[dict] = field(default_factory=list)


def scan_materials(material_dir: str) -> list[Material]:
    """Scan a directory for images and videos, return Material list."""
    material_path = Path(material_dir)
    if not material_path.is_dir():
        return []

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"}

    materials = []
    for f in sorted(material_path.iterdir()):
        if f.is_file():
            ext = f.suffix.lower()
            if ext in image_exts:
                materials.append(Material(
                    path=str(f),
                    file_type="image",
                    tagged_types=[],
                    usable_duration=3.0,  # default 3s per image
                ))
            elif ext in video_exts:
                dur = _get_video_duration(str(f))
                materials.append(Material(
                    path=str(f),
                    file_type="video",
                    tagged_types=[],
                    usable_duration=dur,
                ))
    return materials


def _get_video_duration(video_path: str) -> float:
    """Get video duration via OpenCV."""
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return total / fps
    except Exception:
        return 5.0


def tag_materials_with_vlm(materials: list[Material]) -> list[Material]:
    """Tag materials with shot types using MiMo VL API."""
    import os
    import base64
    import cv2

    mimo_key = os.environ.get("MIMO_API_KEY", "")
    mimo_url = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")

    if not mimo_key:
        # Fallback: assign generic types based on file type
        for m in materials:
            m.tagged_types = ["general"] if m.file_type == "video" else ["product_zoom_in"]
        return materials

    import httpx

    for mat in materials:
        try:
            # Get a representative frame
            if mat.file_type == "video":
                frame = _extract_frame(mat.path, 1.0)
            else:
                frame = cv2.imread(mat.path)

            if frame is None:
                mat.tagged_types = ["general"]
                continue

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buf).decode("utf-8")

            resp = httpx.post(
                mimo_url,
                json={
                    "model": os.environ.get("MIMO_VLM_MODEL", "mimo-v2.5"),
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": (
                                "分析这个画面，返回 JSON：\n"
                                '{"types": ["镜头类型"], "quality": 1-10, "palette": "beauty/digital/food/viral", "notes": "一句话描述", "hook_fit": 0-10, "build_fit": 0-10, "cta_fit": 0-10}\n\n'
                                "镜头类型（可多选）：\n"
                                "- face_closeup: 人脸特写\n"
                                "- product_closeup: 产品特写展示\n"
                                "- product_usage: 使用场景/环境\n"
                                "- hook_attention_grabber: 吸引注意力的开头画面\n"
                                "- text_overlay: 文字/标题为主\n"
                                "- transition: 过渡画面\n"
                                "- before_after: 对比（前后）\n"
                                "- general: 通用画面\n\n"
                                "quality: 画面构图、光线、清晰度综合评分(1-10)\n"
                                "palette: 画面主色调风格(beauty=柔和暖调, digital=冷酷科技, food=温暖食欲, viral=强对比)\n"
                                "hook_fit: 作为开头吸引注意力的适合度(0-10, 10=非常适合)\n"
                                "build_fit: 作为中间展示/信息传达的适合度(0-10)\n"
                                "cta_fit: 作为结尾收束/品牌展示的适合度(0-10)"
                            )},
                        ],
                    }],
                    "max_tokens": 200,
                },
                headers={"Authorization": f"Bearer {mimo_key}"},
                timeout=20.0,
            )

            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                import re
                # Try JSON object format first
                obj_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if obj_match:
                    try:
                        data = json.loads(obj_match.group())
                        mat.tagged_types = [t for t in data.get("types", ["general"]) if isinstance(t, str)]
                        mat.quality_score = data.get("quality", 5)
                        mat.palette_hint = data.get("palette", "")
                        mat.description = data.get("notes", content)
                        mat.hook_fit = float(data.get("hook_fit", 5))
                        mat.build_fit = float(data.get("build_fit", 5))
                        mat.cta_fit = float(data.get("cta_fit", 5))
                    except json.JSONDecodeError:
                        mat.tagged_types = ["general"]
                else:
                    # Fallback: try JSON array
                    arr_match = re.search(r'\[.*?\]', content, re.DOTALL)
                    if arr_match:
                        types = json.loads(arr_match.group())
                        mat.tagged_types = [t for t in types if isinstance(t, str)]
                        mat.description = content
                    else:
                        mat.tagged_types = ["general"]
            else:
                mat.tagged_types = ["general"]

        except Exception:
            mat.tagged_types = ["general"]

    return materials


# ── Task 11: Highlight scoring + phase-fit assignment ──────────────────────

# 权重配置 (先验，非最优，留 A/B 调)
SCORING_WEIGHTS = {
    "quality":   0.35,  # VLM 美学质量分
    "role_fit":  0.40,  # VLM 角色匹配分
    "motion":    0.10,  # 运动能量 (高能量更适合 hook)
    "sharpness": 0.10,  # 清晰度
    "duration":  0.05,  # 时长适度性
}

# 每个 phase 的角色查询 prompt (用于 VLM 已返回的 role_fit 分)
# 实际打分在 tag_materials_with_vlm 的 prompt 里一次完成
ROLE_FIT_KEY = {
    "hook": "hook_fit",
    "build": "build_fit",
    "payoff_cta": "cta_fit",
    "cta": "cta_fit",
}


def _compute_sharpness(frame) -> float:
    """Laplacian 方差作为清晰度代理。0-1 归一化。"""
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = laplacian.var()
    # 归一化: 0-500 → 0-1
    return min(1.0, variance / 500.0)


def _compute_motion_energy(path: str) -> float:
    """从视频文件计算运动能量。0-1 归一化。"""
    import cv2
    try:
        cap = cv2.VideoCapture(path)
        ret1, prev = cap.read()
        if not ret1:
            cap.release()
            return 0.0

        energies = []
        for _ in range(30):  # 最多读 30 帧
            ret2, curr = cap.read()
            if not ret2:
                break
            gray_prev = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
            gray_curr = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(gray_prev, gray_curr)
            energies.append(float(diff.mean()) / 255.0)
            prev = curr

        cap.release()
        return min(1.0, sum(energies) / len(energies) * 10) if energies else 0.0
    except Exception:
        return 0.0


def score_and_assign_materials(
    materials: list[Material],
    gaps: list[PhaseGap],
    template: dict,
) -> dict[str, list[dict]]:
    """Task 11 核心: 对每个材料打分，按 phase 分配。

    打分公式:
    score(clip, phase) = w_quality * quality + w_role_fit * role_fit[phase]
                       + w_motion * motion + w_sharpness * sharpness + w_duration * duration_fit

    返回 { phase: [{ material, score, breakdown }] }
    """
    import cv2

    if not materials:
        return {}

    # 为每个材料计算廉价信号
    for mat in materials:
        if mat.file_type == "video":
            mat.scores = {"_motion": _compute_motion_energy(mat.path)}
            frame = _extract_frame(mat.path, 1.0)
        else:
            mat.scores = {"_motion": 0.0}
            frame = cv2.imread(mat.path)

        if frame is not None:
            mat.scores["_sharpness"] = _compute_sharpness(frame)
        else:
            mat.scores["_sharpness"] = 0.0

    # 归一化 quality_score (1-10 → 0-1)
    max_q = max((m.quality_score for m in materials), default=10)
    min_q = min((m.quality_score for m in materials), default=1)
    q_range = max(max_q - min_q, 1)

    # 对每个 phase 打分
    timeline = template.get("timeline", [])
    phase_names = [p["phase"] for p in timeline]
    if not phase_names:
        phase_names = ["hook", "build", "payoff_cta"]

    assignments: dict[str, list[dict]] = {p: [] for p in phase_names}
    used_paths: set[str] = set()

    for phase in phase_names:
        role_key = ROLE_FIT_KEY.get(phase, "build_fit")

        scored = []
        for mat in materials:
            # 归一化 quality
            q_norm = (mat.quality_score - min_q) / q_range

            # role_fit (0-10 → 0-1)
            role_val = getattr(mat, role_key, 5.0) / 10.0

            # motion (hook 偏高能量, cta 偏低)
            motion = mat.scores.get("_motion", 0.0)
            if phase in ("hook",):
                motion_bonus = motion
            elif phase in ("cta", "payoff_cta"):
                motion_bonus = 1.0 - motion  # 结尾偏好安静
            else:
                motion_bonus = 0.5

            sharpness = mat.scores.get("_sharpness", 0.5)

            # duration fit (视频太短或太长扣分)
            dur_fit = 1.0
            if mat.file_type == "video":
                ideal_dur = 5.0  # 理想 5 秒
                dur_fit = max(0.0, 1.0 - abs(mat.usable_duration - ideal_dur) / 10.0)

            # 合成
            w = SCORING_WEIGHTS
            composite = (
                w["quality"] * q_norm
                + w["role_fit"] * role_val
                + w["motion"] * motion_bonus
                + w["sharpness"] * sharpness
                + w["duration"] * dur_fit
            )

            mat.scores[phase] = composite

            scored.append({
                "material": mat,
                "score": round(composite, 3),
                "breakdown": {
                    "quality": round(q_norm, 3),
                    "role_fit": round(role_val, 3),
                    "motion": round(motion_bonus, 3),
                    "sharpness": round(sharpness, 3),
                    "duration_fit": round(dur_fit, 3),
                },
            })

        # 按分数降序排列
        scored.sort(key=lambda x: -x["score"])

        # 贪心分配 (去重: 同片段不重复占多槽)
        phase_info = next((p for p in timeline if p["phase"] == phase), {})
        needed = max(1, phase_info.get("shot_count_range", [1, 3])[1])

        for item in scored:
            if len(assignments[phase]) >= needed:
                break
            mat_path = item["material"].path
            if mat_path not in used_paths:
                assignments[phase].append(item)
                used_paths.add(mat_path)

    return assignments


def _extract_frame(video_path: str, time_sec: float):
    """Extract a frame from video."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def compute_severity(
    missing_types: set,
    duration_shortfall: float,
    shot_count_shortfall: int,
) -> str:
    """Compute gap severity: HIGH / MEDIUM / LOW."""
    score = 0
    if missing_types:
        score += len(missing_types) * 2
    if duration_shortfall > 3:
        score += 3
    elif duration_shortfall > 1:
        score += 1
    if shot_count_shortfall >= 3:
        score += 3
    elif shot_count_shortfall >= 1:
        score += 1

    if score >= 5:
        return "HIGH"
    elif score >= 2:
        return "MEDIUM"
    return "LOW"


def recommend_strategies(gap: PhaseGap, has_product_image: bool) -> list[dict]:
    """Recommend completion strategies based on gap type and severity."""
    strategies = []

    # Strategy A: Restructure (for HIGH severity hook gaps)
    if gap.severity == "HIGH" and gap.phase == "hook":
        strategies.append({
            "id": "A",
            "name": "结构重排",
            "description": "跳过 hook phase，直接从 build 开场，或 hook 改纯字幕",
            "priority": 1,
        })

    # Strategy C: Packaging fill (most common, if types are packagable)
    packagable = {"text_overlay", "product_zoom_in", "before_after"}
    if set(gap.missing_shot_types) & packagable or has_product_image:
        strategies.append({
            "id": "C",
            "name": "包装补全",
            "description": "用 Remotion 组件（标题条、卖点卡片、贴纸）填充缺失画面",
            "priority": 2,
        })

    # Strategy D: AIGC generation (for scenario gaps)
    if "usage_scenario" in gap.missing_shot_types:
        strategies.append({
            "id": "D",
            "name": "AIGC 生成",
            "description": "用 ComfyUI 本地生成场景图，Remotion 动画化",
            "priority": 3,
        })

    # Strategy E: Material recombination (if good materials but short on count)
    if gap.shot_count_shortfall >= 2:
        strategies.append({
            "id": "E",
            "name": "素材重组",
            "description": "对现有素材做 Ken Burns、变速、反向、裁剪等变换复用",
            "priority": 4,
        })

    # Strategy B: Caption/subtitle fill (always available as fallback)
    strategies.append({
        "id": "B",
        "name": "字幕补全",
        "description": "加大字幕信息密度，用文字承载缺失画面的语义",
        "priority": 5,
    })

    # Sort by priority
    strategies.sort(key=lambda s: s["priority"])
    return strategies


def generate_impact_description(
    phase: str,
    missing_types: list[str],
    template: dict,
) -> str:
    """Generate a natural language impact description (LLM or fallback)."""
    if not missing_types:
        return ""

    phase_names = {"hook": "开头吸引", "build": "中段展示", "payoff_cta": "收尾转化"}
    phase_cn = phase_names.get(phase, phase)

    type_names = {
        "face_closeup": "人脸特写",
        "product_zoom_in": "产品特写",
        "usage_scenario": "使用场景",
        "hook_attention_grabber": "吸睛开头",
        "text_overlay": "文字画面",
        "before_after": "对比画面",
        "transition": "过渡镜头",
    }
    missing_cn = [type_names.get(t, t) for t in missing_types]

    return (
        f"缺少{'、'.join(missing_cn)}，"
        f"会让{phase_cn}环节的表现力下降，"
        f"预估完播率受影响。"
    )


def identify_gaps(template: dict, materials: list[Material]) -> list[PhaseGap]:
    """5-step gap identification algorithm."""
    gaps = []
    timeline = template.get("timeline", [])
    duration_max = template.get("duration_range", [0, 30])[1]

    # Check if user has any product image
    has_product_image = any(
        "product_zoom_in" in m.tagged_types for m in materials
    )

    for phase_data in timeline:
        phase_name = phase_data.get("phase", "unknown")
        required_types = set(phase_data.get("required_shot_types", []))
        dur_pct = phase_data.get("duration_pct", [0, 1])
        required_duration = (dur_pct[1] - dur_pct[0]) * duration_max
        required_count = phase_data.get("shot_count_range", [1, 3])[0]

        # Step 1: Type coverage
        candidate_materials = [
            m for m in materials if set(m.tagged_types) & required_types
        ]
        available_types = set()
        for m in candidate_materials:
            available_types.update(m.tagged_types)
        missing_types = required_types - available_types

        # Step 2: Duration coverage
        available_duration = sum(m.usable_duration for m in candidate_materials)
        duration_shortfall = max(0, required_duration - available_duration)

        # Step 3: Shot count
        shot_count_shortfall = max(0, required_count - len(candidate_materials))

        # Step 4: Quality check
        low_quality = [m for m in candidate_materials if m.quality_score < 0.6]

        # Step 5: Generate gap report
        if missing_types or duration_shortfall > 0 or shot_count_shortfall > 0:
            severity = compute_severity(missing_types, duration_shortfall, shot_count_shortfall)
            impact = generate_impact_description(phase_name, list(missing_types), template)

            gap = PhaseGap(
                phase=phase_name,
                missing_shot_types=list(missing_types),
                duration_shortfall=round(duration_shortfall, 2),
                shot_count_shortfall=shot_count_shortfall,
                low_quality_count=len(low_quality),
                severity=severity,
                impact_on_video=impact,
            )
            gap.recommended_strategies = recommend_strategies(gap, has_product_image)
            gaps.append(gap)

    return gaps


def run_gap_detection(template: dict, material_dir: str, output_dir: str = "") -> dict:
    """Full S3 gap detection pipeline.

    Args:
        template: StructureTemplate dict (from S2)
        material_dir: path to user's materials directory
        output_dir: where to save gap_report.json

    Returns:
        gap_report dict
    """
    # Scan materials
    materials = scan_materials(material_dir)

    # Tag with VLM (includes quality + role-fit scores)
    materials = tag_materials_with_vlm(materials)

    # Identify gaps
    gaps = identify_gaps(template, materials)

    # Task 11: Score and assign materials to phases
    assignments = score_and_assign_materials(materials, gaps, template)

    # Build report
    report = {
        "template_id": template.get("template_id", ""),
        "material_count": len(materials),
        "materials": [
            {
                "path": m.path,
                "type": m.file_type,
                "tagged_types": m.tagged_types,
                "duration": m.usable_duration,
                "quality": m.quality_score,
                "hook_fit": m.hook_fit,
                "build_fit": m.build_fit,
                "cta_fit": m.cta_fit,
                "description": m.description,
            }
            for m in materials
        ],
        "gaps": [asdict(g) for g in gaps],
        "assignments": {
            phase: [
                {
                    "path": item["material"].path,
                    "score": item["score"],
                    "breakdown": item["breakdown"],
                    "description": item["material"].description,
                }
                for item in items
            ]
            for phase, items in assignments.items()
        },
        "summary": {
            "total_gaps": len(gaps),
            "high_severity": sum(1 for g in gaps if g.severity == "HIGH"),
            "medium_severity": sum(1 for g in gaps if g.severity == "MEDIUM"),
            "low_severity": sum(1 for g in gaps if g.severity == "LOW"),
        },
    }

    # Save to file
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        report_path = str(Path(output_dir) / "gap_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        report["saved_to"] = report_path

    return report
