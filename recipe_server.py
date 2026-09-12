from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import auth
import techdb_client


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("RECIPE_DB_PATH", os.path.join(BASE_DIR, "recipes.db"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-tw")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
HOST = os.getenv("RECIPE_HOST", "0.0.0.0")
PORT = int(os.getenv("RECIPE_PORT", "8088"))
PUBLIC_GET = {"/api/health", "/api/auth/login"}
PUBLIC_POST = {"/api/auth/login"}


def get_conn() -> sqlite3.Connection:
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
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
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS recipes_updated_at
            AFTER UPDATE ON recipes
            BEGIN
                UPDATE recipes SET updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
                WHERE id = NEW.id;
            END;
            """
        )
        auth.ensure_auth_schema(conn)
        issued = auth.seed_users(conn)
        if issued:
            names = ", ".join(item["name"] for item in issued)
            print(f"已建立帳號：{names}；預設密碼請使用公司約定值，登入後可自行修改")


def to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join([str(item) for item in value if str(item).strip()])
    return str(value)


def sanitize_role(role: str) -> str:
    return role if role in {"system", "user", "assistant"} else "user"


def list_to_json_rows(rows) -> list[dict]:
    return [dict(row) for row in rows]


def recipe_search(conn, keyword: str) -> list[dict]:
    if not keyword:
        return []
    kw = f"%{keyword}%"
    cur = conn.execute(
        """
        SELECT id, name, ingredients, steps, tags, serving, created_by, created_at, updated_at
        FROM recipes
        WHERE name LIKE ? OR ingredients LIKE ? OR steps LIKE ? OR tags LIKE ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (kw, kw, kw, kw),
    )
    return list_to_json_rows(cur.fetchall())


def parse_json_body(handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length == 0:
        return {}
    data = handler.rfile.read(length).decode("utf-8")
    return json.loads(data)


def write_json(handler, status: int, payload) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Company-Token")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def call_ollama(messages, materials, user_name: str) -> str:
    lines = []
    for item in materials[:8]:
        lines.append(
            f"- [{item.get('name')}] id={item.get('id')} "
            f"供應商={item.get('supplier') or '未標'} "
            f"類別={item.get('material_group') or ''} "
            f"化學={item.get('chemistry') or '未列'} "
            f"功能={item.get('functions') or '未列'} "
            f"用途={item.get('applications') or '未列'} "
            f"完整度={item.get('data_score')}"
        )
    context_text = "\n".join(lines) if lines else "目前正式材料庫沒有對應牌號。"
    system_prompt = (
        "你是公司塗料技術開發與樹脂合成助理，只使用台灣繁體中文。"
        f"目前操作者是 {user_name}。"
        "只能根據下面正式庫搜尋命中的材料回答；禁止編造 Tg、NCO%、固含、黏度或其他規格。"
        "若沒有命中，先說「庫內沒有對應材料」，再只給需要查證的下一步，不要填數字。"
    )
    context_prompt = f"正式庫搜尋命中：\n{context_text}"
    chat = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": context_prompt},
    ]
    for msg in messages[-20:]:
        content = to_str(msg.get("content")).strip()
        if content:
            chat.append({"role": sanitize_role(msg.get("role")), "content": content})

    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "messages": chat,
            "stream": False,
            "options": {"temperature": 0.15, "num_ctx": 4096},
        }
    ).encode("utf-8")
    import urllib.request

    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("message") and result["message"].get("content"):
        return result["message"]["content"]
    return result.get("response", "")


def render_static(path: str):
    safe_root = os.path.join(BASE_DIR, "web")
    fs_path = os.path.normpath(os.path.join(safe_root, path.lstrip("/")))
    if not fs_path.startswith(safe_root) or not os.path.exists(fs_path):
        return None, None
    if os.path.isdir(fs_path):
        fs_path = os.path.join(fs_path, "index.html")
    if not os.path.exists(fs_path):
        return None, None
    ext = os.path.splitext(fs_path)[1].lower()
    mime = {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }.get(ext, "text/plain; charset=utf-8")
    with open(fs_path, "rb") as handle:
        return handle.read(), mime


class RecipeHandler(BaseHTTPRequestHandler):
    server_version = "CompanyWorkbench/1.1"

    def _options(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Company-Token")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._options()

    def current_user(self, required: bool = True):
        with get_conn() as conn:
            user = auth.resolve_token(conn, auth.token_from_headers(self.headers))
        if required and user is None:
            write_json(self, 401, {"error": "請先以 Wayne、Alex、Dios 或 Gary 登入"})
            return None
        return user

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/api/health":
                tech = techdb_client.health()
                with get_conn() as conn:
                    users = [row["name"] for row in auth.list_users(conn)]
                write_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "service": "company-workbench",
                        "model": OLLAMA_MODEL,
                        "db": DB_PATH,
                        "techdb": tech,
                        "users": users,
                    },
                )
                return

            if path in {"/", "/index.html"}:
                path = "/index.html"
                static, mime = render_static(path)
                if static is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(static)))
                    self.end_headers()
                    self.wfile.write(static)
                    return

            if path.startswith("/static/") or path.startswith("/assets/") or path.startswith("/web/"):
                static, mime = render_static(path.replace("/web/", "/", 1))
                if static is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(static)))
                    self.end_headers()
                    self.wfile.write(static)
                    return

            user = self.current_user()
            if user is None:
                return

            if path in {"/api/me"}:
                write_json(self, 200, {"user": user})
                return

            if path == "/api/users":
                with get_conn() as conn:
                    write_json(self, 200, {"users": auth.list_users(conn)})
                return

            if path == "/api/search" or path == "/api/materials":
                keyword = query.get("q", [""])[0].strip()
                group = query.get("group", [""])[0].strip()
                page = int(query.get("page", ["1"])[0] or 1)
                result = techdb_client.search_materials(keyword, material_group=group, page=page)
                with get_conn() as conn:
                    auth.log_search(
                        conn,
                        user,
                        keyword or "(空白)",
                        material_group=group,
                        result_count=result.get("count") or len(result.get("data") or []),
                    )
                result["user"] = user["name"]
                write_json(self, 200, result)
                return

            if path.startswith("/api/materials/"):
                material_id = unquote(path.rsplit("/", 1)[-1]).strip()
                if not material_id.isdigit():
                    write_json(self, 400, {"error": "材料編號無效"})
                    return
                write_json(self, 200, techdb_client.get_material(int(material_id)))
                return

            if path == "/api/tech/stats":
                write_json(self, 200, techdb_client.stats())
                return

            if path == "/api/search-logs":
                with get_conn() as conn:
                    write_json(self, 200, {"data": auth.list_search_logs(conn, user)})
                return

            if path == "/api/recipes":
                keyword = query.get("q", [""])[0]
                with get_conn() as conn:
                    if keyword:
                        rows = recipe_search(conn, keyword)
                    else:
                        rows = list_to_json_rows(
                            conn.execute(
                                """
                                SELECT id, name, ingredients, steps, tags, serving, created_by, created_at, updated_at
                                FROM recipes ORDER BY id DESC LIMIT 50
                                """
                            ).fetchall()
                        )
                write_json(self, 200, {"count": len(rows), "data": rows})
                return

            write_json(self, 404, {"error": "not found"})
        except Exception as exc:
            write_json(self, 500, {"error": str(exc), "type": type(exc).__name__})

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path

            if path == "/api/auth/login":
                body = parse_json_body(self)
                with get_conn() as conn:
                    session = auth.login(
                        conn,
                        to_str(body.get("name") or body.get("username")),
                        to_str(body.get("password")),
                    )
                write_json(self, 200, session)
                return

            user = self.current_user()
            if user is None:
                return

            if path == "/api/auth/logout":
                with get_conn() as conn:
                    auth.logout(conn, auth.token_from_headers(self.headers))
                write_json(self, 200, {"ok": True})
                return

            if path == "/api/auth/change-password":
                body = parse_json_body(self)
                with get_conn() as conn:
                    auth.change_password(
                        conn,
                        user,
                        to_str(body.get("current_password") or body.get("old_password")),
                        to_str(body.get("new_password")),
                        keep_token=auth.token_from_headers(self.headers),
                    )
                write_json(self, 200, {"ok": True, "message": "密碼已更新"})
                return

            if path == "/api/recipes":
                body = parse_json_body(self)
                name = to_str(body.get("name")).strip()
                ingredients = to_str(body.get("ingredients")).strip()
                steps = to_str(body.get("steps")).strip()
                tags = to_str(body.get("tags")).strip()
                serving = body.get("serving")
                if not name or not ingredients or not steps:
                    write_json(self, 400, {"error": "名稱、材料、步驟為必填"})
                    return
                with get_conn() as conn:
                    try:
                        conn.execute(
                            """
                            INSERT INTO recipes
                            (name, ingredients, steps, tags, serving, created_by, created_by_username)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (name, ingredients, steps, tags, serving, user["name"], user["username"]),
                        )
                    except sqlite3.IntegrityError:
                        write_json(self, 409, {"error": "此筆記名稱已存在"})
                        return
                    row = conn.execute(
                        "SELECT id, name, ingredients, steps, tags, serving, created_by FROM recipes WHERE name = ?",
                        (name,),
                    ).fetchone()
                write_json(self, 201, {"message": "created", "recipe": dict(row)})
                return

            if path == "/api/chat":
                body = parse_json_body(self)
                messages = body.get("messages")
                if not isinstance(messages, list):
                    fallback = to_str(body.get("message")).strip()
                    messages = [{"role": "user", "content": fallback}] if fallback else []
                latest = ""
                for item in reversed(messages):
                    if sanitize_role(item.get("role")) == "user":
                        latest = to_str(item.get("content")).strip()
                        break
                if not latest:
                    write_json(self, 400, {"error": "請輸入問題"})
                    return
                search = techdb_client.search_materials(latest, page_size=12)
                matches = search.get("data") or []
                with get_conn() as conn:
                    auth.log_search(
                        conn,
                        user,
                        latest,
                        result_count=search.get("count") or len(matches),
                    )
                    notes = recipe_search(conn, latest)
                answer = call_ollama(messages, matches, user["name"])
                write_json(
                    self,
                    200,
                    {
                        "answer": answer,
                        "matches": matches,
                        "notes": notes,
                        "user": user["name"],
                    },
                )
                return

            write_json(self, 404, {"error": "not found"})
        except PermissionError as exc:
            write_json(self, 401, {"error": str(exc)})
        except ValueError as exc:
            write_json(self, 400, {"error": str(exc)})
        except urllib.error.URLError as exc:
            write_json(self, 503, {"error": f"Ollama 無法連線：{exc}"})
        except Exception as exc:
            write_json(self, 500, {"error": str(exc), "type": type(exc).__name__})


def run() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), RecipeHandler)
    print(f"Company workbench: http://{HOST}:{PORT}")
    print(f"Notes DB: {DB_PATH}")
    print(f"Tech DB: {techdb_client.api_base()}")
    server.serve_forever()


if __name__ == "__main__":
    run()
