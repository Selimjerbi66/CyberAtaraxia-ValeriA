"""
Gestion de la base de données SQLite.
Tables : users, sessions, chats, messages, settings
"""
import sqlite3
import json
import time
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/data/app.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            recovery_hint TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Nouvelle discussion',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            model_override TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,           -- 'user' | 'assistant'
            content TEXT NOT NULL,
            sources_json TEXT,            -- JSON list of {title,url,method}
            created_at REAL NOT NULL,
            feedback TEXT,                -- 'up' | 'down' | NULL
            gen_seconds REAL,             -- temps de generation (perf stats)
            gen_tokens INTEGER,           -- nb de tokens generes (perf stats)
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        # Migration sure pour les DB deja existantes (avant l'ajout de ces colonnes)
        for table, column, coltype in [
            ("chats", "pinned", "INTEGER NOT NULL DEFAULT 0"),
            ("chats", "model_override", "TEXT"),
            ("messages", "feedback", "TEXT"),
            ("messages", "gen_seconds", "REAL"),
            ("messages", "gen_tokens", "INTEGER"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            except sqlite3.OperationalError:
                pass  # la colonne existe deja

        # Default settings if not present
        defaults = {
            "search_engine": "searxng",
            "searxng_url": "http://localhost:8081/search",
            "num_sources": "10",
            "scrape_mode": "hybrid",       # 'hybrid' | 'snippet_only' | 'full_scrape'
            "ollama_url": "http://localhost:11434",
            "ollama_model": "gemma3:4b",
            "scrape_timeout": "8",
            "max_chars_per_page": "4000",
            "custom_instructions": "",
            "temperature": "0.7",
            "search_category": "general",
            "auto_detect_search": "true",
        }
        cur = conn.execute("SELECT key FROM settings")
        existing = {row[0] for row in cur.fetchall()}
        for k, v in defaults.items():
            if k not in existing:
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------- Settings ----------

def get_settings() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {k: v for k, v in rows}


def update_settings(new_values: dict):
    with get_conn() as conn:
        for k, v in new_values.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, str(v)),
            )
        conn.commit()


# ---------- Chats ----------

def create_chat(title: str = "Nouvelle discussion") -> int:
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO chats (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now),
        )
        conn.commit()
        return cur.lastrowid


def list_chats(search: str = "") -> list:
    with get_conn() as conn:
        if search:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, pinned, model_override "
                "FROM chats WHERE title LIKE ? "
                "ORDER BY pinned DESC, updated_at DESC",
                (f"%{search}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, pinned, model_override "
                "FROM chats ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
        return [
            {
                "id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3],
                "pinned": bool(r[4]), "model_override": r[5],
            }
            for r in rows
        ]


def set_pinned(chat_id: int, pinned: bool):
    with get_conn() as conn:
        conn.execute("UPDATE chats SET pinned = ? WHERE id = ?", (1 if pinned else 0, chat_id))
        conn.commit()


def set_model_override(chat_id: int, model: str | None):
    with get_conn() as conn:
        conn.execute("UPDATE chats SET model_override = ? WHERE id = ?", (model, chat_id))
        conn.commit()


def get_chat(chat_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, pinned, model_override "
            "FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3],
            "pinned": bool(row[4]), "model_override": row[5],
        }


def rename_chat(chat_id: int, title: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), chat_id),
        )
        conn.commit()


def touch_chat(chat_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (time.time(), chat_id))
        conn.commit()


def delete_chat(chat_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        conn.commit()


# ---------- Messages ----------

def add_message(
    chat_id: int, role: str, content: str, sources: list | None = None,
    gen_seconds: float | None = None, gen_tokens: int | None = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (chat_id, role, content, sources_json, created_at, "
            "gen_seconds, gen_tokens) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, role, content, json.dumps(sources or []), time.time(),
             gen_seconds, gen_tokens),
        )
        conn.commit()
        return cur.lastrowid


def list_messages(chat_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, role, content, sources_json, created_at, feedback, "
            "gen_seconds, gen_tokens FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "sources": json.loads(r[3]) if r[3] else [],
                "created_at": r[4],
                "feedback": r[5],
                "gen_seconds": r[6],
                "gen_tokens": r[7],
            }
            for r in rows
        ]


def set_feedback(message_id: int, feedback: str | None):
    with get_conn() as conn:
        conn.execute("UPDATE messages SET feedback = ? WHERE id = ?", (feedback, message_id))
        conn.commit()


def delete_last_assistant_message(chat_id: int):
    """Utilisé pour la régénération : supprime la dernière réponse assistant."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE chat_id = ? AND role = 'assistant' "
            "ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM messages WHERE id = ?", (row[0],))
            conn.commit()
