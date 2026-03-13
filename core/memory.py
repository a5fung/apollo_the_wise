"""
Memory — PostgreSQL + pgvector.
Stores conversation history and long-term user memories with semantic search.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import asyncpg

from shared.models import ConversationMessage, MemoryEntry, MessageRole
from shared.secrets import get_secrets

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        secrets = get_secrets()
        # asyncpg uses a different DSN format
        host = secrets.postgres_dsn_sync.split("@")[1].split("/")[0].split(":")[0]
        port_db = secrets.postgres_dsn_sync.split("@")[1].split("/")
        port = int(port_db[0].split(":")[1]) if ":" in port_db[0] else 5432
        db = port_db[1] if len(port_db) > 1 else "apollo"
        user_pass = secrets.postgres_dsn_sync.split("://")[1].split("@")[0]
        user = user_pass.split(":")[0]
        password = user_pass.split(":")[1] if ":" in user_pass else ""

        _pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=db,
            user=user,
            password=password,
            min_size=2,
            max_size=10,
        )
    return _pool


async def initialize_schema() -> None:
    """Create tables if they don't exist. Run at startup."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE EXTENSION IF NOT EXISTS vector;

            CREATE TABLE IF NOT EXISTS conversations (
                message_id      TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                user_id         BIGINT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                agent           TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                metadata        JSONB NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_conversations_conv_id
                ON conversations(conversation_id, created_at);

            CREATE INDEX IF NOT EXISTS idx_conversations_user_id
                ON conversations(user_id, created_at);

            CREATE TABLE IF NOT EXISTS memories (
                entry_id        TEXT PRIMARY KEY,
                user_id         BIGINT NOT NULL,
                category        TEXT NOT NULL,
                content         TEXT NOT NULL,
                embedding       vector(1536),
                source_conv_id  TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at      TIMESTAMPTZ
            );

            CREATE INDEX IF NOT EXISTS idx_memories_user_id
                ON memories(user_id);

            CREATE TABLE IF NOT EXISTS confirmations (
                confirmation_id     TEXT PRIMARY KEY,
                user_id             BIGINT NOT NULL,
                conversation_id     TEXT NOT NULL,
                agent               TEXT NOT NULL,
                action_description  TEXT NOT NULL,
                action_payload      JSONB NOT NULL,
                status              TEXT NOT NULL DEFAULT 'pending',
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at          TIMESTAMPTZ,
                resolved_at         TIMESTAMPTZ
            );

            CREATE INDEX IF NOT EXISTS idx_confirmations_user_pending
                ON confirmations(user_id, status);
        """)
    logger.info("Database schema initialized")


# ── Conversation History ──────────────────────────────────────────────────────

async def save_message(msg: ConversationMessage) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversations
                (message_id, conversation_id, user_id, role, content, agent, created_at, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (message_id) DO NOTHING
            """,
            msg.message_id,
            msg.conversation_id,
            msg.user_id,
            msg.role.value,
            msg.content,
            msg.agent.value if msg.agent else None,
            msg.created_at,
            json.dumps(msg.metadata),
        )


async def get_conversation_history(
    conversation_id: str,
    limit: int = 50,
) -> list[ConversationMessage]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM conversations
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            conversation_id,
            limit,
        )
    return [_row_to_message(row) for row in rows]


async def get_recent_messages(user_id: int, limit: int = 20) -> list[ConversationMessage]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM conversations
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return list(reversed([_row_to_message(row) for row in rows]))


def _row_to_message(row: asyncpg.Record) -> ConversationMessage:
    return ConversationMessage(
        message_id=row["message_id"],
        conversation_id=row["conversation_id"],
        user_id=row["user_id"],
        role=MessageRole(row["role"]),
        content=row["content"],
        agent=row["agent"],
        created_at=row["created_at"],
        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
    )


# ── Long-Term Memory ──────────────────────────────────────────────────────────

async def save_memory(entry: MemoryEntry) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Persona categories are singletons — upsert by (user_id, category)
        if entry.category.startswith("persona:"):
            await conn.execute(
                """
                INSERT INTO memories
                    (entry_id, user_id, category, content, embedding, source_conv_id, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (entry_id) DO UPDATE
                    SET content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                """,
                entry.entry_id,
                entry.user_id,
                entry.category,
                entry.content,
                entry.embedding,
                entry.source_conversation_id,
                entry.created_at,
                entry.expires_at,
            )
            # Also delete any older entries for this (user, category) pair
            await conn.execute(
                """
                DELETE FROM memories
                WHERE user_id = $1 AND category = $2 AND entry_id != $3
                """,
                entry.user_id,
                entry.category,
                entry.entry_id,
            )
        else:
            await conn.execute(
                """
                INSERT INTO memories
                    (entry_id, user_id, category, content, embedding, source_conv_id, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (entry_id) DO UPDATE
                    SET content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                """,
                entry.entry_id,
                entry.user_id,
                entry.category,
                entry.content,
                entry.embedding,
                entry.source_conversation_id,
                entry.created_at,
                entry.expires_at,
            )


async def search_memories(
    user_id: int,
    query_embedding: Optional[list[float]] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> list[MemoryEntry]:
    """Search memories by semantic similarity or category."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if query_embedding and len(query_embedding) > 0:
            # Semantic search via cosine similarity
            where_clause = "WHERE user_id = $1"
            params: list[Any] = [user_id, query_embedding, limit]
            if category:
                where_clause += " AND category = $4"
                params.append(category)
            rows = await conn.fetch(
                f"""
                SELECT * FROM memories
                {where_clause}
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                *params,
            )
        else:
            if category:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories
                    WHERE user_id = $1 AND category = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    user_id, category, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    user_id, limit,
                )

    return [_row_to_memory(row) for row in rows]


def _row_to_memory(row: asyncpg.Record) -> MemoryEntry:
    return MemoryEntry(
        entry_id=row["entry_id"],
        user_id=row["user_id"],
        category=row["category"],
        content=row["content"],
        embedding=list(row["embedding"]) if row["embedding"] else None,
        source_conversation_id=row["source_conv_id"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


# ── Confirmations ─────────────────────────────────────────────────────────────

async def save_confirmation(
    confirmation_id: str,
    user_id: int,
    conversation_id: str,
    agent: str,
    action_description: str,
    action_payload: dict[str, Any],
    expires_at: Optional[datetime] = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO confirmations
                (confirmation_id, user_id, conversation_id, agent,
                 action_description, action_payload, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            confirmation_id,
            user_id,
            conversation_id,
            agent,
            action_description,
            json.dumps(action_payload),
            expires_at,
        )


async def get_pending_confirmation(confirmation_id: str) -> Optional[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM confirmations WHERE confirmation_id = $1 AND status = 'pending'",
            confirmation_id,
        )
    if not row:
        return None
    return dict(row)


async def resolve_confirmation(confirmation_id: str, status: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE confirmations
            SET status = $1, resolved_at = NOW()
            WHERE confirmation_id = $2
            """,
            status,
            confirmation_id,
        )


async def get_pending_confirmations_for_user(user_id: int) -> list[dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM confirmations
            WHERE user_id = $1 AND status = 'pending'
            ORDER BY created_at DESC
            """,
            user_id,
        )
    return [dict(row) for row in rows]
