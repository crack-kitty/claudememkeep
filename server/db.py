"""PostgreSQL database layer using asyncpg."""

import json
import os
from pathlib import Path

import asyncpg

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ["DATABASE_URL"],
            min_size=2,
            max_size=10,
        )
        await _init_schema(_pool)
    return _pool


async def _init_schema(pool: asyncpg.Pool) -> None:
    schema_path = Path(__file__).parent.parent / "sql" / "schema.sql"
    schema_sql = schema_path.read_text()
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def save_artifact(
    project: str,
    type: str,
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
    source_session: str | None = None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO artifacts (project, type, title, content, tags, source_session)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            RETURNING id, project, type, title, content, tags, source_session, created_at
            """,
            project,
            type,
            title,
            content,
            json.dumps(tags or []),
            source_session,
        )
        return _row_to_dict(row)


async def search_artifacts(
    query: str, project: str = "default", limit: int = 5
) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, project, type, title, content, tags, source_session, created_at,
                   ts_rank(search_vector, websearch_to_tsquery('english', $1)) AS rank
            FROM artifacts
            WHERE search_vector @@ websearch_to_tsquery('english', $1)
              AND project = $2
            ORDER BY rank DESC
            LIMIT $3
            """,
            query,
            project,
            limit,
        )
        return [_row_to_dict(row) for row in rows]


async def get_summary(project: str = "default") -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        decisions = await conn.fetch(
            """
            SELECT id, title, content, created_at
            FROM artifacts
            WHERE project = $1 AND type = 'decision'
            ORDER BY created_at DESC
            LIMIT 10
            """,
            project,
        )

        sessions = await conn.fetch(
            """
            SELECT session_id, source, summary, started_at, ended_at
            FROM sessions
            WHERE project = $1
            ORDER BY started_at DESC
            LIMIT 5
            """,
            project,
        )

        type_counts = await conn.fetch(
            """
            SELECT type, COUNT(*) AS count
            FROM artifacts
            WHERE project = $1
            GROUP BY type
            """,
            project,
        )

        return {
            "project": project,
            "recent_decisions": [_row_to_dict(r) for r in decisions],
            "recent_sessions": [_row_to_dict(r) for r in sessions],
            "artifact_counts": {r["type"]: r["count"] for r in type_counts},
        }


async def get_recent(project: str = "default", hours: int = 48) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        artifacts = await conn.fetch(
            """
            SELECT id, project, type, title, content, tags, source_session, created_at
            FROM artifacts
            WHERE project = $1 AND created_at > NOW() - make_interval(hours => $2)
            ORDER BY created_at DESC
            """,
            project,
            hours,
        )

        sessions = await conn.fetch(
            """
            SELECT session_id, source, summary, started_at, ended_at
            FROM sessions
            WHERE project = $1 AND started_at > NOW() - make_interval(hours => $2)
            ORDER BY started_at DESC
            """,
            project,
            hours,
        )

        return {
            "project": project,
            "hours": hours,
            "artifacts": [_row_to_dict(r) for r in artifacts],
            "sessions": [_row_to_dict(r) for r in sessions],
        }


async def upsert_session(
    session_id: str,
    source: str,
    project: str = "default",
    summary: str = "",
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sessions (session_id, source, project, summary)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (session_id) DO UPDATE
              SET summary = EXCLUDED.summary,
                  ended_at = NOW()
            RETURNING id, session_id, source, project, summary, started_at, ended_at
            """,
            session_id,
            source,
            project,
            summary,
        )
        return _row_to_dict(row)


def _row_to_dict(row: asyncpg.Record) -> dict:
    d = dict(row)
    for key, val in d.items():
        if hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d
