# ResearchBridge — 歷史 Streamlit 介面

> 目前展示版使用 FastAPI。請參閱 `README.md`，或執行 `run.cmd` 後開啟 http://127.0.0.1:8000 。以下保留舊版 Streamlit 功能說明。

數位健康與照護銜接的本機研究證據探索原型。原始 `pubmed/`、`openalex/` 與規劃 PDF 均保留。

## 啟動

舊版介面需另行安裝 Streamlit（`python -m pip install streamlit`）。已保存公開來源快照，可離線搜尋。

若要啟動歷史 Streamlit 介面，在 PowerShell 執行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

在瀏覽器開啟 http://127.0.0.1:8501 。服務只綁定本機。關閉服務時在終端按 Ctrl+C。

新電腦需 Python 3.12，建立環境後安裝依賴：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m researchbridge.ingest
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

## 目前功能

- 完整匯入 60 筆原始書目與 135 筆機構名錄；SQLite 保留來源與原始欄位。
- 補入 PubMed 官方記錄、摘要、作者、DOI、文獻類型、MeSH（若來源提供），分開保存出版與歷史日期。
- 20 篇文獻查 OpenAlex work，先核對精確 PMID，再建立去重的作者機構關聯；名錄配對只採標準化名稱精確一致。
- 題名與摘要的 TF-IDF 搜尋，以及可切換的 TF-IDF＋LSA 本機混合排序。
- 人工中英詞彙對照支援「用藥素養」「照護銜接」「蛋白質」「臨床試驗」等查詢；「照護銜接」另需照護語境詞，避免只因 transition 或 community 帶入非照護論文。不宣稱通用中文理解。
- 主題、期刊、有摘要、有機構關聯篩選；最多四篇比較；CSV、來源 JSON 與引文下載。
- 資料範圍、方法、來源覆蓋及固定開發案例的檢索評估。
- 語言與外觀選單固定在頂端，與 Deploy 同列，可切換繁體中文、英文、西班牙文及明亮／深色模式。原始論文題名、摘要保留來源語言；切換語言會翻譯內建預設查詢及提示，使用者自行輸入的研究目標保留原值。
- 頂端兩個選單保留可見的「介面語言／外觀模式」小標，並隨語言翻譯。切換語言或外觀會保留目前頁籤，以固定頁面 ID 對應各語言標籤；研究比較、Bridges 等頁面不會因此跳回文獻探索。
- 查詢欄內建範例（包含舊版「大型語言模型 隱私」等網址與工作階段）及資料推薦關鍵字均有中英西對應；切換語言會更新欄內文字，同一內建概念以固定查詢檢索，確保語言切換不改變排序。自行輸入且不屬於內建詞組的研究內容保留原文。
- 雙端滑桿及數值上下界只設定「文獻探索」的 0–1 搜尋相關度範圍，不影響 Bridges。分數比較目前查詢與論文題名、摘要，用於檢索排序和篩選；不是 correlation、機率或證據品質。TF-IDF 題名加權三次；混合分數使用 80% TF-IDF＋20% 非負 LSA。
- Bridges：由目標相關文獻推薦方法 C，再選擇方法與感興趣的線索 B。推薦必須同時匹配方法與線索，逐篇列出題名或官方摘要的原文依據。Bridge 分數依頁面明示的 Bridge 搜尋式重新計算，因此可探索原目標以外的延伸文獻。
- Bridges 的方法建議也不受搜尋分數門檻影響，但仍套用主題、期刊、有摘要及機構關聯篩選；與搜尋使用相同的顯示筆數設定。
- Bridges 另顯示目前可見結果彼此的兩兩相關性，採與比較頁一致的文件 TF-IDF cosine similarity。3 篇會有 3 組、N 篇會有 N(N-1)/2 組，不包含自己與自己或重複配對；編號對應卡片順序。0 或 1 篇結果時不產生分數。Bridge 匯出同時保留全部符合條件的論文、目前可見結果的配對、分數定義與範圍。卡片上的原 Bridge 搜尋排序分數仍保留。
- 推薦關鍵字按目前資料篩選後的文獻，統計人工概念詞彙的實際出現篇數，交錯推薦研究線索與方法。每個候選需有原文匹配；不是 LLM 自行產生的題目。
- 比較頁提供探索標籤、原文推得的領域、原文提及的方法、來源依據，以及每對論文的共同點、差異與共同詞。關聯分數採文件 TF-IDF cosine similarity，IDF 固定以全部 60 篇語料建立，與查詢、檢索模式及搜尋門檻無關。這是文字相似度，不是 Pearson correlation、因果關聯或研究結果一致程度；缺少摘要時另行提示。
- 搜尋、Bridges、比較、簡報及機構名錄均可匯出 CSV、PDF、HTML。PDF 嵌入微軟正黑體、支援中英西及分頁；HTML 為可離線開啟的獨立檔，CSV 保留來源及分數定義。比較另保留 JSON 與引文，簡報另保留 Markdown。
- 來源核對採保守字面匹配：每行一項，最多 20 項；沒有直接匹配時標為需要人工確認，不推斷主張為假或缺乏科學支持。
- 研究機會簡報可下載 Markdown，包含真實引文、來源、機構與聯絡信草稿。信件不會寄出；比較清單優先於目前結果，手動選取的論文不受後續門檻變更移除。

## 展示流程

1. 先搜尋「用藥素養」，查看 EMPATHICA 的 PubMed 記錄與官方摘要。
2. 展開「論文所載機構」，查看作品來源與穩定機構 ID。
3. 加入比較，再搜尋「照護銜接」並加入另一篇，切至「研究比較」。
4. 切換 TF-IDF／混合檢索，檢查結果是否改變；排序分數不代表醫療效果或研究品質。
5. 搜尋 `zzxq987654xyz`，確認系統如實回報沒有結果。
6. 於「機構名錄」依名稱、城市探索；於「資料與方法」查看來源覆蓋及評估。

## 更新與重現

```powershell
# 使用快取，重建資料庫；既有記錄不重抓
.\.venv\Scripts\python.exe -m researchbridge.ingest

# 連線刷新官方快照；需要可用網路
.\.venv\Scripts\python.exe -m researchbridge.ingest --refresh --openalex-limit 20

# 重跑開發用檢索檢查與測試
.\.venv\Scripts\python.exe -m researchbridge.evaluate
.\.venv\Scripts\python.exe -m pytest tests --basetemp=.cache/testtmp
```

OpenAlex API key 可由執行環境變數 `OPENALEX_API_KEY` 提供（選用）。不要將 key 寫入原始碼或快照。認證與限制依 [OpenAlex 官方文件](https://help.openalex.org/api/authentication/) 為準。刷新失敗會保留既有成功快照，錯誤摘要保存在 `data/snapshots/retrieval_log.json`。

## 架構與檔案

```text
streamlit_app.py               Streamlit 三語介面、範圍控制與探索流程
researchbridge/core.py         XML 解析、SQLite、來源關聯、TF-IDF／LSA、原文摘錄
researchbridge/discovery.py    方法、Bridges、字面來源核對、簡報範本
researchbridge/i18n.py         中英西介面文字與主題標籤
researchbridge/style.py        明亮／深色配色與可存取表格樣式
researchbridge/insights.py     語料頻率推薦、論文領域與方法、兩兩相似度
researchbridge/reports.py      介面與匯出共用的內容結構
researchbridge/exports.py      CSV、獨立 HTML、嵌入中文字型的 PDF
researchbridge/ingest.py       公開 API 抓取、快照、重建資料庫
researchbridge/evaluate.py     固定開發題的 MRR@5 與命中數
data/snapshots/                公開 PubMed XML／JSON、OpenAlex JSON、抓取紀錄
data/researchbridge.sqlite     本機資料庫，可由快照重建
data/evaluation.json           可重現的開發案例與搜尋結果
tests/                         資料、搜尋、關聯與介面流程測試
```

`papers` 保留 starter 與正式 metadata；`institutions` 保存原始名錄；`paper_institutions` 以 `(pmid, institution_id)` 去重；`provenance` 保存原始 CSV 的 SHA-256。

## 技術與邊界

- 主題是探索用 regex 規則標籤，不是官方 MeSH 或臨床分類。
- LSA 是本機 24 維以內的 TruncatedSVD 向量；不是預訓練多語 embedding。混合分數為 0.8 TF-IDF＋0.2 非負 LSA 相似度，且僅重新排序有詞彙交集的文獻。
- 卡片抽取官方摘要原句；沒有摘要時只顯示書目。不生成研究結果、療效或自動研究缺口。
- 機構關聯代表來源收錄的論文 affiliation，不是目前任職、合作意願或醫療專長的證明；未匹配名錄的外部機構保留未知城市。
- 固定八題是開發案例，不是獨立評估、使用者研究或臨床效益實驗。
- ResearchBridge HTML 僅作互動設計參考；不沿用其示例 PMID、機構數、歷史驗證比例或研究空缺結論。本地 60 篇語料未做時間切割的歷史空缺驗證。共用文字線索不等於共同因果機制，缺少匹配也不表示全球沒有相關研究。
- 本版不使用 LLM API、不上傳私人資料、不需要 GPU。後續若增加預訓練 embedding 或 RAG，應獨立比較相關性與引用忠實度。

## 公開來源

- [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- [PubMed 日期說明](https://pubmed.ncbi.nlm.nih.gov/help/#pubdate)
- [OpenAlex ID 查詢](https://help.openalex.org/api/get-single-entities/)
- [OpenAlex authorships](https://help.openalex.org/data/authorships/)

公開發佈前需另行核對摘要／全文的適用授權；本機快照不是全文再散布授權。
