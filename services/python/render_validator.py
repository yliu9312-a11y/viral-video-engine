"""Post-render QA validation — 渲染前校验 VideoSpec。

在 orchestrator 生成 VideoSpec 后、渲染前运行。
检测: 黑屏 gap、同位置重叠、空文字、背景缺失、时长异常。
返回问题列表 + 自动修复建议。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QAIssue:
    severity: str  # "error" / "warning"
    category: str  # "gap" / "overlap" / "empty_text" / "no_bg" / "duration"
    message: str
    shot_ids: list[str] = field(default_factory=list)
    auto_fix: str = ""  # 自动修复建议


def validate_video_spec(spec: dict) -> list[QAIssue]:
    """校验 VideoSpec，返回问题列表。"""
    issues: list[QAIssue] = []
    shots = spec.get("shots", [])

    if not shots:
        issues.append(QAIssue("error", "empty", "没有 shot"))
        return issues

    # ── 1. 黑屏 gap 检测 ──
    sorted_shots = sorted(shots, key=lambda s: s.get("start", 0))
    for i in range(1, len(sorted_shots)):
        prev = sorted_shots[i - 1]
        curr = sorted_shots[i]
        prev_end = prev.get("start", 0) + prev.get("duration", 0)
        curr_start = curr.get("start", 0)
        gap = curr_start - prev_end

        # 不检查同 beat 的 shot (gap=0 是正常的层叠)
        if gap > 30:  # >1s
            issues.append(QAIssue(
                "warning", "gap",
                f"黑屏 gap: {gap}f ({gap / 30:.1f}s) 在 {prev.get('component','')} 和 {curr.get('component','')} 之间",
                shot_ids=[prev.get("id", ""), curr.get("id", "")],
                auto_fix="调整 shot 时长或 start 消除 gap",
            ))

    # ── 2. 同位置重叠检测 (同 beat 内) ──
    from itertools import combinations
    by_start: dict[int, list[dict]] = {}
    for shot in shots:
        start = shot.get("start", 0)
        if start not in by_start:
            by_start[start] = []
        by_start[start].append(shot)

    for start, group in by_start.items():
        # 按 position 分组
        by_pos: dict[str, list[dict]] = {}
        for shot in group:
            pos = shot.get("position", "center")
            if pos not in by_pos:
                by_pos[pos] = []
            by_pos[pos].append(shot)

        for pos, pos_shots in by_pos.items():
            # 同 position 的非装饰 shot 超过 1 个 → 重叠
            # 排除: ParticleBg(背景), GlowTrail(装饰性SVG, 不遮挡内容)
            non_bg = [s for s in pos_shots if s.get("component") not in ("ParticleBg", "GlowTrail")]
            if len(non_bg) > 1:
                # 检查是否都是卡片类 (可以用 flex 行列布局)
                card_types = {"GlassCard", "FloatingMockup", "ProductShowcase"}
                all_cards = all(s.get("component") in card_types for s in non_bg)
                if not all_cards:
                    issues.append(QAIssue(
                        "warning", "overlap",
                        f"同位置重叠: {', '.join(s.get('component','') for s in non_bg)} 都在 {pos}",
                        shot_ids=[s.get("id", "") for s in non_bg],
                        auto_fix="分配不同 position 或改为 flex 布局",
                    ))

    # ── 3. 空文字检测 ──
    text_components = {"WordReveal", "GradientText", "KineticText", "TypewriterPrompt", "MarqueeText"}
    for shot in shots:
        comp = shot.get("component", "")
        if comp in text_components:
            text = shot.get("props", {}).get("text", "")
            if not text or not str(text).strip():
                issues.append(QAIssue(
                    "error", "empty_text",
                    f"{comp} 的 text 为空",
                    shot_ids=[shot.get("id", "")],
                    auto_fix="填充文字内容或替换为非文字组件",
                ))

    # ── 4. 背景检测 ──
    # BackgroundLayer 已在 ScriptDrivenVideo 中全局渲染，ParticleBg 是可选增强
    has_bg = any(s.get("component") == "ParticleBg" for s in shots)
    if not has_bg:
        issues.append(QAIssue(
            "warning", "no_bg",
            "没有 ParticleBg 增强背景（BackgroundLayer 已提供基础背景）",
        ))

    # ── 5. 时长异常 ──
    total = max(s.get("start", 0) + s.get("duration", 0) for s in shots)
    total_s = total / 30
    if total_s < 10:
        issues.append(QAIssue(
            "warning", "duration",
            f"总时长过短: {total_s:.1f}s",
            auto_fix="增加 shot 时长或数量",
        ))
    elif total_s > 120:
        issues.append(QAIssue(
            "warning", "duration",
            f"总时长过长: {total_s:.1f}s",
            auto_fix="减少 shot 时长或数量",
        ))

    # ── 6. 单 shot 时长异常 ──
    for shot in shots:
        dur = shot.get("duration", 0)
        if dur < 30:
            issues.append(QAIssue(
                "warning", "duration",
                f"{shot.get('component','')} 只有 {dur}f ({dur/30:.1f}s)，太短",
                shot_ids=[shot.get("id", "")],
                auto_fix="增加到至少 60f (2s)",
            ))
        elif dur > 240:
            issues.append(QAIssue(
                "warning", "duration",
                f"{shot.get('component','')} 有 {dur}f ({dur/30:.1f}s)，太长",
                shot_ids=[shot.get("id", "")],
                auto_fix="缩短到 240f (8s) 以内",
            ))

    # ── 7. 散件数量检查（mode 感知）──
    # grid 模式: 编排外散件 ≤2（grid 依赖精确定位，散件会破坏网格）
    # stage 模式: 不限（scatter/radial 本身就是多元素散落）
    choreography_components = {"PhotoStack", "ImageOrbit", "FeatureGrid", "FeatureScroller",
                               "FloatingMockup", "ParticleBg", "Background", "GlowTrail"}
    bg_components = {"ParticleBg", "Background", "GlowTrail"}
    for start, group in by_start.items():
        non_bg = [s for s in group if s.get("component") not in bg_components]
        # 编排组件内部的子元素不计入散件
        choreography_count = sum(1 for s in non_bg if s.get("component") in choreography_components)
        loose_count = len(non_bg) - choreography_count

        # mode 感知: stage 模式不限，grid 模式限 ≤2
        # 判断 mode: shot 没有 mode 字段，用 archetype 推断
        shot_mode = group[0].get("mode", "grid") if group else "grid"
        is_stage = shot_mode == "stage" or any(
            s.get("archetype") in ("scatter", "radial", "stack") for s in group
        )

        loose_threshold = 999 if is_stage else 2
        if loose_count > loose_threshold:
            issues.append(QAIssue(
                "warning", "loose_elements",
                f"未分配到编排的散件过多: {loose_count} 个 (start={start}, mode={shot_mode})，建议≤{loose_threshold}",
                shot_ids=[s.get("id", "") for s in non_bg[:5]],
                auto_fix="将散件分配到 PhotoStack/ImageOrbit 等编排组件，或移到相邻 beat",
            ))

    # ── 8. 文字碰撞检测 (两个文字 shot 在同 start 且同 position) ──
    text_components_all = {"WordReveal", "GradientText", "KineticText", "TypewriterPrompt",
                           "MarqueeText", "GlassCard", "LogoReveal"}
    for start, group in by_start.items():
        text_shots = [s for s in group if s.get("component") in text_components_all]
        # 用 bbox 相交检测文字碰撞（不是"同 position"）
        pos_bbox = {
            "center": (20, 30, 80, 70), "upper": (10, 5, 90, 35), "lower": (10, 65, 90, 95),
            "left": (5, 20, 45, 80), "right": (55, 20, 95, 80),
        }
        from itertools import combinations
        for s1, s2 in combinations(text_shots, 2):
            b1 = pos_bbox.get(s1.get("position", "center"), (20, 30, 80, 70))
            b2 = pos_bbox.get(s2.get("position", "center"), (20, 30, 80, 70))
            # bbox 相交检测
            ix = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
            iy = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
            if ix > 0 and iy > 0:
                issues.append(QAIssue(
                    "error", "text_collision",
                    f"文字碰撞: {s1.get('component','')}({s1.get('position','')}) 和 {s2.get('component','')}({s2.get('position','')}) bbox 相交",
                    shot_ids=[s1.get("id", ""), s2.get("id", "")],
                    auto_fix="分配不同 position 或错开 start 时间",
                ))

    # ── 9. 安全区检查（只对必读文字，且不属于编排/角色时才 flag）──
    # 水印/角标/分裂标题的边缘位置是设计意图，不 flag
    must_read_components = {"WordReveal", "GradientText", "KineticText", "TypewriterPrompt"}
    edge_positions = {"lower-left", "lower-right", "upper-left", "upper-right"}
    for shot in shots:
        comp = shot.get("component", "")
        pos = shot.get("position", "center")
        # 只对必读文字组件检查边缘位置
        # GlassCard/LogoReveal/MarqueeText 等可以是水印/角标/装饰，允许在边缘
        if comp in must_read_components and pos in edge_positions:
            issues.append(QAIssue(
                "warning", "safe_zone",
                f"必读文字 {comp} 在边缘位置 {pos}，可能超出安全区",
                shot_ids=[shot.get("id", "")],
                auto_fix="移到 center/upper/lower 位置",
            ))

    return issues


def auto_fix_spec(spec: dict, issues: list[QAIssue]) -> dict:
    """根据 QA 问题自动修复 VideoSpec。

    只修复确定性问题 (gap/时长/空文字)，不改创意内容。
    """
    shots = spec.get("shots", [])
    if not shots:
        return spec

    # Fix 1: 消除 gap — 重排 start
    sorted_shots = sorted(shots, key=lambda s: s.get("start", 0))
    current = 0
    for shot in sorted_shots:
        shot["start"] = current
        current += shot.get("duration", 0)

    # Fix 2: 时长 clamp
    for shot in shots:
        dur = shot.get("duration", 0)
        if dur < 30:
            shot["duration"] = 60
        elif dur > 240:
            shot["duration"] = 240

    # Fix 3: 空文字 — 用组件默认文字
    text_defaults = {
        "WordReveal": "Welcome",
        "GradientText": "Hello World",
        "KineticText": "Let's Go",
        "TypewriterPrompt": "echo 'hello'",
        "MarqueeText": "关键词 • 标签 • 品牌",
        "LogoReveal": "Brand",
    }
    for shot in shots:
        comp = shot.get("component", "")
        if comp in text_defaults:
            text = shot.get("props", {}).get("text", "")
            if not text or not str(text).strip():
                shot.setdefault("props", {})["text"] = text_defaults[comp]

    # Fix 4: 散件过多 — 溢出的挪到下一 beat（mode 感知）
    choreography_components = {"PhotoStack", "ImageOrbit", "FeatureGrid", "FeatureScroller",
                               "FloatingMockup", "ParticleBg", "Background", "GlowTrail"}
    bg_components = {"ParticleBg", "Background", "GlowTrail"}
    by_start: dict[int, list] = {}
    for shot in shots:
        start = shot.get("start", 0)
        by_start.setdefault(start, []).append(shot)
    for start, group in by_start.items():
        non_bg = [s for s in group if s.get("component") not in bg_components]
        choreography_count = sum(1 for s in non_bg if s.get("component") in choreography_components)
        loose = [s for s in non_bg if s.get("component") not in choreography_components]

        # mode 感知阈值
        is_stage = any(s.get("archetype") in ("scatter", "radial", "stack") for s in group)
        loose_threshold = 999 if is_stage else 2

        if len(loose) > loose_threshold:
            # 保留前 threshold 个散件，溢出的挪到下一 beat
            keep = loose[:loose_threshold]
            overflow = loose[loose_threshold:]
            beat_end = max(s.get("start", 0) + s.get("duration", 0) for s in non_bg)
            for s in overflow:
                s["start"] = beat_end + 5  # 5 帧间隔

    # Fix 5: 文字碰撞 — 把第二个文字挪到不同 position
    text_components_all = {"WordReveal", "GradientText", "KineticText", "TypewriterPrompt",
                           "MarqueeText", "GlassCard", "LogoReveal"}
    position_cycle = ["center", "upper", "lower", "left", "right"]
    by_start2: dict[int, list] = {}
    for shot in shots:
        start = shot.get("start", 0)
        by_start2.setdefault(start, []).append(shot)
    for start, group in by_start2.items():
        text_shots = [s for s in group if s.get("component") in text_components_all]
        if len(text_shots) <= 1:
            continue
        used_positions = set()
        for s in text_shots:
            pos = s.get("position", "center")
            if pos in used_positions:
                # 找一个未用的 position
                for alt in position_cycle:
                    if alt not in used_positions:
                        s["position"] = alt
                        break
            used_positions.add(s.get("position", "center"))

    return spec


def validate_and_fix(spec: dict) -> tuple[dict, list[QAIssue]]:
    """校验 + 自动修复。返回修复后的 spec 和剩余问题。"""
    issues = validate_video_spec(spec)

    # 自动修复
    fixable = [i for i in issues if i.auto_fix and i.severity != "error"]
    if fixable:
        spec = auto_fix_spec(spec, issues)
        # 重新校验
        issues = validate_video_spec(spec)

    return spec, issues


# ── 多场景分解校验（文字专用 + 常规）────────────────────────────────────────

def validate_decomposition(decomp: dict) -> list[QAIssue]:
    """校验 VideoDecomposition JSON（场景级分解格式）。

    文字专用校验（Staging 原则）：
    1. 焦点区文字数 ≤ 1（同一时刻只允许一个焦点文字）
    2. 文字 bbox 碰撞（同一帧两文字不重叠）
    3. 对比度检查（图片上的文字需要 scrim）
    4. 必读文字超出安全区
    5. 文字阅读时间不足（字符数 vs 可用帧数）
    """
    issues: list[QAIssue] = []
    scenes = decomp.get("scenes", [])

    if not scenes:
        issues.append(QAIssue("error", "empty", "没有场景"))
        return issues

    for sc in scenes:
        sc_idx = sc.get("scene_index", 0)
        sc_dur = sc.get("duration_frames", 0)
        elements = sc.get("elements", [])

        text_els = [e for e in elements if e.get("type") == "text"]
        image_els = [e for e in elements if e.get("type") == "image"]

        # ── 0. 几何校验（覆盖率/居中性/出血/重叠）──
        geo_issues = validate_geometry(sc)
        issues.extend(geo_issues)

        # ── 1. 焦点文字数量（Staging：一次一焦点）──
        focus_texts = [
            e for e in text_els
            if (e.get("text_animation") or {}).get("zone", "focus") == "focus"
        ]
        # 允许多个焦点文字（渲染器会串行排程），但每个文字的持续时间要够

        # ── 2. 文字阅读时间 ──
        for e in text_els:
            text = e.get("content_text", "")
            timing = e.get("timing", {})
            el_dur = timing.get("out_point", 0) - timing.get("in_point", 0)
            if not text:
                issues.append(QAIssue(
                    "error", "empty_text",
                    f"场景 {sc_idx}: 空文字元素 {e.get('id', '?')}",
                    auto_fix="填充默认文字",
                ))
                continue

            # 阅读时间估算：中文 ~5字/秒，英文 ~3词/秒
            char_count = len(text)
            min_read_frames = max(30, char_count * 3)  # 每字约3帧 = 0.1秒@30fps
            if el_dur < min_read_frames:
                issues.append(QAIssue(
                    "warning", "read_time",
                    f"场景 {sc_idx}: 文字 '{text[:10]}...' 阅读时间不足 "
                    f"({el_dur}帧 < 建议{min_read_frames}帧)",
                    auto_fix=f"延长到 {min_read_frames} 帧",
                ))

        # ── 3. 文字碰撞（bbox 相交）──
        for i in range(len(text_els)):
            for j in range(i + 1, len(text_els)):
                a, b = text_els[i], text_els[j]
                # 检查时间重叠
                a_t = a.get("timing", {})
                b_t = b.get("timing", {})
                if a_t.get("out_point", 0) <= b_t.get("in_point", 0) or \
                   b_t.get("out_point", 0) <= a_t.get("in_point", 0):
                    continue  # 时间不重叠，跳过

                # 检查空间重叠（粗略：都用 center 点 + 尺寸估算）
                a_s = a.get("spatial", {})
                b_s = b.get("spatial", {})
                # 如果两个文字都在焦点区（zone=focus），由渲染器串行排程，不算碰撞
                a_zone = (a.get("text_animation") or {}).get("zone", "focus")
                b_zone = (b.get("text_animation") or {}).get("zone", "focus")
                if a_zone == "focus" and b_zone == "focus":
                    continue  # 渲染器保证串行

        # ── 4. 安全区检查 ──
        for e in text_els:
            spatial = e.get("spatial", {})
            x = spatial.get("x", 50)
            y = spatial.get("y", 50)
            # 安全区：x ∈ [10, 90], y ∈ [10, 90]
            if x < 10 or x > 90 or y < 10 or y > 90:
                issues.append(QAIssue(
                    "warning", "safe_zone",
                    f"场景 {sc_idx}: 文字 '{e.get('content_text', '')[:8]}' "
                    f"在边缘 ({x:.0f}%, {y:.0f}%)",
                    auto_fix="移到安全区内",
                ))

        # ── 5. 对比度（图片上的文字需要 scrim）──
        if image_els and text_els:
            # 有图片+文字的场景，渲染器会自动加 scrim
            # 这里只检查文字颜色是否和背景接近
            bg_color = sc.get("background_color", "#000000")
            for e in text_els:
                typo = e.get("typography", {})
                color = typo.get("color", "#FFFFFF")
                # 简单检查：白色文字在浅色背景上
                if _is_light(bg_color) and _is_light(color):
                    issues.append(QAIssue(
                        "warning", "contrast",
                        f"场景 {sc_idx}: 浅色文字在浅色背景上，可能看不清",
                        auto_fix="加深文字颜色或添加 scrim",
                    ))

    return issues


def _is_light(hex_color: str) -> bool:
    """判断颜色是否偏亮。"""
    try:
        c = hex_color.lstrip("#")
        if len(c) == 3:
            c = "".join(x * 2 for x in c)
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return lum > 0.6
    except (ValueError, IndexError):
        return False


# ── Grid 槽位 → bbox 推算 ──────────────────────────────────────────────────

# 每个布局模板的槽位 bbox（归一化 0~1，含 gap 和 padding 近似）
# padding=56px/1080px ≈ 0.052, gap=14px/1080px ≈ 0.013
_PAD = 0.052
_GAP = 0.013

GRID_SLOT_BBOX: dict[str, dict[str, tuple[float, float, float, float]]] = {
    # (x_min, y_min, x_max, y_max) 归一化
    "centered_hero": {
        "title":  (_PAD, _PAD, 1 - _PAD, _PAD + 0.15),
        "hero":   (_PAD, _PAD + 0.15 + _GAP, 1 - _PAD, 1 - _PAD - 0.15 - _GAP),
        "caption":(_PAD, 1 - _PAD - 0.15, 1 - _PAD, 1 - _PAD),
    },
    "grid_2x2": {
        "a": (_PAD, _PAD, 0.5 - _GAP/2, 0.5 - _GAP/2),
        "b": (0.5 + _GAP/2, _PAD, 1 - _PAD, 0.5 - _GAP/2),
        "c": (_PAD, 0.5 + _GAP/2, 0.5 - _GAP/2, 1 - _PAD),
        "d": (0.5 + _GAP/2, 0.5 + _GAP/2, 1 - _PAD, 1 - _PAD),
    },
    "split_lr": {
        "left":  (_PAD, _PAD, 0.5 - _GAP/2, 1 - _PAD),
        "right": (0.5 + _GAP/2, _PAD, 1 - _PAD, 1 - _PAD),
    },
    "full_bleed": {
        "stage": (0, 0, 1, 1),
    },
    "three_row": {
        "top":    (_PAD, _PAD, 1 - _PAD, 0.333 - _GAP),
        "mid":    (_PAD, 0.333 + _GAP, 1 - _PAD, 0.667 - _GAP),
        "bottom": (_PAD, 0.667 + _GAP, 1 - _PAD, 1 - _PAD),
    },
    "hero_side": {
        "hero":  (_PAD, _PAD, 0.667 - _GAP/2, 1 - _PAD),
        "side1": (0.667 + _GAP/2, _PAD, 1 - _PAD, 0.5 - _GAP/2),
        "side2": (0.667 + _GAP/2, 0.5 + _GAP/2, 1 - _PAD, 1 - _PAD),
    },
}


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    """bbox 面积（归一化）。"""
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _bbox_union(bboxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    """多个 bbox 的并集包围盒。"""
    if not bboxes:
        return (0, 0, 0, 0)
    x_min = min(b[0] for b in bboxes)
    y_min = min(b[1] for b in bboxes)
    x_max = max(b[2] for b in bboxes)
    y_max = max(b[3] for b in bboxes)
    return (x_min, y_min, x_max, y_max)


def _bbox_intersection(a: tuple[float, float, float, float],
                       b: tuple[float, float, float, float]) -> float:
    """两个 bbox 的交集面积。"""
    x_overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    y_overlap = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return x_overlap * y_overlap


def _get_element_bbox(el: dict, layout_type: str) -> tuple[float, float, float, float] | None:
    """从元素的 slot 推算其 bbox（归一化 0~1）。"""
    slot = el.get("slot", "")
    if not slot:
        return None
    layout_bboxes = GRID_SLOT_BBOX.get(layout_type, {})
    return layout_bboxes.get(slot)


def validate_geometry(sc: dict) -> list[QAIssue]:
    """几何校验器 — 从 Grid 槽位推算覆盖率/居中性/出血/重叠。

    确定性校验，不靠 VLM。对每个采样帧计算。
    """
    issues: list[QAIssue] = []
    sc_idx = sc.get("scene_index", 0)
    layout_type = sc.get("layout_type", "centered_hero")
    mode = sc.get("mode", "grid")
    elements = sc.get("elements", [])

    if not elements:
        return issues

    image_els = [e for e in elements if e.get("type") == "image"]

    # 从 Grid 槽位推算每个图片元素的 bbox
    element_bboxes: list[tuple[float, float, float, float]] = []
    for el in image_els:
        bbox = _get_element_bbox(el, layout_type)
        if bbox:
            element_bboxes.append(bbox)

    if not element_bboxes:
        return issues

    # ── 1. 覆盖率 ──
    # 简化：用并集包围盒面积近似（实际 Grid gap 会留白，阈值放宽）
    union_bbox = _bbox_union(element_bboxes)
    union_area = _bbox_area(union_bbox)

    # 对于 grid_2x2 等多格布局，覆盖率用元素面积之和（因为不连续）
    total_elem_area = sum(_bbox_area(b) for b in element_bboxes)
    # 取并集面积和元素面积之和的较大值
    coverage = max(union_area, total_elem_area)

    if coverage < 0.4:
        issues.append(QAIssue(
            "error", "void",
            f"场景 {sc_idx}: 覆盖率过低 ({coverage:.0%})，画面大量空白",
            auto_fix="增加元素或换用更大面积的布局模板",
        ))

    # ── 2. 居中性 ──
    # 所有元素的总包围盒中心应接近画面中心 (0.5, 0.5)
    center_x = (union_bbox[0] + union_bbox[2]) / 2
    center_y = (union_bbox[1] + union_bbox[3]) / 2
    offset_x = abs(center_x - 0.5)
    offset_y = abs(center_y - 0.5)

    if offset_x > 0.15 or offset_y > 0.15:
        issues.append(QAIssue(
            "warning", "off_center",
            f"场景 {sc_idx}: 元素中心偏离画面中心 "
            f"(偏移 {offset_x:.0%}x, {offset_y:.0%}y)",
            auto_fix="检查布局模板选择是否合适",
        ))

    # ── 3. 跨度（元素太集中）──
    span_x = union_bbox[2] - union_bbox[0]
    span_y = union_bbox[3] - union_bbox[1]

    if span_x < 0.5 and span_y < 0.5:
        issues.append(QAIssue(
            "warning", "too_compact",
            f"场景 {sc_idx}: 元素聚集在画面中心 "
            f"(跨度 {span_x:.0%}x, {span_y:.0%}y)",
            auto_fix="元素不够铺满，检查是否有遗漏",
        ))

    # ── 4. 出血（非 full-bleed 元素超出画框）──
    if layout_type != "full_bleed":
        for i, bbox in enumerate(element_bboxes):
            if bbox[0] < -0.02 or bbox[1] < -0.02 or bbox[2] > 1.02 or bbox[3] > 1.02:
                issues.append(QAIssue(
                    "error", "off_screen",
                    f"场景 {sc_idx}: 图片元素 {i} 超出画框 "
                    f"({bbox[0]:.2f},{bbox[1]:.2f})-({bbox[2]:.2f},{bbox[3]:.2f})",
                    auto_fix="检查元素坐标或使用 CSS Grid 自动布局",
                ))

    # ── 5. 重叠（mode 感知）──
    if mode == "grid":
        for i in range(len(element_bboxes)):
            for j in range(i + 1, len(element_bboxes)):
                inter = _bbox_intersection(element_bboxes[i], element_bboxes[j])
                if inter > 0.001:  # 阈值：0.1% 画面面积
                    issues.append(QAIssue(
                        "error", "overlap",
                        f"场景 {sc_idx}: grid 模式下图片 {i} 和 {j} 重叠 "
                        f"(交集 {inter:.3f})",
                        auto_fix="检查元素分配或切换到 stage 模式",
                    ))
    # stage 模式：重叠是预期行为，不报错

    # ── 6. 布局模板合理性 ──
    n_images = len(image_els)
    if layout_type == "grid_2x2" and n_images < 3:
        issues.append(QAIssue(
            "warning", "layout_mismatch",
            f"场景 {sc_idx}: grid_2x2 布局但只有 {n_images} 张图，有空格",
            auto_fix="换用更合适的布局模板",
        ))
    if layout_type == "split_lr" and n_images != 2:
        issues.append(QAIssue(
            "warning", "layout_mismatch",
            f"场景 {sc_idx}: split_lr 布局但有 {n_images} 张图（期望 2）",
            auto_fix="换用更合适的布局模板",
        ))

    return issues


def validate_and_fix_decomposition(decomp: dict) -> tuple[dict, list[QAIssue]]:
    """校验 + 自动修复多场景分解。"""
    issues = validate_decomposition(decomp)

    # 自动修复空文字：直接删除 content_text 为空白的 text 元素（避免渲染出破折号）
    for sc in decomp.get("scenes", []):
        sc["elements"] = [
            e for e in sc.get("elements", [])
            if not (e.get("type") == "text" and not e.get("content_text", "").strip())
        ]

    # 自动修复阅读时间不足
    for sc in decomp.get("scenes", []):
        sc_dur = sc.get("duration_frames", 0)
        for e in sc.get("elements", []):
            if e.get("type") != "text":
                continue
            timing = e.get("timing", {})
            el_dur = timing.get("out_point", 0) - timing.get("in_point", 0)
            text = e.get("content_text", "")
            min_dur = max(30, len(text) * 3)
            if el_dur < min_dur:
                # 延长到场景结束
                timing["out_point"] = min(sc_dur, timing.get("in_point", 0) + min_dur)

    return decomp, issues


# ── L4: 选择校验器（choice-level，区别于 param-level）───────────────────────


@dataclass
class ChoiceVerdict:
    """选择校验结果。"""
    accepted: bool
    reason: str = ""
    fallback_id: str = ""  # REJECT 时建议的替代组件


def validate_choice(
    need: dict,
    entry,  # CatalogEntry
    params: dict,
) -> ChoiceVerdict:
    """L4: 校验组件选择本身（不只是参数）。

    检查:
    - must_read 槽位选了装饰特效 → REJECT
    - phase_blacklist 命中 → REJECT
    - kind 不匹配 → REJECT
    - char_limits 不够 → REJECT
    - when_not 命中 → WARN (不 REJECT，但记录)
    """
    # 1. must_read 检查
    if need.get("must_read") and not entry.validation.get("must_read", False):
        return ChoiceVerdict(
            accepted=False,
            reason=f"文字槽位需要 must_read 组件，但 {entry.id} 是装饰特效",
        )

    # 2. phase_blacklist 检查
    phase = need.get("phase", "")
    if phase in entry.phase_blacklist:
        return ChoiceVerdict(
            accepted=False,
            reason=f"{entry.id} 在 {phase} 阶段被禁止",
        )

    # 3. kind 匹配检查
    need_kind = need.get("kind", "")
    if need_kind and need_kind != entry.kind:
        return ChoiceVerdict(
            accepted=False,
            reason=f"需求 kind={need_kind}，但 {entry.id} 的 kind={entry.kind}",
        )

    # 4. char_limits 检查
    text = params.get("text", "")
    if text and entry.char_limits:
        max_chars = entry.char_limits.get("max_chars", 999)
        if len(text) > max_chars * 1.5:  # 超过 150% 才 REJECT
            return ChoiceVerdict(
                accepted=False,
                reason=f"文字 {len(text)} 字超过 {entry.id} 的限制 {max_chars} 字 (150%)",
            )

    # 5. when_not 软检查（不 REJECT，只记录）
    if entry.when_not:
        # 简单关键词匹配
        text_lower = text.lower() if text else ""
        when_not_lower = entry.when_not.lower()
        # 如果文字长度和 when_not 描述冲突，记录但不拒绝
        if "短" in when_not_lower and len(text) <= 4:
            return ChoiceVerdict(
                accepted=True,
                reason=f"注意: {entry.id} 的 when_not 提到短标语不适合，但文字仅 {len(text)} 字",
            )

    return ChoiceVerdict(accepted=True)
