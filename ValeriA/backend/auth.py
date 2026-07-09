"""
Authentification simple à un seul utilisateur.
- Mot de passe hashé (PBKDF2-HMAC-SHA256, salé).
- Sessions stockées en base, token aléatoire renvoyé en cookie httponly.
- La récupération en cas d'oubli se fait hors-ligne via reset_password.py
  (voir README), pas par email puisqu'il n'y en a pas ici.
"""
import hashlib
import os
import secrets
import time

from database import get_conn

SESSION_DURATION_SECONDS = 60 * 60 * 24 * 30  # 30 jours


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    ).hex()


def set_password(password: str):
    """Crée ou remplace le mot de passe unique de l'application."""
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    now = time.time()
    with get_conn() as conn:
        conn.execute("DELETE FROM users")
        conn.execute(
            "INSERT INTO users (id, password_hash, salt, created_at, updated_at) "
            "VALUES (1, ?, ?, ?, ?)",
            (pw_hash, salt, now, now),
        )
        conn.commit()


def has_password_set() -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = 1").fetchone()
        return row is not None


def verify_password(password: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE id = 1"
        ).fetchone()
        if not row:
            return False
        pw_hash, salt = row
        return secrets.compare_digest(_hash_password(password, salt), pw_hash)


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
            (token, now, now + SESSION_DURATION_SECONDS),
        )
        conn.commit()
    return token


def is_session_valid(token: str | None) -> bool:
    if not token:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not row:
            return False
        return row[0] > time.time()


def destroy_session(token: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def destroy_all_sessions():
    """Utilisé par le script de récupération de mot de passe : on force
    tout le monde à se reconnecter avec le nouveau mot de passe."""
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions")
        conn.commit()
