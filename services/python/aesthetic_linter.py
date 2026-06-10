"""Aesthetic Linter — 渲染前校验视觉美感规则。

基于 vst_aesthetic_engineering_guide.md 的美感规则。
在 S3 策略生成后、S4 渲染前运行，不达标则自动修复或报错。
"""

import re
from dataclasses import dataclass, field


@dataclass
class LintError:
    severity: str  # "error" | "warning"
    rule: str  # iron rule number
    message: str
    phase: str = ""
    auto_fix: str = ""  # description of auto-fix applied


@dataclass
class LintResult:
    errors: list[LintError] = field(default_factory=list)
    auto_fixes: int = 0

    @property
    def passed(self) -> bool:
        return not any(e.severity == "error" for e in self.errors)

    def summary(self) -> str:
        errors = [e for e in self.errors if e.severity == "error"]
        warnings = [e for e in self.errors if e.severity == "warning"]
        parts = []
        if errors:
            parts.append(f"{len(errors)} errors")
        if warnings:
            parts.append(f"{len(warnings)} warnings")
        if self.auto_fixes:
            parts.append(f"{self.auto_fixes} auto-fixes")
        return ", ".join(parts) if parts else "all checks passed"


# ── Design tokens (must match web/src/design-tokens/index.ts) ──

FONT_SIZES = {"display": 96, "headline": 64, "body": 40, "caption": 28}
FONT_SIZE_NAMES = set(FONT_SIZES.keys())

CAPTION_STYLES = {"black_pill", "outlined_white", "highlight_keyword"}

PALETTES = {"beauty", "digital", "food", "viral"}

SAFE_ZONE = {"top": 200, "bottom": 320, "left": 60, "right": 120}

# Max Chinese chars per subtitle line
MAX_CHINESE_CHARS = 18

# Minimum average shot length in seconds
MIN_AVG_SHOT_LENGTH = 1.0

# Max display font usage per video
MAX_DISPLAY_USAGE = 2

# Max caption styles per video
MAX_CAPTION_STYLES = 2


def _count_chinese(text: str) -> int:
    """Count Chinese characters in text."""
    return len(re.findall(r'[一-鿿]', text))


def _luminance(hex_color: str) -> float:
    """Calculate relative luminance for contrast ratio."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return 0
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255

    def to_linear(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * to_linear(r) + 0.7152 * to_linear(g) + 0.0722 * to_linear(b)


def _contrast_ratio(fg: str, bg: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    l1 = _luminance(fg)
    l2 = _luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def lint_assignment(assignment: dict, template: dict = None) -> LintResult:
    """Lint a material_assignment.json against aesthetic rules.

    Args:
        assignment: material_assignment dict with phases
        template: optional StructureTemplate for additional checks

    Returns:
        LintResult with errors/warnings and auto-fix count
    """
    result = LintResult()
    phases = assignment.get("phases", [])

    # ── Rule 1: Safe zone (checked at component level, warn here) ──

    # ── Rule 2+3: Font size must be from 4-tier system ──
    for phase in phases:
        phase_name = phase.get("phase", "")
        for action in phase.get("completion_actions", []):
            params = action.get("params", {})
            # Check fontSize if present
            fs = params.get("fontSize")
            if fs is not None and isinstance(fs, (int, float)):
                # Map to nearest valid size
                valid_sizes = list(FONT_SIZES.values())
                nearest = min(valid_sizes, key=lambda x: abs(x - fs))
                if fs not in valid_sizes:
                    result.errors.append(LintError(
                        severity="warning",
                        rule="2",
                        message=f"Phase '{phase_name}': fontSize {fs}px not in 4-tier system, nearest is {nearest}px",
                        phase=phase_name,
                        auto_fix=f"fontSize {fs} → {nearest}",
                    ))
                    params["fontSize"] = nearest
                    result.auto_fixes += 1

    # ── Rule 4: Max 2 caption styles per video ──
    styles_used = set()
    for phase in phases:
        for action in phase.get("completion_actions", []):
            params = action.get("params", {})
            style = params.get("style")
            if style and style in CAPTION_STYLES:
                styles_used.add(style)
    if len(styles_used) > MAX_CAPTION_STYLES:
        result.errors.append(LintError(
            severity="error",
            rule="4",
            message=f"caption_style 种类过多 ({len(styles_used)} > {MAX_CAPTION_STYLES}), 会显得廉价",
        ))

    # ── Rule 5: Palette consistency ──
    palettes_used = set()
    for phase in phases:
        for action in phase.get("completion_actions", []):
            params = action.get("params", {})
            palette = params.get("palette")
            if palette and palette in PALETTES:
                palettes_used.add(palette)
    if len(palettes_used) > 1:
        result.errors.append(LintError(
            severity="error",
            rule="5",
            message=f"palette 不一致: {', '.join(palettes_used)}, 整个视频必须用同一个 palette",
        ))

    # ── Rule 5: Display font max 2 times ──
    display_count = 0
    for phase in phases:
        for action in phase.get("completion_actions", []):
            params = action.get("params", {})
            if params.get("fontSize") == FONT_SIZES["display"]:
                display_count += 1
    if display_count > MAX_DISPLAY_USAGE:
        result.errors.append(LintError(
            severity="warning",
            rule="2",
            message=f"display 字号使用 {display_count} 次 (> {MAX_DISPLAY_USAGE}), 视觉冲击会被稀释",
        ))

    # ── Rule 7: Average shot length ──
    for phase in phases:
        phase_name = phase.get("phase", "")
        materials = phase.get("materials", [])
        total_dur = phase.get("total_duration_s", 0)
        if materials and total_dur > 0:
            avg_shot = total_dur / len(materials)
            if avg_shot < MIN_AVG_SHOT_LENGTH:
                result.errors.append(LintError(
                    severity="warning",
                    rule="7",
                    message=f"Phase '{phase_name}': 平均 shot 长度 {avg_shot:.1f}s < {MIN_AVG_SHOT_LENGTH}s, 会像快闪 PPT",
                    phase=phase_name,
                ))

    # ── Rule 6: Text length check ──
    for phase in phases:
        phase_name = phase.get("phase", "")
        for action in phase.get("completion_actions", []):
            params = action.get("params", {})
            text = params.get("text", "")
            if isinstance(text, str):
                cn_count = _count_chinese(text)
                if cn_count > MAX_CHINESE_CHARS:
                    result.errors.append(LintError(
                        severity="warning",
                        rule="6",
                        message=f"Phase '{phase_name}': 字幕 {cn_count} 字 > {MAX_CHINESE_CHARS} 字, 需要换行",
                        phase=phase_name,
                    ))

    return result


def lint_and_fix(assignment: dict, template: dict = None) -> tuple[dict, LintResult]:
    """Lint and auto-fix an assignment.

    Returns:
        (fixed_assignment, lint_result)
    """
    result = lint_assignment(assignment, template)

    # Apply auto-fixes
    for phase in assignment.get("phases", []):
        for action in phase.get("completion_actions", []):
            params = action.get("params", {})
            fs = params.get("fontSize")
            if fs is not None and isinstance(fs, (int, float)) and fs not in FONT_SIZES.values():
                valid_sizes = list(FONT_SIZES.values())
                params["fontSize"] = min(valid_sizes, key=lambda x: abs(x - fs))

    return assignment, result
