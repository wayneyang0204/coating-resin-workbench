from __future__ import annotations

import csv
import os
from datetime import datetime
from io import StringIO
from typing import Any

import streamlit as st


def _secret_or_env(name: str, default: str = "") -> str:
    if hasattr(st, "secrets"):
        try:
            value = st.secrets.get(name, "")
            if value:
                return str(value)
        except Exception:
            pass
    return os.getenv(name, default)


for _key in ("TECH_DB_API_BASE", "TECH_DB_DEFAULT_PASSWORD", "RECIPE_DB_PATH", "OLLAMA_URL"):
    _value = _secret_or_env(_key)
    if _value:
        os.environ[_key] = _value

import backend  # noqa: E402

LOGO_PATH = _secret_or_env(
    "RECIPE_LOGO_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "company_logo_transparent.png"),
)
NAMED_USERS = ("Wayne", "Alex", "Dios", "Gary")
MATERIAL_GROUPS = ("", "樹脂", "助劑", "固化劑", "單體／反應稀釋劑", "顏填料", "溶劑")

st.set_page_config(page_title="塗料與樹脂研發工作台", layout="wide")


def _token() -> str:
    return str(st.session_state.get("auth_token") or "")


def get_health() -> dict[str, Any]:
    try:
        return backend.health()
    except Exception:
        return {"ok": False}


def render_login() -> None:
    st.markdown("## 塗料與樹脂研發工作台")
    st.caption("預設密碼四人相同，登入後可在側欄自行修改。")
    with st.form("login_form"):
        name = st.selectbox("帳號", NAMED_USERS)
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", type="primary")
    if submitted:
        try:
            session = backend.login(name, password)
            st.session_state.auth_token = session["token"]
            st.session_state.auth_user = session["user"]
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def init_state() -> None:
    defaults = {
        "auth_token": "",
        "auth_user": None,
        "search_query": "",
        "search_group": "",
        "search_results": [],
        "search_total": 0,
        "chat_history": [],
        "chat_matches": [],
        "search_logs": [],
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def fmt_time(raw: str | None) -> str:
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "")).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return str(raw)


def render_material_card(item: dict[str, Any], key: str) -> None:
    title = item.get("name") or "未命名"
    meta = " ｜ ".join(
        part
        for part in (
            item.get("supplier") or None,
            item.get("material_group") or None,
            item.get("code") or item.get("brand") or None,
        )
        if part
    )
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(f"{meta}　完整度 {item.get('data_score') or 0}")
        if item.get("chemistry"):
            st.write(item["chemistry"])
        if item.get("functions"):
            st.markdown(f"功能：{item['functions']}")
        if item.get("applications"):
            st.markdown(f"用途：{item['applications']}")
        if st.button("帶入技術問答", key=key):
            st.session_state.chat_prefill = f"請依庫內材料 {title}（id={item.get('id')}）說明適用體系與下一步驗證，不要補未記載的規格。"
            st.rerun()


init_state()
health = get_health()
if not st.session_state.auth_user:
    render_login()
    tech = health.get("techdb") if isinstance(health, dict) else {}
    if isinstance(tech, dict) and tech.get("ok"):
        st.success(f"正式庫已連線，材料 {tech.get('materials')} 筆")
    elif isinstance(tech, dict) and tech.get("error"):
        st.warning(f"正式庫尚未連上：{tech.get('error')}")
    st.stop()

user = st.session_state.auth_user
tech = health.get("techdb") if isinstance(health.get("techdb"), dict) else {}

with st.sidebar:
    logo = LOGO_PATH if os.path.exists(LOGO_PATH) else None
    if logo:
        st.image(logo, width=160)
    st.markdown(f"**{user.get('name')}**")
    st.caption(f"角色：{user.get('role')}")
    st.caption("正式庫：" + (tech.get("url") or "http://127.0.0.1:8765"))
    if tech.get("ok"):
        st.success(f"正式庫 {tech.get('materials')} 筆材料")
    else:
        st.error(tech.get("error") or "正式庫未連線")
    if st.button("登出", use_container_width=True):
        try:
            backend.logout(_token())
        except Exception:
            pass
        st.session_state.auth_token = ""
        st.session_state.auth_user = None
        st.rerun()

    with st.expander("修改密碼"):
        with st.form("change_password_form"):
            current_password = st.text_input("目前密碼", type="password")
            new_password = st.text_input("新密碼", type="password")
            confirm_password = st.text_input("再輸入一次新密碼", type="password")
            changed = st.form_submit_button("更新密碼")
        if changed:
            if new_password != confirm_password:
                st.error("兩次新密碼不一致")
            else:
                try:
                    backend.change_password(_token(), current_password, new_password)
                    st.success("密碼已更新，下次請用新密碼登入")
                except Exception as exc:
                    st.error(str(exc))

st.title("塗料與樹脂研發工作台")
st.caption("搜尋走正式材料庫 :8765；實驗筆記留在本機工作台，並標記操作者。")

c1, c2, c3, c4 = st.columns(4)
c1.metric("目前使用者", user.get("name"))
c2.metric("正式材料", tech.get("materials") or "-")
c3.metric("來源文件", tech.get("documents") or "-")
c4.metric("工作台", "正常" if health.get("ok") else "異常")

search_tab, chat_tab, note_tab, log_tab = st.tabs(
    ["材料搜尋", "技術問答", "實驗筆記", "搜尋紀錄"]
)

with search_tab:
    with st.form("search_form"):
        left, mid, right = st.columns([0.55, 0.25, 0.20])
        query = left.text_input(
            "關鍵字",
            value=st.session_state.search_query,
            placeholder="例如：LUX220、NCO、聚氨酯、安鋒",
        )
        group = mid.selectbox(
            "材料大類",
            MATERIAL_GROUPS,
            index=MATERIAL_GROUPS.index(st.session_state.search_group)
            if st.session_state.search_group in MATERIAL_GROUPS
            else 0,
            format_func=lambda value: "全部正式材料" if not value else value,
        )
        submitted = right.form_submit_button("搜尋", use_container_width=True)
    if submitted:
        st.session_state.search_query = query.strip()
        st.session_state.search_group = group
        try:
            result = backend.search(_token(), query.strip(), group)
            st.session_state.search_results = result.get("data") or []
            st.session_state.search_total = result.get("count") or 0
            st.caption(f"由 {result.get('user') or user.get('name')} 查詢")
        except Exception as exc:
            st.session_state.search_results = []
            st.error(str(exc))
    if st.session_state.search_results:
        st.success(f"正式庫命中 {st.session_state.search_total} 筆，顯示 {len(st.session_state.search_results)} 筆")
        for index, item in enumerate(st.session_state.search_results):
            render_material_card(item, f"mat_{item.get('id')}_{index}")
    else:
        st.info("輸入牌號、CAS、功能或樹脂／助劑關鍵字後搜尋。")

with chat_tab:
    prefill = st.session_state.pop("chat_prefill", "")
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if st.session_state.chat_matches:
        with st.expander("本次問答引用的正式庫材料", expanded=True):
            for item in st.session_state.chat_matches[:6]:
                st.markdown(
                    f"- **{item.get('name')}** ｜ {item.get('supplier') or ''} ｜ {item.get('material_group') or ''}"
                )
    typed = st.chat_input("詢問選材、樹脂合成或驗證步驟。沒搜到的規格不會被填寫。")
    prompt = prefill or typed
    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        try:
            reply = backend.chat(_token(), st.session_state.chat_history[-12:])
            answer = (reply.get("answer") or "").strip() or "沒有回覆。"
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.session_state.chat_matches = reply.get("matches") or []
        except Exception as exc:
            st.session_state.chat_history.append({"role": "assistant", "content": f"問答失敗：{exc}"})
            st.session_state.chat_matches = []
        st.rerun()

with note_tab:
    st.caption("實驗筆記存在工作台 SQLite，不會寫入 19 GB 正式庫。")
    with st.form("note_form", clear_on_submit=True):
        name = st.text_input("筆記名稱")
        ingredients = st.text_area("投料／材料")
        steps = st.text_area("步驟與結果")
        tags = st.text_input("標籤", placeholder="2K PU, 小試")
        save = st.form_submit_button("以目前帳號存檔")
    if save:
        try:
            backend.add_note(
                _token(),
                {
                    "name": name,
                    "ingredients": ingredients,
                    "steps": steps,
                    "tags": tags,
                    "serving": 1,
                },
            )
            st.success(f"已用 {user.get('name')} 存檔")
        except Exception as exc:
            st.error(str(exc))
    try:
        notes = backend.list_notes(_token())
        for note in notes:
            st.markdown(
                f"**{note.get('name')}** ｜ {note.get('created_by') or '未記名'} ｜ {fmt_time(note.get('updated_at'))}"
            )
            st.caption(note.get("ingredients") or "")
    except Exception as exc:
        st.warning(str(exc))

with log_tab:
    try:
        logs = backend.search_logs(_token())
        if not logs:
            st.info("尚無搜尋紀錄。")
        else:
            st.dataframe(
                [
                    {
                        "時間": fmt_time(item.get("created_at")),
                        "使用者": item.get("display_name"),
                        "關鍵字": item.get("query"),
                        "大類": item.get("material_group"),
                        "命中": item.get("result_count"),
                    }
                    for item in logs
                ],
                use_container_width=True,
                hide_index=True,
            )
            buf = StringIO()
            writer = csv.DictWriter(buf, fieldnames=["時間", "使用者", "關鍵字", "大類", "命中"])
            writer.writeheader()
            for item in logs:
                writer.writerow(
                    {
                        "時間": fmt_time(item.get("created_at")),
                        "使用者": item.get("display_name"),
                        "關鍵字": item.get("query"),
                        "大類": item.get("material_group"),
                        "命中": item.get("result_count"),
                    }
                )
            st.download_button("下載搜尋紀錄 CSV", buf.getvalue(), "search_logs.csv", "text/csv")
    except Exception as exc:
        st.error(str(exc))
