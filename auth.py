from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PASSWORD_FILE = DATA_DIR / "initial_passwords.txt"
SESSION_HOURS = 12
PBKDF2_ROUNDS = 180_000
DEFAULT_PASSWORD = os.getenv("TECH_DB_DEFAULT_PASSWORD", "80016004")

TEAM_USERS = (
    {"username": "wayne", "name": "Wayne", "role": "admin"},
    {"username": "alex", "name": "Alex", "role": "researcher"},
    {"username": "dios", "name": "Dios", "role": "researcher"},
    {"username": "gary", "name": "Gary", "role": "researcher"},
)


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ROUNDS,
    )
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, _digest = stored.split("$", 1)
    return hmac.compare_digest(_hash_password(password, salt), stored)


def ensure_auth_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            last_login_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY (username) REFERENCES users(username)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            display_name TEXT NOT NULL,
            query TEXT NOT NULL,
            material_group TEXT,
            result_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
        )
        """
    )


def seed_users(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """Create the four named accounts once with the shared default password."""

    issued: list[dict[str, str]] = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for spec in TEAM_USERS:
        row = conn.execute(
            "SELECT username FROM users WHERE username = ?",
            (spec["username"],),
        ).fetchone()
        if row:
            continue
        conn.execute(
            """
            INSERT INTO users (username, name, role, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (
                spec["username"],
                spec["name"],
                spec["role"],
                _hash_password(DEFAULT_PASSWORD),
            ),
        )
        issued.append({"name": spec["name"], "username": spec["username"]})
    return issued


def apply_default_password(conn: sqlite3.Connection) -> list[str]:
    """Reset Wayne/Alex/Dios/Gary to the shared default. Users can change it later."""

    updated: list[str] = []
    hashed = _hash_password(DEFAULT_PASSWORD)
    for spec in TEAM_USERS:
        conn.execute(
            """
            INSERT INTO users (username, name, role, password_hash)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash
            """,
            (spec["username"], spec["name"], spec["role"], hashed),
        )
        updated.append(spec["name"])
    if PASSWORD_FILE.exists():
        PASSWORD_FILE.unlink()
    return updated


def change_password(
    conn: sqlite3.Connection,
    user: dict[str, Any],
    current_password: str,
    new_password: str,
    *,
    keep_token: str = "",
) -> None:
    current_password = (current_password or "").strip()
    new_password = (new_password or "").strip()
    if not current_password or not new_password:
        raise ValueError("請輸入目前密碼與新密碼")
    if len(new_password) < 6:
        raise ValueError("新密碼至少 6 碼")
    if current_password == new_password:
        raise ValueError("新密碼不可與目前密碼相同")
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username = ?",
        (user["username"],),
    ).fetchone()
    if row is None or not _verify_password(current_password, row["password_hash"]):
        raise PermissionError("目前密碼不正確")
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (_hash_password(new_password), user["username"]),
    )
    if keep_token:
        conn.execute(
            "DELETE FROM sessions WHERE username = ? AND token <> ?",
            (user["username"], keep_token),
        )
    else:
        conn.execute("DELETE FROM sessions WHERE username = ?", (user["username"],))


def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    return {
        "username": data["username"],
        "name": data["name"],
        "role": data["role"],
        "last_login_at": data.get("last_login_at"),
    }


def list_users(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT username, name, role, last_login_at FROM users ORDER BY name"
    ).fetchall()
    return [public_user(row) for row in rows]


def login(conn: sqlite3.Connection, name_or_username: str, password: str) -> dict[str, Any]:
    identity = (name_or_username or "").strip()
    if not identity or not password:
        raise ValueError("請輸入帳號與密碼")
    row = conn.execute(
        """
        SELECT username, name, role, password_hash
        FROM users
        WHERE lower(username) = lower(?) OR lower(name) = lower(?)
        """,
        (identity, identity),
    ).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        raise PermissionError("帳號或密碼不正確")
    now = time.time()
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    conn.execute(
        "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, row["username"], now, now + SESSION_HOURS * 3600),
    )
    conn.execute(
        "UPDATE users SET last_login_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE username = ?",
        (row["username"],),
    )
    return {
        "token": token,
        "user": public_user(row),
        "expires_in_hours": SESSION_HOURS,
    }


def logout(conn: sqlite3.Connection, token: str) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def resolve_token(conn: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    now = time.time()
    row = conn.execute(
        """
        SELECT u.username, u.name, u.role, u.last_login_at
        FROM sessions s
        JOIN users u ON u.username = s.username
        WHERE s.token = ? AND s.expires_at > ?
        """,
        (token, now),
    ).fetchone()
    if row is None:
        return None
    return public_user(row)


def log_search(
    conn: sqlite3.Connection,
    user: dict[str, Any],
    query: str,
    *,
    material_group: str = "",
    result_count: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO search_logs (username, display_name, query, material_group, result_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user["username"],
            user["name"],
            query[:500],
            (material_group or "")[:80],
            int(result_count),
        ),
    )


def list_search_logs(
    conn: sqlite3.Connection,
    user: dict[str, Any],
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    if user["role"] == "admin":
        rows = conn.execute(
            """
            SELECT display_name, username, query, material_group, result_count, created_at
            FROM search_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT display_name, username, query, material_group, result_count, created_at
            FROM search_logs
            WHERE username = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user["username"], limit),
        ).fetchall()
    return [dict(row) for row in rows]


def token_from_headers(headers: Any) -> str:
    auth = str(headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return str(headers.get("X-Company-Token") or "").strip()
