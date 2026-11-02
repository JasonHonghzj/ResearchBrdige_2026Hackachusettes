# 最新版驗證、整理與限制

整理日期：2026-11-02。預設 `run.cmd`／`app.py` 已改用 2026-10-30 正式取得的
80,025 篇快照，50×32 軸、534 個空格檢查、425 個低結果候選。沒有在 11 月 2 日
重新抓取全部 PubMed，資料日期與程式整理日期分開記錄。

## 這次整理

- 用已完成來源對帳、實際建圖與 HTTP 載入的快照取代舊預設資料；保留一份目前的
  serving JSON、tree/count cache、來源紀錄及 `data/snapshot.json`。
- 移除舊 Streamlit 程式／設定／專用測試、未被目前 UI 使用的樣式模組、舊 pipeline
  展示、過時 DESIGN、探索 probes、重複 starter ZIP 和未使用的機構區域快取。
- README 重寫為目前唯一 FastAPI 入口；兩份舊修正報告整併到本文件，舊數字不再
  混作目前展示數字。.kiro 三份說明同步維護目前架構與證據規則。
- 舊輸出、測試暫存、影像／影片審視素材、原附件與被取代文件移出專案，保存在本機
  專案外備份。原始 `DS+X real.zip` 未修改；歷史 tracked 內容仍可由 Git history 取得。
- 完整原始語料與 manifests 保存在本地 `data/`，不推送到 Git；目前小型來源證據在
  `data/audit/`，可與 SQLite／官方來源 snapshots 一起隨程式保存。

## 語料與來源

44,156 + 36,684 − 803（跨查詢窗重複）＝80,037；排除儲存出版年為 2027 的 12 篇後
為 80,025。嚴格同母體切割為 ≤2018 的 43,353／>2018 的 36,672，交集 0。標題無缺值，
MeSH 100%，摘要 69,013 篇（86.24%）。儲存年份依 Journal/PubDate/Year、ArticleDate/Year、
MedlineDate 開頭年份依序解析；並非每種來源日期均作為獨立欄位保存。

production 30／past 15／future 15，共 60 個不同 PMID，重新向官方取得標題與 MeSH IDs
比對全部一致；不涵蓋全部紀錄或摘要全文。`data/audit/spot_check_*.json` 與
`corpus_audit.json` 保留 sampled PMIDs、來源 SHA-256 與時間。原始稽核檔內路徑記錄
2026-10-30 執行時的位置；整理後檔案位置為 `data/`，檔案內容雜湊才是來源身份依據。
`data/audit/run.json` 的 saved-demo 比較及 unchanged 記錄指當次隔離稽核，不是本次
將新快照提升為預設後的狀態。

534 組 confirmation 中，533 組沿用歷史快取，僅 1 組在 2026-10-30 新查詢；舊快取
沒有逐組時間戳。425 只能稱保存查詢下的候選，不能稱全部當天重新驗證，更不能
作新穎性或研究有效性的證明。需要最新配對數字時使用 UI 的 Refresh PubMed。

舊版本標示 79,940，但原始 ZIP 沒有其完整 corpus／PMID 清單。因此新快照無法證明
已復原舊集合，也無法把數量差 85 解讀為單純新增 85 篇。兩個舊圖配對即使取消日期
過濾仍比新資料多一篇；要確定原因，需舊原始語料及生成版本。該舊版本不再作預設展示。

## 回溯評估與宣稱

`data/audit/history-evaluation.json` 是目前的獨立回溯分析，使用訓練期選軸／詞彙／IDF／
排序、固定 ontology 和無放回配對。訓練期 744 空格中有 522 被標記、222 可作對照，
得到 171 對、44 個疾病，僅覆蓋 32.76% 被標記格。後期至少一篇：24/171（14.04%）
對 50/171（29.24%）；疾病群組 bootstrap 差值 −15.20 百分點，95% 區間
[−23.08, −7.60]。獨立 PMID 集合交集重算一致；結果不支持恢復 2× 宣稱。

這是現在標註下的回溯共現分析，缺少 as-of-2018 索引、ontology 和文獻可見時間。
配對覆蓋有限，跨疾病共用方法／論文的相依性也未完全調整。不是因果、新穎性或
前瞻性研究成效證明。`data/validation.json` 維持 `pending_remeasurement`，保留撤回
理由及有日期的負面結果。凍結評估 ontology 保存在 `data/audit/history_mesh_trees.json`；
它是重現這份評估的必要來源，不用於正式全期建圖。

正式重驗原成效需要原排序程式／參數、舊完整 corpus 或 PMID、切割時點的索引與
ontology，以及預先定義的 holdout／結果門檻／對照規則。資料不足時維持撤回。

## Verification

2026-10-30 曾完成 207 個 Python 測試（含已移除的 15 個 Streamlit 測試）、8 個 Node
測試、45 組三語 CSV／HTML／PDF 實際 HTTP 匯出；舊 Streamlit 自訂安裝目錄的測試
啟動方式需要明確指定一般模式。現在已移除該介面，主程式不再需要其套件或測試設定。
本次整理後的實際測試結果、HTTP 與封裝核對記錄在 `data/audit/release-checks.json`。

HTTP 檢查涵蓋回應、PMIDs、32 筆搜尋／20 張卡片、完整匯出及 PDF 可解析文字。
它不能替代畫面／列印預覽驗證。先前實際瀏覽器已下載 Markdown、CSV、HTML、PDF，
並目視檢查代表性英／中 PDF 第一頁。完整手機版、西文視覺、深淺主題及原生列印預覽
尚未全部完成；先前 Computer Use 無法可靠識別 Windows 瀏覽器網址而停止，未列為通過。

## Manual browser checks

1. 用 `run.cmd` 啟動，開啟 http://127.0.0.1:8000。首頁應顯示 80,025 篇／425 候選。
   選 Obesity × PCR，檢查 Brief 的 pairing、2,403／0 保存數字與精確查詢相符。
2. Library 搜尋 `study`，確認 32 筆符合／20 張卡片；切換繁中與西文並核對保存論文。
3. 390px 裝置模擬逐一查看 Check、Map、Library、Brief、Method；文字與按鈕可讀，
   map 可在自己的容器內捲動，整頁不應橫向溢出。
4. 選 pairing → Brief → Print / save PDF。預覽只含選定 brief，數字／查詢相符；深淺
   螢幕主題均應印成白底深字。Library 的伺服器 PDF 匯出與這個系統列印功能不同。
