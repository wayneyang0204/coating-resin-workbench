from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import auth
import techdb_client


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("RECIPE_DB_PATH", str(BASE_DIR / "recipes.db")))


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with closing(_conn()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                ingredients TEXT NOT NULL,
                steps TEXT NOT NULL,
                tags TEXT,
                serving INTEGER,
                created_by TEXT,
                created_by_username TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(recipes)")}
        if "created_by" not in columns:
            conn.execute("ALTER TABLE recipes ADD COLUMN created_by TEXT")
        if "created_by_username" not in columns:
            conn.execute("ALTER TABLE recipes ADD COLUMN created_by_username TEXT")
        auth.ensure_auth_schema(conn)
        auth.seed_users(conn)


def health() -> dict[str, Any]:
    init()
    with closing(_conn()) as conn:
        users = [row["name"] for row in auth.list_users(conn)]
    return {
        "ok": True,
        "service": "company-workbench",
        "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b-tw"),
        "db": str(DB_PATH),
        "techdb": techdb_client.health(),
        "users": users,
    }


def login(name: str, password: str) -> dict[str, Any]:
    init()
    with closing(_conn()) as conn, conn:
        return auth.login(conn, name, password)


def logout(token: str) -> None:
    with closing(_conn()) as conn, conn:
        auth.logout(conn, token)


def resolve(token: str | None) -> dict[str, Any] | None:
    with closing(_conn()) as conn:
        return auth.resolve_token(conn, token)


def change_password(token: str, current_password: str, new_password: str) -> None:
    user = resolve(token)
    if user is None:
        raise PermissionError("請先登入")
    with closing(_conn()) as conn, conn:
        auth.change_password(
            conn,
            user,
            current_password,
            new_password,
            keep_token=token,
        )


def search(token: str, query: str, group: str = "") -> dict[str, Any]:
    user = resolve(token)
    if user is None:
        raise PermissionError("請先登入")
    result = techdb_client.search_materials(query, material_group=group)
    with closing(_conn()) as conn, conn:
        auth.log_search(
            conn,
            user,
            query or "(空白)",
            material_group=group,
            result_count=result.get("count") or len(result.get("data") or []),
        )
    result["user"] = user["name"]
    return result


def search_logs(token: str) -> list[dict[str, Any]]:
    user = resolve(token)
    if user is None:
        raise PermissionError("請先登入")
    with closing(_conn()) as conn:
        return auth.list_search_logs(conn, user)


def add_note(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    user = resolve(token)
    if user is None:
        raise PermissionError("請先登入")
    name = str(payload.get("name") or "").strip()
    ingredients = str(payload.get("ingredients") or "").strip()
    steps = str(payload.get("steps") or "").strip()
    tags = str(payload.get("tags") or "").strip()
    serving = payload.get("serving")
    if not name or not ingredients or not steps:
        raise ValueError("名稱、材料、步驟為必填")
    with closing(_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO recipes
            (name, ingredients, steps, tags, serving, created_by, created_by_username)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, ingredients, steps, tags, serving, user["name"], user["username"]),
        )
        row = conn.execute(
            "SELECT id, name, ingredients, steps, tags, serving, created_by FROM recipes WHERE name = ?",
            (name,),
        ).fetchone()
    return {"message": "created", "recipe": dict(row)}


def list_notes(token: str) -> list[dict[str, Any]]:
    user = resolve(token)
    if user is None:
        raise PermissionError("請先登入")
    with closing(_conn()) as conn:
        rows = conn.execute(
            """
            SELECT id, name, ingredients, steps, tags, serving, created_by, created_at, updated_at
            FROM recipes ORDER BY id DESC LIMIT 50
            """
        ).fetchall()
    return [dict(row) for row in rows]


def chat(token: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    user = resolve(token)
    if user is None:
        raise PermissionError("請先登入")
    latest = ""
    for item in reversed(messages or []):
        if item.get("role") == "user":
            latest = str(item.get("content") or "").strip()
            if latest:
                break
    if not latest:
        raise ValueError("請輸入問題")
    result = search(token, latest)
    matches = result.get("data") or []
    try:
        from recipe_server import call_ollama

        answer = call_ollama(messages, matches, user["name"])
    except Exception as exc:
        names = "、".join(str(item.get("name") or "") for item in matches[:8] if item.get("name"))
        answer = (
            f"AI 問答僅在公司內網（Ollama）可用：{exc}\n"
            f"本次正式庫命中：{names or '無'}"
        )
    return {"answer": answer, "matches": matches, "user": user["name"]}
