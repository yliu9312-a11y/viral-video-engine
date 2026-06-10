"""Mapping from KB atom remotion_component to actual Remotion component names + params.

The KB stores atom descriptions like "ProductZoomFrame", "ComparisonDemo", etc.
This module maps them to the actual Remotion components available in the rendering pipeline.
"""

# Component name mapping: KB atom component → actual Remotion component
COMPONENT_MAP = {
    # Hook phase components
    "TitleBar": "KineticText",
    "FaceCloseupFrame": "KineticText",
    "AttentionGrabber": "CountdownTimer",
    "hook_attention_grabber": "CountdownTimer",

    # Build phase components
    "ProductZoomFrame": "ProductShowcase",
    "ProductShowcase": "ProductShowcase",
    "UsageDemoFrame": "BeforeAfter",
    "ComparisonDemo": "BeforeAfter",
    "BeforeAfterSplit": "BeforeAfter",
    "DataGraphic": "BarChart",
    "FeatureHighlight": "SellingPointCard",
    "IngredientDetail": "SellingPointCard",
    "ProcessStepFrame": "SellingPointCard",
    "TutorialStepFrame": "SellingPointCard",
    "LifestyleFrame": "ParticleBg",
    "BrollFrame": "ParticleBg",
    "ReactionFrame": "KineticText",
    "HandGestureFrame": "KineticText",
    "ScreenRecordFrame": "BarChart",

    # Payoff phase components
    "CTAOverlay": "PriceReveal",
    "CountdownTimer": "CountdownTimer",
    "PriceReveal": "PriceReveal",
    "NumberRoll": "NumberRoll",

    # Generic fallback
    "GenericFrame": "KineticText",
    "StickerPack": "ParticleBg",
}

# Default params per component
DEFAULT_PARAMS = {
    "KineticText": {"mode": "bounce", "fontSize": 64, "color": "#FFFFFF"},
    "CountdownTimer": {"countdown": 3, "color": "#FF416C", "goText": "开始!"},
    "ProductShowcase": {"productName": "", "cta": "了解更多"},
    "BeforeAfter": {"beforeLabel": "Before", "afterLabel": "After"},
    "BarChart": {"data": [{"label": "效果", "value": 85}, {"label": "性价比", "value": 92}]},
    "SellingPointCard": {"points": []},
    "PriceReveal": {"originalPrice": "¥199", "currentPrice": "¥39.9", "badge": "限时特价"},
    "NumberRoll": {"value": 10000, "suffix": "+", "color": "#FFD700"},
    "ParticleBg": {"count": 25, "color": "#FFD700", "style": "float", "opacity": 0.3},
}

# Phase-specific text defaults
PHASE_TEXT_DEFAULTS = {
    "hook": {
        "text": "这款产品太绝了!",
        "mode": "bounce",
        "fontSize": 72,
    },
    "build": {
        "text": "核心卖点展示",
        "mode": "slide",
        "fontSize": 48,
    },
    "payoff_cta": {
        "text": "立即抢购",
        "mode": "shake",
        "fontSize": 56,
    },
}

# Phase-specific price defaults
PHASE_PRICE_DEFAULTS = {
    "hook": {"originalPrice": "¥299", "currentPrice": "¥99", "badge": "新品特惠"},
    "build": {"originalPrice": "¥199", "currentPrice": "¥59.9", "badge": "限时特价"},
    "payoff_cta": {"originalPrice": "¥199", "currentPrice": "¥39.9", "badge": "最后优惠"},
}

# Phase-specific chart defaults
PHASE_CHART_DEFAULTS = {
    "hook": [{"label": "好评率", "value": 98}, {"label": "回购率", "value": 85}],
    "build": [{"label": "效果", "value": 92}, {"label": "性价比", "value": 88}, {"label": "颜值", "value": 95}],
    "payoff_cta": [{"label": "销量", "value": 100}, {"label": "好评", "value": 98}],
}


def map_atom_to_component(atom: dict, phase: str = "build") -> dict:
    """Map a KB atom to an actual Remotion component with params.

    Args:
        atom: KB atom dict with remotion_component, description, fills_shot_types
        phase: which phase this is for (hook/build/payoff_cta)

    Returns:
        dict with 'component' name and 'params' for the Remotion component
    """
    kb_component = atom.get("remotion_component", "GenericFrame")
    actual_component = COMPONENT_MAP.get(kb_component, "KineticText")
    description = atom.get("description", "")

    # Start with defaults
    params = dict(DEFAULT_PARAMS.get(actual_component, {}))

    # Customize based on phase and atom info
    if actual_component == "KineticText":
        phase_defaults = PHASE_TEXT_DEFAULTS.get(phase, PHASE_TEXT_DEFAULTS["build"])
        params.update(phase_defaults)
        # Use atom description as text if it's short enough
        if description and len(description) < 30:
            params["text"] = description

    elif actual_component == "PriceReveal":
        price_defaults = PHASE_PRICE_DEFAULTS.get(phase, PHASE_PRICE_DEFAULTS["build"])
        params.update(price_defaults)

    elif actual_component == "BarChart":
        params["data"] = PHASE_CHART_DEFAULTS.get(phase, PHASE_CHART_DEFAULTS["build"])

    elif actual_component == "SellingPointCard":
        # Extract selling points from description
        if description:
            # Split by common delimiters
            points = [p.strip() for p in description.replace("，", "|").replace(",", "|").split("|") if p.strip()]
            params["points"] = points[:4] if points else [description]

    elif actual_component == "BeforeAfter":
        if "before" in description.lower() or "对比" in description:
            params["beforeLabel"] = "使用前"
            params["afterLabel"] = "使用后"

    return {
        "component": actual_component,
        "params": params,
    }


def get_components_for_phase(atoms: list[dict], phase: str, max_components: int = 3) -> list[dict]:
    """Get mapped components for a list of KB atoms in a specific phase.

    Args:
        atoms: list of KB atom dicts
        phase: which phase
        max_components: max components to return

    Returns:
        list of dicts with 'component' and 'params'
    """
    # Sort by visual_impact_score
    sorted_atoms = sorted(
        atoms,
        key=lambda a: a.get("visual_impact_score", 0),
        reverse=True,
    )

    seen_components = set()
    result = []
    for atom in sorted_atoms:
        mapped = map_atom_to_component(atom, phase)
        # Avoid duplicate components
        if mapped["component"] not in seen_components:
            seen_components.add(mapped["component"])
            result.append(mapped)
            if len(result) >= max_components:
                break

    return result
