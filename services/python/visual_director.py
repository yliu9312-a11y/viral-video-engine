"""视觉导演 — 分析参考视频视觉结构，规划新内容的视觉素材需求，自动填充缺口。

流程:
1. VLM 分析参考视频 → 提取视觉结构（背景/前景/装饰/文字）
2. LLM 规划新内容的视觉需求 → VisualPlan
3. 检测缺口 → 分类（L1 素材库/L2 AI 生成/L3 用户输入）
4. 自动填充（Gemini 生图）→ 汇报剩余缺口
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import httpx

logger = logging.getLogger(__name__)

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_API_URL = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
MIMO_VLM_MODEL = os.environ.get("MIMO_VLM_MODEL", "mimo-v2.5")
MIMO_PRO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class VisualScene:
    """参考视频中的一个视觉场景。"""
    time_range: str
    background: str
    images: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    animation: str = ""
    has_image_content: bool = False


@dataclass
class AssetRequirement:
    """新内容的一个视觉素材需求。"""
    scene_id: str
    asset_type: str  # background / image / logo / mockup / decoration
    description: str
    can_generate: bool = True
    generation_prompt: str = ""
    priority: str = "high"  # high / medium / low
    status: str = "pending"  # pending / generating / done / failed / needs_user
    output_path: str = ""


@dataclass
class VisualPlan:
    """完整的视觉规划。"""
    reference_scenes: list[VisualScene] = field(default_factory=list)
    requirements: list[AssetRequirement] = field(default_factory=list)
    gaps: list[AssetRequirement] = field(default_factory=list)
    generated: list[AssetRequirement] = field(default_factory=list)
    needs_user: list[AssetRequirement] = field(default_factory=list)


# ── Step 1: VLM 分析参考视频视觉结构 ────────────────────────────────

def analyze_reference_visual(video_path: str) -> list[VisualScene]:
    """用 VLM 分析参考视频的完整视觉结构。"""
    frames_b64 = _extract_key_frames(video_path, count=6)
    if not frames_b64:
        logger.warning("无法提取关键帧")
        return []

    logger.info(f"提取了 {len(frames_b64)} 帧，调用 VLM 分析...")

    prompt = """分析这些视频帧，提取完整的视觉结构。

对每个时间段，描述：
1. 背景色（十六进制）
2. 有哪些图片/视觉元素？描述具体内容（产品截图、风景、人物、图标等）
3. 文字内容和位置
4. 元素的动画方式

返回 JSON：
{
  "scenes": [
    {
      "time_range": "0-3s",
      "background": "#000000",
      "images": ["描述看到的图片/视觉元素"],
      "text": ["文字1", "文字2"],
      "animation": "fade/scale/slide/zoom"
    }
  ]
}

只返回 JSON，不要其他文字。"""

    result = _vlm_call(frames_b64, prompt)
    logger.info(f"VLM 返回: {len(result) if result else 0} 字符")
    if not result:
        return []

    data = _parse_json(result)
    logger.info(f"JSON 解析: {'成功' if data else '失败'}, scenes={len(data.get('scenes', [])) if data else 0}")
    if not data:
        return []

    scenes = []
    for s in data.get("scenes", []):
        images = s.get("images", [])
        scenes.append(VisualScene(
            time_range=s.get("time_range", ""),
            background=s.get("background", "#000000"),
            images=images,
            text=s.get("text", []),
            animation=s.get("animation", ""),
            has_image_content=len(images) > 0 and any(
                len(img) > 10 for img in images  # 描述长度 > 10 = 真正的视觉内容
            ),
        ))

    return scenes


# ── Step 2: LLM 规划视觉需求 ────────────────────────────────────────

def plan_visual_assets(
    reference_scenes: list[VisualScene],
    new_topic: str,
    scene_description: dict,
) -> VisualPlan:
    """用 LLM 规划新内容需要的视觉素材。"""
    plan = VisualPlan(reference_scenes=reference_scenes)

    # 构造参考视频视觉结构摘要
    ref_summary = []
    for i, scene in enumerate(reference_scenes):
        ref_summary.append(
            f"场景{i+1} ({scene.time_range}): 背景={scene.background}, "
            f"图片={scene.images if scene.images else '无'}, "
            f"文字={scene.text}, 动画={scene.animation}"
        )
    ref_text = "\n".join(ref_summary)

    # 构造新内容元素摘要
    elements = scene_description.get("elements", [])
    elem_summary = []
    for el in elements:
        elem_summary.append(f"- {el.get('content_text', '')} @ ({el.get('spatial', {}).get('x', 0)}%,{el.get('spatial', {}).get('y', 0)}%)")
    elem_text = "\n".join(elem_summary[:15])

    prompt = f"""你是视频制作的视觉导演。

参考视频的视觉结构：
{ref_text}

新主题：{new_topic}
新内容的元素：
{elem_text}

任务：为新主题规划视觉素材。每个参考场景都需要对应的视觉素材。

输出要求：
- scene_id: 场景编号
- asset_type: background / image / logo / mockup
- description: 需要什么素材（中文）
- can_generate: true（AI可生成）或 false（需要用户提供）
- generation_prompt: 英文生图 prompt（can_generate=true 时必填）
- priority: high / medium / low

用 JSON 数组格式输出，不要其他文字。"""

    result = _vlm_call([], prompt)  # 不需要图片，纯文本分析
    if not result:
        return plan

    data = _parse_json(result)
    if not data:
        return plan

    for req_data in data.get("requirements", []):
        req = AssetRequirement(
            scene_id=req_data.get("scene_id", ""),
            asset_type=req_data.get("asset_type", "image"),
            description=req_data.get("description", ""),
            can_generate=req_data.get("can_generate", True),
            generation_prompt=req_data.get("generation_prompt", ""),
            priority=req_data.get("priority", "high"),
        )
        plan.requirements.append(req)

    return plan


# ── Step 3: 检测缺口 ────────────────────────────────────────────────

def detect_visual_gaps(
    plan: VisualPlan,
    scene_description: dict,
    material_dir: str = "",
) -> VisualPlan:
    """检测视觉缺口，分类为 L1/L2/L3。"""
    elements = scene_description.get("elements", [])
    has_image_elements = any(
        el.get("type") == "image" or el.get("content_src")
        for el in elements
    )

    # 检查现有素材
    existing_materials = []
    if material_dir and Path(material_dir).is_dir():
        existing_materials = [
            f for f in os.listdir(material_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp4'))
        ]

    for req in plan.requirements:
        # L1: 素材库有匹配
        if existing_materials and req.asset_type in ("background", "image"):
            # 简单匹配：有素材就行
            req.status = "done"
            plan.generated.append(req)
            continue

        # L2: AI 可生成
        if req.can_generate and req.generation_prompt:
            plan.gaps.append(req)
            continue

        # L3: 需要用户输入
        req.status = "needs_user"
        plan.needs_user.append(req)

    return plan


# ── Step 4: 自动填充（Gemini 生图）──────────────────────────────────

def auto_fill_gaps(plan: VisualPlan, output_dir: str) -> VisualPlan:
    """用 Gemini 自动生成可填充的视觉素材。"""
    from gemini_imager import generate_image

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for i, req in enumerate(plan.gaps):
        if not req.generation_prompt:
            continue

        filename = f"generated_{req.scene_id}_{i}.jpg"
        output_path = str(Path(output_dir) / filename)

        logger.info(f"[视觉导演] 生成素材 {i+1}/{len(plan.gaps)}: {req.description}")
        req.status = "generating"

        result = generate_image(
            prompt=req.generation_prompt,
            output_path=output_path,
            width=1280,
            height=720,
        )

        if result:
            req.status = "done"
            req.output_path = result
            plan.generated.append(req)
            logger.info(f"[视觉导演] ✅ 生成成功: {result}")
        else:
            req.status = "needs_user"
            plan.needs_user.append(req)
            logger.warning(f"[视觉导演] ❌ 生成失败: {req.description}")

    # 清空 gaps（已处理）
    plan.gaps = [g for g in plan.gaps if g.status != "done"]

    return plan


# ── 汇报 ────────────────────────────────────────────────────────────

def format_visual_report(plan: VisualPlan) -> str:
    """格式化视觉素材报告。"""
    lines = ["=" * 50]
    lines.append("视觉素材报告")
    lines.append("=" * 50)

    # 参考视频视觉结构
    lines.append(f"\n参考视频: {len(plan.reference_scenes)} 个视觉场景")
    for i, scene in enumerate(plan.reference_scenes):
        img_desc = ", ".join(scene.images[:3]) if scene.images else "无"
        lines.append(f"  场景{i+1} ({scene.time_range}): {scene.background} | 图片: {img_desc}")

    # 已生成
    if plan.generated:
        lines.append(f"\n✅ 已自动生成 {len(plan.generated)} 个素材:")
        for g in plan.generated:
            lines.append(f"  - {g.description} → {g.output_path}")

    # 需要用户输入
    if plan.needs_user:
        lines.append(f"\n⚠️ 需要您提供 {len(plan.needs_user)} 个素材:")
        for g in plan.needs_user:
            lines.append(f"  - [{g.priority}] {g.description}")

    # 剩余缺口
    remaining = [g for g in plan.gaps if g.status not in ("done", "needs_user")]
    if remaining:
        lines.append(f"\n🔴 剩余 {len(remaining)} 个缺口未处理:")
        for g in remaining:
            lines.append(f"  - {g.description}")

    if not plan.needs_user and not remaining:
        lines.append("\n✅ 所有视觉素材已就绪！")

    return "\n".join(lines)


# ── 工具函数 ─────────────────────────────────────────────────────────

def _extract_key_frames(video_path: str, count: int = 8) -> list[str]:
    """提取关键帧的 base64。"""
    import base64
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    frames_b64 = []
    for idx in range(0, total, max(1, total // count)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        h, w = frame.shape[:2]
        if w > 540:
            scale = 540 / w
            frame = cv2.resize(frame, (540, int(h * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        frames_b64.append(base64.b64encode(buf).decode("utf-8"))
        if len(frames_b64) >= count:
            break

    cap.release()
    return frames_b64


def _vlm_call(frames_b64: list[str], prompt: str, max_tokens: int = 2000, retries: int = 2) -> str | None:
    """调用 VLM。有图片用 VLM 模型，纯文本用 Pro 模型。带重试。"""
    if not MIMO_API_KEY:
        return None

    content = []
    for b64 in frames_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    content.append({"type": "text", "text": prompt})

    model = MIMO_VLM_MODEL if frames_b64 else MIMO_PRO_MODEL

    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                MIMO_API_URL,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                },
                headers={"Authorization": f"Bearer {MIMO_API_KEY}"},
                timeout=90.0,
            )
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                text = msg.get("content", "").strip()
                if not text:
                    text = msg.get("reasoning_content", "").strip()
                if text:
                    return text
                logger.warning(f"VLM 返回空内容 (attempt {attempt+1})")
            elif resp.status_code == 429:
                logger.warning(f"VLM 限流，等待重试 (attempt {attempt+1})")
                import time
                time.sleep(2 ** (attempt + 1))
                continue
            else:
                logger.warning(f"VLM HTTP {resp.status_code} (attempt {attempt+1})")
        except Exception as e:
            logger.warning(f"VLM 调用异常 (attempt {attempt+1}): {e}")

        if attempt < retries:
            import time
            time.sleep(1)

    return None


def _parse_json(text: str) -> dict | None:
    """从文本中提取 JSON（支持 markdown 代码块、嵌套结构）。

    策略：
    1. 提取 markdown 代码块中的 JSON
    2. 直接解析整个文本
    3. 用括号匹配找完整的 JSON 对象（处理嵌套）
    """
    import re

    # 1. 提取 markdown 代码块
    code_blocks = re.findall(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    for block in code_blocks:
        try:
            result = json.loads(block.strip())
            if isinstance(result, dict):
                return result
            elif isinstance(result, list) and len(result) > 0:
                return {"requirements": result}
        except json.JSONDecodeError:
            continue

    # 2. 直接解析
    cleaned = re.sub(r'```json\s*', '', text)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
        elif isinstance(result, list) and len(result) > 0:
            return {"requirements": result}
    except json.JSONDecodeError:
        pass

    # 3. 括号匹配找完整 JSON 对象或数组（处理嵌套）
    for i, char in enumerate(text):
        if char in ('{', '['):
            open_char = char
            close_char = '}' if char == '{' else ']'
            depth = 0
            for j in range(i, len(text)):
                if text[j] == open_char:
                    depth += 1
                elif text[j] == close_char:
                    depth -= 1
                    if depth == 0:
                        candidate = text[i:j+1]
                        try:
                            result = json.loads(candidate)
                            if isinstance(result, dict) and len(result) > 0:
                                return result
                            elif isinstance(result, list) and len(result) > 0:
                                # 数组包装为 dict 返回
                                return {"requirements": result}
                        except json.JSONDecodeError:
                            break
                        break

    return None
