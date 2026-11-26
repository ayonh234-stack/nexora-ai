"""Read uploaded documents and generate downloadable PDF / DOCX / XLSX / CSV / TXT files (Bengali-safe)."""

from __future__ import annotations

import csv
import io
import logging
import os
import re

logger = logging.getLogger(__name__)
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "txt": "text/plain",
    "md": "text/markdown",
}
READABLE = (".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md", ".json", ".html", ".htm", ".tsv", ".log")


# ---------------------------------------------------------------- reading
def extract_text(data: bytes, filename: str, max_chars: int = 120_000) -> str:
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf") or data[:5] == b"%PDF-":
            from pypdf import PdfReader

            r = PdfReader(io.BytesIO(data))
            pages = []
            for i, p in enumerate(r.pages[:200]):
                t = (p.extract_text() or "").strip()
                if t:
                    pages.append(f"[Page {i + 1}]\n{t}")
                if sum(len(x) for x in pages) > max_chars:
                    break
            text = "\n\n".join(pages)
            if not text.strip():
                text = "[This PDF has no selectable text — it is probably scanned images.]"
        elif name.endswith(".docx"):
            import docx

            d = docx.Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for row in t.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            text = "\n".join(parts)
        elif name.endswith((".xlsx", ".xlsm")):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets[:10]:
                parts.append(f"## Sheet: {ws.title}")
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i >= 2000:
                        parts.append("… (more rows)"); break
                    if any(v is not None for v in row):
                        parts.append(" | ".join("" if v is None else str(v) for v in row))
            text = "\n".join(parts)
        else:
            for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
                try:
                    text = data.decode(enc); break
                except Exception:
                    continue
            if name.endswith((".html", ".htm")):
                from sglbot.websearch import _readable

                text = _readable(text)[1]
    except Exception as exc:
        logger.warning("extract_text failed for %s: %s", filename, exc)
        return f"[Could not read this file: {type(exc).__name__}]"
    text = re.sub(r"\n{3,}", "\n\n", text or "")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… [truncated]"
    return text


# ---------------------------------------------------------------- writing
def _safe_name(title: str, ext: str) -> str:
    base = re.sub(r"[^\w\u0980-\u09FF -]+", "", title or "").strip().replace(" ", "-")[:60] or "nexora"
    return f"{base}.{ext}"


def _md_lines(content: str):
    """Very small Markdown subset → (kind, text) lines."""
    for raw in (content or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            yield ("blank", ""); continue
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            yield (f"h{min(len(m.group(1)), 3)}", m.group(2).strip()); continue
        m = re.match(r"^\s*[-*•]\s+(.*)", line)
        if m:
            yield ("bullet", m.group(1)); continue
        m = re.match(r"^\s*(\d+)[.)]\s+(.*)", line)
        if m:
            yield ("num", f"{m.group(1)}. {m.group(2)}"); continue
        if re.match(r"^\s*\|.*\|\s*$", line):
            if re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
                continue
            yield ("row", line); continue
        yield ("p", line)


def _plain(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*|__(.+?)__|`(.+?)`", lambda m: m.group(1) or m.group(2) or m.group(3), s)


def make_pdf(title: str, content: str, rows: list[list] | None = None) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_margins(16, 16, 16)
    for style, f in (("", "HindSiliguri-Regular.ttf"), ("B", "HindSiliguri-Bold.ttf")):
        pdf.add_font("Hind", style, os.path.join(FONT_DIR, f))
    try:
        pdf.set_text_shaping(True)  # HarfBuzz: correct Bengali conjuncts and vowel signs
    except Exception as exc:
        logger.warning("text shaping unavailable: %s", exc)
    pdf.add_page()
    w = pdf.epw
    if title:
        pdf.set_font("Hind", "B", 20)
        pdf.multi_cell(w, 10, _plain(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(3)
    for kind, text in _md_lines(content):
        text = _plain(text)
        if kind == "blank":
            pdf.ln(3); continue
        if kind in ("h1", "h2", "h3"):
            pdf.ln(2); pdf.set_font("Hind", "B", {"h1": 17, "h2": 15, "h3": 13}[kind])
            pdf.multi_cell(w, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT); continue
        pdf.set_font("Hind", "", 11.5)
        if kind == "bullet":
            pdf.multi_cell(w, 6.5, "•  " + text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif kind == "row":
            cells = [c.strip() for c in text.strip().strip("|").split("|")]
            pdf.multi_cell(w, 6.5, "   |   ".join(cells), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.multi_cell(w, 6.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if rows:
        pdf.ln(4); pdf.set_font("Hind", "", 9.5)
        cols = max(len(r) for r in rows)
        with pdf.table(col_widths=tuple([1] * cols), text_align="LEFT", line_height=5.5) as table:
            for i, r in enumerate(rows[:500]):
                row = table.row()
                for c in list(r) + [""] * (cols - len(r)):
                    row.cell(str(c if c is not None else "")[:300])
    return bytes(pdf.output())


def make_docx(title: str, content: str, rows: list[list] | None = None) -> bytes:
    import docx
    from docx.oxml.ns import qn
    from docx.shared import Pt

    d = docx.Document()
    st = d.styles["Normal"]; st.font.name = "Nirmala UI"; st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:cs"), "Nirmala UI")
    if title:
        d.add_heading(_plain(title), 0)
    table_rows: list[list[str]] = []

    def flush():
        if table_rows:
            cols = max(len(r) for r in table_rows)
            t = d.add_table(rows=0, cols=cols); t.style = "Table Grid"
            for r in table_rows:
                cells = t.add_row().cells
                for i, v in enumerate(r):
                    cells[i].text = v
            table_rows.clear()

    for kind, text in _md_lines(content):
        if kind == "row":
            table_rows.append([_plain(c.strip()) for c in text.strip().strip("|").split("|")]); continue
        flush()
        text = _plain(text)
        if kind == "blank":
            continue
        if kind in ("h1", "h2", "h3"):
            d.add_heading(text, int(kind[1]))
        elif kind == "bullet":
            d.add_paragraph(text, style="List Bullet")
        elif kind == "num":
            d.add_paragraph(text.split(". ", 1)[-1], style="List Number")
        else:
            d.add_paragraph(text)
    flush()
    if rows:
        cols = max(len(r) for r in rows)
        t = d.add_table(rows=0, cols=cols); t.style = "Table Grid"
        for r in rows[:2000]:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = "" if v is None else str(v)
    out = io.BytesIO(); d.save(out)
    return out.getvalue()


def make_xlsx(title: str, rows: list[list], content: str = "") -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    if not rows and content:
        rows = [[c.strip() for c in line.strip().strip("|").split("|")]
                for k, line in _md_lines(content) if k == "row"] or [[line] for k, line in _md_lines(content) if k != "blank"]
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = (re.sub(r"[\[\]:*?/\\]", "", title or "Sheet") or "Sheet")[:31]
    for r in rows[:20000]:
        ws.append(["" if v is None else v for v in r])
    if rows:
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="10A37F")
            c.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"
        for i in range(1, max(len(r) for r in rows) + 1):
            width = max(len(str(ws.cell(row=j, column=i).value or "")) for j in range(1, min(ws.max_row, 200) + 1))
            ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, width + 2))
    out = io.BytesIO(); wb.save(out)
    return out.getvalue()


def make_csv(rows: list[list]) -> bytes:
    buf = io.StringIO(); w = csv.writer(buf)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel shows Bengali correctly


def make_file(fmt: str, title: str, content: str = "", rows: list[list] | None = None) -> tuple[bytes, str, str]:
    """(bytes, filename, mime)"""
    fmt = (fmt or "pdf").lower().lstrip(".")
    fmt = {"excel": "xlsx", "xls": "xlsx", "word": "docx", "doc": "docx", "text": "txt", "markdown": "md"}.get(fmt, fmt)
    if fmt == "pdf":
        data = make_pdf(title, content, rows)
    elif fmt == "docx":
        data = make_docx(title, content, rows)
    elif fmt == "xlsx":
        data = make_xlsx(title, rows or [], content)
    elif fmt == "csv":
        if not rows and content:
            rows = [[c.strip() for c in line.strip().strip("|").split("|")] for k, line in _md_lines(content) if k == "row"]
        data = make_csv(rows or [])
    else:
        fmt = "md" if fmt == "md" else "txt"
        data = ((f"# {title}\n\n" if title and fmt == "md" else (title + "\n\n" if title else "")) + (content or "")).encode("utf-8")
    return data, _safe_name(title, fmt), MIME[fmt]
