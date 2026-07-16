"""SQLite-backed copywriting (文案) library — CRUD for scripts."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import ROOT_DIR
from .utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = ROOT_DIR / "backend" / "data" / "copywriting.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _word_count(text: str) -> int:
    return len((text or "").strip())


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS copywriting (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                input_mode TEXT NOT NULL DEFAULT 'direct',
                notes TEXT NOT NULL DEFAULT '',
                word_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_copywriting_updated_at ON copywriting(updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_copywriting_title ON copywriting(title)"
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "tags": row["tags"] or "",
        "inputMode": row["input_mode"] or "direct",
        "notes": row["notes"] or "",
        "wordCount": int(row["word_count"] or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_copywriting(
    *,
    q: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    init_db()
    keyword = (q or "").strip()
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))

    with _connect() as conn:
        if keyword:
            like = f"%{keyword}%"
            total = conn.execute(
                """
                SELECT COUNT(*) FROM copywriting
                WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? OR notes LIKE ?
                """,
                (like, like, like, like),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM copywriting
                WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? OR notes LIKE ?
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (like, like, like, like, limit, offset),
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) FROM copywriting").fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM copywriting
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

    return [_row_to_dict(row) for row in rows], int(total)


def get_copywriting(item_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM copywriting WHERE id = ?",
            (item_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_copywriting(
    *,
    title: str,
    content: str,
    tags: str = "",
    input_mode: str = "direct",
    notes: str = "",
) -> dict[str, Any]:
    init_db()
    title = (title or "").strip() or "未命名文案"
    content = (content or "").strip()
    if not content:
        raise ValueError("文案内容不能为空。")

    item_id = str(uuid.uuid4())
    now = _utc_now()
    payload = (
        item_id,
        title,
        content,
        (tags or "").strip(),
        (input_mode or "direct").strip() or "direct",
        (notes or "").strip(),
        _word_count(content),
        now,
        now,
    )
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO copywriting (
                id, title, content, tags, input_mode, notes, word_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    logger.info("Copywriting created id=%s title=%s", item_id, title)
    item = get_copywriting(item_id)
    assert item is not None
    return item


def update_copywriting(
    item_id: str,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[str] = None,
    input_mode: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    init_db()
    existing = get_copywriting(item_id)
    if not existing:
        raise KeyError(f"文案不存在：{item_id}")

    next_title = (title if title is not None else existing["title"]).strip() or "未命名文案"
    next_content = (content if content is not None else existing["content"]).strip()
    if not next_content:
        raise ValueError("文案内容不能为空。")
    next_tags = (tags if tags is not None else existing["tags"]).strip()
    next_mode = (
        (input_mode if input_mode is not None else existing["inputMode"]).strip() or "direct"
    )
    next_notes = (notes if notes is not None else existing["notes"]).strip()
    now = _utc_now()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE copywriting
            SET title = ?, content = ?, tags = ?, input_mode = ?, notes = ?,
                word_count = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                next_title,
                next_content,
                next_tags,
                next_mode,
                next_notes,
                _word_count(next_content),
                now,
                item_id,
            ),
        )
    logger.info("Copywriting updated id=%s", item_id)
    item = get_copywriting(item_id)
    assert item is not None
    return item


def delete_copywriting(item_id: str) -> bool:
    init_db()
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM copywriting WHERE id = ?", (item_id,))
        deleted = cursor.rowcount > 0
    if deleted:
        logger.info("Copywriting deleted id=%s", item_id)
    return deleted
