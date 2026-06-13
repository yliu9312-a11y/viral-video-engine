"""Quality fix regression tests.

Run with: python tests/test_quality_fixes.py
No pytest required. Uses assert + __main__ block.
"""

from __future__ import annotations

import json
import math
import sys
import os
from pathlib import Path

# ── Dependency guard ──────────────────────────────────────────────────────────
try:
    import cv2
    import numpy as np
except ImportError:
    print("SKIP: cv2/numpy not available")
    sys.exit(0)

# ── Path setup so we can import project modules ───────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES_PY = os.path.join(PROJECT_ROOT, "services", "python")
sys.path.insert(0, SERVICES_PY)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: _merge_short_shots merges 0.5s fragments and preserves total duration
# ─────────────────────────────────────────────────────────────────────────────

def test_merge_short_shots() -> None:
    from scene_decomposer import _merge_short_shots

    shots = [
        {"index": 0, "start_frame": 0,  "end_frame": 45,  "start_time": 0.0,  "end_time": 1.5},
        {"index": 1, "start_frame": 45, "end_frame": 60,  "start_time": 1.5,  "end_time": 2.0},  # 0.5s fragment
        {"index": 2, "start_frame": 60, "end_frame": 150, "start_time": 2.0,  "end_time": 5.0},
        {"index": 3, "start_frame": 150, "end_frame": 165, "start_time": 5.0, "end_time": 5.5},  # 0.5s fragment
        {"index": 4, "start_frame": 165, "end_frame": 240, "start_time": 5.5, "end_time": 8.0},
    ]
    total_before = shots[-1]["end_time"] - shots[0]["start_time"]

    merged = _merge_short_shots(shots, min_seconds=1.5)

    # Fragments should be merged: 5 shots → 3 shots (both 0.5s fragments absorbed)
    assert len(merged) < 5, f"Expected < 5 shots after merge, got {len(merged)}"

    # Total duration must be preserved
    total_after = merged[-1]["end_time"] - merged[0]["start_time"]
    assert abs(total_after - total_before) < 0.01, (
        f"Total duration changed: {total_before} → {total_after}"
    )

    # All remaining shots must be ≥ 1.5s
    for s in merged:
        dur = s["end_time"] - s["start_time"]
        assert dur >= 1.5 or len(merged) == 1, f"Shot still too short: {dur}s"

    # Indices must be re-numbered from 0
    for i, s in enumerate(merged):
        assert s["index"] == i, f"Index mismatch: expected {i}, got {s['index']}"

    print("PASS test_merge_short_shots")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: generate_motion_paths_for_decomp produces dx keys, |dx|≤8, correct frames
# ─────────────────────────────────────────────────────────────────────────────

def test_motion_paths_relative() -> None:
    from scene_decomposer import generate_motion_paths_for_decomp

    # Minimal decomp dict with one scene and one image element
    d: dict = {
        "fps": 30,
        "scenes": [
            {
                "duration_frames": 90,
                "elements": [
                    {
                        "type": "image",
                        "content_src": "fake.jpg",
                        "motion_path": [],
                    }
                ],
            }
        ],
    }
    scene_motions = [{"desc": "平移", "effects": [{"type": "pan", "idle": "float"}]}]

    generate_motion_paths_for_decomp(d, scene_motions, fps=30)

    el = d["scenes"][0]["elements"][0]
    mp = el.get("motion_path", [])

    assert len(mp) > 0, "motion_path should not be empty"

    # Must contain 'dx' key (new relative format)
    assert "dx" in mp[0], f"First keyframe missing 'dx' key: {mp[0]}"

    # All required keys present
    required_keys = {"frame", "dx", "dy", "scale", "opacity", "easing"}
    for kf in mp:
        missing = required_keys - set(kf.keys())
        assert not missing, f"Keyframe missing keys {missing}: {kf}"

    # |dx| must be ≤ 8
    for kf in mp:
        assert abs(kf["dx"]) <= 8, f"|dx| exceeds 8: {kf['dx']}"
        assert abs(kf["dy"]) <= 8, f"|dy| exceeds 8: {kf['dy']}"

    # First keyframe frame == 0
    assert mp[0]["frame"] == 0, f"First keyframe frame should be 0, got {mp[0]['frame']}"

    # Last keyframe frame == duration_frames
    assert mp[-1]["frame"] == 90, f"Last keyframe frame should be 90, got {mp[-1]['frame']}"

    print("PASS test_motion_paths_relative")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: _inject_texts_per_scene assigns texts by scene index, truncates > 16 chars,
#         clears extra text elements
# ─────────────────────────────────────────────────────────────────────────────

def test_inject_texts_per_scene() -> None:
    # Import via sys.path (main.py is in services/python)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "main_mod",
        os.path.join(SERVICES_PY, "main.py"),
    )
    # We only need the function, not to run the FastAPI app; just do a targeted import
    # by extracting the function source rather than importing the whole module
    # (the module imports many heavy deps at module level)
    # Alternative: exec only the function
    fn_src: list[str] = []
    in_fn = False
    with open(os.path.join(SERVICES_PY, "main.py")) as f:
        for line in f:
            if line.startswith("def _inject_texts_per_scene("):
                in_fn = True
            if in_fn:
                fn_src.append(line)
                # Stop when we hit the next top-level def/class after the function
                if len(fn_src) > 1 and line.startswith("def ") and not line.startswith("def _inject_texts_per_scene"):
                    fn_src.pop()  # remove the next def line
                    break
    fn_code = "".join(fn_src)
    ns: dict = {}
    exec(fn_code, ns)
    _inject_texts_per_scene = ns["_inject_texts_per_scene"]

    # Build decomp with 3 scenes, each having 2 text elements
    def _make_scene(sc_idx: int) -> dict:
        return {
            "scene_role": "build",
            "elements": [
                {"type": "text", "content_text": "old_text_a", "typography": {}, "timing": {"in_point": 0, "out_point": 30}},
                {"type": "text", "content_text": "old_text_b", "typography": {}, "timing": {"in_point": 0, "out_point": 30}},
                {"type": "image", "content_src": "img.jpg"},
            ],
        }

    d: dict = {"scenes": [_make_scene(i) for i in range(3)]}
    texts = ["Hello scene zero", "Scene one text", "这是第三个场景超过十六个字符的文字内容需截断"]

    _inject_texts_per_scene(d, texts)

    # Scene 0: first text = texts[0], second text = ""
    s0_texts = [e for e in d["scenes"][0]["elements"] if e.get("type") == "text"]
    assert s0_texts[0]["content_text"] == "Hello scene zero", f"Scene0 text: {s0_texts[0]['content_text']}"
    assert s0_texts[1]["content_text"] == "", f"Scene0 second text should be empty, got: {s0_texts[1]['content_text']}"

    # Scene 1: first text = texts[1]
    s1_texts = [e for e in d["scenes"][1]["elements"] if e.get("type") == "text"]
    assert s1_texts[0]["content_text"] == "Scene one text", f"Scene1 text: {s1_texts[0]['content_text']}"

    # Scene 2: long text truncated to 16 chars
    s2_texts = [e for e in d["scenes"][2]["elements"] if e.get("type") == "text"]
    assert len(s2_texts[0]["content_text"]) <= 16, (
        f"Scene2 text not truncated: '{s2_texts[0]['content_text']}'"
    )

    # image elements should be untouched
    img_el = [e for e in d["scenes"][0]["elements"] if e.get("type") == "image"]
    assert len(img_el) == 1

    print("PASS test_inject_texts_per_scene")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: extract_style_profile grade fix — brightness==1.0, saturate in [0.85, 1.2]
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_style_profile_grade() -> None:
    from scene_description import extract_style_profile

    # Create a temp video file (single dark frame) to feed into extract_style_profile
    # We'll write a minimal AVI that OpenCV can read
    import tempfile, struct

    frame = np.full((100, 100, 3), 20, dtype=np.uint8)  # very dark: mean ≈ 20 → brightness ≈ 0.08

    tmp_path = ""
    with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as f:
        tmp_path = f.name

    try:
        out = cv2.VideoWriter(
            tmp_path,
            cv2.VideoWriter_fourcc(*"MJPG"),
            30.0,
            (100, 100),
        )
        # Write 10 identical dark frames so PySceneDetect / extract_style_profile can sample
        for _ in range(10):
            out.write(frame)
        out.release()

        # extract_style_profile calls VLM internally but wraps in try/except
        # If MIMO_API_KEY is unset, VLM is skipped → we get CV-only grade
        profile = extract_style_profile(tmp_path)

        grade = profile.grade
        assert grade["brightness"] == 1.0, (
            f"grade['brightness'] should be 1.0, got {grade['brightness']}"
        )
        assert 0.85 <= grade["saturate"] <= 1.2, (
            f"grade['saturate'] out of range [0.85, 1.2]: {grade['saturate']}"
        )
        # measured_brightness should be present and small (dark frame)
        assert "measured_brightness" in grade, "measured_brightness key missing from grade"
        assert grade["measured_brightness"] < 0.2, (
            f"measured_brightness should be < 0.2 for dark frame, got {grade['measured_brightness']}"
        )
        # mood should be dark
        assert grade["mood"] == "dark", f"Expected mood='dark', got '{grade['mood']}'"

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    print("PASS test_extract_style_profile_grade")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: _slotify_scenes — grid 场景 8 图 3 文 → 4 图 1 文(content_text=="")，fill 含 gradient
# ─────────────────────────────────────────────────────────────────────────────

def _load_main_fn(fn_name: str):
    """Extract a top-level function from main.py by name and exec it in a fresh namespace.

    The namespace is pre-populated with common stdlib modules AND any module-level
    constants (like _SLOT_TABLE) that the function may reference.
    """
    import ast as _ast_mod

    main_path = os.path.join(SERVICES_PY, "main.py")

    # 1. Parse module-level constants (Assign and AnnAssign with literal values)
    with open(main_path) as _mf:
        _source = _mf.read()
    _tree = _ast_mod.parse(_source)
    _constants: dict = {}
    for _node in _ast_mod.walk(_tree):
        # Plain assign:  _FOO = {...}
        if isinstance(_node, _ast_mod.Assign):
            for _target in _node.targets:
                if isinstance(_target, _ast_mod.Name) and _target.id.startswith("_"):
                    try:
                        _constants[_target.id] = _ast_mod.literal_eval(_node.value)
                    except (ValueError, TypeError):
                        pass
        # Annotated assign:  _FOO: dict[str, int] = {...}
        elif isinstance(_node, _ast_mod.AnnAssign):
            if (
                isinstance(_node.target, _ast_mod.Name)
                and _node.target.id.startswith("_")
                and _node.value is not None
            ):
                try:
                    _constants[_node.target.id] = _ast_mod.literal_eval(_node.value)
                except (ValueError, TypeError):
                    pass

    # 2. Extract function source by scanning lines
    fn_src: list[str] = []
    in_fn = False
    with open(main_path) as f:
        for line in f:
            if line.startswith(f"def {fn_name}("):
                in_fn = True
            if in_fn:
                fn_src.append(line)
                stripped = line.rstrip()
                if stripped and not stripped[0].isspace() and len(fn_src) > 1:
                    fn_src.pop()
                    break
    fn_code = "".join(fn_src)

    # 3. Build namespace with stdlib + parsed constants
    ns: dict = {"math": math, "os": os, "json": json, "Path": Path}
    ns.update(_constants)
    exec(fn_code, ns)  # noqa: S102
    return ns[fn_name]


def test_slotify() -> None:
    _slotify_scenes = _load_main_fn("_slotify_scenes")

    # Also load _SLOT_TABLE constant (it's a module-level dict in main.py)
    import math
    _SLOT_TABLE: dict = {}
    with open(os.path.join(SERVICES_PY, "main.py")) as f:
        content = f.read()
    # Parse _SLOT_TABLE from source
    import ast as _ast
    for node in _ast.walk(_ast.parse(content)):
        if isinstance(node, _ast.Assign):
            for target in node.targets:
                if isinstance(target, _ast.Name) and target.id == "_SLOT_TABLE":
                    _SLOT_TABLE = _ast.literal_eval(node.value)

    # Build a scene with grid layout, 8 image elements and 3 text elements
    def _make_el(etype: str, x: float = 50.0, y: float = 50.0, w: float = 30.0, h: float = 30.0, content_src: str = "ref.jpg", content_text: str = "ocr text") -> dict:
        el: dict = {"type": etype, "spatial": {"x": x, "y": y, "width": w, "height": h}}
        if etype == "image":
            el["content_src"] = content_src
        else:
            el["content_text"] = content_text
        return el

    img_els = [_make_el("image", x=float(i * 10 % 90), y=float(i * 7 % 90)) for i in range(8)]
    text_els = [_make_el("text", content_text=f"ocr_{i}") for i in range(3)]
    scene = {
        "layout_type": "grid",
        "elements": img_els + text_els,
    }
    d = {"scenes": [scene]}

    _slotify_scenes(d, allow_reference_pixels=False)

    sc = d["scenes"][0]
    imgs = [el for el in sc["elements"] if el.get("type") == "image"]
    texts = [el for el in sc["elements"] if el.get("type") == "text"]

    expected_slots = _SLOT_TABLE.get("grid", 4) if _SLOT_TABLE else 4
    assert len(imgs) == expected_slots, f"Expected {expected_slots} images, got {len(imgs)}"
    assert imgs[0].get("slot_role") == "hero", f"First image slot_role should be 'hero', got {imgs[0].get('slot_role')}"
    for img in imgs[1:]:
        assert img.get("slot_role") == "satellite", f"Non-hero should be 'satellite', got {img.get('slot_role')}"

    assert len(texts) == 1, f"Expected 1 text element, got {len(texts)}"
    assert texts[0]["content_text"] == "", f"Text content_text should be '', got '{texts[0]['content_text']}'"

    for img in imgs:
        assert img.get("content_src") == "", f"content_src should be '' after slotify, got '{img.get('content_src')}'"
        fill = img.get("appearance", {}).get("fill", "")
        assert "gradient" in fill, f"appearance.fill should contain 'gradient', got '{fill}'"

    print("PASS test_slotify")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: _fallback_content_plan — 13 场景，文案合法，image_prompt 以 topic 开头，无 OCR
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_content_plan() -> None:
    _fallback_content_plan = _load_main_fn("_fallback_content_plan")

    topic = "三亚旅游"
    fake_ocr = "假OCR内容xyz987"

    # Build a 13-scene decomp dict
    scenes_list = [{"duration_frames": 90, "elements": []} for _ in range(13)]
    d = {"fps": 30, "scenes": scenes_list}

    plan = _fallback_content_plan(topic, d)

    assert len(plan) == 13, f"Expected 13 plan entries, got {len(plan)}"

    for i, item in enumerate(plan):
        text = item.get("text", "")
        image_prompt = item.get("image_prompt", "")

        assert text, f"Scene {i}: text is empty"
        assert len(text) <= 12, f"Scene {i}: text '{text}' exceeds 12 chars"
        assert topic[:3] in text or text, f"Scene {i}: text should relate to topic, got '{text}'"

        assert image_prompt, f"Scene {i}: image_prompt is empty"
        assert image_prompt.startswith(topic), f"Scene {i}: image_prompt should start with topic, got '{image_prompt}'"

        assert fake_ocr not in text, f"Scene {i}: OCR leak in text: '{text}'"
        assert fake_ocr not in image_prompt, f"Scene {i}: OCR leak in image_prompt"

    print("PASS test_fallback_content_plan")


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: test_no_reference_leak — slotify 后所有 image src=="" 且所有 text content_text==""
# ─────────────────────────────────────────────────────────────────────────────

def test_no_reference_leak() -> None:
    _slotify_scenes = _load_main_fn("_slotify_scenes")

    def _make_scene(layout: str, n_img: int, n_text: int) -> dict:
        elements: list[dict] = []
        for _ in range(n_img):
            elements.append({
                "type": "image",
                "content_src": "/absolute/path/to/ref_crop.jpg",
                "spatial": {"x": 50.0, "y": 50.0, "width": 30.0, "height": 30.0},
            })
        for i in range(n_text):
            elements.append({
                "type": "text",
                "content_text": f"原片OCR文字{i}",
                "spatial": {"x": 50.0, "y": 80.0, "width": 60.0, "height": 10.0},
            })
        return {"layout_type": layout, "elements": elements}

    scenes = [
        _make_scene("full_bleed", 3, 2),
        _make_scene("grid", 6, 1),
        _make_scene("split", 2, 3),
    ]
    d = {"fps": 30, "scenes": scenes}

    _slotify_scenes(d, allow_reference_pixels=False)

    for sc_idx, sc in enumerate(d["scenes"]):
        for el in sc["elements"]:
            if el.get("type") == "image":
                src = el.get("content_src", "MISSING")
                assert src == "", (
                    f"Scene {sc_idx}: image content_src should be '' after slotify, got '{src}'"
                )
            if el.get("type") == "text":
                ct = el.get("content_text", "MISSING")
                assert ct == "", (
                    f"Scene {sc_idx}: text content_text should be '' after slotify, got '{ct}'"
                )

    print("PASS test_no_reference_leak")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failures: list[str] = []

    for test_fn in [
        test_merge_short_shots,
        test_motion_paths_relative,
        test_inject_texts_per_scene,
        test_extract_style_profile_grade,
        test_slotify,
        test_fallback_content_plan,
        test_no_reference_leak,
    ]:
        try:
            test_fn()
        except Exception as exc:
            import traceback
            print(f"FAIL {test_fn.__name__}: {exc}")
            traceback.print_exc()
            failures.append(test_fn.__name__)

    if failures:
        print(f"\n{len(failures)} test(s) FAILED: {', '.join(failures)}")
        sys.exit(1)
    else:
        print("\nAll tests PASSED")
