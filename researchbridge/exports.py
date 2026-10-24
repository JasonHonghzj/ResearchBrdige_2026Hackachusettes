"""Portable CSV, standalone HTML and paginated PDFs using embedded CJK fonts."""
from __future__ import annotations
import csv
from functools import lru_cache
from html import escape
import io
from pathlib import Path
import re
import unicodedata


def _text(value):
    # Keep exported spreadsheet strings literal, including user-authored goals.
    return str(value) if value is not None else ""


def csv_bytes(rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out,fieldnames=keys)
    writer.writeheader()
    for row in rows:
        safe = {}
        for k,v in row.items():
            value = _text(v)
            safe[k] = "'"+value if value.lstrip().startswith(("=","+","-","@")) else value
        writer.writerow(safe)
    return out.getvalue().encode("utf-8-sig")


def html_bytes(title, sections, lang="zh"):
    body = "".join("<section><h2>"+escape(s["heading"])+"</h2>"+"".join("<p>"+escape(p)+"</p>" for p in s["paragraphs"])+"</section>" for s in sections)
    return ("<!doctype html><html lang='"+{"zh":"zh-Hant","en":"en","es":"es"}[lang]+"'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"+escape(title)+"</title><style>body{font:16px/1.75 system-ui,'Microsoft JhengHei',sans-serif;color:#142e43;background:#f6f8fb;margin:0}main{max-width:940px;margin:30px auto;background:white;padding:36px;border:1px solid #dce5ed;border-radius:12px}h1{font-size:28px}h2{font-size:19px;color:#087f8c;border-top:1px solid #dce5ed;padding-top:20px}p{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#526b7d}@media print{body{background:white}main{border:0;margin:0;padding:0}h2{break-after:avoid}p{orphans:3;widows:3}}@media(max-width:600px){main{margin:0;padding:20px}}</style><main><small>RESEARCHBRIDGE / RESEARCH EXPORT</small><h1>"+escape(title)+"</h1>"+body+"</main></html>").encode("utf-8")


@lru_cache(maxsize=1)
def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    normal,bold = Path("C:/Windows/Fonts/msjh.ttc"),Path("C:/Windows/Fonts/msjhbd.ttc")
    if not normal.exists():
        raise RuntimeError("PDF export requires the Microsoft JhengHei fonts used by this Windows project.")
    pdfmetrics.registerFont(TTFont("RBExport",str(normal),subfontIndex=0))
    pdfmetrics.registerFont(TTFont("RBExportBold",str(bold),subfontIndex=0))
    pdfmetrics.registerFontFamily("RBExport",normal="RBExport",bold="RBExportBold",italic="RBExport",boldItalic="RBExportBold")
    return "RBExport","RBExportBold"


def pdf_bytes(title, sections, lang="zh"):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    normal,bold = _fonts()
    out = io.BytesIO()
    doc = SimpleDocTemplate(out,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=52,bottomMargin=48,title=title,author="ResearchBridge",pageCompression=1)
    body = ParagraphStyle("body",fontName=normal,fontSize=9.3,leading=15.5,textColor=colors.HexColor("#243b4b"),wordWrap="CJK",splitLongWords=True,spaceAfter=8)
    heading = ParagraphStyle("heading",parent=body,fontName=bold,fontSize=13,leading=20,textColor=colors.HexColor("#087f8c"),spaceBefore=14,spaceAfter=9,keepWithNext=True)
    hero = ParagraphStyle("title",parent=heading,fontSize=22,leading=29,textColor=colors.HexColor("#142e43"),spaceBefore=0,spaceAfter=16)
    def p(text, style):
        text = re.sub(r"[\u2010-\u2015\u2212]","-",unicodedata.normalize("NFC",text))
        return Paragraph(escape(text).replace("\n","<br/>"),style)
    story = [p(title,hero)]
    for section in sections:
        story.append(p(section["heading"],heading))
        for paragraph in section["paragraphs"]:
            if paragraph:
                story.append(p(paragraph,body))
        story.append(Spacer(1,3))
    def footer(canvas,document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dce5ed"))
        canvas.line(44,36,A4[0]-44,36)
        canvas.setFont(normal,8)
        canvas.setFillColor(colors.HexColor("#526b7d"))
        canvas.drawString(44,23,"ResearchBridge | "+{"zh":"研究探索匯出","en":"Research export","es":"Exportación de investigación"}[lang])
        canvas.drawRightString(A4[0]-44,23,str(document.page))
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()


def export_bytes(title, sections, rows, file_format="csv", lang="zh"):
    if file_format == "csv":
        return csv_bytes(rows),"text/csv"
    if file_format == "html":
        return html_bytes(title,sections,lang),"text/html"
    if file_format == "pdf":
        return pdf_bytes(title,sections,lang),"application/pdf"
    raise ValueError("Unsupported export format")
