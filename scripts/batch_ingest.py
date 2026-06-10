#!/usr/bin/env python3
"""Batch ingest templates into the knowledge base.

Usage:
  python scripts/batch_ingest.py                           # ingest all from e2e_demo/viral_templates/
  python scripts/batch_ingest.py --dir /path/to/templates  # ingest from custom dir
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.graph_backend import GraphBackend
from kb.template_store import TemplateStore
from kb.agent.ingestion_agent import ingest_template

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DIR = PROJECT_ROOT / "e2e_demo" / "viral_templates"
DB_PATH = PROJECT_ROOT / "data" / "graph.db"


async def batch_ingest(template_dir: Path):
    if not DB_PATH.exists():
        print(f"ERROR: KB not found at {DB_PATH}. Run 'docker compose run --rm seed' first.")
        return

    gb = GraphBackend(f"file://{DB_PATH}")
    await gb.connect()
    store = TemplateStore(gb)

    template_files = sorted(template_dir.glob("tpl_*.json"))
    if not template_files:
        print(f"No template files found in {template_dir}")
        return

    print(f"Ingesting {len(template_files)} templates into KB...")
    print(f"DB: {DB_PATH}\n")

    stats = {"merge_existing": 0, "create_new": 0, "split": 0, "error": 0}
    t0 = time.time()

    for i, f in enumerate(template_files):
        with open(f, encoding="utf-8") as fh:
            template = json.load(fh)

        category = template.get("category", "通用")
        tid = template.get("template_id", f.stem)
        print(f"  [{i+1:2d}/{len(template_files)}] {tid} ({category})...", end=" ", flush=True)

        try:
            result = await ingest_template(template, vertical=category, gb=gb, store=store)
            stats[result.decision] = stats.get(result.decision, 0) + 1

            if result.decision == "merge_existing":
                print(f"merge → {result.target_tid}")
            elif result.decision == "create_new":
                print(f"create → {result.new_tids}")
            elif result.decision == "split":
                print(f"split → {result.new_tids}")
            else:
                print(f"{result.decision}: {result.reason}")
        except Exception as e:
            stats["error"] += 1
            print(f"ERROR: {e}")

    elapsed = round(time.time() - t0, 2)
    await gb.close()

    print(f"\n{'='*50}")
    print(f"Done in {elapsed}s")
    print(f"  merge_existing: {stats['merge_existing']}")
    print(f"  create_new:     {stats['create_new']}")
    print(f"  split:          {stats['split']}")
    print(f"  error:          {stats['error']}")

    # Count total patterns in KB
    gb2 = GraphBackend(f"file://{DB_PATH}")
    await gb2.connect()
    patterns = await gb2.execute("SELECT count() FROM pattern GROUP ALL")
    atoms = await gb2.execute("SELECT count() FROM atom GROUP ALL")
    modules = await gb2.execute("SELECT count() FROM module GROUP ALL")
    await gb2.close()

    print(f"\nKB size:")
    print(f"  patterns: {patterns}")
    print(f"  modules:  {modules}")
    print(f"  atoms:    {atoms}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="Template directory")
    args = parser.parse_args()

    asyncio.run(batch_ingest(Path(args.dir)))


if __name__ == "__main__":
    main()
