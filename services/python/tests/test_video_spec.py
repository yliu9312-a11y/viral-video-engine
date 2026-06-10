"""VideoSpec 单元测试
运行: cd services/python && pytest tests/test_video_spec.py -v
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# 确保能 import 同级模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from video_spec_schema import (
    VideoSpec,
    ShotSpec,
    FONT_SIZE_MAP,
    PALETTE_MAP,
    _resolve_props,
    _calc_start,
)


# ── 合法数据 fixture ──────────────────────────────────────

VALID_KINETIC_SHOT = {
    "component": "KineticText",
    "props": {
        "text": "你还在用过期护肤品？",
        "mode": "shake",
        "font_size": "headline",
        "color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 3,
    },
    "duration_frames": 45,
    "phase": "hook",
}

VALID_PRODUCT_SHOT = {
    "component": "ProductShowcase",
    "props": {
        "product_name": "美白精华",
        "price": "¥199",
        "cta": "立即抢购",
    },
    "duration_frames": 60,
    "phase": "build",
}

VALID_PARTICLE_SHOT = {
    "component": "ParticleBg",
    "props": {
        "count": 25,
        "color": "#FFD60A",
        "secondary_color": "#FF416C",
        "style": "float",
        "opacity": 0.3,
    },
    "duration_frames": 105,
    "phase": "hook",
}

VALID_SPEC_DATA = {
    "shots": [VALID_KINETIC_SHOT, VALID_PRODUCT_SHOT, VALID_PARTICLE_SHOT],
    "fps": 30,
    "palette": "beauty",
    "total_duration_frames": 210,  # 45+60+105
}


# ── Test 1: 正常生成 ──────────────────────────────────────

def test_valid_spec_parses():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    assert len(spec.shots) == 3
    assert spec.palette == "beauty"
    assert spec.fps == 30


def test_valid_spec_total_frames():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    assert spec.total_duration_frames == 210
    assert sum(s.duration_frames for s in spec.shots) == 210


# ── Test 2: total_duration_frames 不一致被拒绝 ────────────

def test_total_frames_mismatch_rejected():
    bad = {**VALID_SPEC_DATA, "total_duration_frames": 999}
    with pytest.raises(ValidationError) as exc_info:
        VideoSpec.model_validate(bad)
    assert "total_duration_frames" in str(exc_info.value).lower() or "不一致" in str(exc_info.value)


# ── Test 3: 非法 font_size 被拒绝 ─────────────────────────

def test_invalid_font_size_rejected():
    bad_shot = {
        **VALID_KINETIC_SHOT,
        "props": {**VALID_KINETIC_SHOT["props"], "font_size": "big"},
    }
    bad_spec = {**VALID_SPEC_DATA, "shots": [bad_shot, VALID_PRODUCT_SHOT, VALID_PARTICLE_SHOT]}
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(bad_spec)


# ── Test 4: 非法 palette 被拒绝 ─────────────────────────

def test_invalid_palette_rejected():
    bad = {**VALID_SPEC_DATA, "palette": "purple"}
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(bad)


# ── Test 5: 非法组件名被拒绝 ─────────────────────────────

def test_invalid_component_rejected():
    bad_shot = {**VALID_KINETIC_SHOT, "component": "NonExistentWidget"}
    bad_spec = {**VALID_SPEC_DATA, "shots": [bad_shot, VALID_PRODUCT_SHOT, VALID_PARTICLE_SHOT]}
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(bad_spec)


# ── Test 6: to_render_input() 格式正确 ───────────────────

def test_to_render_input_format():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    render_input = spec.to_render_input()
    assert "shots" in render_input
    assert "globalStyle" in render_input
    assert render_input["fps"] == 30
    assert len(render_input["shots"]) == 3

    first = render_input["shots"][0]
    assert "component" in first
    assert "props" in first
    assert "duration" in first
    assert "start" in first
    assert "role" in first
    assert "id" in first


# ── Test 7: 少于3个 shot 被拒绝 ──────────────────────────

def test_too_few_shots_rejected():
    bad = {
        **VALID_SPEC_DATA,
        "shots": [VALID_KINETIC_SHOT, VALID_PRODUCT_SHOT],
        "total_duration_frames": 105,
    }
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(bad)


# ── Test 8: duration_frames 超出范围被拒绝 ────────────────

def test_duration_frames_out_of_range():
    bad_shot = {**VALID_KINETIC_SHOT, "duration_frames": 5}  # 低于最小值15
    bad_spec = {
        **VALID_SPEC_DATA,
        "shots": [bad_shot, VALID_PRODUCT_SHOT, VALID_PARTICLE_SHOT],
        "total_duration_frames": 170,
    }
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(bad_spec)


# ── Test 9: font_size → fontSize 映射正确 ─────────────────

def test_font_size_mapping():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    render = spec.to_render_input()
    # KineticText 用 font_size="headline" → fontSize=64
    kt_shot = render["shots"][0]
    assert kt_shot["props"]["fontSize"] == 64


# ── Test 10: snake_case → camelCase 转换 ──────────────────

def test_snake_to_camel_conversion():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    render = spec.to_render_input()
    # ProductShowcase: product_name → productName
    ps_shot = render["shots"][1]
    assert "productName" in ps_shot["props"]
    assert ps_shot["props"]["productName"] == "美白精华"


# ── Test 11: start 帧计算正确 ─────────────────────────────

def test_start_frame_calculation():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    render = spec.to_render_input()
    assert render["shots"][0]["start"] == 0
    assert render["shots"][1]["start"] == 45
    assert render["shots"][2]["start"] == 105  # 45+60


# ── Test 12: globalStyle 包含 palette 颜色 ────────────────

def test_global_style_palette():
    spec = VideoSpec.model_validate(VALID_SPEC_DATA)
    render = spec.to_render_input()
    assert render["globalStyle"]["palette"] == "beauty"
    assert render["globalStyle"]["bgColor"] == PALETTE_MAP["beauty"]["primary"]


# ── Test 13: 非法 mode 被拒绝 ─────────────────────────────

def test_invalid_mode_rejected():
    bad_shot = {
        **VALID_KINETIC_SHOT,
        "props": {**VALID_KINETIC_SHOT["props"], "mode": "spin"},  # 非法值
    }
    bad_spec = {**VALID_SPEC_DATA, "shots": [bad_shot, VALID_PRODUCT_SHOT, VALID_PARTICLE_SHOT]}
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(bad_spec)


# ── Test 14: 所有9个组件都可创建 ──────────────────────────

ALL_COMPONENT_SHOTS = [
    {"component": "KineticText", "props": {"text": "test", "mode": "bounce"}, "duration_frames": 45, "phase": "hook"},
    {"component": "ProductShowcase", "props": {"product_name": "test"}, "duration_frames": 45, "phase": "build"},
    {"component": "CountdownTimer", "props": {"countdown": 3}, "duration_frames": 45, "phase": "hook"},
    {"component": "PriceReveal", "props": {"original_price": "¥199", "current_price": "¥99"}, "duration_frames": 45, "phase": "cta"},
    {"component": "BeforeAfter", "props": {}, "duration_frames": 45, "phase": "build"},
    {"component": "BarChart", "props": {"data": [{"label": "A", "value": 10}]}, "duration_frames": 45, "phase": "build"},
    {"component": "NumberRoll", "props": {"value": 1000}, "duration_frames": 45, "phase": "build"},
    {"component": "DonutChart", "props": {"segments": [{"label": "A", "value": 60}]}, "duration_frames": 45, "phase": "build"},
    {"component": "ParticleBg", "props": {"count": 20}, "duration_frames": 45, "phase": "hook"},
]


def test_all_components_valid():
    """所有9个组件都能通过 schema 校验。"""
    # 取前3个做一组测试
    spec_data = {
        "shots": ALL_COMPONENT_SHOTS[:3],
        "fps": 30,
        "palette": "viral",
        "total_duration_frames": 135,
    }
    spec = VideoSpec.model_validate(spec_data)
    assert len(spec.shots) == 3


def test_each_component_individually():
    """每个组件单独测试都能通过。"""
    for shot_data in ALL_COMPONENT_SHOTS:
        spec_data = {
            "shots": [shot_data, VALID_PARTICLE_SHOT, VALID_KINETIC_SHOT],
            "fps": 30,
            "palette": "viral",
            "total_duration_frames": shot_data["duration_frames"] + 105 + 45,
        }
        spec = VideoSpec.model_validate(spec_data)
        assert spec.shots[0].component == shot_data["component"]
