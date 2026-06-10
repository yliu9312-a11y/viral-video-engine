"""Load all seed data (atoms, modules, patterns) into SurrealDB with embeddings."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    from kb.graph_backend import GraphBackend
    from kb.template_store import TemplateStore

    db_path = str(Path(__file__).parent.parent / "data" / "graph.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    gb = GraphBackend(f"file://{db_path}")
    await gb.connect()
    store = TemplateStore(gb)

    print("=== Step 1: 初始化 schema (4 节点 + 3 边) ===")
    await store.init_schema()
    print("Schema + HNSW indexes created.")

    # ── Load atoms ──
    atoms_dir = Path(__file__).parent.parent / "kb" / "seeds" / "atoms"
    atom_files = sorted(atoms_dir.glob("*.json"))
    print(f"\n=== Step 2: 加载 {len(atom_files)} 个 Atom ===")
    t0 = time.time()
    atom_ids = []
    for f in atom_files:
        with open(f, "r", encoding="utf-8") as fh:
            atom = json.load(fh)
        aid = await store.store_atom(atom)
        atom_ids.append(aid)
        print(f"  atom:{aid} [{atom.get('category')}] {atom.get('description', '')[:40]}")
    print(f"Atoms loaded in {time.time() - t0:.1f}s")

    # ── Load modules ──
    modules_dir = Path(__file__).parent.parent / "kb" / "seeds" / "modules"
    mod_files = sorted(modules_dir.glob("*.json"))
    print(f"\n=== Step 3: 加载 {len(mod_files)} 个 Module ===")
    t0 = time.time()
    module_ids = []
    for f in mod_files:
        with open(f, "r", encoding="utf-8") as fh:
            mod = json.load(fh)
        mid = await store.store_module(mod)
        module_ids.append(mid)
        atom_count = len(mod.get("atoms", []))
        print(f"  module:{mid} [{mod.get('phase')}] → {atom_count} atoms")
    print(f"Modules loaded in {time.time() - t0:.1f}s")

    # ── Load patterns with composed_of edges ──
    print(f"\n=== Step 4: 加载 Pattern + composed_of 边 ===")
    templates = [
        {
            "template_id": "tpl_makeup_01",
            "category": "美妆",
            "duration_range": [25, 35],
            "narrative": {"hook_type": "痛点_反问句", "build_pattern": "对比展示_揭示原因", "cta_type": "限时优惠"},
            "timeline": [
                {"phase": "hook", "duration_pct": [0, 0.2], "required_shot_types": ["face_closeup", "text_overlay"]},
                {"phase": "build", "duration_pct": [0.2, 0.75], "required_shot_types": ["product_zoom_in", "before_after"]},
                {"phase": "payoff_cta", "duration_pct": [0.75, 1.0], "required_shot_types": ["text_overlay"]},
            ],
            "provenance": {"extraction_date": "2026-05-21"},
        },
        {
            "template_id": "tpl_digital_01",
            "category": "数码",
            "duration_range": [35, 45],
            "narrative": {"hook_type": "利益_直接", "build_pattern": "教程演示_步骤拆解", "cta_type": "社会认同"},
            "timeline": [
                {"phase": "hook", "duration_pct": [0, 0.15], "required_shot_types": ["product_zoom_in"]},
                {"phase": "build", "duration_pct": [0.15, 0.8], "required_shot_types": ["product_zoom_in", "usage_scenario"]},
                {"phase": "payoff_cta", "duration_pct": [0.8, 1.0], "required_shot_types": ["text_overlay"]},
            ],
            "provenance": {"extraction_date": "2026-05-21"},
        },
        {
            "template_id": "tpl_food_01",
            "category": "美食",
            "duration_range": [20, 30],
            "narrative": {"hook_type": "悬念_反问句", "build_pattern": "痛点列举_方案展示_效果对比", "cta_type": "直接索取"},
            "timeline": [
                {"phase": "hook", "duration_pct": [0, 0.2], "required_shot_types": ["hook_attention_grabber"]},
                {"phase": "build", "duration_pct": [0.2, 0.8], "required_shot_types": ["usage_scenario", "product_zoom_in"]},
                {"phase": "payoff_cta", "duration_pct": [0.8, 1.0], "required_shot_types": ["text_overlay"]},
            ],
            "provenance": {"extraction_date": "2026-05-21"},
        },
    ]

    # Map phase → module_id for composed_of linking
    phase_module_map = {
        "hook": "mod_hook_question",
        "build": "mod_build_compare",
        "payoff_cta": "mod_payoff_urgency",
    }

    for tpl in templates:
        tpl_modules = [phase_module_map.get(p["phase"], "") for p in tpl.get("timeline", [])]
        tpl_modules = [m for m in tpl_modules if m]
        pid = await store.store_template(tpl, vertical=tpl["category"], module_ids=tpl_modules)
        print(f"  pattern:{pid} ({tpl['category']}) → {len(tpl_modules)} modules")

    # ── Verify counts ──
    print(f"\n=== Step 5: 验证图统计 ===")
    for table in ["pattern", "module", "atom", "vertical"]:
        count = await store.gb.execute(f"SELECT count() FROM {table} GROUP ALL")
        print(f"  {table}: {count}")
    for rel in ["composed_of", "built_from", "best_for"]:
        count = await store.gb.execute(f"SELECT count() FROM {rel} GROUP ALL")
        print(f"  {rel}: {count}")

    await gb.close()
    print("\n✅ 知识库种子数据加载完成")


if __name__ == "__main__":
    asyncio.run(main())
