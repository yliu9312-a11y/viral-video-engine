#!/usr/bin/env python3
"""build_registry.py — 从 catalog.json 自动生成注册文件。

只生成 TypeScript COMPONENT_MAP（必须 codegen）。
Python 侧用 runtime create_model（不生成 .py）。

用法: python scripts/build_registry.py [--check]
  --check: 只校验不生成（CI 模式）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CATALOG_PATH = PROJECT_ROOT / "catalog.json"
TS_OUTPUT = PROJECT_ROOT / "web" / "src" / "components" / "mg" / "_generated_component_map.ts"
COMPONENTS_DIR = PROJECT_ROOT / "web" / "src" / "components" / "mg"


def load_catalog() -> list[dict]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("components", [])


def validate_import_paths(components: list[dict]) -> list[str]:
    """校验每个 implemented 组件的 import_path 对应真实 .tsx 文件。"""
    errors = []
    for comp in components:
        if comp.get("status") != "implemented":
            continue
        import_path = comp.get("import_path", "")
        if not import_path:
            errors.append(f"{comp['id']}: missing import_path")
            continue
        # import_path like "../../components/mg/WordReveal"
        # Resolve relative to the generated file location
        tsx_name = import_path.split("/")[-1]
        tsx_file = COMPONENTS_DIR / f"{tsx_name}.tsx"
        if not tsx_file.exists():
            errors.append(f"{comp['id']}: import_path '{import_path}' → {tsx_file} NOT FOUND")
    return errors


def generate_ts_map(components: list[dict]) -> str:
    """生成 TypeScript COMPONENT_MAP 文件内容。"""
    lines = [
        "// AUTO-GENERATED from catalog.json — DO NOT EDIT",
        "// Run: python scripts/build_registry.py",
        "",
    ]

    # Imports
    imports = []
    for comp in components:
        if comp.get("status") != "implemented":
            continue
        name = comp["render_component"]
        path = comp.get("import_path", "")
        if path:
            imports.append(f'import {{ {name} }} from "{path}";')

    lines.extend(sorted(imports))
    lines.append("")

    # Component map
    lines.append("export const GENERATED_COMPONENT_MAP: Record<string, React.FC<Record<string, unknown>>> = {")
    for comp in components:
        if comp.get("status") != "implemented":
            continue
        cid = comp["id"]
        name = comp["render_component"]
        lines.append(f"  {cid}: (props) => <{name} {{...props}} />,")
    lines.append("};")
    lines.append("")

    # Reverse map: render_component → catalog_id
    lines.append("export const COMPONENT_ID_MAP: Record<string, string> = {")
    for comp in components:
        if comp.get("status") != "implemented":
            continue
        lines.append(f'  "{comp["render_component"]}": "{comp["id"]}",')
    lines.append("};")
    lines.append("")

    return "\n".join(lines)


def main():
    check_mode = "--check" in sys.argv
    components = load_catalog()
    print(f"Catalog: {len(components)} components")

    # Validate
    errors = validate_import_paths(components)
    if errors:
        print(f"\n❌ Validation errors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        if check_mode:
            sys.exit(1)
        else:
            print("\n⚠️  Continuing despite errors (some components may not render)")
    else:
        print("✅ All import_paths validated")

    # Generate TS
    if not check_mode:
        ts_content = generate_ts_map(components)
        TS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        TS_OUTPUT.write_text(ts_content, encoding="utf-8")
        print(f"✅ Generated: {TS_OUTPUT}")
    else:
        # Check mode: verify existing file matches
        if TS_OUTPUT.exists():
            expected = generate_ts_map(components)
            actual = TS_OUTPUT.read_text(encoding="utf-8")
            if expected.strip() == actual.strip():
                print("✅ TS map is up to date")
            else:
                print("❌ TS map is stale — run `python scripts/build_registry.py`")
                sys.exit(1)
        else:
            print("❌ TS map not found — run `python scripts/build_registry.py`")
            sys.exit(1)

    # Stats
    implemented = [c for c in components if c.get("status") == "implemented"]
    kinds = {}
    for c in implemented:
        k = c.get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1
    print(f"\nStats: {len(implemented)} implemented, kinds={kinds}")


if __name__ == "__main__":
    main()
