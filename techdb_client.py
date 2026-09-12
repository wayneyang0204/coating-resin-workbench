from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def api_base() -> str:
    return os.getenv("TECH_DB_API_BASE", "http://127.0.0.1:8765").rstrip("/")


def _timeout() -> float:
    return float(os.getenv("TECH_DB_TIMEOUT_SECONDS", "25"))


LIST_FIELDS = (
    "id",
    "name",
    "brand",
    "code",
    "supplier",
    "material_group",
    "category",
    "data_score",
    "chemistry",
    "functions",
    "applications",
    "confidence",
)


def compact_material(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in LIST_FIELDS}


def _request(path: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
    query = urllib.parse.urlencode(
        {key: value for key, value in (params or {}).items() if value not in (None, "")},
        doseq=True,
        safe="",
        encoding="utf-8",
    )
    url = f"{api_base()}{path}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout or _timeout()) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"正式庫 HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"無法連線正式材料庫 {api_base()}：{exc.reason}") from exc


def health() -> dict[str, Any]:
    try:
        payload = _request("/api/health", timeout=5)
        stats = {}
        try:
            stats = _request("/api/stats", timeout=8)
        except Exception:
            stats = {}
        return {
            "ok": payload.get("status") == "ok" and bool(payload.get("database_ready", True)),
            "url": api_base(),
            "started_at": payload.get("started_at"),
            "database_size_bytes": payload.get("database_size_bytes"),
            "materials": stats.get("materials"),
            "documents": stats.get("documents"),
            "groups": stats.get("groups") or {},
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": api_base(),
            "error": str(exc),
        }


def stats() -> dict[str, Any]:
    return _request("/api/stats")


def search_materials(
    query: str,
    *,
    material_group: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    payload = _request(
        "/api/search",
        {
            "q": query,
            "group": material_group,
            "scope": "catalog",
            "page": max(1, page),
            "page_size": min(40, max(10, page_size)),
        },
    )
    items = [compact_material(item) for item in payload.get("items") or []]
    return {
        "count": payload.get("total", len(items)),
        "page": payload.get("page", page),
        "page_size": payload.get("page_size", page_size),
        "data": items,
        "source": "company-technical-database",
    }


def get_material(material_id: int) -> dict[str, Any]:
    payload = _request(f"/api/materials/{int(material_id)}")
    if not isinstance(payload, dict) or payload.get("error"):
        raise RuntimeError(payload.get("error") if isinstance(payload, dict) else "找不到材料")
    return payload
