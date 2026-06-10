"""SurrealDB abstract layer. All DB calls go through this class."""

from surrealdb import AsyncSurreal
from typing import Any


class GraphBackend:
    """Async SurrealDB wrapper. If we migrate to another graph DB, only this file changes."""

    def __init__(self, db_url: str = "file://./data/graph.db"):
        self.db_url = db_url
        self.db: AsyncSurreal | None = None

    async def connect(self):
        self.db = AsyncSurreal(self.db_url)
        await self.db.connect()
        await self.db.use("vst", "main")
        return self

    async def execute(self, query: str, params: dict[str, Any] | None = None):
        return await self.db.query(query, params or {})

    async def create_node(self, table: str, id: str, data: dict):
        return await self.db.create(f"{table}:{id}", data)

    async def relate(self, from_id: str, rel: str, to_id: str, data: dict | None = None):
        set_clause = ""
        if data:
            items = ", ".join(f"{k} = {v!r}" if not isinstance(v, (int, float)) else f"{k} = {v}" for k, v in data.items())
            set_clause = f" SET {items}"
        return await self.db.query(f"RELATE {from_id}->{rel}->{to_id}{set_clause}")

    async def vector_search(self, table: str, query_vec: list[float], k: int = 3, ef: int = 100):
        return await self.db.query(
            f"SELECT *, vector::distance::knn() AS dist "
            f"FROM {table} WHERE embedding <|{k},{ef}|> $vec ORDER BY dist LIMIT {k}",
            {"vec": query_vec}
        )

    async def close(self):
        if self.db:
            await self.db.close()
