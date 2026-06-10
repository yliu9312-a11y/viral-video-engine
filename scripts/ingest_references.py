#!/usr/bin/env python3
"""Ingest viral reference videos: S1→S2→KB for each video."""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "python"))

from s1_analyzer import run_s1
from s2_extractor import run_s2
from kb.graph_backend import GraphBackend
from kb.template_store import TemplateStore
from kb.agent.ingestion_agent import ingest_template

PROJECT_ROOT = Path(__file__).parent.parent
REF_DIR = Path("/Users/adrian-us/project/VST/assets/motion_graphics/viral_references")
DB_PATH = PROJECT_ROOT / "data" / "graph.db"
OUTPUT_DIR = PROJECT_ROOT / "e2e_demo" / "ref_output"


def main():
    if not DB_PATH.exists():
        print(f"ERROR: KB not found at {DB_PATH}")
        return

    video_files = sorted(REF_DIR.glob("*.mp4"))
    if not video_files:
        print(f"No videos found in {REF_DIR}")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Processing {len(video_files)} reference videos...\n")

    async def process():
        gb = GraphBackend(f"file://{DB_PATH}")
        await gb.connect()
        store = TemplateStore(gb)

        t0 = time.time()
        for i, vf in enumerate(video_files):
            print(f"[{i+1}/{len(video_files)}] {vf.name}")
            vid_output = str(OUTPUT_DIR / vf.stem)
            Path(vid_output).mkdir(parents=True, exist_ok=True)

            # S1: video analysis
            try:
                s1 = run_s1(str(vf), output_dir=vid_output)
                print(f"  S1: {len(s1.shots)} shots, {s1.total_duration:.1f}s")
            except Exception as e:
                print(f"  S1 FAILED: {e}")
                continue

            # S2: structure extraction
            try:
                template = run_s2(s1)
                template["source_videos"] = [str(vf)]
                tpl_path = Path(vid_output) / "template.json"
                with open(tpl_path, "w", encoding="utf-8") as f:
                    json.dump(template, f, ensure_ascii=False, indent=2)
                print(f"  S2: {template['template_id']} ({template['category']})")
            except Exception as e:
                print(f"  S2 FAILED: {e}")
                continue

            # S5: KB ingest
            try:
                result = await ingest_template(template, vertical=template.get("category", "MG"), gb=gb, store=store)
                if result.decision == "merge_existing":
                    print(f"  KB: merge → {result.target_tid}")
                elif result.decision == "create_new":
                    print(f"  KB: create → {result.new_tids}")
                else:
                    print(f"  KB: {result.decision}")
            except Exception as e:
                print(f"  KB FAILED: {e}")

        elapsed = round(time.time() - t0, 1)
        await gb.close()
        print(f"\nDone in {elapsed}s")

    asyncio.run(process())


if __name__ == "__main__":
    main()
