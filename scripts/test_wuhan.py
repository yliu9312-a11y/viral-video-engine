#!/usr/bin/env python3
"""武汉文化主题迁移 — 完整管线。

S0 分解 → S3 缺口 + Strategy D (Gemini 图片生成) → LLM 编排 → 渲染
"""
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "python"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

VIDEO_PATH = PROJECT_ROOT / "123605298.mov"
TOPIC = "武汉文化"
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "wuhan_test2"


def step(msg: str):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


# ── Gemini 图片生成 ────────────────────────────────────────────────────────

# 每个 phase 的图片 prompt 模板
SCENE_PROMPTS = {
    "hook": [
        "Yellow Crane Tower (黄鹤楼) cinematic aerial, golden hour, dramatic sky, 4K",
        "Wuhan Yangtze River Bridge sunset, city skyline reflection, warm tones",
        "Hot dry noodles (热干面) steam rising close-up, street food stall, warm light",
        "Wuhan city skyline at blue hour, rivers merging, modern buildings, cinematic",
        "Cherry blossoms at Wuhan University (武汉大学樱花), pink petals, dreamy spring",
        "Wuhan street food market (户部巷) at night, neon lights, vibrant atmosphere",
    ],
    "build": [
        "East Lake (东湖) greenway, cherry blossoms path, spring sunlight, serene 4K",
        "Hubu Xiang (户部巷) food street night, neon signs, bustling crowds, warm tones",
        "Wuhan ferry crossing Yangtze, city lights on water, blue hour, cinematic",
        "Wuhan University cherry blossoms campus, pink canopy, students walking, dreamy",
        "Wuhan Yangtze River Bridge double decker, trains and cars, engineering marvel",
        "Wuhan Guode Temple (古德寺) Buddhist architecture, unique blend style, golden light",
        "Wuhan Jianghan Road (江汉路) pedestrian street, historic buildings, modern shops",
        "Wuhan skyline with Yangtze River, green bridge, panoramic view, golden hour",
    ],
    "cta": [
        "Wuhan panorama from Yellow Crane Tower, rivers merging, dramatic clouds, epic",
        "Wuhan morning street life, breakfast culture (过早), warm daily scene",
        "Wuhan night skyline, colorful lights, river reflection, celebration atmosphere",
        "Wuhan Yellow Crane Tower at night, illuminated, golden glow, majestic",
    ],
}


def generate_scene_images(topic: str, scenes: list[dict], output_dir: str, style_profile=None) -> dict:
    """为每个场景生成 Gemini 图片。返回 {scene_index: [image_paths]}。"""
    from gemini_imager import generate_image

    img_dir = output_dir / "generated"
    img_dir.mkdir(parents=True, exist_ok=True)

    # 分配 phase
    n = len(scenes)
    scene_images = {}
    gen_count = 0

    for i, sc in enumerate(scenes):
        if i == 0 or i <= n * 0.25:
            phase = "hook"
        elif i >= n * 0.75:
            phase = "cta"
        else:
            phase = "build"

        prompts = SCENE_PROMPTS.get(phase, SCENE_PROMPTS["build"])

        # 按场景元素数生成对应数量的图片
        n_elements = len(sc.get("elements", []))
        n_imgs = max(2, min(n_elements, 6))  # 每场景 2-6 张

        paths = []
        for j in range(n_imgs):
            fname = f"s{i}_gen_{j}.png"
            fpath = str(img_dir / fname)
            # 已有图片直接复用（但也确保复制到 public）
            if Path(fpath).exists():
                public_dst = PROJECT_ROOT / "web" / "public" / "data" / "output" / output_dir.name / "generated" / fname
                public_dst.parent.mkdir(parents=True, exist_ok=True)
                if not public_dst.exists():
                    shutil.copy2(fpath, public_dst)
                paths.append(fname)
                gen_count += 1
                continue
            prompt = prompts[j % len(prompts)]
            print(f"  Scene {i} [{phase}] img{j}: 生成...")
            result = generate_image(prompt, fpath, width=1280, height=720, style_profile=style_profile)
            if result:
                # 复制到 web/public（Remotion staticFile 需要）
                public_dst = PROJECT_ROOT / "web" / "public" / "data" / "output" / output_dir.name / "generated" / fname
                public_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(result, public_dst)
                # 也复制到 output_dir 根目录
                shutil.copy2(result, output_dir / fname)
                paths.append(fname)
                gen_count += 1
                print(f"    ✅ {fname}")
            else:
                print(f"    ❌ 生成失败")

        scene_images[i] = paths

    print(f"  共生成 {gen_count} 张图片")
    return scene_images


# ── VLM 运动分析 ────────────────────────────────────────────────────────────

def vlm_analyze_motion(video_path: str, scenes: list[dict]) -> list[dict]:
    """用 VLM 分析每个场景的运动模式。

    从每个场景取相邻帧对，让 VLM 描述运动。
    返回每个场景的运动描述列表。
    """
    import cv2, base64
    sys.path.insert(0, str(PROJECT_ROOT / "services" / "python"))
    from scene_description import _vlm_call

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    # 运动类型关键词 → 动画参数映射
    MOTION_MAP = {
        "平移": {"type": "slide", "idle": "float"},
        "旋转": {"type": "3d", "idle": "rotate"},
        "缩放": {"type": "scale", "idle": "breathe"},
        "淡入淡出": {"type": "fade", "idle": "float"},
        "弹性": {"type": "scale", "idle": "elastic_pop"},
        "级联": {"type": "slide", "idle": "float"},
        "飘浮": {"type": "fade", "idle": "float"},
        "拉伸": {"type": "scale", "idle": "breathe"},
    }

    scene_motions = []
    for sc in scenes:
        start_f = sc.get("start_frame", 0)
        end_f = sc.get("end_frame", total)
        # 取场景中间偏前的两帧
        mid_f = start_f + int((end_f - start_f) * 0.3)
        gap = max(2, int(fps * 0.15))  # 0.15s 间隔

        frames_b64 = []
        for pos in [mid_f, min(mid_f + gap, end_f - 1)]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ret, frame = cap.read()
            if ret:
                _, buf = cv2.imencode('.jpg', frame)
                frames_b64.append(base64.b64encode(buf).decode())

        motion_desc = ""
        if len(frames_b64) == 2:
            prompt = (
                "这是视频中相邻两帧。分析运动：\n"
                "1. 元素运动类型（平移/旋转/缩放/淡入淡出/弹性/级联出现/飘浮）\n"
                "2. 运动方向和速度\n"
                "3. 整体节奏\n"
                "只回答运动类型关键词，用/分隔，如：旋转/弹性/级联。30字以内。"
            )
            motion_desc = _vlm_call(frames_b64, prompt) or ""

        # 解析 VLM 描述 → 动画参数
        matched = []
        for keyword, params in MOTION_MAP.items():
            if keyword in motion_desc:
                matched.append(params)

        # 至少给一个默认动效
        if not matched:
            matched = [{"type": "fade", "idle": "float"}]

        scene_motions.append({
            "desc": motion_desc,
            "effects": matched,
        })
        print(f"  Scene {sc.get('scene_index',0)}: {motion_desc[:50]}")

    cap.release()
    return scene_motions


# ── 主流程 ──────────────────────────────────────────────────────────────────

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ── S0: 分解参考视频 ──
    step("S0 场景分解")
    from scene_decomposer import (
        decompose_video, decomposition_to_dict, decomposition_from_dict,
        decomposition_to_orchestrator_template,
    )

    decomp_json = OUTPUT_DIR / "decomposition.json"
    if decomp_json.exists():
        print("  使用缓存")
        with open(decomp_json) as f:
            d = json.load(f)
        decomp = decomposition_from_dict(d)
        # 不再调 decomposition_to_dict — 缓存已有正确 scene-local timing
    else:
        t = time.time()
        decomp = decompose_video(str(VIDEO_PATH), output_dir=str(OUTPUT_DIR))
        d = decomposition_to_dict(decomp)
        with open(decomp_json, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print(f"  耗时: {round(time.time()-t, 1)}s")

    print(f"  {len(decomp.scenes)} 场景, {sum(len(s.elements) for s in decomp.scenes)} 元素")

    # ── 提取 StyleProfile（CV + VLM 视觉风格）──
    step("提取 StyleProfile — 参考视频的视觉风格")
    from scene_description import extract_style_profile
    style_profile = extract_style_profile(str(VIDEO_PATH))
    print(f"  风格家族: {style_profile.style_family}")
    print(f"  调色板: bg={style_profile.palette['bg_color']}, accent={style_profile.palette['accent']}")
    print(f"  影调: mood={style_profile.grade['mood']}, brightness={style_profile.grade['brightness']}")
    print(f"  FX: vignette={style_profile.fx['vignette']}, grain={style_profile.fx['film_grain']}, glow={style_profile.fx['glow']}")
    print(f"  排版: weight={style_profile.typography['weight']}, glow_text={style_profile.typography['glow_text']}")

    # ── VLM 运动分析（提取参考视频的真实运动语言）──
    step("VLM 运动分析 — 提取参考视频的运动模式")
    scene_motions = vlm_analyze_motion(str(VIDEO_PATH), d["scenes"])

    # ── 生成 motion_path 关键帧（VLM 动画类型 → 连续运动轨迹）──
    step("生成 motion_path 关键帧")
    from scene_decomposer import generate_motion_paths_for_decomp
    generate_motion_paths_for_decomp(d, scene_motions, fps=d.get("fps", 30))
    # 统计
    total_mp = sum(1 for sc in d["scenes"]
                   for el in sc["elements"]
                   if el.get("type") == "image" and len(el.get("motion_path", [])) > 2)
    print(f"  {total_mp} 个元素有连续运动轨迹")

    # ── Gemini 生成主题图片（不复用原视频裁剪图）──
    step("Gemini 生成主题图片")
    scene_images = generate_scene_images(TOPIC, d["scenes"], OUTPUT_DIR, style_profile=style_profile)

    # 替换 content_src 为 Gemini 生成的图
    for i, sc in enumerate(d["scenes"]):
        imgs = scene_images.get(i, [])
        img_idx = 0
        for el in sc["elements"]:
            if el.get("type") == "image":
                if img_idx < len(imgs):
                    el["content_src"] = f"data/output/{OUTPUT_DIR.name}/generated/{imgs[img_idx]}"
                    img_idx += 1
                else:
                    el["content_src"] = ""  # 没有生成图的元素清空

    # ── LLM 编排文字 ──
    step("S4 LLM 编排 — 武汉文化文字")
    template = decomposition_to_orchestrator_template(decomp, topic=TOPIC)
    from animation_orchestrator import orchestrate_from_beats

    llm_texts = {}
    try:
        spec = await orchestrate_from_beats(template, topic=TOPIC, verify=False)
        for shot in spec.get("shots", []):
            role = shot.get("role", "")
            text = shot.get("props", {}).get("text", "")
            if role and text:
                llm_texts.setdefault(role, []).append(text)
        print(f"  ✅ {len(spec.get('shots',[]))} shots")
    except Exception as e:
        print(f"  ⚠️ 编排失败: {e}")

    # ── 注入文字 + 分配动效（基于 VLM 运动分析）──
    step("注入文字 + 分配动效（基于 VLM 运动分析）")
    ROLE_TO_PHASE = {"unknown": "build", "hook": "hook", "feature": "build", "cta": "cta"}

    phase_idx = {"hook": 0, "build": 0, "cta": 0}
    for sc_idx, sc in enumerate(d["scenes"]):
        phase = ROLE_TO_PHASE.get(sc.get("scene_role", "unknown"), "build")
        texts = llm_texts.get(phase, [])
        idx = phase_idx.get(phase, 0)

        # 从 VLM 运动分析获取动效
        motion = scene_motions[sc_idx] if sc_idx < len(scene_motions) else {}
        effects = motion.get("effects", [{"type": "fade", "idle": "float"}])

        for el_idx, el in enumerate(sc["elements"]):
            if el.get("type") == "text" and texts:
                if idx >= len(texts):
                    el["content_text"] = ""  # 用完不循环
                    continue
                new_text = texts[idx]
                if len(new_text) > 14:
                    new_text = new_text[:14]
                el["content_text"] = new_text
                # 字号 (vh 单位)
                typo = el.get("typography", {})
                n = len(new_text)
                typo["font_size"] = 6 if n <= 4 else (4.5 if n <= 8 else 3.5)
                el["typography"] = typo
                # 时长 ≥0.5s
                timing = el.get("timing", {})
                min_frames = max(15, len(new_text) * 3)
                if timing.get("out_point", 0) - timing.get("in_point", 0) < min_frames:
                    timing["out_point"] = timing.get("in_point", 0) + min_frames
                el["timing"] = timing
                # 重新分配文字动画（VLM 分析的原视频风格）
                # 原视频用 typewriter/blur_in/mask_reveal，不要全用 word_stagger
                if len(new_text) <= 4:
                    entrance, split = "char_pop", "char"
                elif len(new_text) <= 10:
                    # 短句用 typewriter（原视频最常用）
                    entrance, split = "typewriter", "char"
                else:
                    # 长句用 blur_in（原视频的模糊→清晰效果）
                    entrance, split = "blur_in", "word"
                el["text_animation"] = {
                    "entrance": entrance,
                    "exit": "fade_up",
                    "split_mode": split,
                    "direction": "center",
                    "zone": "focus",
                }
                idx += 1
                phase_idx[phase] = idx

            if el.get("type") == "image":
                # 从 VLM 运动分析 + 混搭分配动效
                # 不同元素用不同 idle 动画，避免同步运动看起来像静止
                idle_pool = ["float", "breathe", "rotate", "elastic_pop", "2_5d_push"]
                eff = effects[el_idx % len(effects)]
                # 混搭: 用 VLM 分析的 + 池中的不同动画
                el["effect_type"] = idle_pool[(sc_idx + el_idx) % len(idle_pool)]
                timing = el.get("timing", {})
                if not timing.get("entrance"):
                    timing["entrance"] = {
                        "type": eff.get("type", "fade"),
                        "direction": ["left", "right", "top", "bottom"][el_idx % 4],
                        "duration": 6,
                    }
                if not timing.get("exit"):
                    timing["exit"] = {"type": "fade", "duration": 3}

    # 保存（含 StyleProfile）
    d["style_profile"] = style_profile.to_dict()
    with open(decomp_json, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    # ── 渲染 ──
    step("Remotion 渲染 — MultiSceneVideo")
    public_data = PROJECT_ROOT / "web" / "public" / "data" / "output" / OUTPUT_DIR.name / "generated"
    public_data.mkdir(parents=True, exist_ok=True)

    # 用 dict 浅拷贝 + 重算场景边界（deepcopy 会破坏渲染数据）
    render_scenes = []
    frame = 0
    for sc in d["scenes"]:
        sc_copy = dict(sc)
        sc_copy["start_frame"] = frame
        sc_copy["end_frame"] = frame + sc["duration_frames"]
        frame += sc["duration_frames"]
        render_scenes.append(sc_copy)

    render_decomp = {
        "canvas_width": d["canvas_width"],
        "canvas_height": d["canvas_height"],
        "fps": d["fps"],
        "total_frames": frame,
        "scenes": render_scenes,
    }

    w = d["canvas_width"] or 1280
    h = d["canvas_height"] or 720
    output_video = OUTPUT_DIR / "wuhan_culture.mp4"

    import subprocess
    cmd = [
        "npx", "remotion", "render",
        str(PROJECT_ROOT / "web" / "src" / "remotion" / "index.ts"),
        "MultiSceneVideo", str(output_video),
        f"--props={json.dumps({'decomposition': render_decomp})}",
        "--fps=30", f"--width={w}", f"--height={h}",
        f"--duration-in-frames={frame}", "--codec=h264",
    ]
    print(f"  {w}×{h}, {frame}f ({frame/30:.1f}s)")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT / "web"), capture_output=True, text=True, timeout=600)
    if result.returncode == 0:
        mb = output_video.stat().st_size / 1024 / 1024
        print(f"  ✅ {output_video} ({mb:.1f}MB)")
    else:
        print(f"  ❌ {result.stderr[-300:]}")

    print(f"\n总耗时: {round(time.time()-t0, 1)}s")


if __name__ == "__main__":
    asyncio.run(main())
