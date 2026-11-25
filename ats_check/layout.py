"""Row roles from page layout: which extracted text row is a role header, a wrapped bullet row or a page footer.

The line-based extractors (poppler, pdfplumber, PDFium, PdfPig) hand over rows with no position. Wording cannot tell
a wrapped bullet row ("November 2026, and has done its SEO...") from a role header; layout can: a wrapped bullet row
starts at the bullet's TEXT indent (right of the margin), a role header starts at the margin, a page footer repeats
at the same height on every page. PyMuPDF's visual rows (geometry.py) are the authority; each extractor row is
projected onto them by its text. A row that cannot be located, a PDF with no usable layout (scan, OCR, columns,
tables) and a layout with no bullet indent (wrapped rows back at the margin) get no role, and the parser keeps its
line-shape behaviour for them."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import fields as fd
from .geometry import Geometry, Line

FOOTER, CONT, BULLET, HEADER, PLAIN, OTHER = "footer", "cont", "bullet", "header", "plain", "other"
AT_MARGIN = (HEADER, PLAIN)   # where a role header can start: a bold row or one with a right-aligned part, or plain text
PAGE_NUMBER = re.compile(r"(?:page\s*)?\d{1,3}(?:\s*(?:/|of)\s*\d{1,3})?|[-–—]\s*\d{1,3}\s*[-–—]", re.I)
INDENT_TOL = 3.0     # pt: closer than this to the margin is "at the margin"; to the bullet's text x is "at the text indent"
SAME_Y_TOL = 3.0     # pt: a footer repeats at this height on the other pages
WINDOW = 80          # rows searched ahead of the last located row before a document-wide search


def _key(text: str) -> str:
    """Letters and digits only, NFKC (ligatures split), lower case: equal across extractors that disagree on
    spacing, bullet glyph, dash, quote and ligature."""
    return "".join(c for c in unicodedata.normalize("NFKC", text).lower() if c.isalnum())


@dataclass
class Row:
    page: int
    y0: float
    y1: float
    x0: float
    text: str
    key: str
    bold: bool          # the row starts in bold
    parts: int          # visual pieces on the row: 2 = a title and a right-aligned date
    text_x: float | None
    role: str = OTHER


@dataclass
class Layout:
    rows: list[Row] = field(default_factory=list)
    margin: float = 0.0
    keys: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return len(self.rows) >= 3

    def classes_for(self, lines: list[str]) -> tuple[list[str | None], float]:
        """One role per extracted row (None: not located, or only a part of a visual row), and the share located."""
        out: list[str | None] = [None] * len(lines)
        cursor, seen, hit = 0, 0, 0
        for n, ln in enumerate(lines):
            k = _key(ln)
            if not k:
                continue
            seen += 1
            j, last, whole = self._locate(k, cursor)
            if j is None:
                continue
            hit += 1
            cursor = last
            if whole:
                out[n] = self.rows[j].role
        return out, (hit / seen if seen else 0.0)

    def _locate(self, k: str, cursor: int) -> tuple[int | None, int, bool]:
        """(first row, last row, whole): the visual rows that hold k, nearest at or after the cursor first. whole: the extractor
        row IS the visual row, or starts it (its head, or a paragraph a joining extractor made of several rows, which takes the
        role of its first row); a part in the middle or at the tail gets no role, as it would be a guess."""
        n = len(self.keys)
        order = list(range(cursor, min(cursor + WINDOW, n))) + [j for j in range(n) if j < cursor or j >= cursor + WINDOW]
        part = None
        for j in order:
            rk = self.keys[j]
            if rk == k or (rk.startswith(k) and len(k) >= 4):
                return j, j, True
            if len(rk) >= 8 and k.startswith(rk):
                last, acc = j, rk
                while last + 1 < n and k.startswith(acc + self.keys[last + 1]) and self.keys[last + 1]:
                    last += 1
                    acc += self.keys[last]
                return j, last, True
            if part is None and len(k) >= 6 and k in rk:
                part = j
        return (part, part, False) if part is not None else (None, 0, False)


def build(g: Geometry) -> Layout | None:
    """The layout of a PDF, or None when its text has no reading order a row projection could rely on."""
    if not g.lines or g.columns or g.tables:
        return None
    rows = _visual_rows(g.lines)
    if len(rows) < 3:
        return None
    L = Layout(rows=rows)
    _classify(L, g)
    L.keys = [r.key for r in rows]
    return L


def _visual_rows(lines: list[Line]) -> list[Row]:
    """Lines on one baseline (a title and its right-aligned date) are one row, left to right; rows run page by page, top down."""
    rows: list[Row] = []
    for pno in sorted({l.page for l in lines}):
        pl = sorted((l for l in lines if l.page == pno), key=lambda l: ((l.y0 + l.y1) / 2, l.x0))
        group: list[Line] = []

        def flush():
            if not group:
                return
            g = sorted(group, key=lambda l: l.x0)
            text = " ".join(l.text for l in g)
            rows.append(Row(pno, min(l.y0 for l in g), max(l.y1 for l in g), g[0].x0, text, _key(text), g[0].lead_bold, len(g), g[0].text_x))
            group.clear()

        for l in pl:
            if group:
                top, bot = min(m.y0 for m in group), max(m.y1 for m in group)
                if min(bot, l.y1) - max(top, l.y0) < 0.5 * min(bot - top, l.y1 - l.y0):
                    flush()
            group.append(l)
        flush()
    return rows


def _classify(L: Layout, g: Geometry) -> None:
    rows = L.rows
    _footers(rows, g)
    bold_x = sorted(r.x0 for r in rows if r.bold and r.parts == 1 and r.role != FOOTER)
    margin = next((x for x in bold_x if sum(abs(y - x) <= INDENT_TOL for y in bold_x) >= 2), None)
    if margin is None:
        plain = [r.x0 for r in rows if r.role != FOOTER and r.text[:1] not in fd.BULLETS]
        margin = min(plain, default=0.0)
    L.margin = margin
    xs = [r.text_x for r in rows if r.text_x is not None]
    doc_text_x = max(set(round(x) for x in xs), key=lambda v: sum(round(x) == v for x in xs)) if xs else None
    text_x: float | None = None
    in_bullet = False
    for r in rows:
        if r.role == FOOTER:
            continue
        if fd.is_bullet(r.text):
            r.role, in_bullet = BULLET, True
            text_x = r.text_x if r.text_x is not None else doc_text_x
            continue
        at_margin = r.x0 - margin <= INDENT_TOL
        if in_bullet and not at_margin and text_x is not None and abs(r.x0 - text_x) <= INDENT_TOL:
            r.role = CONT
            continue
        in_bullet = False
        r.role = (HEADER if r.bold or r.parts > 1 else PLAIN) if at_margin else OTHER


def _footers(rows: list[Row], g: Geometry) -> None:
    """A page number shape that is the first or last row of its page and sits at the same height on another page, or
    anywhere in the header/footer band; a running footer whose text repeats (digits aside) on another page."""
    by_page: dict[int, list[Row]] = {}
    for r in rows:
        by_page.setdefault(r.page, []).append(r)
    edge = {id(r) for rs in by_page.values() for r in (rs[:2] + rs[-2:])}
    in_band = {id(r) for r in rows if _in_band(r, g)}
    shaped = [r for r in rows if PAGE_NUMBER.fullmatch(r.text.strip())]
    for r in shaped:
        repeats = any(o.page != r.page and abs(o.y0 - r.y0) <= SAME_Y_TOL for o in shaped)
        if (id(r) in edge and repeats) or id(r) in in_band:
            r.role = FOOTER
    running: dict[str, set[int]] = {}
    for r in rows:
        if id(r) in in_band:
            running.setdefault(_stem(r), set()).add(r.page)
    for r in rows:
        if id(r) in in_band and len(running[_stem(r)]) >= 2:
            r.role = FOOTER


def _stem(r: Row) -> str:
    """A running footer's text without its page number."""
    return re.sub(r"\d+", "", r.key)


def _in_band(r: Row, g: Geometry) -> bool:
    return r.y1 <= 0.065 * g.page_h or r.y0 >= 0.935 * g.page_h
