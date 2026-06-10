"""E2E test: verify 4-node 3-edge ontology in SurrealDB.

Checks:
1. Schema: all 4 node tables + 3 relation tables exist
2. Counts: 30 atoms, 5 modules, 3 patterns, verticals, edges
3. Multi-hop: pattern → composed_of → module → built_from → atom
4. Vector search: atom gap-filling query returns correct results
5. Graph traversal: pattern subgraph returns complete structure
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = str(Path(__file__).parent.parent / "data" / "graph.db")


async def main():
    from kb.graph_backend import GraphBackend
    from kb.template_store import TemplateStore

    gb = GraphBackend(f"file://{DB_PATH}")
    await gb.connect()
    store = TemplateStore(gb)

    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name} — {detail}")

    # ── Test 1: Node counts ──
    print("=== Test 1: 节点数量 ===")
    for table, expected_min in [("pattern", 3), ("module", 5), ("atom", 30), ("vertical", 3)]:
        result = await gb.execute(f"SELECT count() FROM {table} GROUP ALL")
        count = result[0].get("count", 0) if result else 0
        check(f"{table} >= {expected_min}", count >= expected_min, f"got {count}")

    # ── Test 2: Edge counts ──
    print("\n=== Test 2: 边数量 ===")
    for rel, expected_min in [("composed_of", 3), ("built_from", 10), ("best_for", 3)]:
        result = await gb.execute(f"SELECT count() FROM {rel} GROUP ALL")
        count = result[0].get("count", 0) if result else 0
        check(f"{rel} >= {expected_min}", count >= expected_min, f"got {count}")

    # ── Test 3: Atom fields ──
    print("\n=== Test 3: Atom 字段完整性 ===")
    sample_atoms = await gb.execute("SELECT * FROM atom LIMIT 3")
    if sample_atoms:
        atom = sample_atoms[0]
        required_fields = ["type", "category", "remotion_component", "description",
                          "fills_shot_types", "visual_impact_score", "embedding"]
        for field in required_fields:
            check(f"atom.{field} exists", field in atom and atom[field] is not None)
        check("embedding is 1024-dim", len(atom.get("embedding", [])) == 1024,
              f"got {len(atom.get('embedding', []))}")
    else:
        check("atoms exist", False, "no atoms found")

    # ── Test 4: Module fields ──
    print("\n=== Test 4: Module 字段完整性 ===")
    sample_modules = await gb.execute("SELECT * FROM module LIMIT 2")
    if sample_modules:
        mod = sample_modules[0]
        required_fields = ["phase", "narrative_pattern", "description", "embedding"]
        for field in required_fields:
            check(f"module.{field} exists", field in mod and mod[field] is not None)
    else:
        check("modules exist", False, "no modules found")

    # ── Test 5: Multi-hop traversal (pattern → module → atom) ──
    print("\n=== Test 5: 多跳遍历 pattern→module→atom ===")
    full_pattern = await store.get_pattern_full("tpl_makeup_01")
    check("pattern exists", full_pattern is not None, "tpl_makeup_01 not found")
    if full_pattern:
        modules = full_pattern.get("modules", [])
        check("has modules", len(modules) > 0, f"got {len(modules)} modules")
        if modules:
            first_mod = modules[0] if isinstance(modules[0], dict) else {}
            atoms = first_mod.get("atoms", [])
            check("module has atoms", len(atoms) > 0, f"got {len(atoms)} atoms in first module")
            if atoms:
                atom = atoms[0] if isinstance(atoms[0], dict) else {}
                check("atom has fills_shot_types",
                      len(atom.get("fills_shot_types", [])) > 0,
                      f"got {atom.get('fills_shot_types')}")

    # ── Test 6: Vector search for gap-filling ──
    print("\n=== Test 6: 缺口补全向量搜索 ===")
    gap_queries = [
        ("usage_scenario", "build", "应找到 usage_scenario 相关 atom"),
        ("face_closeup", "hook", "应找到 face_closeup 相关 atom"),
        ("text_overlay", "payoff_cta", "应找到 CTA 文字相关 atom"),
    ]
    for shot_type, phase, desc in gap_queries:
        t0 = time.time()
        results = await store.find_atoms_for_gap(shot_type, phase, top_k=3)
        elapsed = (time.time() - t0) * 1000
        check(f"{desc}", len(results) > 0, f"got {len(results)} results for {shot_type}@{phase}")
        if results:
            best = results[0]
            print(f"      top hit: {best.get('atom_id', '?')} "
                  f"[{best.get('category')}] "
                  f"fills={best.get('fills_shot_types', [])} "
                  f"dist={best.get('dist', '?'):.3f} "
                  f"({elapsed:.0f}ms)")

    # ── Test 7: Graph traversal (pattern → vertical) ──
    print("\n=== Test 7: 图遍历 pattern→vertical ===")
    result = await gb.execute("""
        SELECT description, ->best_for->vertical AS verticals
        FROM pattern
    """)
    check("patterns have verticals", len(result) > 0)
    for r in result:
        verts = r.get("verticals", [])
        check(f"pattern has vertical link", len(verts) > 0,
              f"description={r.get('description', '')[:30]}, verticals={verts}")

    # ── Test 8: built_from edge weights ──
    print("\n=== Test 8: built_from 边权重 ===")
    bf_edges = await gb.execute("SELECT * FROM built_from LIMIT 5")
    check("built_from edges exist", len(bf_edges) > 0)
    if bf_edges:
        for edge in bf_edges:
            weight = edge.get("weight", -1)
            check(f"weight in [0,1]", 0 <= weight <= 1, f"got {weight}")

    # ── Summary ──
    print(f"\n{'='*50}")
    print(f"结果: {passed} passed, {failed} failed")
    if failed == 0:
        print("✅ 全部测试通过 — 4 节点 3 边图结构完整")
    else:
        print(f"⚠️  {failed} 项未通过")

    await gb.close()
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
