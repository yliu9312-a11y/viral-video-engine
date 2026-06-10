"""Generate 30 atom + 5 module seed JSON files."""
import json
from pathlib import Path

ATOMS_DIR = Path(__file__).parent.parent / "kb" / "seeds" / "atoms"
MODULES_DIR = Path(__file__).parent.parent / "kb" / "seeds" / "modules"

ATOMS_DIR.mkdir(parents=True, exist_ok=True)
MODULES_DIR.mkdir(parents=True, exist_ok=True)

atoms = [
    # ── Hook atoms (10) ──
    {"atom_id":"hook_face_closeup","type":"shot","category":"hook","remotion_component":"FaceCloseupFrame","description":"面部特写镜头，展示真实人物表情，快速建立信任感","required_inputs":["face_video_or_image"],"fills_shot_types":["face_closeup"],"duration_min_s":1.5,"duration_max_s":4.0,"visual_impact_score":0.85,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"hook_text_title","type":"caption","category":"hook","remotion_component":"TitleBar","description":"大字标题覆盖层，3秒内传达核心卖点","required_inputs":["text_content"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":5.0,"visual_impact_score":0.7,"tech_stack":["remotion","gsap"]},
    {"atom_id":"hook_attention_grab","type":"shot","category":"hook","remotion_component":"AttentionGrabber","description":"高能量开场画面，配合动效快速抓住注意力","required_inputs":["bg_video_or_image"],"fills_shot_types":["hook_attention_grabber"],"duration_min_s":1.0,"duration_max_s":3.0,"visual_impact_score":0.9,"tech_stack":["remotion","gsap","lottie"]},
    {"atom_id":"hook_before_after","type":"shot","category":"hook","remotion_component":"BeforeAfterSplit","description":"左右对比分屏，使用前vs使用后效果展示","required_inputs":["before_image","after_image"],"fills_shot_types":["before_after"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.88,"tech_stack":["remotion"]},
    {"atom_id":"hook_problem_hook","type":"caption","category":"hook","remotion_component":"ProblemStatement","description":"痛点问题文字展示，引发用户共鸣","required_inputs":["problem_text"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.72,"tech_stack":["remotion","gsap"]},
    {"atom_id":"hook_curiosity_gap","type":"shot","category":"hook","remotion_component":"CuriosityGap","description":"悬念式开场，先展示结果再揭示过程","required_inputs":["result_image"],"fills_shot_types":["hook_attention_grabber"],"duration_min_s":1.5,"duration_max_s":3.5,"visual_impact_score":0.87,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"hook_number_list","type":"caption","category":"hook","remotion_component":"NumberListIntro","description":"数字列表式开头，如'3个方法让你...'","required_inputs":["number","topic_text"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.68,"tech_stack":["remotion"]},
    {"atom_id":"hook_reaction","type":"shot","category":"hook","remotion_component":"ReactionShot","description":"夸张反应镜头，展示使用后的惊喜表情","required_inputs":["reaction_video"],"fills_shot_types":["face_closeup"],"duration_min_s":1.0,"duration_max_s":3.0,"visual_impact_score":0.82,"tech_stack":["remotion"]},
    {"atom_id":"hook_unboxing","type":"shot","category":"hook","remotion_component":"UnboxingShot","description":"产品开箱镜头，展示包装和第一印象","required_inputs":["unboxing_video"],"fills_shot_types":["product_zoom_in"],"duration_min_s":2.0,"duration_max_s":5.0,"visual_impact_score":0.78,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"hook_transition_in","type":"transition","category":"hook","remotion_component":"TransitionWipe","description":"入场转场动效，从黑屏/模糊到清晰画面","required_inputs":[],"fills_shot_types":["transition"],"duration_min_s":0.5,"duration_max_s":1.5,"visual_impact_score":0.6,"tech_stack":["remotion","gsap"]},

    # ── Build atoms (12) ──
    {"atom_id":"build_product_zoom","type":"shot","category":"build","remotion_component":"ProductZoomFrame","description":"产品特写镜头，展示细节和质感","required_inputs":["product_image_or_video"],"fills_shot_types":["product_zoom_in"],"duration_min_s":2.0,"duration_max_s":5.0,"visual_impact_score":0.8,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"build_usage_scenario","type":"shot","category":"build","remotion_component":"UsageScenarioFrame","description":"使用场景展示，真实环境中展示产品使用过程","required_inputs":["usage_video_or_image"],"fills_shot_types":["usage_scenario"],"duration_min_s":3.0,"duration_max_s":6.0,"visual_impact_score":0.82,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"build_feature_highlight","type":"shot","category":"build","remotion_component":"FeatureHighlight","description":"产品卖点高亮展示，配合标注和动效","required_inputs":["product_image","feature_text"],"fills_shot_types":["product_zoom_in"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.76,"tech_stack":["remotion","gsap"]},
    {"atom_id":"build_comparison","type":"shot","category":"build","remotion_component":"ComparisonDemo","description":"对比演示，竞品对比或使用前后对比","required_inputs":["item_a_image","item_b_image"],"fills_shot_types":["before_after"],"duration_min_s":3.0,"duration_max_s":6.0,"visual_impact_score":0.84,"tech_stack":["remotion"]},
    {"atom_id":"build_tutorial_step","type":"shot","category":"build","remotion_component":"TutorialStep","description":"教程步骤展示，分步骤演示操作过程","required_inputs":["step_video_or_image","step_number"],"fills_shot_types":["usage_scenario"],"duration_min_s":2.5,"duration_max_s":5.0,"visual_impact_score":0.74,"tech_stack":["remotion","gsap"]},
    {"atom_id":"build_ingredient_detail","type":"shot","category":"build","remotion_component":"IngredientDetail","description":"成分/材料特写，展示产品核心成分或材质","required_inputs":["ingredient_image"],"fills_shot_types":["product_zoom_in"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.72,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"build_process_montage","type":"shot","category":"build","remotion_component":"ProcessMontage","description":"过程蒙太奇，多镜头快剪展示完整使用流程","required_inputs":["process_videos"],"fills_shot_types":["usage_scenario"],"duration_min_s":3.0,"duration_max_s":7.0,"visual_impact_score":0.78,"tech_stack":["remotion"]},
    {"atom_id":"build_testimonial","type":"shot","category":"build","remotion_component":"TestimonialFrame","description":"用户证言镜头，真实用户分享使用体验","required_inputs":["testimonial_video"],"fills_shot_types":["face_closeup"],"duration_min_s":3.0,"duration_max_s":6.0,"visual_impact_score":0.8,"tech_stack":["remotion"]},
    {"atom_id":"build_data_graphic","type":"caption","category":"build","remotion_component":"DataGraphic","description":"数据图表展示，用数字说话增强说服力","required_inputs":["data_values","chart_type"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.68,"tech_stack":["remotion","gsap"]},
    {"atom_id":"build_lifestyle","type":"shot","category":"build","remotion_component":"LifestyleFrame","description":"生活方式场景，展示产品融入日常的自然画面","required_inputs":["lifestyle_image"],"fills_shot_types":["usage_scenario"],"duration_min_s":2.0,"duration_max_s":5.0,"visual_impact_score":0.75,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"build_texture_closeup","type":"shot","category":"build","remotion_component":"TextureCloseup","description":"材质纹理特写，展示产品的精细质感","required_inputs":["texture_image"],"fills_shot_types":["product_zoom_in"],"duration_min_s":1.5,"duration_max_s":3.5,"visual_impact_score":0.7,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"build_speed_demo","type":"shot","category":"build","remotion_component":"SpeedChangeDemo","description":"变速演示，慢放展示细节或快进展示效率","required_inputs":["demo_video"],"fills_shot_types":["usage_scenario"],"duration_min_s":2.0,"duration_max_s":5.0,"visual_impact_score":0.73,"tech_stack":["remotion"]},

    # ── Payoff/CTA atoms (8) ──
    {"atom_id":"payoff_cta_button","type":"caption","category":"payoff_cta","remotion_component":"CTAButton","description":"行动号召按钮动画，引导用户点击购买","required_inputs":["cta_text"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.8,"tech_stack":["remotion","gsap","lottie"]},
    {"atom_id":"payoff_social_proof","type":"caption","category":"payoff_cta","remotion_component":"SocialProof","description":"社会认同展示，销量/好评数/关注数等","required_inputs":["proof_number","proof_type"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.75,"tech_stack":["remotion","gsap"]},
    {"atom_id":"payoff_price_reveal","type":"caption","category":"payoff_cta","remotion_component":"PriceReveal","description":"价格揭示动效，原价划掉+现价突出显示","required_inputs":["original_price","sale_price"],"fills_shot_types":["text_overlay"],"duration_min_s":1.5,"duration_max_s":3.5,"visual_impact_score":0.82,"tech_stack":["remotion","gsap"]},
    {"atom_id":"payoff_limited_offer","type":"caption","category":"payoff_cta","remotion_component":"LimitedOffer","description":"限时优惠倒计时，营造紧迫感","required_inputs":["offer_text","deadline"],"fills_shot_types":["text_overlay"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.85,"tech_stack":["remotion","gsap"]},
    {"atom_id":"payoff_product_final","type":"shot","category":"payoff_cta","remotion_component":"ProductFinalShot","description":"产品最终展示镜头，全貌+品牌logo","required_inputs":["product_image"],"fills_shot_types":["product_zoom_in"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.7,"tech_stack":["remotion","ken_burns"]},
    {"atom_id":"payoff_happy_customer","type":"shot","category":"payoff_cta","remotion_component":"HappyCustomer","description":"满意用户镜头，展示使用后的开心状态","required_inputs":["customer_video_or_image"],"fills_shot_types":["face_closeup"],"duration_min_s":2.0,"duration_max_s":4.0,"visual_impact_score":0.72,"tech_stack":["remotion"]},
    {"atom_id":"payoff_brand_logo","type":"transition","category":"payoff_cta","remotion_component":"BrandLogoOutro","description":"品牌logo收尾动画，加深品牌印象","required_inputs":["logo_image"],"fills_shot_types":["transition"],"duration_min_s":1.0,"duration_max_s":2.5,"visual_impact_score":0.65,"tech_stack":["remotion","gsap","lottie"]},
    {"atom_id":"payoff_summary_card","type":"caption","category":"payoff_cta","remotion_component":"SummaryCard","description":"总结卡片，回顾核心卖点+CTA组合","required_inputs":["summary_points","cta_text"],"fills_shot_types":["text_overlay"],"duration_min_s":2.5,"duration_max_s":5.0,"visual_impact_score":0.78,"tech_stack":["remotion","gsap"]},
]

modules = [
    {
        "module_id": "mod_hook_question",
        "phase": "hook",
        "narrative_pattern": "痛点反问句",
        "script_template": "你知道{痛点}吗？99%的人都不知道{解决方案}",
        "duration_min_s": 3.0,
        "duration_max_s": 6.0,
        "description": "痛点反问式开场，用问题引发共鸣",
        "atoms": [
            {"atom_id": "hook_face_closeup", "weight": 0.4, "optional": False},
            {"atom_id": "hook_problem_hook", "weight": 0.35, "optional": False},
            {"atom_id": "hook_transition_in", "weight": 0.25, "optional": True},
        ]
    },
    {
        "module_id": "mod_hook_number",
        "phase": "hook",
        "narrative_pattern": "数字利益点",
        "script_template": "{数字}个方法让你{利益点}",
        "duration_min_s": 3.0,
        "duration_max_s": 5.0,
        "description": "数字列表式开场，直接给出利益点",
        "atoms": [
            {"atom_id": "hook_number_list", "weight": 0.5, "optional": False},
            {"atom_id": "hook_attention_grab", "weight": 0.3, "optional": False},
            {"atom_id": "hook_transition_in", "weight": 0.2, "optional": True},
        ]
    },
    {
        "module_id": "mod_build_compare",
        "phase": "build",
        "narrative_pattern": "对比展示",
        "script_template": "使用前{痛点} vs 使用后{效果}",
        "duration_min_s": 5.0,
        "duration_max_s": 10.0,
        "description": "对比式内容构建，用视觉差异证明效果",
        "atoms": [
            {"atom_id": "build_comparison", "weight": 0.35, "optional": False},
            {"atom_id": "build_product_zoom", "weight": 0.25, "optional": False},
            {"atom_id": "build_usage_scenario", "weight": 0.25, "optional": False},
            {"atom_id": "build_data_graphic", "weight": 0.15, "optional": True},
        ]
    },
    {
        "module_id": "mod_build_tutorial",
        "phase": "build",
        "narrative_pattern": "教程演示",
        "script_template": "第一步{准备}，第二步{操作}，第三步{完成}",
        "duration_min_s": 6.0,
        "duration_max_s": 12.0,
        "description": "教程式内容构建，分步骤展示使用方法",
        "atoms": [
            {"atom_id": "build_tutorial_step", "weight": 0.3, "optional": False},
            {"atom_id": "build_usage_scenario", "weight": 0.3, "optional": False},
            {"atom_id": "build_product_zoom", "weight": 0.2, "optional": False},
            {"atom_id": "build_feature_highlight", "weight": 0.2, "optional": True},
        ]
    },
    {
        "module_id": "mod_payoff_urgency",
        "phase": "payoff_cta",
        "narrative_pattern": "限时紧迫",
        "script_template": "限时{优惠}，点击{行动}，{社会认同}人已购买",
        "duration_min_s": 3.0,
        "duration_max_s": 6.0,
        "description": "紧迫感收尾，限时优惠+社会认同双重驱动",
        "atoms": [
            {"atom_id": "payoff_limited_offer", "weight": 0.3, "optional": False},
            {"atom_id": "payoff_cta_button", "weight": 0.3, "optional": False},
            {"atom_id": "payoff_social_proof", "weight": 0.2, "optional": False},
            {"atom_id": "payoff_price_reveal", "weight": 0.2, "optional": True},
        ]
    },
]

# Write atom files
for atom in atoms:
    path = ATOMS_DIR / f"{atom['atom_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(atom, f, ensure_ascii=False, indent=2)

# Write module files
for mod in modules:
    path = MODULES_DIR / f"{mod['module_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mod, f, ensure_ascii=False, indent=2)

print(f"Generated {len(atoms)} atom files in {ATOMS_DIR}")
print(f"Generated {len(modules)} module files in {MODULES_DIR}")
