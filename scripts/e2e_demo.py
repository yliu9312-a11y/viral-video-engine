#!/usr/bin/env python3
"""E2E Demo: uses a pre-built template with specific shot_types to show gap detection + strategy.

Usage:
  python scripts/e2e_demo.py                   # full demo
  python scripts/e2e_demo.py --skip-render     # skip Remotion render
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "python"))

PROJECT_ROOT = Path(__file__).parent.parent
DEMO_TEMPLATE = PROJECT_ROOT / "e2e_demo" / "demo_template.json"
MATERIALS_DIR = PROJECT_ROOT / "e2e_demo" / "materials"
OUTPUT_DIR = PROJECT_ROOT / "e2e_demo" / "demo_output"


def step(msg: str):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ── Load demo template ──
    step("加载演示模板 (好物推荐)")
    with open(DEMO_TEMPLATE, encoding="utf-8") as f:
        template = json.load(f)
    print(f"  Template: {template['template_id']}")
    print(f"  Category: {template['category']}")
    for p in template["timeline"]:
        print(f"  Phase '{p['phase']}': needs {p['required_shot_types']}")

    # ── S3a: Gap Detection ──
    step("S3a 缺口检测 (用真实产品图)")
    from s3_gap_detector import run_gap_detection
    t = time.time()
    gap_dir = str(OUTPUT_DIR / "gap")
    Path(gap_dir).mkdir(parents=True, exist_ok=True)
    report = run_gap_detection(
        template=template,
        material_dir=str(MATERIALS_DIR),
        output_dir=gap_dir,
    )
    elapsed = round(time.time() - t, 2)
    gaps = report.get("gaps", [])
    summary = report.get("summary", {})
    print(f"  Materials: {len(list(MATERIALS_DIR.glob('*.jpg')))} images")
    print(f"  Gaps found: {len(gaps)}")
    print(f"  Severity: {summary.get('overall_severity', 'LOW')}")
    for g in gaps:
        print(f"    - Phase '{g['phase']}': missing {g['missing_shot_types']}, "
              f"shortfall {g.get('shot_count_shortfall', 0)} shots")
    print(f"  Time: {elapsed}s")

    # ── S3b: Strategy Assignment ──
    step("S3b 策略生成 (KB-aware)")
    from s3_strategist import run_strategist
    t = time.time()
    assign_dir = str(OUTPUT_DIR / "assign")
    Path(assign_dir).mkdir(parents=True, exist_ok=True)
    gap_report_path = str(Path(gap_dir) / "gap_report.json")
    template_path = str(OUTPUT_DIR / "template.json")
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    assignment = run_strategist(
        gap_report_path=gap_report_path,
        template_path=template_path,
        material_dir=str(MATERIALS_DIR),
        output_dir=assign_dir,
    )
    elapsed = round(time.time() - t, 2)

    strategies = {}
    for phase in assignment.get("phases", []):
        sid = phase.get("strategy_id", "?")
        sname = phase.get("strategy_name", "?")
        strategies[sid] = sname
        actions = phase.get("completion_actions", [])
        print(f"  Phase '{phase['phase']}': strategy {sid} ({sname})")
        if actions:
            for a in actions:
                print(f"    → {a.get('action_type', '?')}: {a.get('component', '?')}")
        kb = phase.get("kb_atoms", [])
        if kb:
            print(f"    → KB推荐: {[k.get('description', '')[:30] for k in kb]}")
    print(f"  Strategies: {strategies}")
    print(f"  Time: {elapsed}s")

    # ── S3.5: Aesthetic Lint ──
    step("S3.5 美感校验")
    from aesthetic_linter import lint_and_fix
    assignment_path = str(Path(assign_dir) / "material_assignment.json")
    with open(assignment_path, encoding="utf-8") as f:
        import json as _json
        assign_data = _json.load(f)
    fixed_assign, lint_result = lint_and_fix(assign_data)
    print(f"  Result: {lint_result.summary()}")
    for err in lint_result.errors:
        icon = "❌" if err.severity == "error" else "⚠️"
        print(f"    {icon} [{err.rule}] {err.message}")
    if lint_result.auto_fixes:
        with open(assignment_path, "w", encoding="utf-8") as f:
            _json.dump(fixed_assign, f, ensure_ascii=False, indent=2)
        print(f"  Auto-fixed {lint_result.auto_fixes} issues")

    # ── S4: Rendering ──
    if not args.skip_render:
        step("S4 Remotion 渲染")
        import subprocess
        t = time.time()
        render_out = str(OUTPUT_DIR / "demo_render.mp4")
        assignment_path = str(Path(assign_dir) / "material_assignment.json")
        cmd = [
            "npx", "tsx",
            str(PROJECT_ROOT / "scripts" / "render.ts"),
            assignment_path,
            render_out,
            "22",
        ]
        print(f"  Rendering...")
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)
        elapsed = round(time.time() - t, 2)
        if proc.returncode == 0 and Path(render_out).exists():
            size_mb = Path(render_out).stat().st_size / (1024 * 1024)
            print(f"  Output: {render_out} ({size_mb:.1f}MB)")
        else:
            print(f"  FAILED: {proc.stderr[-300:]}")
        print(f"  Time: {elapsed}s")

    # ── S5: KB Ingestion ──
    step("S5 知识库入图")
    import asyncio
    from kb.graph_backend import GraphBackend
    from kb.template_store import TemplateStore
    from kb.agent.ingestion_agent import ingest_template

    t = time.time()
    db_path = str(PROJECT_ROOT / "data" / "graph.db")
    if Path(db_path).exists():
        async def _ingest():
            gb = GraphBackend(f"file://{db_path}")
            await gb.connect()
            store = TemplateStore(gb)
            result = await ingest_template(template, vertical="好物推荐", gb=gb, store=store)
            await gb.close()
            return result
        kb_result = asyncio.run(_ingest())
        print(f"  Decision: {kb_result.decision}")
        print(f"  Reason: {kb_result.reason}")
    else:
        print("  KB not initialized, skipping")
    print(f"  Time: {round(time.time() - t, 2)}s")

    total = round(time.time() - t0, 2)
    step(f"Demo 完成 ({total}s)")
    print(f"  素材: {len(list(MATERIALS_DIR.glob('*.jpg')))} 张产品图")
    print(f"  缺口: {len(gaps)} 个")
    print(f"  策略: {', '.join(f'{k}({v})' for k,v in strategies.items())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
