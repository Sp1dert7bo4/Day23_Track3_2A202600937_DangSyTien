"""Checkpointer adapter."""

from __future__ import annotations

from typing import Any


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer.

    TODO(student): implement SQLite support for the persistence extension track.
    The starter provides MemorySaver only — SQLite/Postgres are extension tasks.

    For SQLite:
    - pip install langgraph-checkpoint-sqlite
    - Use SqliteSaver with sqlite3.connect() and WAL mode
    - See: https://langchain-ai.github.io/langgraph/how-tos/persistence/
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            import os
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver

            db_path = database_url or ".checkpoints/state.db"
            db_dir = os.path.dirname(db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            # Requires langgraph-checkpoint-sqlite v3.x pattern
            conn = sqlite3.connect(db_path, check_same_thread=False)
            # Optional: Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            
            return SqliteSaver(conn=conn)
        except ImportError as exc:
            raise RuntimeError(
                "SQLite checkpointer requires 'langgraph-checkpoint-sqlite'. "
                "Please install it using: pip install langgraph-checkpoint-sqlite"
            ) from exc
    if kind == "postgres":
        raise NotImplementedError(
            "TODO(student): implement Postgres checkpointer (optional extension)"
        )
    raise ValueError(f"Unknown checkpointer kind: {kind}")
