#!/usr/bin/env python3
"""E2E demo with LLM-orchestrated animation scripts.

Usage:
  python scripts/e2e_orchestrated.py                 # full demo with LLM orchestration
  python scripts/e2e_orchestrated.py --skip-render   # skip Remotion render
  python scripts/e2e_orchestrated.py --fallback      # use fallback scripts (no LLM)
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "python"))

PROJECT_ROOT = Path(__file__).parent.parent
DEMO_TEMPLATE = PROJECT_ROOT / "e2e_demo" / "demo_template.json"
MATERIALS_DIR = PROJECT_ROOT / "e2e_demo" / "materials"
OUTPUT_DIR = PROJECT_ROOT / "e2e_demo" / "orchestrated_output"


def step(msg: str):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


async def orchestrate_phase(phase_name: str, gap: dict, template: dict, materials: list, kb_atoms: list, use_fallback: bool) -> dict:
    """Generate animation script for a single phase."""
    from animation_orchestrator import orchestrate_animation, _fallback_decision, decisions_to_spec

    if use_fallback:
        decision = _fallback_decision(phase_name)
        spec = decisions_to_spec(decision, phase_name, materials)
        return spec.model_dump()

    return await orchestrate_animation(
        phase=phase_name,
        gap=gap,
        kb_atoms=kb_atoms,
        materials=materials,
        template=template,
    )


def render_script(script: dict, phase_name: str, output_path: str):
    """Render an animation script using Remotion."""
    import subprocess

    # Write script to temp file
    script_path = OUTPUT_DIR / f"script_{phase_name}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # Calculate total frames from shots[]
    max_frame = 0
    for shot in script.get("shots", []):
        end = shot.get("start", 0) + shot.get("duration", 90)
        if end > max_frame:
            max_frame = end
    if max_frame == 0:
        max_frame = 90  # default 3 seconds

    # Copy materials to web/public/materials
    import shutil
    materials_dir = PROJECT_ROOT / "web" / "public" / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)
    for src_file in MATERIALS_DIR.glob("*.jpg"):
        dst = materials_dir / src_file.name
        if not dst.exists():
            shutil.copy2(src_file, dst)

    # Render using Remotion with ScriptDrivenVideo composition
    cmd = [
        "npx", "tsx",
        str(PROJECT_ROOT / "scripts" / "render_script.ts"),
        str(script_path),
        output_path,
        str(max_frame),
    ]

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        print(f"  Render failed: {proc.stderr[-300:]}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--fallback", action="store_true", help="Use fallback scripts (no LLM)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # Load template
    step("加载模板")
    with open(DEMO_TEMPLATE, encoding="utf-8") as f:
        template = json.load(f)
    print(f"  Template: {template['template_id']} ({template['category']})")

    # List materials
    materials = [{"path": str(f), "type": "image", "filename": f.name} for f in MATERIALS_DIR.glob("*.jpg")]
    print(f"  Materials: {len(materials)} images")

    # S3a: Gap detection
    step("S3a 缺口检测")
    from s3_gap_detector import run_gap_detection
    gap_dir = str(OUTPUT_DIR / "gap")
    Path(gap_dir).mkdir(parents=True, exist_ok=True)
    report = run_gap_detection(template=template, material_dir=str(MATERIALS_DIR), output_dir=gap_dir)
    gaps = report.get("gaps", [])
    print(f"  Gaps: {len(gaps)}")
    for g in gaps:
        print(f"    - {g['phase']}: missing {g['missing_shot_types']}")

    # Query KB atoms per phase
    step("查询 KB 推荐")
    kb_atoms_per_phase = {}
    try:
        from kb.graph_backend import GraphBackend
        from kb.template_store import TemplateStore

        db_path = str(PROJECT_ROOT / "data" / "graph.db")
        if Path(db_path).exists():
            async def query_kb():
                gb = GraphBackend(f"file://{db_path}")
                await gb.connect()
                store = TemplateStore(gb)
                for gap in gaps:
                    phase = gap.get("phase", "")
                    missing = gap.get("missing_shot_types", [])
                    atoms = []
                    for shot_type in missing:
                        results = await store.find_atoms_for_gap(shot_type, phase, top_k=3)
                        for r in results:
                            atom_id = str(r.get("id", "")).split(":")[-1]
                            atoms.append({
                                "atom_id": atom_id,
                                "remotion_component": r.get("remotion_component", ""),
                                "description": r.get("description", ""),
                                "fills_shot_types": r.get("fills_shot_types", []),
                                "visual_impact_score": r.get("visual_impact_score", 0),
                            })
                    kb_atoms_per_phase[phase] = atoms
                    print(f"  {phase}: {len(atoms)} KB atoms")
                await gb.close()
            asyncio.run(query_kb())
    except Exception as e:
        print(f"  KB query failed: {e}")

    # Generate animation scripts per phase
    step("LLM 编排动画脚本")
    scripts = {}
    for gap in gaps:
        phase = gap.get("phase", "")
        atoms = kb_atoms_per_phase.get(phase, [])
        print(f"  {phase}: orchestrating...", end=" ", flush=True)
        t = time.time()
        script = asyncio.run(orchestrate_phase(phase, gap, template, materials, atoms, args.fallback))
        scripts[phase] = script
        shot_count = len(script.get("shots", []))
        print(f"{shot_count} shots ({round(time.time()-t, 1)}s)")

    # Save all scripts
    all_scripts_path = OUTPUT_DIR / "animation_scripts.json"
    with open(all_scripts_path, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)
    print(f"\n  Scripts saved: {all_scripts_path}")

    # Render each phase
    if not args.skip_render:
        step("Remotion 渲染")
        for phase_name, script in scripts.items():
            output_path = str(OUTPUT_DIR / f"{phase_name}.mp4")
            print(f"  Rendering {phase_name}...", end=" ", flush=True)
            t = time.time()
            ok = render_script(script, phase_name, output_path)
            elapsed = round(time.time() - t, 1)
            if ok and Path(output_path).exists():
                size_mb = Path(output_path).stat().st_size / (1024 * 1024)
                print(f"OK ({size_mb:.1f}MB, {elapsed}s)")
            else:
                print(f"FAILED ({elapsed}s)")

    total = round(time.time() - t0, 1)
    step(f"完成 ({total}s)")
    print(f"  Scripts: {len(scripts)} phases")
    print(f"  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
