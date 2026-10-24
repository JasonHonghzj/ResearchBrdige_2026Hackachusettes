"""Rebuild the Chinese proposal PDF with embedded fonts and ASCII-safe streams.

Run with the bundled PDF-authoring Python runtime (reportlab, pypdf).
All final PDF copies must be written as bytes, never with text encodings.
"""
from pathlib import Path
from html import escape
import base64
import io
import json
import re
import zlib

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, ArrayObject, StreamObject

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output' / 'pdf'
QA = ROOT / 'tmp' / 'pdfs' / 'repair-zh'
OUT.mkdir(parents=True, exist_ok=True)
QA.mkdir(parents=True, exist_ok=True)

pdfmetrics.registerFont(TTFont('RBTC', 'C:/Windows/Fonts/msjh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('RBTCBold', 'C:/Windows/Fonts/msjhbd.ttc', subfontIndex=0))
pdfmetrics.registerFontFamily('RBTC', normal='RBTC', bold='RBTCBold', italic='RBTC', boldItalic='RBTCBold')

NAVY = colors.HexColor('#142D42')
TEAL = colors.HexColor('#127C80')
INK = colors.HexColor('#243B4B')
MUTED = colors.HexColor('#60727E')
LIGHT = colors.HexColor('#EDF5F5')
LINE = colors.HexColor('#D8E3E7')
W, H = A4
M = 43
CW = W - M * 2


def safe(text):
    return re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)', '&amp;', text)


class Report:
    def __init__(self):
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=A4, pageCompression=1)
        self.c.setTitle('醫療與生技：提案、研究流程與技術實作')
        self.c.setAuthor('Project planning document')
        self.c.setSubject('Chinese edition - repaired fonts and layout')
        self.n = 0
        self.used = []
        self.body = ParagraphStyle('body', fontName='RBTC', fontSize=10.8, leading=17.4, textColor=INK, wordWrap='CJK', splitLongWords=True)
        self.small = ParagraphStyle('small', parent=self.body, fontSize=9.1, leading=13.7, textColor=MUTED)
        self.cell = ParagraphStyle('cell', parent=self.body, fontSize=9.5, leading=14.5)
        self.head = ParagraphStyle('head', parent=self.cell, fontName='RBTCBold', textColor=colors.white)

    def check(self, h):
        if self.y - h < 58:
            raise ValueError(f'Page {self.n} overflow: y={self.y:.1f}, height={h:.1f}')

    def p(self, text, style=None, size=None, leading=None, color=None, bold=False, after=9):
        style = style or self.body
        if size or leading or color or bold:
            style = ParagraphStyle('derived', parent=style, fontName='RBTCBold' if bold else style.fontName, fontSize=size or style.fontSize, leading=leading or style.leading, textColor=color or style.textColor)
        p = Paragraph(safe(text), style)
        _, h = p.wrap(CW, 2000)
        self.check(h)
        p.drawOn(self.c, M, self.y - h)
        self.y -= h + after

    def page(self, label, title, subtitle=''):
        if self.n:
            self.endpage()
        self.n += 1
        c = self.c
        c.setFillColor(TEAL)
        c.rect(0, H - 9, W, 9, fill=1, stroke=0)
        c.setFillColor(MUTED)
        c.setFont('RBTCBold', 8.6)
        c.drawString(M, H - 37, 'HEALTHCARE & BIOTECH / PROJECT PROPOSALS')
        c.drawRightString(W - M, H - 37, f'{self.n:02d}')
        self.y = H - 64
        self.p(label, size=9.5, leading=14, color=TEAL, bold=True, after=8)
        self.p(title, size=22, leading=30, color=NAVY, bold=True, after=9)
        if subtitle:
            self.p(subtitle, style=self.small, after=15)
        else:
            self.y -= 6

    def section(self, text):
        self.y -= 3
        self.p(text, size=12.5, leading=19, color=NAVY, bold=True, after=7)

    def bullet(self, text):
        self.p(text if re.match(r'^\d+\.', text) else '- ' + text, after=6)

    def ref(self, text):
        self.p(text, style=self.small, after=5)

    def box(self, title, text):
        tp = Paragraph(safe(title), ParagraphStyle('boxhead', parent=self.body, fontName='RBTCBold', fontSize=11.2, leading=17, textColor=TEAL))
        bp = Paragraph(safe(text), self.body)
        _, ht = tp.wrap(CW - 26, 2000)
        _, hb = bp.wrap(CW - 26, 2000)
        h = ht + hb + 31
        self.check(h)
        self.c.setFillColor(LIGHT)
        self.c.roundRect(M, self.y - h, CW, h, 7, fill=1, stroke=0)
        tp.drawOn(self.c, M + 13, self.y - 11 - ht)
        bp.drawOn(self.c, M + 13, self.y - 18 - ht - hb)
        self.y -= h + 13

    def table(self, headers, rows, fractions):
        data = [[Paragraph(escape(str(v)), self.head) for v in headers]]
        data += [[Paragraph(safe(str(v)), self.cell) for v in row] for row in rows]
        table = Table(data, colWidths=[CW * f for f in fractions], hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#F2F6F8'), colors.white]),
            ('LINEBELOW', (0, 1), (-1, -1), .4, LINE),
        ]))
        _, h = table.wrap(CW, 2000)
        self.check(h)
        table.drawOn(self.c, M, self.y - h)
        self.y -= h + 13

    def architecture(self):
        nodes = ['1. 原始 CSV 與官方 API', '2. 清理、驗證、版本與快取', '3. 正規化資料與關聯表', '4. 檢索、篩選與規則', '5. 有來源的文字生成', '6. 使用者檢視與人工確認']
        bw, bh, gap = (CW - 24) / 2, 48, 24
        self.check(bh * 3 + gap * 2)
        for i, text in enumerate(nodes):
            row, col = divmod(i, 2)
            x, top = M + col * (bw + 24), self.y - row * (bh + gap)
            self.c.setFillColor(LIGHT)
            self.c.setStrokeColor(LINE)
            self.c.roundRect(x, top - bh, bw, bh, 5, fill=1, stroke=1)
            p = Paragraph(text, ParagraphStyle('node', parent=self.cell, fontName='RBTCBold', alignment=1, textColor=NAVY))
            _, ph = p.wrap(bw - 18, 200)
            p.drawOn(self.c, x + 9, top - (bh + ph) / 2)
        for row in range(3):
            x, y = M + bw, self.y - row * (bh + gap) - bh / 2
            self.c.setStrokeColor(TEAL)
            self.c.setFillColor(TEAL)
            self.c.line(x + 3, y, x + 20, y)
            path = self.c.beginPath()
            path.moveTo(x + 20, y)
            path.lineTo(x + 15, y + 3)
            path.lineTo(x + 15, y - 3)
            path.close()
            self.c.drawPath(path, fill=1, stroke=0)
        self.y -= bh * 3 + gap * 2 + 13

    def endpage(self):
        self.used.append(round(H - 64 - self.y, 1))
        self.c.setStrokeColor(LINE)
        self.c.line(M, 43, W - M, 43)
        self.c.setFillColor(MUTED)
        self.c.setFont('RBTC', 8)
        self.c.drawString(M, 28, '規劃文件 / 尚未實作或驗證產品成效')
        self.c.drawRightString(W - M, 28, f'2026-10-24   |   {self.n:02d} / 10')
        self.c.showPage()

    def finish(self):
        self.endpage()
        self.c.save()
        original = self.buffer.getvalue()
        reader = PdfReader(io.BytesIO(original), strict=True)
        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        stream_count = 0
        for obj in writer._objects:
            if isinstance(obj, StreamObject):
                payload = obj.get_data()
                obj._data = base64.a85encode(zlib.compress(payload), adobe=False) + b'~>'
                obj[NameObject('/Filter')] = ArrayObject([NameObject('/ASCII85Decode'), NameObject('/FlateDecode')])
                obj.pop(NameObject('/DecodeParms'), None)
                stream_count += 1
        target = io.BytesIO()
        writer.write(target)
        result = target.getvalue().replace(b'%\xe2\xe3\xcf\xd3', b'%RBZH')
        assert result.isascii(), 'PDF must be fully ASCII-safe while retaining embedded CJK fonts'
        verify = PdfReader(io.BytesIO(result), strict=True)
        assert len(verify.pages) == 10
        full = '\n'.join(p.extract_text() or '' for p in verify.pages)
        for expected in ['醫療與生技', '資料盤點', '研究過程', 'ResearchBridge', 'Coverage Guide']:
            assert expected in full, expected
        assert '\ufffd' not in full and '(cid:' not in full
        output = OUT / 'healthcare_biotech_proposals_zh-TW_fixed.pdf'
        output.write_bytes(result)
        (QA / 'fixed-text.txt').write_text(full, encoding='utf-8')
        print(json.dumps({'output': str(output), 'pages': 10, 'bytes': len(result), 'ascii_safe': True, 'encoded_streams': stream_count, 'used_heights': self.used}, ensure_ascii=False))


def main():
    r = Report()
    r.page('選題與決策摘要', '醫療與生技：提案、研究流程與技術實作', '以 PubMed 與 OpenAlex starter kit 為基礎 | 繁體中文版')
    r.box('首選：ResearchBridge 研究證據與合作導航', '從一個醫療或生技問題出發，找到可追溯的論文、理解方法與限制，再探索具有文獻依據的研究機構關聯。先聚焦「數位健康與照護銜接」，較容易做出完整而可信的展示。')
    r.p('本文件整理三個主要提案與兩個延伸想法，逐一列出使用者、產品內容、實作流程、技術與研究驗證。中文與英文版採相同結構。')
    r.table(['方案', '使用情境', '資料準備程度'], [
        ['ResearchBridge', '文獻與研究合作導航', '最貼近現有資料；關聯需補齊'],
        ['CareBridge', '照護銜接的證據與待辦助手', '有文獻線索；需實務流程'],
        ['TrialBridge', '多語臨床研究導航', '需新增試驗登錄資料'],
        ['Wearable Evidence Lab', '穿戴技術證據與驗證規劃', '需擴充專題文獻'],
        ['Coverage Guide', 'MassHealth 續保資訊與待辦', '需官方規則與行政資料'],
    ], [.28, .38, .34])
    r.ref('閱讀方式：第 2 頁看資料限制；第 3-6 頁看提案；第 7-9 頁看技術、研究與時程；第 10 頁查來源。')

    r.page('01 / 資料盤點', '兩份資料能支持什麼？', '已完整閱讀 9 個檔案與兩份 CSV 的所有資料列；參考圖片作為選題背景。')
    r.table(['項目', 'PubMed [D1]', 'OpenAlex [D2]'], [
        ['粒度與規模', '每列一筆文獻；60 列、5 欄', '每列一筆機構；135 列、4 欄'],
        ['實際欄位', 'pmid, title, journal, published, authors', 'institution, city, works, cited_by'],
        ['品質檢查', '欄位空值 0；重複 PMID 0；完全重複列 0', '欄位空值 0；完全重複列 0'],
        ['關鍵缺口', '沒有摘要、全文、作者機構、DOI 或試驗資訊', '沒有論文、主題、作者、年度、OpenAlex ID 或 ROR'],
    ], [.19, .405, .405])
    r.section('必須先釐清的四件事')
    for text in [
        '日期語義：PubMed 的 published 年份字串為 2024 年 32 筆、2025 年 26 筆、2026 年 2 筆。README 宣稱 2024 年；應回查紙本、電子與收錄日期，不直接判定資料錯誤。[R2]',
        '不能直接串接：兩份 CSV 沒有共同鍵。作者姓名字串無法直接證明機構關聯。機構名稱也需要穩定 ID 與層級核對。',
        '抓取腳本不等於重建流程：PubMed 只查 20 個 PMID；OpenAlex 只取前 25 筆，未分頁。兩者輸出 fresh.json，不能重建現有完整 CSV。',
        '統計意義：OpenAlex 名錄混合不同機構類型與層級，作品與引用數沒有年度。不能據此宣稱醫療品質、目前專長、成長趨勢或全州獨立論文總量。',
    ]: r.bullet(text)
    r.ref('README 註記保存日為 2026-10-18；這是文件所載日期，不是獨立驗證的抓取時間。')

    r.page('02 / 主要提案一', 'ResearchBridge', '研究證據與合作導航 | 最建議先做的 MVP')
    r.section('使用者與問題')
    r.p('研究生、生技研發與醫療創新團隊，常需要同時回答「有哪些方法？」「證據有什麼限制？」「哪些研究機構值得進一步了解？」。產品把三個問題串成同一條可追溯路徑。')
    r.section('產品內容與展示情境')
    r.p('使用者輸入「如何用數位工具改善照護銜接？」後，看到相關文獻、研究卡片、方法比較，以及經查證的作者機構關聯。資料中已有用藥素養聊天機器人（PMID 41726533）及照顧者支援（41726516）等題名線索。')
    r.section('實作流程')
    for text in [
        '1. 保留原始 CSV；以 PMID 去重，用 EFetch 補摘要、DOI、文獻類型與可取得的 affiliation。[R1]',
        '2. 用 PMID 或 DOI 查 OpenAlex work，再讀 authorships 的 institution ID；對照並補齊原機構名錄。[R3-R4]',
        '3. 先做關鍵字搜尋，再加入向量搜尋；讓生成式模型依檢索內容整理方法、限制與逐項來源。',
        '4. 顯示未匹配或缺資料狀態；人工核對有歧義的機構。只有題名時，只提供書目資訊與題名層級分類。',
    ]: r.bullet(text)
    r.table(['技術', '用途'], [
        ['Python / pandas / SQLite', '清理、去重、保存來源與關聯表'],
        ['Keyword search + embeddings', '以關鍵字基準比較語意檢索的增益'],
        ['LLM API + Streamlit', '附來源的研究卡片與互動搜尋原型'],
    ], [.37, .63])
    r.ref('驗證：前五筆結果相關性、引用支持率、論文機構配對正確率，以及找到可用證據的任務時間。這些是待測量指標，尚無成效結果。')

    r.page('03 / 主要提案二', 'CareBridge', '照護銜接的證據與待辦助手')
    r.section('使用者與問題')
    r.p('服務照護協調人員、社工與社區健康工作者。先鎖定「從護理機構返回社區」的一段流程，協助整理資訊交接、回診、用藥理解與服務連結中需要確認的事項。')
    r.section('資料起點與產品內容')
    r.p('PMID 41726541 的題名涉及下肢骨折患者返回社區的行動應用原型；41726533 涉及用藥素養；41001595 涉及產後保險變動。它們提供研究線索，尚不能證明任何流程或介入的成效。[D1]')
    r.box('展示情境：使用合成案例', '協調人員輸入一個虛構出院情境，系統整理「待確認資訊、可參考的研究、可採用的流程草稿」。每個項目標明來自研究、官方流程，或仍需人工確認。')
    r.section('實作流程與技術')
    for text in [
        '先訪談實務人員，畫出目前流程與常見漏項；不要讓模型自行發明標準作業程序。',
        '將研究證據、機構核可流程與服務名錄分開建檔，保留適用範圍、版本及更新時間。',
        '採用 Python、SQLite、結構化待辦模板與檢索式生成；規則層管理必要欄位與狀態，模型協助解釋文字。',
        '初版只做草稿與確認流程。若要處理實際轉診、預約或交通，還需要對應機構的正式資料與系統介接。',
    ]: r.bullet(text)
    r.ref('驗證：合成案例必要事項涵蓋率、錯誤或無來源項目數、使用者完成任務時間與清晰度。臨床判斷留給合格專業人員。')

    r.page('04 / 主要提案三', 'TrialBridge', '多語臨床研究導航')
    r.section('使用者與價值')
    r.p('讓患者、家屬與轉介人員更容易找到值得詢問的研究，理解參與負擔、地點與需要確認的條件。目的在支持研究探索與詢問，不輸出最終參加資格判定。')
    r.section('為什麼必須補資料？')
    r.p('目前只有討論顱底疾病試驗可近性的文獻題名（PMID 41140426）。論文不能代表現在招募中的研究；研究機構所在地也不能直接當作試驗地點。需新增 ClinicalTrials.gov 登錄資料。[R6]')
    r.table(['新增欄位', '功能'], [
        ['NCT ID / study title', '穩定識別研究與連回官方記錄'],
        ['Recruitment status / update date', '呈現目前登錄狀態與資料新鮮度'],
        ['Eligibility criteria', '白話解釋條件與待確認問題'],
        ['Locations / contacts', '依實際試驗地點提供探索與聯繫路徑'],
    ], [.42, .58])
    r.section('實作流程與技術')
    for text in [
        '用 API 取得研究記錄，快取並保留更新日；區分機構地址與試驗執行地點。',
        '用結構化篩選處理研究狀態與地點；對未提供或模糊條件保留未知狀態，不讓模型猜測。',
        '模型產生多語說明與研究團隊詢問清單；保留原始條件供對照。初版用 Streamlit，擴充時再拆成前端與 API。',
    ]: r.bullet(text)
    r.ref('驗證：條件解釋忠實度、招募狀態過期情形、地點正確性、多語回譯與「缺資料不下定論」測試。最終資格由研究團隊核實。')

    r.page('05 / 延伸想法', '穿戴健康與續保支援', '可作後續產品方向；兩份 starter CSV 尚未提供各自需要的核心資料。')
    r.section('Wearable Evidence Lab')
    r.p('定位：幫研發團隊回答「這類感測或穿戴技術如何被驗證？適用哪些族群？還缺哪些量測？」。現有生物感測（PMID 41669754）與生物電子（41058940）題名可作種子，但不是個人穿戴訊號資料。')
    r.bullet('實作：擴充專題檢索，從摘要或可合法取得的全文抽取感測模態、族群、參考標準、驗證方法與限制，由研究者核對。')
    r.bullet('技術：文獻檢索、結構化抽取、欄位驗證與比較表。若要做風險預測，另需時間序列、裝置資訊、結果標籤與適當的受試者層級驗證。')
    r.ref('研究界線：小型文獻集合缺少某技術，不能直接證明研究空白；必須先有可重現的搜尋與篩選策略。')
    r.section('Coverage Guide')
    r.p('定位：將 MassHealth 官方通知與續保步驟轉成可理解的說明、文件清單及需詢問的事項。現有保險變動文獻（PMID 41001595）僅能提供議題線索，不能取代官方規定。')
    r.bullet('實作：先收集最新官方規則、通知範本、語言版本與協助管道；若要判讀個別通知，再加入文件文字擷取與人工確認。')
    r.bullet('技術：文件解析、依版本檢索、規則化待辦與多語說明。個案期限只依通知或官方來源擷取，無明確證據時顯示待確認。')
    r.ref('本文件沒有核定現行續保頻率、期限或資格規則。若採此題，先完成官方政策查證；州政府保留資格決定權。')

    r.page('06 / 技術架構', '先建資料關聯，再加入生成式模型', '小型原型不需要訓練大型模型，也不需要一開始就架設獨立向量資料庫。')
    r.architecture()
    r.ref('流程依 1 到 6 執行；第 3 步的關聯必須從補充的 PMID／DOI 與 institution ID 建立，不是直接合併兩份 CSV。')
    r.table(['資料表', '主要欄位與用途'], [
        ['papers', 'pmid, doi, title, abstract, publication_dates, source_url'],
        ['institutions', 'institution_id, ror, name, city, parent_ids, source_url'],
        ['paper_institutions', 'pmid、institution_id、關聯來源與人工核對狀態'],
        ['evidence_cards', 'paper_id、抽取欄位、支持文字、模型與版本'],
        ['source_snapshots', '來源、查詢條件、抓取時間與原始回應參照'],
    ], [.32, .68])
    r.p('技術選型：Python 處理資料，SQLite 保存小型原型，關鍵字檢索建立基準，embeddings 支援語意相似度，LLM 整理檢索內容，Streamlit 提供操作介面。規模與多人需求確定後，再考慮 FastAPI 與 PostgreSQL。')
    r.ref('工程要求：缺值保留為未知；論文以穩定 ID 去重；多機構論文避免重複計數；API 採快取、分頁、重試，認證與限制依實作時最新文件。[R5]')

    r.page('07 / 研究與驗證', '如何知道原型真的有幫助？', '以下是建議的研究設計與評估方法，不是已完成的產品實驗。')
    r.section('研究過程')
    for text in [
        '1. 問題定義：選定一種使用者與一個任務，訪談目前如何找資料、哪些地方耗時，以及什麼輸出才可採用。',
        '2. 文獻與資料：預先記錄搜尋式、日期、納入排除條件；補齊摘要與機構關聯，保留查不到與有爭議的紀錄。',
        '3. 人工標註：建立一小組代表性問題與相關文獻答案集；由兩位評閱者獨立判定部分樣本，再討論分歧。',
        '4. 方法比較：在同一份候選文獻集上，比較關鍵字、向量、混合檢索；保持問題與評分規則一致。',
        '5. 使用者測試：以相同任務比較既有搜尋方式與原型，觀察時間、錯誤、完成情況與使用者困惑。小型測試用於發現問題，不用來宣稱臨床效益。',
    ]: r.bullet(text)
    r.table(['指標', '計算或判定方式'], [
        ['Precision@5', '前五筆中被人工判為相關的筆數 / 5；固定返回五筆的評估題使用'],
        ['引用支持率', '被引文實際支持的可核驗主張 / 已評閱主張'],
        ['機構配對正確率', '正確的論文機構配對 / 人工抽查配對；另報未匹配比例'],
        ['任務表現', '完成率、完成時間、錯誤與漏項；搭配使用者訪談'],
    ], [.30, .70])
    r.ref('必測案例：沒有摘要、找不到機構、同名機構、多機構論文、來源互相矛盾、過期試驗與語言翻譯改變條件。尚未設定或達成任何成效數字。')

    r.page('08 / 實作與交付', '先完成一條可驗證的使用流程', '時程為小型團隊的規劃參考，需依人力、API 權限與資料品質調整。')
    r.table(['階段', '工作', '可檢查的產出'], [
        ['第 1-2 天', '確認題目、盤點資料、補摘要與日期', '欄位字典、來源記錄、缺資料清單'],
        ['第 3-4 天', '完成書目搜尋與研究卡片', '關鍵字基準與可點回的文獻來源'],
        ['第 5-6 天', '補機構 ID 與論文關聯', '配對結果、未匹配狀態與人工核對'],
        ['第 7-8 天', '比較檢索方法、加入來源約束回答', '評估題、結果與錯誤案例'],
        ['第 9-10 天', '使用者測試、修正介面與示範', '測試紀錄、已知限制與下一版清單'],
    ], [.18, .39, .43])
    r.section('如果只有 48 小時')
    r.p('只做 ResearchBridge 的一條流程：問題輸入、文獻搜尋、來源卡片與經人工核實的少量機構關聯。若摘要或機構匹配未完成，就明示缺資料，將展示停在書目搜尋，不自動補出結論。')
    r.section('交付範圍與完成條件')
    r.bullet('交付：可執行原型、資料字典與來源清單、可重跑的抓取清理腳本、評估結果、示範案例。')
    r.bullet('完成條件：每個機構推薦能追溯到文獻；每個研究結論有支持內容；缺資料時保留未知；人工核對的爭議已處理或明示。')
    r.bullet('後續擴充：先確認 ResearchBridge 的使用價值，再選擇增加 TrialBridge、照護流程，或穿戴技術專題；避免同時擴大所有題目。')

    r.page('09 / 來源與適用範圍', '資料、方法與查證依據', '文件編製日期：2026-10-24。官方連結為本次研究的查證依據；實作前仍應核對最新文件。')
    r.section('本機資料與背景')
    r.p('[D1] pubmed/data.csv、README.md、fetch.py、fetch.js：60 筆書目與資料取得方式。<br/>[D2] openalex/data.csv、README.md、fetch.py、fetch.js：135 筆機構彙總與取得方式。<br/>[D3] 根目錄 README.md，以及使用者提供的六張 Healthcare &amp; biotech 主題截圖。')
    references = [
        ('R1', 'NCBI E-utilities', 'https://www.ncbi.nlm.nih.gov/books/NBK25497/', 'ESearch 查識別碼；EFetch 取完整記錄。欄位可能仍有缺失。'),
        ('R2', 'PubMed Help', 'https://pubmed.ncbi.nlm.nih.gov/help/#pubdate', '出版日期欄位與紙本、電子日期的解讀。'),
        ('R3', 'OpenAlex: Get Singleton', 'https://help.openalex.org/api/get-single-entities/', '用 PMID、DOI 或 OpenAlex ID 查單一作品。'),
        ('R4', 'OpenAlex: Authorships', 'https://help.openalex.org/data/authorships/', '作者、原始 affiliation 與研究機構關聯。'),
        ('R5', 'OpenAlex: Authentication', 'https://help.openalex.org/api/authentication/', '認證、使用預算與分頁限制，以最新文件為準。'),
        ('R6', 'ClinicalTrials.gov API record example', 'https://clinicaltrials.gov/api/v2/studies/NCT02993146', '官方登錄結構範例；不是本提案推薦的試驗。'),
    ]
    for ident, title, url, description in references:
        r.p(f'[{ident}] <b>{escape(title)}</b><br/>{description}<br/><link href="{escape(url, quote=True)}" color="#127C80">{escape(url)}</link>', style=r.small, after=11)
    r.section('閱讀與使用界線')
    r.p('提案、架構、時程與指標為建議設計，尚未完成原型、使用者研究或臨床成效驗證。研究內容需要來源支持；醫療判斷由合格專業人員負責，試驗資格由研究團隊確認，MassHealth 資格由州政府決定。若未來要公開轉載摘要或全文，另核對各來源授權。')
    r.finish()


if __name__ == '__main__':
    main()
