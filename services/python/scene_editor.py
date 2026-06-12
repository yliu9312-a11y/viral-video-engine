"""NL Scene Editor — 自然语言编辑 VideoSpec 的场景/组件。

核心思路: 不预定义操作枚举，而是把完整的 VideoSpec 交给 LLM，
让它直接输出修改后的 spec。LLM 是"全知"的——它理解自然语言，
理解组件 schema，能做任何修改。

与 control_vector.py 的区别:
- control_vector: 全局参数 (文字密度/节奏/风格)，影响整个视频
- scene_editor: shot 级别精确编辑 (组件/文字/时长/运动/顺序/...)
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from video_spec_schema import _PROPS_MAP, _sanitize_props, PALETTE_MAP


# ═══════════════════════════════════════════════════════════
# 组件目录 — 给 LLM 的参考
# ═══════════════════════════════════════════════════════════

COMPONENT_NAMES = list(_PROPS_MAP.keys())
POSITIONS = ["center", "upper", "lower"]
TRANSITIONS = ["crossfade", "none"]
PALETTES = list(PALETTE_MAP.keys())


def _build_component_reference() -> str:
    """生成完整的组件参考手册，让 LLM 知道每个组件能接受什么 props。"""
    lines = []
    for name, cls in _PROPS_MAP.items():
        fields = []
        for fname, field in cls.model_fields.items():
            default = field.default
            desc = field.description or ""
            # 提取类型提示
            ann = field.annotation
            type_name = getattr(ann, "__name__", str(ann)) if ann else "any"
            if default is not None and default != ...:
                fields.append(f"    {fname}: {type_name} = {default!r}  # {desc}")
            else:
                fields.append(f"    {fname}: {type_name}  # {desc} (必填)")
        lines.append(f"  {name}:")
        lines.extend(fields[:8])  # 最多显示 8 个字段
        if len(fields) > 8:
            lines.append(f"    ... (共 {len(fields)} 个字段)")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# LLM Prompt — 柔性编辑
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是视频编辑专家。用户会给你一段视频的结构描述（VideoSpec JSON）和自然语言编辑指令。
你的任务是输出修改后的完整 VideoSpec。

## 规则

1. **只修改用户提到的部分**，其他保持不变
2. **输出完整的 VideoSpec JSON**（不是 diff，是完整的 shots 数组）
3. 组件名必须是以下之一: {component_names}
4. 每个 shot 的 duration 范围 30-240 帧 (30fps: 60=2s, 90=3s, 120=4s, 180=6s)
5. position: center / upper / lower
6. transition: crossfade / none
7. phase: hook / build / cta
8. props 必须匹配组件的 schema（见下方参考）
9. 可以增删 shot、重排顺序、改任何属性

## 组件 Props 参考

{component_reference}

## 输出格式

```json
{{
  "shots": [
    {{
      "id": "hook_0",
      "role": "hook",
      "component": "KineticText",
      "props": {{"text": "...", "mode": "bounce", ...}},
      "start": 0,
      "duration": 90,
      "position": "center",
      "transition": "crossfade"
    }},
    ...
  ],
  "globalStyle": {{"bgColor": "#050510", "palette": "promo"}},
  "reasoning": "简短说明你做了什么修改"
}}
```

只输出 JSON，不要其他文字。"""


# ═══════════════════════════════════════════════════════════
# 校验 & 修复
# ═══════════════════════════════════════════════════════════

def validate_and_fix_spec(raw: dict, original_spec: dict) -> tuple[dict, list[str]]:
    """校验 LLM 输出的 spec，自动修复可修复的问题，返回 (fixed_spec, warnings)。"""
    warnings: list[str] = []

    shots = raw.get("shots", [])
    if not shots:
        return original_spec, ["LLM 输出的 shots 为空，保持原样"]

    fixed_shots = []
    for i, shot in enumerate(shots):
        # 确保必要字段存在
        component = shot.get("component", "")
        if component not in COMPONENT_NAMES:
            warnings.append(f"shot[{i}]: 未知组件 '{component}'，保持原组件")
            # 尝试从原 spec 找对应位置的组件
            if i < len(original_spec.get("shots", [])):
                component = original_spec["shots"][i]["component"]
            else:
                component = "KineticText"  # 兜底

        # 校验 & 修复 props
        props = shot.get("props", {})
        if not isinstance(props, dict):
            props = {}
        sanitized = _sanitize_props(component, props)
        try:
            props_cls = _PROPS_MAP[component]
            props_cls.model_validate(sanitized)
        except Exception as e:
            warnings.append(f"shot[{i}] {component}: props 校验失败 ({e})，尝试修复")
            # 用默认值填充缺失字段
            defaults = _default_props(component)
            sanitized = {**defaults, **sanitized}
            try:
                props_cls = _PROPS_MAP[component]
                props_cls.model_validate(sanitized)
            except Exception:
                sanitized = defaults
                warnings.append(f"shot[{i}] {component}: 使用默认 props")

        # 校验 duration
        duration = shot.get("duration", shot.get("duration_frames", 90))
        if not isinstance(duration, (int, float)):
            duration = 90
        duration = max(30, min(240, int(duration)))

        # 校验 position
        position = shot.get("position", "center")
        if position not in POSITIONS:
            position = "center"

        # 校验 transition
        transition = shot.get("transition", "crossfade")
        if transition not in TRANSITIONS:
            transition = "crossfade"

        # 校验 phase/role
        role = shot.get("role", shot.get("phase", "build"))
        if role not in ("hook", "build", "cta"):
            role = "build"

        fixed_shots.append({
            "id": shot.get("id", f"{role}_{i}"),
            "role": role,
            "component": component,
            "props": sanitized,
            "start": 0,  # 后面重算
            "duration": duration,
            "position": position,
            "transition": transition,
        })

    # 重算 start 时间
    current_start = 0
    for s in fixed_shots:
        s["start"] = current_start
        current_start += s["duration"]

    # 处理 globalStyle
    global_style = raw.get("globalStyle", original_spec.get("globalStyle", {}))
    palette = global_style.get("palette", "promo")
    if palette not in PALETTES:
        palette = "promo"
        warnings.append(f"未知色板，回退到 promo")
    bg_color = global_style.get("bgColor", PALETTE_MAP[palette]["primary"])

    return {
        "fps": 30,
        "globalStyle": {"bgColor": bg_color, "palette": palette},
        "shots": fixed_shots,
    }, warnings


def _default_props(component: str) -> dict:
    """为组件生成默认 props。"""
    props_cls = _PROPS_MAP.get(component)
    if not props_cls:
        return {}
    defaults = {}
    for name, field in props_cls.model_fields.items():
        if field.default is not None and field.default != ...:
            defaults[name] = field.default
    return defaults


# ═══════════════════════════════════════════════════════════
# Diff 生成 — 对比新旧 spec
# ═══════════════════════════════════════════════════════════

def generate_diff(old_spec: dict, new_spec: dict) -> list[str]:
    """对比新旧 spec，生成人类可读的变更描述。"""
    diffs: list[str] = []
    old_shots = old_spec.get("shots", [])
    new_shots = new_spec.get("shots", [])

    # 逐 shot 对比
    max_len = max(len(old_shots), len(new_shots))
    for i in range(max_len):
        old = old_shots[i] if i < len(old_shots) else None
        new = new_shots[i] if i < len(new_shots) else None

        if old and not new:
            diffs.append(f"🗑️ 删除 shot[{i}]: {old['component']}")
            continue
        if new and not old:
            diffs.append(f"➕ 新增 shot[{i}]: {new['component']}")
            continue

        # 两边都有，逐字段对比
        assert old is not None and new is not None
        changes: list[str] = []

        if old["component"] != new["component"]:
            changes.append(f"组件 {old['component']} → {new['component']}")

        if old.get("duration") != new.get("duration"):
            old_d = old.get("duration", 0)
            new_d = new.get("duration", 0)
            changes.append(f"时长 {old_d/30:.1f}s → {new_d/30:.1f}s")

        if old.get("position") != new.get("position"):
            changes.append(f"位置 {old.get('position')} → {new.get('position')}")

        if old.get("transition") != new.get("transition"):
            changes.append(f"转场 {old.get('transition')} → {new.get('transition')}")

        if old.get("role") != new.get("role"):
            changes.append(f"角色 {old.get('role')} → {new.get('role')}")

        # props 对比 — 只报告有意义的变更
        old_props = old.get("props", {})
        new_props = new.get("props", {})
        all_keys = set(list(old_props.keys()) + list(new_props.keys()))
        for k in sorted(all_keys):
            ov = old_props.get(k)
            nv = new_props.get(k)
            # 跳过两边都是 None/空 或值相同的情况
            if ov == nv:
                continue
            # 跳过从 None → 默认值 的"假变更"
            if ov is None and nv is not None:
                # 检查 nv 是否是该组件的默认值
                props_cls = _PROPS_MAP.get(new["component"])
                if props_cls and k in props_cls.model_fields:
                    default_val = props_cls.model_fields[k].default
                    if default_val is not None and default_val != ... and nv == default_val:
                        continue
            changes.append(f"{k}: {ov!r} → {nv!r}")

        if changes:
            comp = new["component"]
            diffs.append(f"shot[{i}] {comp}: " + "; ".join(changes))

    # 全局样式对比
    old_gs = old_spec.get("globalStyle", {})
    new_gs = new_spec.get("globalStyle", {})
    if old_gs.get("palette") != new_gs.get("palette"):
        diffs.append(f"🎨 色板: {old_gs.get('palette')} → {new_gs.get('palette')}")
    if old_gs.get("bgColor") != new_gs.get("bgColor"):
        diffs.append(f"🖼️ 背景色: {old_gs.get('bgColor')} → {new_gs.get('bgColor')}")

    # 总时长变化
    old_total = sum(s.get("duration", 0) for s in old_shots) / 30
    new_total = sum(s.get("duration", 0) for s in new_shots) / 30
    if abs(old_total - new_total) > 0.1:
        diffs.append(f"⏱️ 总时长: {old_total:.1f}s → {new_total:.1f}s")

    if len(old_shots) != len(new_shots):
        diffs.append(f"📊 镜头数: {len(old_shots)} → {len(new_shots)}")

    if not diffs:
        diffs.append("无变更")

    return diffs


# ═══════════════════════════════════════════════════════════
# decomposition → VideoSpec 转换
# ═══════════════════════════════════════════════════════════

def _scenes_to_shots(spec: dict) -> list[dict]:
    """将 decomposition 的 scenes 转换为 VideoSpec 的 shots 格式。"""
    fps = spec.get("fps", 30)
    shots = []
    for sc in spec.get("scenes", []):
        # 从 elements 中提取文字和图片
        texts = []
        images = []
        for el in sc.get("elements", []):
            if el.get("type") == "text" or el.get("content_text"):
                texts.append(el.get("content_text", el.get("text", "")))
            if el.get("type") == "image" or el.get("content_src"):
                images.append(el.get("content_src", ""))

        # 确定组件类型
        role = sc.get("scene_role", sc.get("role", "build"))
        if role in ("hook", "opening"):
            component = "HookBeat"
        elif role in ("cta", "payoff", "closing"):
            component = "ClosingBeat"
        else:
            component = "KineticText"

        # 如果有图片，用 ProductShowcase
        if images:
            component = "ProductShowcase"

        duration_frames = sc.get("duration_frames", 90)
        shot = {
            "component": component,
            "role": role,
            "duration": duration_frames,
            "duration_s": round(duration_frames / fps, 1),
            "props": {
                "text": texts[0] if texts else "",
                "image_src": images[0] if images else "",
            },
        }
        shots.append(shot)
    return shots


def _sync_shots_to_scenes(edited_spec: dict, original_spec: dict):
    """把 LLM 编辑后的 shots 改动同步回 decomposition 的 scenes。"""
    shots = edited_spec.get("shots", [])
    scenes = original_spec.get("scenes", [])
    for i, shot in enumerate(shots):
        if i >= len(scenes):
            break
        sc = scenes[i]
        # 同步文字
        new_text = shot.get("props", {}).get("text", "")
        if new_text:
            for el in sc.get("elements", []):
                if el.get("type") == "text" or el.get("content_text"):
                    el["content_text"] = new_text
                    el["text"] = new_text
                    break
        # 同步时长
        new_dur = shot.get("duration", shot.get("duration_s", 0))
        if isinstance(new_dur, float):
            new_dur = int(new_dur * original_spec.get("fps", 30))
        if new_dur > 0:
            sc["duration_frames"] = new_dur
    # 重算场景边界
    frame = 0
    for sc in scenes:
        sc["start_frame"] = frame
        sc["end_frame"] = frame + sc["duration_frames"]
        frame += sc["duration_frames"]
    original_spec["total_frames"] = frame


# ═══════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════

async def edit_scene(spec_path: str, instruction: str) -> dict:
    """自然语言编辑 VideoSpec。

    Args:
        spec_path: VideoSpec JSON 文件路径
        instruction: 自然语言编辑指令（任意表达）

    Returns:
        { success, diff, updated_spec_path, before, after, warnings, reasoning }
    """
    from openai import OpenAI

    api_key = os.environ.get("MIMO_API_KEY", "")
    api_url = os.environ.get("MIMO_API_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    # OpenAI 客户端会自动加 /chat/completions，所以要去掉末尾的
    api_url = api_url.replace("/chat/completions", "")
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        return {"success": False, "error": "MIMO_API_KEY not set"}

    # 1. 加载 VideoSpec
    spec_file = Path(spec_path)
    if not spec_file.is_file():
        return {"success": False, "error": f"Spec 文件不存在: {spec_path}"}

    with open(spec_file) as f:
        spec = json.load(f)

    shots = spec.get("shots", [])
    # 兼容 decomposition 格式（scenes → shots 转换）
    if not shots and "scenes" in spec:
        shots = _scenes_to_shots(spec)
        spec = {**spec, "shots": shots}
    if not shots:
        return {"success": False, "error": "Spec 中没有 shots"}

    # 2. 构造 LLM prompt — 给完整的 spec JSON + 组件参考
    component_reference = _build_component_reference()
    system_msg = SYSTEM_PROMPT.format(
        component_names=", ".join(COMPONENT_NAMES),
        component_reference=component_reference,
    )

    # 把当前 spec 作为上下文
    spec_json = json.dumps(spec, ensure_ascii=False, indent=2)
    user_msg = f"## 当前 VideoSpec\n```json\n{spec_json}\n```\n\n## 编辑指令\n{instruction}"

    # 3. LLM 调用
    try:
        client = OpenAI(api_key=api_key, base_url=api_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_completion_tokens=4000,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)
    except Exception as e:
        return {"success": False, "error": f"LLM 调用失败: {e}"}

    # 4. 校验 & 修复
    new_spec, validation_warnings = validate_and_fix_spec(parsed, spec)

    # 5. 生成 diff
    diff = generate_diff(spec, new_spec)

    # 6. 保存 — 如果原始是 decomposition 格式，把 shots 的改动同步回 scenes
    output_dir = spec_file.parent
    clean_stem = spec_file.stem.replace("_edited", "")
    new_spec_path = output_dir / f"{clean_stem}_edited.json"

    # 如果原始 spec 有 scenes（decomposition 格式），同步改动
    if "scenes" in spec:
        _sync_shots_to_scenes(new_spec, spec)
        save_data = spec  # 保存完整的 decomposition（含 scenes）
        # 同时把 shots 也加进去方便后续编辑
        save_data["shots"] = new_spec.get("shots", [])
    else:
        save_data = new_spec

    with open(new_spec_path, "w") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    # 7. 返回
    old_total = sum(s.get("duration_frames", s.get("duration", 0)) for s in spec.get("shots", spec.get("scenes", []))) / 30
    new_total = sum(s.get("duration", 0) for s in new_spec.get("shots", [])) / 30

    return {
        "success": True,
        "reasoning": parsed.get("reasoning", ""),
        "diff": diff,
        "updated_spec_path": str(new_spec_path),
        "before": {
            "shot_count": len(spec.get("shots", [])),
            "total_duration": f"{old_total:.1f}s",
            "shots": [
                {
                    "index": i,
                    "component": s.get("component", "?"),
                    "role": s.get("role", s.get("phase", "?")),
                    "duration_s": round(s.get("duration", 0) / 30, 1),
                    "text": s.get("props", {}).get("text", s.get("props", {}).get("product_name", "")),
                }
                for i, s in enumerate(spec.get("shots", []))
            ],
        },
        "after": {
            "shot_count": len(new_spec.get("shots", [])),
            "total_duration": f"{new_total:.1f}s",
            "shots": [
                {
                    "index": i,
                    "component": s.get("component", "?"),
                    "role": s.get("role", "?"),
                    "duration_s": round(s.get("duration", 0) / 30, 1),
                    "text": s.get("props", {}).get("text", s.get("props", {}).get("product_name", "")),
                }
                for i, s in enumerate(new_spec.get("shots", []))
            ],
        },
        "warnings": validation_warnings,
    }
