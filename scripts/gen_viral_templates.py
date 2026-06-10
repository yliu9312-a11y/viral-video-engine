#!/usr/bin/env python3
"""Generate 50+ StructureTemplate JSONs based on common viral video patterns.

Categories: 好物推荐, 美妆, 美食, 数码, 生活, 健身, 知识, 宠物, 母婴, 家居
Each template has: hook → build → payoff_cta with specific shot_types.
"""

import json
import hashlib
import random
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "e2e_demo" / "viral_templates"

# ── Shot type vocabulary ──
SHOT_TYPES = [
    "face_closeup", "text_overlay", "product_closeup", "product_usage",
    "before_after", "unboxing", "ingredients", "cooking_process",
    "step_demo", "comparison", "outdoor_scene", "indoor_scene",
    "reaction_shot", "data_display", "lifestyle_broll",
    "hand_gesture", "screen_recording", "tutorial_step",
]

HOOK_TYPES = [
    "痛点_引发共鸣", "利益_直接", "悬念_留白", "反常识_颠覆认知",
    "提问_好奇", "数字_量化", "对比_冲突", "故事_场景",
]
BUILD_PATTERNS = [
    "产品展示_多角度", "教程演示_步骤拆解", "对比测评_竞品PK",
    "使用场景_沉浸体验", "成分解析_科学背书", "制作过程_ASMR",
    "变化过程_前后对比", "数据展示_图表说话",
]
CTA_TYPES = [
    "限时优惠", "社会认同", "行动号召", "悬念引导",
    "互动提问", "收藏关注", "评论区见",
]
CATEGORIES = {
    "好物推荐": {
        "desc": "产品种草、好物分享",
        "hooks": ["痛点_引发共鸣", "利益_直接", "对比_冲突"],
        "builds": ["产品展示_多角度", "使用场景_沉浸体验", "对比测评_竞品PK"],
        "ctas": ["限时优惠", "社会认同", "收藏关注"],
        "shot_pool": ["face_closeup", "product_closeup", "product_usage", "before_after", "text_overlay", "unboxing", "hand_gesture"],
    },
    "美妆": {
        "desc": "化妆教程、护肤分享",
        "hooks": ["痛点_引发共鸣", "反常识_颠覆认知", "故事_场景"],
        "builds": ["教程演示_步骤拆解", "变化过程_前后对比", "成分解析_科学背书"],
        "ctas": ["限时优惠", "收藏关注", "互动提问"],
        "shot_pool": ["face_closeup", "product_closeup", "step_demo", "before_after", "text_overlay", "product_usage", "reaction_shot"],
    },
    "美食": {
        "desc": "美食制作、探店分享",
        "hooks": ["悬念_留白", "数字_量化", "利益_直接"],
        "builds": ["制作过程_ASMR", "教程演示_步骤拆解", "使用场景_沉浸体验"],
        "ctas": ["互动提问", "收藏关注", "评论区见"],
        "shot_pool": ["ingredients", "cooking_process", "product_closeup", "step_demo", "before_after", "text_overlay", "hand_gesture"],
    },
    "数码": {
        "desc": "数码评测、科技分享",
        "hooks": ["反常识_颠覆认知", "数字_量化", "提问_好奇"],
        "builds": ["对比测评_竞品PK", "产品展示_多角度", "数据展示_图表说话"],
        "ctas": ["限时优惠", "行动号召", "收藏关注"],
        "shot_pool": ["product_closeup", "unboxing", "screen_recording", "data_display", "comparison", "product_usage", "text_overlay"],
    },
    "生活": {
        "desc": "日常生活、Vlog 分享",
        "hooks": ["故事_场景", "悬念_留白", "提问_好奇"],
        "builds": ["使用场景_沉浸体验", "教程演示_步骤拆解", "变化过程_前后对比"],
        "ctas": ["互动提问", "评论区见", "收藏关注"],
        "shot_pool": ["indoor_scene", "outdoor_scene", "lifestyle_broll", "face_closeup", "hand_gesture", "text_overlay", "product_usage"],
    },
    "健身": {
        "desc": "健身教程、运动分享",
        "hooks": ["数字_量化", "对比_冲突", "利益_直接"],
        "builds": ["教程演示_步骤拆解", "数据展示_图表说话", "变化过程_前后对比"],
        "ctas": ["互动提问", "收藏关注", "行动号召"],
        "shot_pool": ["face_closeup", "step_demo", "before_after", "outdoor_scene", "text_overlay", "data_display", "product_usage"],
    },
    "知识": {
        "desc": "知识科普、技能教学",
        "hooks": ["反常识_颠覆认知", "提问_好奇", "数字_量化"],
        "builds": ["数据展示_图表说话", "教程演示_步骤拆解", "对比测评_竞品PK"],
        "ctas": ["收藏关注", "互动提问", "评论区见"],
        "shot_pool": ["text_overlay", "screen_recording", "data_display", "face_closeup", "indoor_scene", "step_demo", "comparison"],
    },
    "宠物": {
        "desc": "宠物日常、萌宠分享",
        "hooks": ["故事_场景", "悬念_留白", "提问_好奇"],
        "builds": ["使用场景_沉浸体验", "变化过程_前后对比", "教程演示_步骤拆解"],
        "ctas": ["互动提问", "收藏关注", "评论区见"],
        "shot_pool": ["face_closeup", "indoor_scene", "outdoor_scene", "lifestyle_broll", "reaction_shot", "text_overlay", "product_usage"],
    },
    "母婴": {
        "desc": "育儿分享、母婴好物",
        "hooks": ["痛点_引发共鸣", "故事_场景", "提问_好奇"],
        "builds": ["产品展示_多角度", "教程演示_步骤拆解", "使用场景_沉浸体验"],
        "ctas": ["社会认同", "收藏关注", "限时优惠"],
        "shot_pool": ["face_closeup", "product_closeup", "product_usage", "step_demo", "indoor_scene", "text_overlay", "reaction_shot"],
    },
    "家居": {
        "desc": "家居改造、收纳整理",
        "hooks": ["对比_冲突", "悬念_留白", "数字_量化"],
        "builds": ["变化过程_前后对比", "教程演示_步骤拆解", "产品展示_多角度"],
        "ctas": ["收藏关注", "互动提问", "行动号召"],
        "shot_pool": ["before_after", "indoor_scene", "product_closeup", "step_demo", "hand_gesture", "text_overlay", "lifestyle_broll"],
    },
}

# ── Narrative patterns (hook_type → build_pattern → cta_type combos) ──
NARRATIVE_COMBOS = [
    ("痛点_引发共鸣", "产品展示_多角度", "限时优惠"),
    ("利益_直接", "教程演示_步骤拆解", "社会认同"),
    ("悬念_留白", "使用场景_沉浸体验", "互动提问"),
    ("反常识_颠覆认知", "对比测评_竞品PK", "收藏关注"),
    ("提问_好奇", "数据展示_图表说话", "评论区见"),
    ("数字_量化", "制作过程_ASMR", "行动号召"),
    ("对比_冲突", "变化过程_前后对比", "悬念引导"),
    ("故事_场景", "成分解析_科学背书", "限时优惠"),
]


def make_template_id(category: str, idx: int) -> str:
    raw = f"{category}_{idx}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"tpl_{h}"


def pick_shots(pool: list[str], count: int) -> list[str]:
    """Pick count unique shot types from pool, with replacement if needed."""
    if count <= len(pool):
        return random.sample(pool, count)
    return pool + random.choices(pool, k=count - len(pool))


def generate_template(category: str, idx: int) -> dict:
    cat = CATEGORIES[category]
    combo = random.choice(NARRATIVE_COMBOS)
    hook_type = random.choice(cat["hooks"])
    build_pattern = random.choice(cat["builds"])
    cta_type = random.choice(cat["ctas"])

    # Shot distribution: hook 1-2, build 3-5, payoff 1-2
    hook_shots = pick_shots(cat["shot_pool"], random.randint(1, 2))
    build_shots = pick_shots(cat["shot_pool"], random.randint(3, 5))
    payoff_shots = pick_shots(cat["shot_pool"], random.randint(1, 2))

    duration = random.choice([15, 20, 25, 30])

    return {
        "template_id": make_template_id(category, idx),
        "source_videos": [],
        "category": category,
        "duration_range": [max(10, duration - 5), min(45, duration + 5)],
        "narrative": {
            "hook_type": hook_type,
            "build_pattern": build_pattern,
            "cta_type": cta_type,
        },
        "timeline": [
            {
                "phase": "hook",
                "duration_pct": [0.15, 0.25],
                "shot_count_range": [1, 2],
                "avg_shot_length_s": random.choice([2.0, 3.0, 4.0]),
                "required_shot_types": hook_shots,
                "caption_style": {
                    "font": "思源黑体",
                    "color": "#FFFFFF",
                    "size": "large",
                    "position": "bottom_third",
                    "animation": random.choice(["typewriter_fast", "fade_in", "bounce_in"]),
                },
                "audio_energy": "high",
                "bgm_role": "节奏带动",
            },
            {
                "phase": "build",
                "duration_pct": [0.50, 0.65],
                "shot_count_range": [3, 5],
                "avg_shot_length_s": random.choice([2.5, 3.0, 3.5, 4.0]),
                "required_shot_types": build_shots,
                "caption_style": {
                    "font": "思源黑体",
                    "color": "#FFFFFF",
                    "size": "medium",
                    "position": "bottom_third",
                    "animation": random.choice(["fade_in", "slide_up", "typewriter_fast"]),
                },
                "audio_energy": "medium",
                "bgm_role": "背景铺垫",
            },
            {
                "phase": "payoff_cta",
                "duration_pct": [0.15, 0.25],
                "shot_count_range": [1, 2],
                "avg_shot_length_s": random.choice([3.0, 4.0, 5.0]),
                "required_shot_types": payoff_shots,
                "caption_style": {
                    "font": "思源黑体",
                    "color": "#FFD700",
                    "size": "xlarge",
                    "position": "center",
                    "animation": random.choice(["bounce_in", "scale_up", "glow"]),
                },
                "audio_energy": "high",
                "bgm_role": "高潮推动",
            },
        ],
        "rhythm_profile": {
            "avg_shot_length_s": random.choice([2.5, 3.0, 3.5]),
            "shot_length_variance": random.choice(["low", "medium", "high"]),
            "energy_curve": random.choice(["wave", "ascending", "peak_end"]),
        },
        "cta_type": cta_type,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    templates = []
    idx = 0

    for category in CATEGORIES:
        for i in range(5):  # 5 templates per category = 50 total
            tpl = generate_template(category, idx)
            templates.append(tpl)

            # Save individual file
            path = OUTPUT_DIR / f"{tpl['template_id']}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=2)
            idx += 1

    # Save all templates in one file
    all_path = OUTPUT_DIR / "_all_templates.json"
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(templates)} templates across {len(CATEGORIES)} categories:")
    for cat in CATEGORIES:
        count = sum(1 for t in templates if t["category"] == cat)
        print(f"  {cat}: {count}")
    print(f"\nSaved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
