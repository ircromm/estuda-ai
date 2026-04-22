"""
SQLite database module for Estuda Ai.
Stores user accounts and gamification stats.
"""

import sqlite3
import os
import json
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

def _resolve_db_path() -> str:
    """Return a writable DB path, falling back to /tmp if needed."""
    preferred = os.getenv("DB_PATH", "/app/data/estuda.db")
    try:
        Path(preferred).parent.mkdir(parents=True, exist_ok=True)
        # Test writability
        test_file = Path(preferred).parent / ".write_test"
        test_file.touch()
        test_file.unlink()
        return preferred
    except (PermissionError, OSError):
        fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estuda.db")
        return os.getenv("DB_PATH_FALLBACK", fallback)


DB_PATH = _resolve_db_path()


def init_db():
    """Initialize the database schema."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL COLLATE NOCASE,
            pin_hash TEXT NOT NULL,
            ano TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY,
            total_xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_study_date TEXT,
            badges TEXT DEFAULT '[]',
            subject_counts TEXT DEFAULT '{}',
            total_sessions INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            total_practice INTEGER DEFAULT 0,
            total_understood INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_users_nome ON users(nome);
        """
    )
    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# User operations
# ──────────────────────────────────────────────


def create_user(nome: str, pin_hash: str, ano: Optional[str] = None) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO users (nome, pin_hash, ano) VALUES (?, ?, ?)",
            (nome, pin_hash, ano),
        )
        user_id = cursor.lastrowid
        # Initialize empty stats row
        conn.execute("INSERT INTO stats (user_id) VALUES (?)", (user_id,))
        return user_id


def get_user_by_nome(nome: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE nome = ? COLLATE NOCASE", (nome,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, nome, ano, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def user_exists(nome: str) -> bool:
    return get_user_by_nome(nome) is not None


# ──────────────────────────────────────────────
# Stats operations
# ──────────────────────────────────────────────


def get_stats(user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM stats WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return {
                "totalXP": 0,
                "streak": 0,
                "lastStudyDate": None,
                "badges": [],
                "subjectCounts": {},
                "totalSessions": 0,
                "totalMessages": 0,
                "totalPractice": 0,
                "totalUnderstood": 0,
            }
        return {
            "totalXP": row["total_xp"],
            "streak": row["streak"],
            "lastStudyDate": row["last_study_date"],
            "badges": json.loads(row["badges"] or "[]"),
            "subjectCounts": json.loads(row["subject_counts"] or "{}"),
            "totalSessions": row["total_sessions"],
            "totalMessages": row["total_messages"],
            "totalPractice": row["total_practice"],
            "totalUnderstood": row["total_understood"],
        }


def save_stats(user_id: int, stats: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stats (
                user_id, total_xp, streak, last_study_date, badges,
                subject_counts, total_sessions, total_messages,
                total_practice, total_understood, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                total_xp = excluded.total_xp,
                streak = excluded.streak,
                last_study_date = excluded.last_study_date,
                badges = excluded.badges,
                subject_counts = excluded.subject_counts,
                total_sessions = excluded.total_sessions,
                total_messages = excluded.total_messages,
                total_practice = excluded.total_practice,
                total_understood = excluded.total_understood,
                updated_at = datetime('now')
            """,
            (
                user_id,
                stats.get("totalXP", 0),
                stats.get("streak", 0),
                stats.get("lastStudyDate"),
                json.dumps(stats.get("badges", [])),
                json.dumps(stats.get("subjectCounts", {})),
                stats.get("totalSessions", 0),
                stats.get("totalMessages", 0),
                stats.get("totalPractice", 0),
                stats.get("totalUnderstood", 0),
            ),
        )
