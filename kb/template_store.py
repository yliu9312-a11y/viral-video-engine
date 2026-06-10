"""Knowledge base: write/search StructureTemplates with SurrealDB + BGE-M3."""

import json
import uuid
from pathlib import Path
from typing import Any

from kb.graph_backend import GraphBackend


class TemplateStore:
    """Read/write StructureTemplates to SurrealDB with vector embeddings."""

    def __init__(self, gb: GraphBackend, embedder=None):
        self.gb = gb
        self._embedder = embedder

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("BAAI/bge-m3")
        return self._embedder

    async def init_schema(self):
        """Create tables and HNSW indexes for the full 4-node 3-edge ontology."""
        # ── Node tables ──
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS pattern SCHEMAFULL;
            DEFINE FIELD IF NOT EXISTS category       ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS description    ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS hook_type      ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS build_pattern  ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS cta_type       ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS duration_min   ON pattern TYPE float;
            DEFINE FIELD IF NOT EXISTS duration_max   ON pattern TYPE float;
            DEFINE FIELD IF NOT EXISTS full_json      ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS appearance_count ON pattern TYPE int DEFAULT 1;
            DEFINE FIELD IF NOT EXISTS target_vertical ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS created_at     ON pattern TYPE string;
            DEFINE FIELD IF NOT EXISTS embedding      ON pattern TYPE array<float>;
        """)
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS module SCHEMAFULL;
            DEFINE FIELD IF NOT EXISTS phase             ON module TYPE string;
            DEFINE FIELD IF NOT EXISTS narrative_pattern  ON module TYPE string;
            DEFINE FIELD IF NOT EXISTS script_template    ON module TYPE string;
            DEFINE FIELD IF NOT EXISTS duration_min_s     ON module TYPE float;
            DEFINE FIELD IF NOT EXISTS duration_max_s     ON module TYPE float;
            DEFINE FIELD IF NOT EXISTS description        ON module TYPE string;
            DEFINE FIELD IF NOT EXISTS appearance_count   ON module TYPE int DEFAULT 1;
            DEFINE FIELD IF NOT EXISTS embedding          ON module TYPE array<float>;
        """)
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS atom SCHEMAFULL;
            DEFINE FIELD IF NOT EXISTS type               ON atom TYPE string;
            DEFINE FIELD IF NOT EXISTS category           ON atom TYPE string;
            DEFINE FIELD IF NOT EXISTS remotion_component ON atom TYPE string;
            DEFINE FIELD IF NOT EXISTS description        ON atom TYPE string;
            DEFINE FIELD IF NOT EXISTS required_inputs    ON atom TYPE array<string>;
            DEFINE FIELD IF NOT EXISTS fills_shot_types   ON atom TYPE array<string>;
            DEFINE FIELD IF NOT EXISTS has_3d_fallback    ON atom TYPE option<string>;
            DEFINE FIELD IF NOT EXISTS duration_min_s     ON atom TYPE float;
            DEFINE FIELD IF NOT EXISTS duration_max_s     ON atom TYPE float;
            DEFINE FIELD IF NOT EXISTS visual_impact_score ON atom TYPE float;
            DEFINE FIELD IF NOT EXISTS tech_stack         ON atom TYPE array<string>;
            DEFINE FIELD IF NOT EXISTS appearance_count   ON atom TYPE int DEFAULT 0;
            DEFINE FIELD IF NOT EXISTS embedding          ON atom TYPE array<float>;
        """)
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS vertical SCHEMAFULL;
            DEFINE FIELD IF NOT EXISTS name ON vertical TYPE string;
        """)
        # ── Relation tables ──
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS best_for SCHEMAFULL TYPE RELATION;
            DEFINE FIELD IF NOT EXISTS confidence ON best_for TYPE float;
        """)
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS composed_of SCHEMAFULL TYPE RELATION;
            DEFINE FIELD IF NOT EXISTS position         ON composed_of TYPE int;
            DEFINE FIELD IF NOT EXISTS duration_pct_min ON composed_of TYPE float;
            DEFINE FIELD IF NOT EXISTS duration_pct_max ON composed_of TYPE float;
        """)
        await self.gb.execute("""
            DEFINE TABLE IF NOT EXISTS built_from SCHEMAFULL TYPE RELATION;
            DEFINE FIELD IF NOT EXISTS weight   ON built_from TYPE float;
            DEFINE FIELD IF NOT EXISTS optional ON built_from TYPE bool DEFAULT false;
        """)
        # ── HNSW indexes (OVERWRITE to be idempotent) ──
        for table in ["pattern", "module", "atom"]:
            await self.gb.execute(f"""
                DEFINE INDEX OVERWRITE {table}_embedding_idx
                ON {table}
                FIELDS embedding
                HNSW DIMENSION 1024 DIST COSINE
            """)

    @staticmethod
    def _safe_id(name: str) -> str:
        """Convert Chinese name to ASCII-safe ID."""
        import hashlib
        # Use pinyin-like transliteration or hash
        mapping = {
            "美妆": "meizhuang", "数码": "shuma", "美食": "meishi",
            "通用": "tongyong", "护肤": "hufu", "家居": "jiaju",
        }
        if name in mapping:
            return mapping[name]
        # Fallback: short hash
        return hashlib.md5(name.encode()).hexdigest()[:8]

    async def store_atom(self, atom: dict) -> str:
        """Store an Atom node with embedding. Returns atom ID."""
        atom_id = atom.get("atom_id", f"atom_{uuid.uuid4().hex[:8]}")
        desc = atom.get("description", "")
        emb = self.embedder.encode([desc])[0].tolist()

        await self.gb.create_node("atom", atom_id, {
            "type": atom.get("type", "shot"),
            "category": atom.get("category", "build"),
            "remotion_component": atom.get("remotion_component", ""),
            "description": desc,
            "required_inputs": atom.get("required_inputs", []),
            "fills_shot_types": atom.get("fills_shot_types", []),
            "has_3d_fallback": atom.get("has_3d_fallback"),
            "duration_min_s": atom.get("duration_min_s", 1.0),
            "duration_max_s": atom.get("duration_max_s", 5.0),
            "visual_impact_score": atom.get("visual_impact_score", 0.5),
            "tech_stack": atom.get("tech_stack", []),
            "appearance_count": atom.get("appearance_count", 0),
            "embedding": emb,
        })
        return atom_id

    async def store_module(self, mod: dict) -> str:
        """Store a Module node with embedding + built_from edges to atoms. Returns module ID."""
        module_id = mod.get("module_id", f"mod_{uuid.uuid4().hex[:8]}")
        desc = mod.get("description", "")
        emb = self.embedder.encode([desc])[0].tolist()

        await self.gb.create_node("module", module_id, {
            "phase": mod.get("phase", "build"),
            "narrative_pattern": mod.get("narrative_pattern", ""),
            "script_template": mod.get("script_template", ""),
            "duration_min_s": mod.get("duration_min_s", 3.0),
            "duration_max_s": mod.get("duration_max_s", 8.0),
            "description": desc,
            "appearance_count": 1,
            "embedding": emb,
        })

        # Create built_from edges to atoms
        for atom_ref in mod.get("atoms", []):
            atom_id = atom_ref.get("atom_id", "")
            if atom_id:
                await self.gb.relate(
                    f"module:{module_id}", "built_from", f"atom:{atom_id}",
                    {"weight": atom_ref.get("weight", 0.5), "optional": atom_ref.get("optional", False)}
                )
        return module_id

    async def store_template(self, template: dict, vertical: str = "通用", module_ids: list[str] | None = None) -> str:
        """Store a StructureTemplate with embedding. Returns pattern ID.

        Args:
            template: StructureTemplate dict
            vertical: product/content category
            module_ids: optional list of module IDs to link via composed_of
        """
        pattern_id = template.get("template_id", f"tpl_{uuid.uuid4().hex[:8]}")

        # Build description for embedding
        narrative = template.get("narrative", {})
        timeline = template.get("timeline", [])
        desc_parts = [
            f"类别:{template.get('category', '通用')}",
            f"钩子:{narrative.get('hook_type', '')}",
            f"结构:{narrative.get('build_pattern', '')}",
            f"CTA:{narrative.get('cta_type', '')}",
        ]
        for phase in timeline:
            desc_parts.append(f"{phase.get('phase', '')}:{','.join(phase.get('required_shot_types', []))}")
        description = "|".join(desc_parts)

        # Generate embedding
        emb = self.embedder.encode([description])[0].tolist()

        # Store pattern node
        await self.gb.create_node("pattern", pattern_id, {
            "category": template.get("category", "通用"),
            "description": description,
            "hook_type": narrative.get("hook_type", ""),
            "build_pattern": narrative.get("build_pattern", ""),
            "cta_type": narrative.get("cta_type", ""),
            "duration_min": template.get("duration_range", [0, 30])[0],
            "duration_max": template.get("duration_range", [0, 30])[1],
            "full_json": json.dumps(template, ensure_ascii=False),
            "appearance_count": 1,
            "target_vertical": vertical,
            "created_at": template.get("provenance", {}).get("extraction_date", ""),
            "embedding": emb,
        })

        # Create vertical node with ASCII-safe ID, then relate
        vert_id = self._safe_id(vertical)
        await self.gb.execute(
            f"UPSERT vertical:{vert_id} SET name = $name",
            {"name": vertical}
        )
        await self.gb.relate(f"pattern:{pattern_id}", "best_for", f"vertical:{vert_id}", {"confidence": 0.9})

        # Create composed_of edges to modules
        if module_ids:
            timeline = template.get("timeline", [])
            for i, mid in enumerate(module_ids):
                phase_data = timeline[i] if i < len(timeline) else {}
                dur_pct = phase_data.get("duration_pct", [0, 0.33])
                await self.gb.relate(
                    f"pattern:{pattern_id}", "composed_of", f"module:{mid}",
                    {"position": i, "duration_pct_min": dur_pct[0], "duration_pct_max": dur_pct[1]}
                )

        return pattern_id

    async def search_similar(self, query: str, top_k: int = 3) -> list[dict]:
        """Search for similar patterns by semantic similarity."""
        query_emb = self.embedder.encode([query])[0].tolist()

        results = await self.gb.execute("""
            SELECT *,
                   vector::distance::knn() AS dist,
                   ->best_for->vertical.name AS verticals
            FROM pattern
            WHERE embedding <|10,100|> $vec
            ORDER BY dist
            LIMIT $k
        """, {"vec": query_emb, "k": top_k})

        # Parse full_json back to dict
        for r in results:
            if "full_json" in r and isinstance(r["full_json"], str):
                try:
                    r["template"] = json.loads(r["full_json"])
                except json.JSONDecodeError:
                    r["template"] = {}

        return results

    async def get_pattern(self, pattern_id: str) -> dict | None:
        """Get a single pattern by ID."""
        results = await self.gb.execute(
            f"SELECT * FROM pattern:{pattern_id}"
        )
        if results and results[0]:
            r = results[0]
            if "full_json" in r and isinstance(r["full_json"], str):
                try:
                    r["template"] = json.loads(r["full_json"])
                except json.JSONDecodeError:
                    r["template"] = {}
            return r
        return None

    async def find_atoms_for_gap(
        self,
        missing_shot_type: str,
        phase: str,
        have_3d: bool = False,
        top_k: int = 5,
    ) -> list[dict]:
        """Find candidate atoms that can fill a specific gap.

        Uses vector search on atom descriptions + category/fills_shot_types filtering.
        """
        type_emb = self.embedder.encode([missing_shot_type])[0].tolist()

        results = await self.gb.execute("""
            SELECT *,
                   vector::distance::knn() AS dist
            FROM atom
            WHERE embedding <|10,100|> $vec
              AND category = $phase
              AND $shot_type IN fills_shot_types
            ORDER BY visual_impact_score DESC, dist ASC
            LIMIT $k
        """, {"vec": type_emb, "phase": phase, "shot_type": missing_shot_type, "k": top_k})

        return results

    async def get_pattern_full(self, pattern_id: str) -> dict | None:
        """Get full pattern subgraph: pattern → modules → atoms (multi-hop)."""
        # Get pattern
        pattern_results = await self.gb.execute(
            f"SELECT * FROM pattern:{pattern_id}"
        )
        if not pattern_results or not pattern_results[0]:
            return None
        pattern = pattern_results[0]

        # Get composed_of edges to find module IDs
        edge_results = await self.gb.execute(
            f"SELECT out, position FROM composed_of WHERE in = pattern:{pattern_id}"
        )

        modules = []
        for edge in (edge_results or []):
            out_ref = edge.get("out", "")
            mod_id = str(out_ref).split(":")[-1] if ":" in str(out_ref) else str(out_ref)
            if not mod_id:
                continue

            # Get module data
            mod_results = await self.gb.execute(f"SELECT * FROM module:{mod_id}")
            if not mod_results or not mod_results[0]:
                continue
            mod = mod_results[0]

            # Get built_from edges to find atom IDs
            atom_edges = await self.gb.execute(
                f"SELECT out, weight, optional FROM built_from WHERE in = module:{mod_id}"
            )

            atoms = []
            for ae in (atom_edges or []):
                atom_ref = ae.get("out", "")
                atom_id = str(atom_ref).split(":")[-1] if ":" in str(atom_ref) else str(atom_ref)
                if not atom_id:
                    continue
                atom_results = await self.gb.execute(f"SELECT * FROM atom:{atom_id}")
                if atom_results and atom_results[0]:
                    atom_data = atom_results[0]
                    atom_data["_weight"] = ae.get("weight", 0.5)
                    atom_data["_optional"] = ae.get("optional", False)
                    atoms.append(atom_data)

            mod["atoms"] = atoms
            mod["_position"] = edge.get("position", 0)
            modules.append(mod)

        # Sort modules by position
        modules.sort(key=lambda m: m.get("_position", 0))
        pattern["modules"] = modules
        return pattern

    async def list_patterns(self, limit: int = 50) -> list[dict]:
        """List all patterns."""
        results = await self.gb.execute(
            "SELECT description, category, hook_type, appearance_count, ->best_for->vertical.name AS verticals FROM pattern LIMIT $l",
            {"l": limit}
        )
        return results
