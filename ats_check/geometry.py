"""Layout facts from PyMuPDF: columns, tables, images, header/footer bands, heading styles."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .fields import BULLETS

DATE_ONLY = re.compile(r"^[\s\d/\-–—.,A-Za-z']{0,40}$")
RANGE_RX = re.compile(r"(\d{4}|present|current|now)\s*$", re.I)
RANGE_FULL = re.compile(r"^[A-Za-z]{0,9}\.?\s*[\d'/]{0,4}\s*[–—-]\s*[A-Za-z]{0,9}\.?\s*[\d'/]{0,4}$|^[A-Za-z]{3,9}\.?\s*\d{4}\s*[–—-]\s*([A-Za-z]{3,9}\.?\s*\d{4}|present|current)$|^\d{4}\s*[–—-]\s*(\d{4}|present)$", re.I)
CONTACT_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|linkedin\.com|github\.com", re.I)


@dataclass
class Line:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float
    bold: bool
    words: list = field(default_factory=list)  # (x0, x1, text)
    lead_bold: bool = False      # the first span is bold ("*Title*, Company": a role header whose company is not)
    text_x: float | None = None  # x of the first word after a leading bullet marker (None: no marker, or glued to the word)


@dataclass
class Geometry:
    pages: int = 0
    page_w: float = 612.0
    page_h: float = 792.0
    lines: list[Line] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)   # {page, x, lines}
    tables: list[dict] = field(default_factory=list)    # {page, rows, cols, words}
    images: list[dict] = field(default_factory=list)    # {page, area_frac, words_inside, ocr}
    header_lines: list[Line] = field(default_factory=list)
    footer_lines: list[Line] = field(default_factory=list)
    body_size: float = 10.0
    style_headings: set[str] = field(default_factory=set)


def _is_bold(span) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower() or "black" in span["font"].lower()


def _text_x(text: str, bbox, page_words) -> float | None:
    """Where a bullet's text starts: x of the first word after the marker. None for a row with no marker, or a marker
    glued to its word ('•Built'), where no indent can be read."""
    if not (text[:1] in BULLETS and text[1:2] in ("", " ", "\t")):
        return None
    x0, y0, x1, y1 = bbox
    ws = sorted((w for w in page_words if y0 <= (w[1] + w[3]) / 2 <= y1 and x0 - 1 <= w[0] <= x1 + 1), key=lambda w: w[0])
    if len(ws) >= 2 and ws[0][4] in BULLETS:
        return ws[1][0]
    return None


def _ocr(page, rect) -> str:
    exe = shutil.which("tesseract")
    if not exe:
        return ""
    try:
        pix = page.get_pixmap(clip=rect, dpi=200)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "i.png"
            pix.save(f)
            r = subprocess.run([exe, str(f), "-", "--psm", "6"], capture_output=True, text=True, timeout=60)
            return " ".join(r.stdout.split())[:300]
    except Exception:
        return ""


def analyze(pdf: Path) -> Geometry:
    g = Geometry()
    with pymupdf.open(pdf) as doc:
        g.pages = len(doc)
        for pno, page in enumerate(doc):
            g.page_w, g.page_h = page.rect.width, page.rect.height
            page_words = page.get_text("words")
            for b in page.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    spans = [s for s in l["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in l["spans"]).strip()
                    x0, y0, x1, y1 = l["bbox"]
                    g.lines.append(Line(pno, x0, y0, x1, y1, text, max(s["size"] for s in spans),
                                        all(_is_bold(s) for s in spans),
                                        [(s["bbox"][0], s["bbox"][2], s["text"]) for s in spans],
                                        _is_bold(spans[0]), _text_x(text, (x0, y0, x1, y1), page_words)))
            # images
            page_area = page.rect.width * page.rect.height
            for im in page.get_image_info():
                r = pymupdf.Rect(im["bbox"]) & page.rect
                frac = r.get_area() / page_area
                if frac < 0.005:
                    continue
                inside = [w for w in page.get_text("words") if r.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))]
                g.images.append({"page": pno + 1, "area_frac": round(frac, 3), "words_inside": len(inside),
                                 "ocr": _ocr(page, r) if len(inside) < 3 else ""})
            # tables: ruled grid = >=2 vertical + >=2 horizontal stroke segments forming a box
            # (PyMuPDF find_tables gave false positives on plain section rules, so own check)
            hs, vs = [], []
            for dr in page.get_drawings():
                for it in dr["items"]:
                    if it[0] == "l":
                        p1, p2 = it[1], it[2]
                        if abs(p1.y - p2.y) < 1 and abs(p1.x - p2.x) > 15:
                            hs.append((p1.y, min(p1.x, p2.x), max(p1.x, p2.x)))
                        elif abs(p1.x - p2.x) < 1 and abs(p1.y - p2.y) > 15:
                            vs.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))
                    elif it[0] == "re":
                        r = it[1]
                        if r.width < 1.5 and r.height > 15:
                            vs.append((r.x0, r.y0, r.y1))
                        elif r.height < 1.5 and r.width > 15:
                            hs.append((r.y0, r.x0, r.x1))
            if len({round(v[0]) for v in vs}) >= 2 and len({round(h[0]) for h in hs}) >= 2:
                g.tables.append({"page": pno + 1, "rows": len({round(h[0]) for h in hs}) - 1,
                                 "cols": len({round(v[0]) for v in vs}) - 1,
                                 "words": len(page.get_text("words"))})
    sizes = sorted(l.size for l in g.lines)
    if sizes:
        g.body_size = sizes[len(sizes) // 2]
    _columns(g)
    _bands(g)
    _style_headings(g)
    return g


def _columns(g: Geometry):
    """A gutter: >=6% page width gap inside a line with >=20 chars on both sides, repeated at one x."""
    gutters: dict[int, list[float]] = {}
    for l in g.lines:
        ws = sorted(l.words)
        if len(ws) < 2:
            continue
        for i in range(len(ws) - 1):
            gap = ws[i + 1][0] - ws[i][1]
            if gap < 0.06 * g.page_w:
                continue
            left = "".join(w[2] for w in ws[: i + 1]).strip()
            right = "".join(w[2] for w in ws[i + 1:]).strip()
            if len(left) < 20 or len(right) < 20:
                continue
            gutters.setdefault(l.page, []).append((ws[i][1] + ws[i + 1][0]) / 2)
    # also: separate blocks side by side (a column's wrapped lines are single-span lines)
    by_page: dict[int, list[Line]] = {}
    for l in g.lines:
        by_page.setdefault(l.page, []).append(l)
    for pno, ls in by_page.items():
        for l in ls:
            if len(l.text) < 10:
                continue
            for m in ls:
                if m is l or len(m.text) < 10 or m.x0 <= l.x1 + 0.03 * g.page_w or RANGE_FULL.match(m.text.strip()):
                    continue
                if min(l.y1, m.y1) - max(l.y0, m.y0) > 0.5 * (l.y1 - l.y0):
                    gutters.setdefault(pno, []).append((l.x1 + m.x0) / 2)
    for pno, xs in gutters.items():
        xs.sort()
        cluster = [xs[0]]
        for x in xs[1:] + [1e9]:
            if x - cluster[-1] > 15:
                if len(cluster) >= 5:
                    g.columns.append({"page": pno + 1, "x": round(sum(cluster) / len(cluster)), "lines": len(cluster)})
                cluster = [x]
            else:
                cluster.append(x)


def _bands(g: Geometry):
    top, bot = 0.065 * g.page_h, 0.935 * g.page_h
    for l in g.lines:
        if l.y1 <= top:
            g.header_lines.append(l)
        elif l.y0 >= bot:
            g.footer_lines.append(l)


def _style_headings(g: Geometry):
    for i, l in enumerate(g.lines):
        t = l.text.strip()
        if i < 2 or not t or len(t.split()) > 5 or any(c in t for c in ",·|:;•") or re.search(r"\d", t):
            continue
        if l.bold and l.size <= 1.35 * g.body_size:
            g.style_headings.add(t)
