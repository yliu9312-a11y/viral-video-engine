"""Quality fix regression tests.

Run with: python tests/test_quality_fixes.py
No pytest required. Uses assert + __main__ block.
"""

from __future__ import annotations

import sys
import os

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
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    failures: list[str] = []

    for test_fn in [
        test_merge_short_shots,
        test_motion_paths_relative,
        test_inject_texts_per_scene,
        test_extract_style_profile_grade,
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
