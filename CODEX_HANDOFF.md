# 研發工作台連線修復

- project_id: coating-resin-workbench
- 本機根目錄: E:\V2.2\tmp\coating-resin-workbench_repair_20261109
- Codex 任務: V2.2／解決 Streamlit 異常（2026-11-09）
- 原始版本: 4b2d2e4；正式網址 https://coating-resin-workbench.streamlit.app/
- 已定位：雲端預設向自身 127.0.0.1:8765 查材料，錯誤呈現為正式庫故障；公司本機正式庫健康。
- 修正：區分 cloud/local/auto 執行環境。雲端配合 loopback 時，清楚提供筆記模式，停用無法工作的材料搜尋與問答；本機及已配置遠端 API 保留原路徑及真實故障訊息。
- 不修改／重啟 D 槽正式材料庫，不上傳材料、原始文件、私有資料或憑證，不建立公網 Tunnel。
- 本機版若啟動僅綁定 127.0.0.1，工作台筆記獨立保存；不與雲端筆記冒稱同步。
- 驗收：連線邊界單元測試、原帳號及搜尋測試、synthetic Streamlit UI；發布後再確認雲端登入頁及本機 API 連線。
- 更新載入：API client 僅在來源版本改變時重新載入，跨工作階段共用鎖；後端重新綁定目前的 client，避免快取舊模組與並行 reload。
