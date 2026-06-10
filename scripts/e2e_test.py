#!/usr/bin/env python3
"""E2E pipeline test: video → shots → template → gap → assign → render → KB ingest.

Usage:
  python scripts/e2e_test.py                    # fast mode (skip S1 VLM, use algorithmic only)
  python scripts/e2e_test.py --with-vlm         # full mode (call MiMo-V2.5 for scene captions)
  python scripts/e2e_test.py --skip-render      # skip Remotion render step
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add project root and services/python to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "python"))

PROJECT_ROOT = Path(__file__).parent.parent
TEST_VIDEO = PROJECT_ROOT / "e2e_demo" / "test_video.mp4"
MATERIALS_DIR = PROJECT_ROOT / "e2e_demo" / "materials"
OUTPUT_DIR = PROJECT_ROOT / "e2e_demo" / "output"


def step(msg: str):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def run_s1(video_path: str, with_vlm: bool = False) -> dict:
    """S1: Video analysis → shots + features."""
    from s1_analyzer import run_s1

    output_dir = str(OUTPUT_DIR / "s1")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = run_s1(video_path, output_dir=output_dir)
    return {
        "shots": len(result.shots),
        "duration": result.total_duration,
        "fps": result.fps,
        "resolution": f"{result.width}x{result.height}",
        "output_dir": output_dir,
        "s1_output": result,
    }


def run_s2(s1_output) -> dict:
    """S2: Structure extraction → StructureTemplate JSON."""
    from s2_extractor import run_s2

    template = run_s2(s1_output)
    output_dir = str(OUTPUT_DIR / "s2")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    template_path = str(Path(output_dir) / "structure_template.json")
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    return {
        "template_id": template.get("template_id", ""),
        "category": template.get("category", ""),
        "phases": len(template.get("timeline", [])),
        "template_path": template_path,
        "template": template,
    }


def run_gap(template: dict, material_dir: str) -> dict:
    """S3a: Gap detection."""
    from s3_gap_detector import run_gap_detection

    output_dir = str(OUTPUT_DIR / "gap")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    report = run_gap_detection(
        template=template,
        material_dir=material_dir,
        output_dir=output_dir,
    )

    gap_report_path = str(Path(output_dir) / "gap_report.json")
    return {
        "total_gaps": report.get("summary", {}).get("total_gaps", 0),
        "severity": report.get("summary", {}).get("overall_severity", "LOW"),
        "gap_report_path": gap_report_path,
        "gap_report": report,
    }


def run_assign(gap_report_path: str, template_path: str, material_dir: str) -> dict:
    """S3b: Strategy assignment."""
    from s3_strategist import run_strategist

    output_dir = str(OUTPUT_DIR / "assign")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = run_strategist(
        gap_report_path=gap_report_path,
        template_path=template_path,
        material_dir=material_dir,
        output_dir=output_dir,
    )

    strategies_used = set()
    for phase in result.get("phases", []):
        sid = phase.get("strategy_id", "")
        if sid:
            strategies_used.add(sid)

    assignment_path = str(Path(output_dir) / "material_assignment.json")
    return {
        "phases": len(result.get("phases", [])),
        "strategies": sorted(strategies_used),
        "total_duration": result.get("total_duration_s", 0),
        "assignment_path": assignment_path,
        "assignment": result,
    }


def run_kb_ingest(template: dict, vertical: str = "通用") -> dict:
    """S5: KB ingestion agent."""
    import asyncio
    from kb.graph_backend import GraphBackend
    from kb.template_store import TemplateStore
    from kb.agent.ingestion_agent import ingest_template

    db_path = str(PROJECT_ROOT / "data" / "graph.db")
    if not Path(db_path).exists():
        return {"decision": "skipped", "reason": "KB not initialized (run seed first)"}

    async def _ingest():
        gb = GraphBackend(f"file://{db_path}")
        await gb.connect()
        store = TemplateStore(gb)
        result = await ingest_template(template, vertical=vertical, gb=gb, store=store)
        await gb.close()
        return result

    result = asyncio.run(_ingest())
    return {
        "decision": result.decision,
        "reason": result.reason,
        "target_tid": result.target_tid,
        "new_tids": result.new_tids,
        "similar_count": len(result.similar_patterns),
    }


def main():
    parser = argparse.ArgumentParser(description="VST E2E Pipeline Test")
    parser.add_argument("--with-vlm", action="store_true", help="Use VLM for S1 captions")
    parser.add_argument("--skip-render", action="store_true", help="Skip Remotion rendering")
    args = parser.parse_args()

    if not TEST_VIDEO.exists():
        print(f"ERROR: Test video not found: {TEST_VIDEO}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    t0 = time.time()

    # ── S1: Video Analysis ──
    step("S1 视频分析")
    t = time.time()
    s1 = run_s1(str(TEST_VIDEO), with_vlm=args.with_vlm)
    s1["elapsed"] = round(time.time() - t, 2)
    results["s1"] = s1
    print(f"  Shots: {s1['shots']}")
    print(f"  Duration: {s1['duration']:.1f}s")
    print(f"  Resolution: {s1['resolution']}")
    print(f"  Time: {s1['elapsed']}s")

    # ── S2: Structure Extraction ──
    step("S2 结构提取")
    t = time.time()
    s2 = run_s2(s1["s1_output"])
    s2["elapsed"] = round(time.time() - t, 2)
    results["s2"] = s2
    print(f"  Template ID: {s2['template_id']}")
    print(f"  Category: {s2['category']}")
    print(f"  Phases: {s2['phases']}")
    print(f"  Time: {s2['elapsed']}s")

    # ── S3a: Gap Detection ──
    step("S3a 缺口检测")
    t = time.time()
    gap = run_gap(s2["template"], str(MATERIALS_DIR))
    gap["elapsed"] = round(time.time() - t, 2)
    results["gap"] = gap
    print(f"  Total gaps: {gap['total_gaps']}")
    print(f"  Severity: {gap['severity']}")
    print(f"  Time: {gap['elapsed']}s")

    # ── S3b: Strategy Assignment ──
    step("S3b 策略生成")
    t = time.time()
    assign = run_assign(gap["gap_report_path"], s2["template_path"], str(MATERIALS_DIR))
    assign["elapsed"] = round(time.time() - t, 2)
    results["assign"] = assign
    print(f"  Phases: {assign['phases']}")
    print(f"  Strategies: {', '.join(assign['strategies'])}")
    print(f"  Duration: {assign['total_duration']:.1f}s")
    print(f"  Time: {assign['elapsed']}s")

    # ── S4: Rendering ──
    if not args.skip_render:
        step("S4 Remotion 渲染")
        t = time.time()
        import subprocess
        render_out = str(OUTPUT_DIR / "render.mp4")
        cmd = [
            "npx", "tsx",
            str(PROJECT_ROOT / "scripts" / "render.ts"),
            assign["assignment_path"],
            render_out,
            "22",
        ]
        print(f"  Running: {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)
        render_elapsed = round(time.time() - t, 2)
        if proc.returncode == 0 and Path(render_out).exists():
            size_mb = Path(render_out).stat().st_size / (1024 * 1024)
            results["render"] = {"success": True, "path": render_out, "size_mb": round(size_mb, 2), "elapsed": render_elapsed}
            print(f"  Output: {render_out} ({size_mb:.1f}MB)")
        else:
            results["render"] = {"success": False, "stderr": proc.stderr[-500:] if proc.stderr else "", "elapsed": render_elapsed}
            print(f"  FAILED: {proc.stderr[-200:] if proc.stderr else 'unknown error'}")
        print(f"  Time: {render_elapsed}s")
    else:
        results["render"] = {"success": False, "reason": "skipped"}
        print("\n  S4 渲染: SKIPPED")

    # ── S5: KB Ingestion ──
    step("S5 知识库入图")
    t = time.time()
    kb = run_kb_ingest(s2["template"])
    kb["elapsed"] = round(time.time() - t, 2)
    results["kb"] = kb
    print(f"  Decision: {kb['decision']}")
    print(f"  Reason: {kb['reason']}")
    if kb.get("target_tid"):
        print(f"  Merged into: {kb['target_tid']}")
    if kb.get("new_tids"):
        print(f"  Created: {kb['new_tids']}")
    print(f"  Time: {kb['elapsed']}s")

    # ── Summary ──
    total = round(time.time() - t0, 2)
    step("E2E 测试结果")
    print(f"  总耗时: {total}s")
    print(f"  S1 shots: {results['s1']['shots']}")
    print(f"  S2 template: {results['s2']['template_id']} ({results['s2']['category']})")
    print(f"  S3 gaps: {results['gap']['total_gaps']} ({results['gap']['severity']})")
    print(f"  S3 strategies: {', '.join(results['assign']['strategies'])}")
    print(f"  S4 render: {'OK' if results['render'].get('success') else 'SKIP/FAIL'}")
    print(f"  S5 KB: {results['kb']['decision']}")

    # Save summary
    summary_path = str(OUTPUT_DIR / "e2e_summary.json")
    save_results = {k: {kk: vv for kk, vv in v.items() if kk != "s1_output" and kk != "template" and kk != "gap_report" and kk != "assignment"} for k, v in results.items()}
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(save_results, f, ensure_ascii=False, indent=2)
    print(f"\n  Summary saved: {summary_path}")

    # Determine pass/fail
    passed = all([
        results["s1"]["shots"] > 0,
        results["s2"]["template_id"] != "",
        results["assign"]["phases"] > 0,
    ])
    print(f"\n  {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
