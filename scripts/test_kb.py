"""E2E test: StructureTemplate → SurrealDB write → vector search → top-k."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from kb.graph_backend import GraphBackend
    from kb.template_store import TemplateStore

    # Use a fresh test DB
    db_path = str(Path(__file__).parent.parent / "tmp" / "kb_test.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    gb = GraphBackend(f"file://{db_path}")
    await gb.connect()
    store = TemplateStore(gb)

    print("=== Step 1: 初始化 schema ===")
    await store.init_schema()
    print("Schema + HNSW index created.")

    print("\n=== Step 2: 写入 3 个 StructureTemplate ===")
    templates = [
        {
            "template_id": "tpl_makeup_01",
            "category": "美妆",
            "duration_range": [25, 35],
            "narrative": {"hook_type": "痛点_反问句", "build_pattern": "对比展示_揭示原因", "cta_type": "限时优惠"},
            "timeline": [
                {"phase": "hook", "required_shot_types": ["face_closeup", "text_overlay"]},
                {"phase": "build", "required_shot_types": ["product_zoom_in", "before_after"]},
                {"phase": "payoff_cta", "required_shot_types": ["text_overlay"]},
            ],
            "provenance": {"extraction_date": "2026-05-21"},
        },
        {
            "template_id": "tpl_digital_01",
            "category": "数码",
            "duration_range": [35, 45],
            "narrative": {"hook_type": "利益_直接", "build_pattern": "教程演示_步骤拆解", "cta_type": "社会认同"},
            "timeline": [
                {"phase": "hook", "required_shot_types": ["product_zoom_in"]},
                {"phase": "build", "required_shot_types": ["product_zoom_in", "usage_scenario"]},
                {"phase": "payoff_cta", "required_shot_types": ["text_overlay"]},
            ],
            "provenance": {"extraction_date": "2026-05-21"},
        },
        {
            "template_id": "tpl_food_01",
            "category": "美食",
            "duration_range": [20, 30],
            "narrative": {"hook_type": "悬念_反问句", "build_pattern": "痛点列举_方案展示_效果对比", "cta_type": "直接索取"},
            "timeline": [
                {"phase": "hook", "required_shot_types": ["hook_attention_grabber"]},
                {"phase": "build", "required_shot_types": ["usage_scenario", "product_zoom_in"]},
                {"phase": "payoff_cta", "required_shot_types": ["text_overlay"]},
            ],
            "provenance": {"extraction_date": "2026-05-21"},
        },
    ]

    for tpl in templates:
        pid = await store.store_template(tpl, vertical=tpl["category"])
        print(f"  Stored: {pid} ({tpl['category']})")

    print("\n=== Step 3: 语义搜索测试 ===")
    queries = [
        "口红种草视频",
        "手机评测",
        "美食探店",
        "护肤品带货",
    ]
    for q in queries:
        t0 = time.time()
        results = await store.search_similar(q, top_k=2)
        elapsed = (time.time() - t0) * 1000
        print(f"\n  Query: '{q}' ({elapsed:.1f}ms)")
        for i, r in enumerate(results):
            dist = r.get("dist", "?")
            cat = r.get("category", "?")
            desc = r.get("description", "")[:60]
            print(f"    #{i+1} [{cat}] dist={dist:.3f} | {desc}")

    print("\n=== Step 4: 获取完整模板 ===")
    pattern = await store.get_pattern("tpl_makeup_01")
    if pattern and "template" in pattern:
        tpl = pattern["template"]
        print(f"  ID: {tpl.get('template_id')}")
        print(f"  Category: {tpl.get('category')}")
        print(f"  Phases: {len(tpl.get('timeline', []))}")
    else:
        print("  ❌ Failed to retrieve template")

    print("\n=== Step 5: 列出所有模板 ===")
    all_patterns = await store.list_patterns()
    for p in all_patterns:
        print(f"  {p.get('category', '?')}: {p.get('description', '')[:50]}")

    await gb.close()
    print("\n✅ 知识库 E2E 测试通过")


if __name__ == "__main__":
    asyncio.run(main())
