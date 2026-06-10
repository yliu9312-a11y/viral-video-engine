"""组件目录 — 统一真相源。

从 catalog.json 加载所有组件条目，提供:
- 按 kind/phase/role 硬过滤
- BGE-M3 语义搜索（带缓存）
- 运行时 Pydantic 模型生成（create_model，不 codegen）
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent.parent / "catalog.json"
EMBED_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "catalog_embeddings.pkl"


@dataclass
class CatalogEntry:
    """组件目录条目 — 单一真相源。"""
    id: str
    source: str           # remocn / mg_library / parametric / codegen
    render_component: str # 实际 Remotion 组件名
    import_path: str      # TS 导入路径
    status: str           # implemented / stub
    kind: str             # text / layout / transition / effect / background / composition
    description: str
    when_to_use: str
    when_not: str
    example_effect: str   # 一句效果描述（富候选卡用）
    props_schema: dict
    defaults: dict
    char_limits: dict | None
    phases: list[str]
    roles: list[str]
    tags: list[str]
    validation: dict
    phase_blacklist: list[str]
    kb_atom_names: list[str]
    visual_impact_score: float
    duration_range_s: list[float]
    embedding: list[float] | None = None


class ComponentCatalog:
    """统一组件目录 — 加载、过滤、搜索、生成 Pydantic 模型。"""

    def __init__(self, catalog_path: str | Path = CATALOG_PATH):
        self.entries: dict[str, CatalogEntry] = {}
        self._embedder = None  # lazy BGE-M3
        self._load(catalog_path)

    def _load(self, path: str | Path):
        """加载 catalog.json。"""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for comp in data.get("components", []):
            entry = CatalogEntry(
                id=comp["id"],
                source=comp.get("source", "unknown"),
                render_component=comp["render_component"],
                import_path=comp.get("import_path", ""),
                status=comp.get("status", "implemented"),
                kind=comp.get("kind", "composition"),
                description=comp.get("description", ""),
                when_to_use=comp.get("when_to_use", ""),
                when_not=comp.get("when_not", ""),
                example_effect=comp.get("example_effect", ""),
                props_schema=comp.get("props_schema", {}),
                defaults=comp.get("defaults", {}),
                char_limits=comp.get("char_limits"),
                phases=comp.get("phases", ["hook", "build", "cta"]),
                roles=comp.get("roles", []),
                tags=comp.get("tags", []),
                validation=comp.get("validation", {}),
                phase_blacklist=comp.get("phase_blacklist", []),
                kb_atom_names=comp.get("kb_atom_names", []),
                visual_impact_score=comp.get("visual_impact_score", 0.5),
                duration_range_s=comp.get("duration_range_s", [2, 8]),
            )
            self.entries[entry.id] = entry
        logger.info(f"组件目录加载: {len(self.entries)} 条目")

    # ── 查询 ──────────────────────────────────────────────────────────────

    def get(self, id: str) -> CatalogEntry | None:
        return self.entries.get(id)

    def list_all(self) -> list[CatalogEntry]:
        return list(self.entries.values())

    def list_by_kind(self, kind: str) -> list[CatalogEntry]:
        return [e for e in self.entries.values() if e.kind == kind]

    def list_by_phase(self, phase: str) -> list[CatalogEntry]:
        return [e for e in self.entries.values() if phase in e.phases]

    def list_implemented(self) -> list[CatalogEntry]:
        return [e for e in self.entries.values() if e.status == "implemented"]

    # ── 硬过滤（确定性，不靠 LLM）────────────────────────────────────────

    def filter_candidates(
        self,
        phase: str | None = None,
        kind: str | None = None,
        role: str | None = None,
        char_len: int | None = None,
        must_read: bool | None = None,
    ) -> list[CatalogEntry]:
        """硬过滤候选（确定性，不靠 LLM）。

        Args:
            phase: hook/build/cta
            kind: text/composition/effect/background/transition
            role: hero_text/content_cards/decorative/background/bottom_ticker/logo
            char_len: 文字长度（过滤掉 char_limits 不够的）
            must_read: True=只返回需要可读性的组件
        """
        candidates = self.list_implemented()

        if kind:
            candidates = [e for e in candidates if e.kind == kind]

        if phase:
            candidates = [e for e in candidates if phase in e.phases]
            candidates = [e for e in candidates if phase not in e.phase_blacklist]

        if role:
            candidates = [e for e in candidates if role in e.roles]

        if char_len is not None:
            # 过滤掉 char_limits 不够的组件
            filtered = []
            for e in candidates:
                if e.char_limits is None:
                    filtered.append(e)  # 无限制的组件总是可用
                elif char_len <= e.char_limits.get("max_chars", 999):
                    filtered.append(e)
            candidates = filtered

        if must_read is True:
            candidates = [e for e in candidates if e.validation.get("must_read", False)]

        return candidates

    # ── L1: 结构化需求 ────────────────────────────────────────────────────

    @staticmethod
    def build_need(
        phase: str,
        kind: str = "text",
        role: str = "hero_text",
        content_lang: str = "zh",
        content_len: int = 10,
        layout_family: str = "centered",
        style_family: str = "dark_neon_ui",
        mood: str = "energetic",
        must_read: bool = True,
    ) -> dict:
        """从场景数据构建结构化需求（L1 查询构造）。"""
        return {
            "phase": phase,
            "kind": kind,
            "role": role,
            "content_lang": content_lang,
            "content_len": content_len,
            "layout_family": layout_family,
            "style_family": style_family,
            "mood": mood,
            "must_read": must_read,
        }

    @staticmethod
    def need_to_query(need: dict) -> str:
        """将结构化需求转为 BGE-M3 语义查询字符串。"""
        parts = []
        if need.get("style_family"):
            parts.append(need["style_family"].replace("_", " "))
        if need.get("mood"):
            parts.append(need["mood"])
        if need.get("kind"):
            parts.append(need["kind"])
        if need.get("role"):
            parts.append(need["role"].replace("_", " "))
        if need.get("content_lang") == "en":
            parts.append("English")
        elif need.get("content_lang") == "zh":
            parts.append("Chinese")
        if need.get("content_len", 0) <= 4:
            parts.append("short")
        elif need.get("content_len", 0) <= 15:
            parts.append("medium length")
        else:
            parts.append("long")
        return " ".join(parts)

    # ── L2: 多因子排序 ────────────────────────────────────────────────────

    def rank(
        self,
        candidates: list[CatalogEntry],
        query: str,
        need: dict | None = None,
        already_used: list[str] | None = None,
        top_k: int = 5,
    ) -> list[tuple[CatalogEntry, float]]:
        """多因子排序（不只 cosine）。

        score = 0.35*cosine + 0.2*phase_fit + 0.15*style_fit
              + 0.1*visual_impact + 0.1*char_fit + 0.1*kind_fit
              - diversity_penalty
        """
        if not candidates:
            return []

        # cosine 分数
        cosine_scores = {}
        embedder = self._get_embedder()
        if embedder is not None:
            self._ensure_embeddings()
            query_vec = embedder.encode([query])[0]
            for entry in candidates:
                if entry.embedding is not None:
                    dot = sum(a * b for a, b in zip(query_vec, entry.embedding))
                    norm_q = sum(a * a for a in query_vec) ** 0.5
                    norm_e = sum(a * a for a in entry.embedding) ** 0.5
                    cosine_scores[entry.id] = dot / (norm_q * norm_e) if norm_q > 0 and norm_e > 0 else 0
        else:
            # keyword fallback
            query_lower = query.lower()
            for entry in candidates:
                text = f"{entry.description} {entry.when_to_use} {' '.join(entry.tags)}".lower()
                matches = sum(1 for w in query_lower.split() if w in text)
                cosine_scores[entry.id] = matches / max(len(query_lower.split()), 1)

        already_used = set(already_used or [])
        scored = []
        for entry in candidates:
            cos = cosine_scores.get(entry.id, 0)

            # phase 适配: 在 phases 里=1, 不在=0
            phase_fit = 1.0 if need and need.get("phase") in entry.phases else 0.5

            # style 适配: tags 里有 style_family 关键词
            style_fit = 0.5
            if need and need.get("style_family"):
                style_key = need["style_family"].replace("_", " ")
                entry_text = f"{entry.description} {entry.when_to_use} {' '.join(entry.tags)}".lower()
                style_fit = 1.0 if style_key in entry_text else 0.3

            # visual impact
            vis = entry.visual_impact_score

            # char 适配
            char_fit = 0.5
            if need and need.get("content_len") and entry.char_limits:
                max_c = entry.char_limits.get("max_chars", 999)
                ratio = need["content_len"] / max_c
                char_fit = 1.0 if ratio <= 1.0 else max(0, 1.0 - (ratio - 1.0) * 2)

            # kind 适配
            kind_fit = 1.0 if need and need.get("kind") == entry.kind else 0.3

            # 多样性惩罚: 已用过的组件降权
            diversity = -0.3 if entry.id in already_used else 0

            score = (
                0.35 * cos
                + 0.20 * phase_fit
                + 0.15 * style_fit
                + 0.10 * vis
                + 0.10 * char_fit
                + 0.10 * kind_fit
                + diversity
            )
            scored.append((entry, round(score, 4)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ── BGE-M3 语义搜索 ──────────────────────────────────────────────────

    def _get_embedder(self):
        """懒加载 BGE-M3。"""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("BAAI/bge-m3")
                logger.info("BGE-M3 加载完成")
            except Exception as e:
                logger.warning(f"BGE-M3 加载失败: {e}")
        return self._embedder

    def _compute_embeddings(self):
        """计算所有条目的 embedding 并缓存。"""
        embedder = self._get_embedder()
        if embedder is None:
            return

        for entry in self.entries.values():
            if entry.embedding is None:
                text = f"{entry.description} {entry.when_to_use}"
                entry.embedding = embedder.encode([text])[0].tolist()

        # 缓存到磁盘
        try:
            EMBED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cache = {eid: e.embedding for eid, e in self.entries.items() if e.embedding}
            with open(EMBED_CACHE_PATH, "wb") as f:
                pickle.dump(cache, f)
            logger.info(f"Embedding 缓存: {len(cache)} 条 → {EMBED_CACHE_PATH}")
        except Exception as e:
            logger.warning(f"Embedding 缓存失败: {e}")

    def _load_cached_embeddings(self) -> bool:
        """从缓存加载 embedding。返回是否成功。

        NOTE: pickle 仅用于加载本进程自己写入的缓存文件（data/catalog_embeddings.pkl）。
        该文件由 _compute_embeddings() 生成，不接受外部输入。
        """
        if not EMBED_CACHE_PATH.exists():
            return False
        try:
            with open(EMBED_CACHE_PATH, "rb") as f:
                cache = pickle.load(f)
            for eid, emb in cache.items():
                if eid in self.entries:
                    self.entries[eid].embedding = emb
            logger.info(f"从缓存加载 embedding: {len(cache)} 条")
            return True
        except Exception:
            return False

    def _ensure_embeddings(self):
        """确保所有条目有 embedding（缓存 → 计算）。"""
        has_all = all(e.embedding is not None for e in self.entries.values())
        if has_all:
            return
        if not self._load_cached_embeddings():
            self._compute_embeddings()

    def search(
        self,
        query: str,
        phase: str | None = None,
        kind: str | None = None,
        top_k: int = 5,
    ) -> list[tuple[CatalogEntry, float]]:
        """语义搜索。先硬过滤，再 BGE-M3 相似度排序。"""
        candidates = self.filter_candidates(phase=phase, kind=kind)
        if not candidates:
            return []

        embedder = self._get_embedder()
        if embedder is None:
            # fallback: 关键词匹配
            return self._keyword_search(query, candidates, top_k)

        self._ensure_embeddings()
        query_vec = embedder.encode([query])[0]

        scored = []
        for entry in candidates:
            if entry.embedding is None:
                continue
            # cosine similarity
            dot = sum(a * b for a, b in zip(query_vec, entry.embedding))
            norm_q = sum(a * a for a in query_vec) ** 0.5
            norm_e = sum(a * a for a in entry.embedding) ** 0.5
            sim = dot / (norm_q * norm_e) if norm_q > 0 and norm_e > 0 else 0
            scored.append((entry, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _keyword_search(
        self,
        query: str,
        candidates: list[CatalogEntry],
        top_k: int,
    ) -> list[tuple[CatalogEntry, float]]:
        """关键词 fallback 搜索。"""
        query_lower = query.lower()
        scored = []
        for entry in candidates:
            text = f"{entry.description} {entry.when_to_use} {' '.join(entry.tags)}".lower()
            # 简单关键词重叠
            matches = sum(1 for word in query_lower.split() if word in text)
            score = matches / max(len(query_lower.split()), 1)
            if score > 0:
                scored.append((entry, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ── Pydantic 模型生成（运行时，不 codegen）───────────────────────────

    _TYPE_MAP = {"str": str, "int": int, "float": float, "bool": bool, "list": list}

    def build_pydantic_model(self, entry_id: str) -> type[BaseModel]:
        """从 props_schema 动态创建 Pydantic 模型。"""
        entry = self.entries.get(entry_id)
        if entry is None:
            raise KeyError(f"Unknown catalog entry: {entry_id}")

        fields = {}
        for name, schema in entry.props_schema.items():
            typ = self._TYPE_MAP.get(schema.get("type", "str"), str)
            constraints = {}

            if "range" in schema:
                constraints["ge"] = schema["range"][0]
                constraints["le"] = schema["range"][1]
            if "max_chars" in schema:
                constraints["max_length"] = schema["max_chars"]
            if "enum" in schema:
                typ = str  # enum 在 create_model 里不好处理，用 str + 手动校验

            if schema.get("required"):
                default = ...
            else:
                default = schema.get("default")

            fields[name] = (typ, Field(default, **constraints))

        model_name = f"{entry.render_component}Props"
        return create_model(model_name, **fields)

    def get_all_pydantic_models(self) -> dict[str, type[BaseModel]]:
        """为所有 implemented 条目生成 Pydantic 模型。"""
        models = {}
        for entry in self.list_implemented():
            try:
                models[entry.id] = self.build_pydantic_model(entry.id)
            except Exception as e:
                logger.warning(f"Pydantic 模型生成失败 ({entry.id}): {e}")
        return models

    # ── KB 反向映射 ──────────────────────────────────────────────────────

    def get_kb_atom_map(self) -> dict[str, str]:
        """kb_atom_name → catalog_id 反向映射。"""
        result = {}
        for entry in self.entries.values():
            for atom_name in entry.kb_atom_names:
                result[atom_name] = entry.id
        return result

    # ── 统计 ──────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        implemented = self.list_implemented()
        kinds = {}
        for e in implemented:
            kinds[e.kind] = kinds.get(e.kind, 0) + 1
        return {
            "total": len(self.entries),
            "implemented": len(implemented),
            "stub": len(self.entries) - len(implemented),
            "by_kind": kinds,
        }


# ── 单例 ──────────────────────────────────────────────────────────────────

_catalog: ComponentCatalog | None = None


def get_catalog() -> ComponentCatalog:
    """获取全局单例目录。"""
    global _catalog
    if _catalog is None:
        _catalog = ComponentCatalog()
    return _catalog
