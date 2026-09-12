# RTX 5070 Ti 配方查詢多人共用版（Ollama + SQLite）

這個版本是你目前需求的「可多人共用」完整骨架：

- 後端：Python + SQLite（`recipes.db`）
- LLM：`qwen2.5:7b-tw`（台灣繁體固定）
- 資料：可新增/查詢配方
- 查詢介面：
  - 傳統版：`http://<伺服器IP>:8088`
  - Streamlit 版：`http://localhost:8501`

## 你現在已經完成哪些前置

1. 已安裝並驗證 `qwen2.5:7b-tw` 可用
2. 我建立了：
   - `recipe_server.py`：API + 網頁伺服器
   - `web/index.html`：配方查詢 / 新增 / 問答介面
  - `app.py`：Streamlit 專業版（聊天、搜尋、新增、多人共用）
  - `requirements.txt`：Streamlit 相關套件
  - `scripts/start_all.ps1`：一鍵啟動 Ollama 服務 + 配方服務
   - `scripts/start_streamlit.ps1`：僅啟動 Streamlit 前端
   - `scripts/stop_all.ps1`：關閉服務（僅關閉本機本專案啟動的進程）
   - `scripts/setup_firewall.ps1`：可選的防火牆開放（需系統管理員）
   - `scripts/import_csv.ps1`：匯入 CSV 資料到配方資料庫
   - `data/sample_recipes.csv`：配方樣本

## 一鍵啟動流程

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
cd C:\Users\User\OneDrive\Desktop\CODEX\企業資料庫
./scripts/start_all.ps1
```

啟動後，請用：
- 健康檢查：`http://你的IP:8088/api/health`
- 舊版查詢頁：`http://你的IP:8088/`
- Streamlit 查詢頁：`http://localhost:8501`

首次要跑 Streamlit，請先安裝套件：

```powershell
pip install -r requirements.txt
```

如果要同時啟動 API 與 Streamlit：

```powershell
./scripts/start_all.ps1 -WithStreamlit
```

如果只啟動 Streamlit（API 已先行啟動）：

```powershell
./scripts/start_streamlit.ps1
```

多人共用注意事項：
- Ollama 會以 `OLLAMA_HOST=0.0.0.0:11434` 啟動
- API 服務預設監聽 `0.0.0.0:8088`
- 為了讓其他電腦可以存取，請確認你路由器/防火牆無阻擋

## 建議的安全設定

- 目前設定已將 `OLLAMA_ORIGINS="*"`（最方便）
- 若只開放內網，建議改成 `OLLAMA_ORIGINS="http://10.0.0.0/8"` 或實際前端網址
- 建議把 API 只綁定在內部網段，避免直接曝露到公網
- 可加反向代理加上登入驗證（Nginx / IIS / Apache）

## 匯入範例配方

啟動服務後，另開一個終端機執行：

```powershell
./scripts/import_csv.ps1
```

## 常用 API

### 查詢配方
`GET /api/recipes?q=雞蛋`

### 新增配方
`POST /api/recipes`
```json
{
  "name": "番茄炒蛋",
  "ingredients": "番茄 3顆，雞蛋 3顆，蔥 5g，鹽 1小匙",
  "steps": "1) 打散蛋\n2) 番茄切塊\n3) 下油爆香...",
  "tags": "早餐,簡單",
  "serving": 2
}
```

### AI 問答
`POST /api/chat`
```json
{
  "message": "我只有雞蛋和番茄，怎麼做快手料理？"
}
```

Streamlit 版聊天室同樣會呼叫 `/api/chat`，並保留近期訊息當上下文，回覆會保留在頁面對話框中。

### 公司 Logo

預設會讀取：
`C:\\Users\\User\\OneDrive\\Desktop\\logo(含字)上下寬.jpg.png`
你也可用環境變數覆寫：

```powershell
$Env:RECIPE_LOGO_PATH="C:\\你自己的路徑\\logo.png"
./scripts/start_streamlit.ps1
```

## 常見修正

### Python 檔案不能啟動
先確認 `python` 在 PATH，並從專案根目錄執行 `python recipe_server.py`。

### `ollama` 連不到
先在本機測試 `ollama list` 與 `ollama run qwen2.5:7b-tw "1+1"`，再確認 `start_all.ps1` 是否已成功啟動背景服務。

### 我要結束服務
在同樣目錄執行：

```powershell
./scripts/stop_all.ps1
```

若你只要關閉本次啟動的配方 API，直接執行上面指令；若也要關閉同時啟動的 Ollama，請加：

```powershell
./scripts/stop_all.ps1 -WithOllama
```

若有同時啟動 Streamlit，`./scripts/stop_all.ps1` 會一併關閉 Streamlit。

## 常用資料庫維護

DB 檔：`recipes.db`（SQLite）
可直接用 DB 工具備份/還原，支援多人同時讀取，寫入時依需求可再改為 WAL/交易鎖控制。

## Streamlit Cloud 上傳部署

程式入口是 `app.py`。**19 GB 正式材料庫不要上傳**，雲端也連不到公司內網 `http://127.0.0.1:8765`。

雲端能用：登入、改密、實驗筆記（存在雲端自己的 SQLite，和公司電腦不是同一份）。
雲端不能用：正式材料搜尋、Ollama 技術問答。四人查材料請用本機 `http://127.0.0.1:8501`。

1. 私有 GitHub repo（不要公開），不要提交 `recipes.db`、`.venv`、`.streamlit/secrets.toml`。
2. 到 [share.streamlit.io](https://share.streamlit.io) → New app：
   - Main file path：`app.py`
   - Advanced settings → Python **3.12**
3. 不要把正式庫 API 用 ngrok／公網隧道接到雲端。

本機 Streamlit：

```powershell
cd C:\Users\User\OneDrive\Desktop\CODEX\企業資料庫
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
./scripts/start_streamlit.ps1
```
