"""Layer 1: parse health. Every check -> PASS / WARN / FAIL with evidence and a fix."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from . import extract as ex
from . import fields as fd
from . import geometry as geo

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
LIGATURES = {chr(c) for c in range(0xFB00, 0xFB07)}
CID_RX = re.compile(r"\(cid:\d+\)")
ALLOWED_SYMBOLS = set("•●▪■◦‣∙·–—‘’“”…→©®™°±×")


@dataclass
class Check:
    id: str
    title: str
    status: str
    evidence: list[str] = field(default_factory=list)
    fix: str = ""


@dataclass
class Health:
    checks: list[Check]
    extractions: list[ex.Extraction]
    geometry: geo.Geometry
    parsed: dict[str, fd.Parsed]
    match_view: str            # extractor whose text feeds the matcher
    agreement: dict[str, float]
    openresume: dict | None = None   # the optional OpenResume layer's raw output (ats_check.openresume)

    @property
    def gate_failed(self) -> bool:
        return any(c.status == FAIL for c in self.checks)


def _tok(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _garbage(text: str) -> tuple[float, str]:
    if not text.strip():
        return 0.0, ""
    bad = len(CID_RX.findall(text)) * 7
    for c in text:
        o = ord(c)
        if c == "\ufffd" or (o < 32 and c not in "\n\r\t\f") or 0xE000 <= o <= 0xF8FF:
            bad += 1
    sample = next((l.strip()[:60] for l in text.splitlines() if CID_RX.search(l) or any(
        ord(c) < 32 and c not in "\t\r\f" or c == "\ufffd" or 0xE000 <= ord(c) <= 0xF8FF for c in l)), "")
    return bad / max(len(text), 1), sample


def agreement(oks: list[ex.Extraction]) -> tuple[str, dict[str, float], dict[str, float]]:
    toks = {e.name: _tok(e.text) for e in oks}
    order: dict[tuple[str, str], float] = {}
    names = list(toks)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            order[(a, b)] = SequenceMatcher(None, toks[a], toks[b], autojunk=False).ratio() if toks[a] and toks[b] else 0.0
    mean = {n: (sum(v for k, v in order.items() if n in k) / max(1, len(names) - 1)) for n in names}
    ref = max(names, key=lambda n: (mean[n], n == "pymupdf"))
    vs_ref = {n: (1.0 if n == ref else order.get((ref, n), order.get((n, ref), 0.0))) for n in names}
    return ref, vs_ref, mean


def _agg(per_view: dict[str, bool]) -> str:
    v = list(per_view.values())
    return PASS if all(v) else (FAIL if not any(v) else WARN)


def run(pdf: Path) -> Health:
    exs = ex.run_all(pdf)
    g = geo.analyze(pdf)
    oks = [e for e in exs if e.ok and e.text.strip()]
    checks: list[Check] = []

    # 1 extractors -------------------------------------------------------------
    failed = [e for e in exs if not e.ok]
    if len(oks) < 3:
        checks.append(Check("extractors", "Independent extractors", FAIL,
                            [f"only {len(oks)} of {len(exs)} produced text"] + [f"{e.name}: {e.error}" for e in failed],
                            "Fix the PDF (see other checks) or the local tooling; fewer than 3 views cannot be compared."))
    elif failed:
        checks.append(Check("extractors", "Independent extractors", WARN, [f"{e.name}: {e.error}" for e in failed],
                            "Install the missing extractor for a full comparison (README: filee)."))
    else:
        checks.append(Check("extractors", "Independent extractors", PASS, [f"{len(oks)} extractors ok: " + ", ".join(e.name for e in oks)]))

    # 2 text layer -------------------------------------------------------------
    alpha = {e.name: sum(c.isalpha() for c in e.text) for e in exs if e.ok}
    if not alpha or max(alpha.values()) < 150:
        checks.append(Check("text_layer", "Text layer present", FAIL,
                            [f"max letters extracted by any tool: {max(alpha.values(), default=0)}"],
                            "The PDF has no real text (scan, outlined glyphs or image export). Re-export from the source with embedded fonts."))
    else:
        checks.append(Check("text_layer", "Text layer present", PASS, [f"{max(alpha.values())} letters extracted"]))

    # 3 garbage (ToUnicode / cid) ---------------------------------------------
    bad = []
    for e in exs:
        if e.ok:
            r, sample = _garbage(e.text)
            if r > 0.02:
                bad.append((e.name, r, sample))
    if bad:
        checks.append(Check("tounicode", "Fonts map to real characters (ToUnicode)", FAIL,
                            [f"{n}: {r:.0%} of output is control/private-use/(cid:N) junk, e.g. {s!r}" for n, r, s in bad],
                            "A font lacks a ToUnicode map, so parsers read glyph IDs not letters. Re-export with a standard font (embed TrueType/OpenType with Unicode cmap)."))
    else:
        checks.append(Check("tounicode", "Fonts map to real characters (ToUnicode)", PASS))

    # 4 ligatures --------------------------------------------------------------
    lig = {}
    for e in exs:
        if e.ok:
            hit = [w for w in re.findall(r"\S*[" + "".join(LIGATURES) + r"]\S*", e.text)]
            if hit:
                lig[e.name] = hit
    if lig:
        ev = [f"{n}: {len(h)} words contain ligature codepoints, e.g. {h[0]!r}" for n, h in lig.items()]
        checks.append(Check("ligatures", "No ligature codepoints in extracted text", WARN, ev,
                            "Keyword search for 'workflow' misses 'workﬂow'. Turn ligatures off in the typesetter (typst: ligatures: false; LaTeX: \\usepackage{microtype}/disable fi ligature)."))
    else:
        checks.append(Check("ligatures", "No ligature codepoints in extracted text", PASS))

    # 5 icon glyphs ------------------------------------------------------------
    icons = Counter()
    for e in oks:
        for c in e.text:
            if ord(c) > 127 and c not in ALLOWED_SYMBOLS and c not in LIGATURES and unicodedata.category(c) in ("So", "Sk", "Co", "Cn"):
                icons[c] += 1
    if icons:
        checks.append(Check("icons", "No icon / symbol glyphs in text", WARN,
                            [f"symbols in text: {''.join(sorted(icons))!r}"],
                            "Icons (envelope, phone, emoji) can become garbage or vanish. Replace with plain words ('Email:', 'Phone:') or drop them."))
    else:
        checks.append(Check("icons", "No icon / symbol glyphs in text", PASS))

    # 6 reading order + layout ---------------------------------------------------
    ref, vs_ref, mean = ("", {}, {})
    if len(oks) >= 2:
        ref, vs_ref, mean = agreement(oks)
    low = {n: round(v, 2) for n, v in vs_ref.items() if v < 0.90}
    ev = [f"reading-order agreement vs consensus '{ref}': " + ", ".join(f"{n} {v:.2f}" for n, v in vs_ref.items())] if vs_ref else []
    col_ev = [f"page {c['page']}: text gutter at x={c['x']}pt across {c['lines']} lines" for c in g.columns]
    tab_ev = [f"page {t['page']}: ruled table {t['rows']}x{t['cols']}" for t in g.tables]
    if g.columns:
        st = FAIL if low else WARN
        checks.append(Check("columns", "Single-column reading order", st, ev + col_ev,
                            "Two-column text is read across the gutter by some parsers. Use one column; keep a sidebar's content in the main flow."))
    else:
        checks.append(Check("columns", "Single-column reading order", PASS, ["no repeated text gutter found"]))
    if g.tables:
        st = FAIL if low else WARN
        checks.append(Check("tables", "No layout tables", st, ev + tab_ev,
                            "Table cells are linearised unpredictably (dates detach from titles). Replace the table with plain lines: 'Title, Company  dates' then bullets."))
    else:
        checks.append(Check("tables", "No layout tables", PASS))
    if low and not g.columns and not g.tables:
        checks.append(Check("reading_order", "Extractors agree on reading order", WARN, ev + [f"diverging: {low}"],
                            "Text order differs between parsers; inspect report.json extraction diffs."))
    elif vs_ref:
        checks.append(Check("reading_order", "Extractors agree on reading order", PASS, ev))

    # words missing in one extractor ---------------------------------------------
    if len(oks) >= 3:
        bags = {e.name: set(w for w in _tok(e.text) if w.isalpha() and len(w) >= 4) for e in oks}
        common = Counter(w for b in bags.values() for w in b)
        missing = {n: sorted(w for w, c in common.items() if c >= len(oks) - 1 and w not in b)[:6] for n, b in bags.items()}
        missing = {n: m for n, m in missing.items() if len(m) >= 3}
        if missing and not any(c.id in ("tounicode",) and c.status == FAIL for c in checks):
            checks.append(Check("chars_lost", "No words lost by one extractor", WARN,
                                [f"{n} lacks words the others have: {m}" for n, m in missing.items()],
                                "A tool dropped or mangled words (font or encoding issue)."))
        else:
            checks.append(Check("chars_lost", "No words lost by one extractor", PASS))

    # 7 images -----------------------------------------------------------------
    imgs = [i for i in g.images if i["area_frac"] >= 0.02]
    big_empty = [i for i in imgs if i["words_inside"] < 3]
    if big_empty:
        checks.append(Check("images", "No content locked in images", FAIL,
                            [f"page {i['page']}: image covers {i['area_frac']:.1%} of the page with no text layer"
                             + (f"; OCR reads: {i['ocr']!r}" if i["ocr"] else "") for i in big_empty],
                            "Text inside an image is invisible to parsers (only an OCR pipeline would read it). Put it back as real text."))
    elif g.images:
        checks.append(Check("images", "No content locked in images", WARN, [f"{len(g.images)} image(s) present; decorative?"], "Remove decorative images."))
    else:
        checks.append(Check("images", "No content locked in images", PASS))

    # 8 header / footer -------------------------------------------------------------
    hf_text = [l.text for l in g.header_lines + g.footer_lines]
    body_text = " ".join(l.text for l in g.lines if l not in g.header_lines and l not in g.footer_lines)
    hf_contact = [t for t in hf_text if geo.CONTACT_RX.search(t)]
    if hf_contact and not fd.EMAIL.search(body_text) and not fd.PHONE.search(body_text):
        checks.append(Check("header_footer", "Contact info is in the page body", FAIL,
                            [f"contact only in page header/footer band: {t[:70]!r}" for t in hf_contact],
                            "Many parsers drop header/footer text. Move name, email and phone into the first lines of the body."))
    elif hf_text and (g.pages > 1 or hf_contact):
        checks.append(Check("header_footer", "Contact info is in the page body", WARN,
                            [f"text in header/footer band: {t[:70]!r}" for t in hf_text[:3]],
                            "Header/footer text may be ignored; keep nothing important there."))
    else:
        checks.append(Check("header_footer", "Contact info is in the page body", PASS))

    # 9+ field checks on every view -------------------------------------------------
    junk = {n for n, _, _ in bad}
    parsed = {e.name: fd.parse(e.text, g.style_headings) for e in oks if e.name not in junk}
    if parsed:
        checks += _field_checks(parsed)
    # a table whose cells scramble job entries is a failure, not a style note
    by = {c.id: c for c in checks}
    if "tables" in by and by["tables"].status == WARN and "entries" in by and by["entries"].status != PASS:
        by["tables"].status = FAIL
        by["tables"].evidence.append("entry fields broke under at least one extractor (see entries)")
    clean_oks = [e for e in oks if e.name not in junk]
    match_view = ref if ref in {e.name for e in clean_oks} else (clean_oks[0].name if clean_oks else "")
    from . import openresume as orl          # optional layer; imported here because openresume imports Check from this module
    ref_text = next((e.text for e in clean_oks if e.name == match_view), "")
    or_checks, or_raw = orl.checks(pdf, ref_text, parsed.get(match_view)) if ref_text else ([], None)
    checks += or_checks
    H = Health(checks, exs, g, parsed, match_view, vs_ref)
    H.openresume = or_raw
    return H


def _field_checks(parsed: dict[str, fd.Parsed]) -> list[Check]:
    out: list[Check] = []
    n = len(parsed)

    def agg(label, pred, fix, ev_fn=None, soft=False):
        per = {k: bool(pred(p)) for k, p in parsed.items()}
        st = _agg(per)
        if soft and st == FAIL:
            st = WARN
        ev = [f"parsed under {sum(per.values())}/{n} extractors"] if st != PASS else []
        if st != PASS and ev_fn:
            ev += ev_fn()
        return Check(label[0], label[1], st, ev, fix if st != PASS else "")

    out.append(agg(("name", "Name found"), lambda p: p.name, "Put your full name alone on the first line.", soft=True))
    out.append(agg(("email", "Email found"), lambda p: p.email, "Put a plain-text email in the first lines of the body."))
    out.append(agg(("phone", "Phone found"), lambda p: p.phone, "Add a phone as (415) 555-0142 in the contact line.", soft=True))
    out.append(agg(("location", "Location found"), lambda p: p.location, "Add 'City, ST' to the contact line (location filters).", soft=True))
    out.append(agg(("sec_experience", "Experience section recognised"), lambda p: p.section("experience") and p.entries,
                   "Rename the heading to 'Experience' or 'Work Experience'.",
                   lambda: ["headings seen: " + ", ".join(sorted({s.title for p in parsed.values() for s in p.sections}))]))
    out.append(agg(("sec_education", "Education section recognised"), lambda p: p.section("education") and p.education,
                   "Add an 'Education' heading with degree and school (or ignore if the role has no degree requirement).", soft=True))
    out.append(agg(("sec_skills", "Skills section has text"), lambda p: p.section("skills") and len(p.skills) >= 3,
                   "Give Skills a heading and plain comma-separated text, not an image or table."))

    # unknown headings
    unknown = sorted({s.title for p in parsed.values() for s in p.sections if s.canon == "other"})
    if unknown:
        out.append(Check("headings", "Standard section headings", WARN, [f"non-standard: {', '.join(unknown)}"],
                         "Parsers map headings to Experience/Education/Skills by keyword; rename or merge: 'Projects', 'Experience', 'Skills'."))
    else:
        out.append(Check("headings", "Standard section headings", PASS))

    # experience entries (judge by the view with most entries; report fragility)
    def entry_state(p: fd.Parsed):
        if not p.entries:
            return None
        return [(e.title, e.company, e.dates_ok, e.dates_problem) for e in p.entries]

    per_view = {k: entry_state(p) for k, p in parsed.items()}
    any_entries = [v for v in per_view.values() if v]
    if not any_entries:
        out.append(Check("entries", "Each job has title, company and parseable dates", FAIL,
                         ["no experience entries could be parsed"], "Use 'Title, Company  Mon YYYY – Mon YYYY' lines under Experience."))
    else:
        probs = []
        for k, p in parsed.items():
            for e in p.entries:
                if not e.title and not e.company:
                    probs.append((FAIL, f"{k}: no title/company in '{e.header[:50]}'"))
                elif not e.title:
                    probs.append((WARN, f"{k}: no job title recognised in '{e.header[:50]}'"))
                elif not e.company:
                    probs.append((WARN, f"{k}: no company recognised in '{e.header[:50]}'"))
                elif fd.looks_like_location(e.company):
                    probs.append((WARN, f"{k}: company '{e.company[:40]}' looks like a location fragment in '{e.header[:50]}'"))
                if e.dates_problem and not e.dates_ok:
                    probs.append((FAIL, f"{k}: '{e.header[:40]}' -> {e.dates_problem}"))
                elif e.dates_problem:
                    probs.append((WARN, f"{k}: '{e.header[:40]}' -> {e.dates_problem}"))
        # dedupe by message minus view
        uniq = {}
        for st, m in probs:
            uniq.setdefault(m.split(": ", 1)[1], (st, m.split(": ", 1)[0]))
        counts = {k: len(p.entries) for k, p in parsed.items()}
        if not uniq:
            out.append(Check("entries", "Each job has title, company and parseable dates", PASS,
                             [f"{max(counts.values())} entries, all fields parsed"]))
        else:
            worst = FAIL if any(s == FAIL for s, _ in uniq.values()) else WARN
            out.append(Check("entries", "Each job has title, company and parseable dates", worst,
                             [f"{m} (seen in {v})" for m, (s, v) in list(uniq.items())[:6]],
                             "Write dates as 'Mon YYYY – Mon YYYY' or 'Mon YYYY – Present' (no seasons, no 'YY); put title and company on one line."))
    # fragility across views: always a check (a fixed denominator), WARN when any view loses or gains an entry
    sig = {k: len(p.entries) for k, p in parsed.items()}
    if len(set(sig.values())) > 1:
        out.append(Check("entries_fragile", "Entry count identical under every extractor", WARN,
                         [f"entries per extractor: {sig}; a role header glued to the previous bullet makes a job vanish in that view"],
                         "Layout makes entries parse differently per tool: put a blank line or spacing before each role header and keep each header on its own line."))
        e = next((c for c in out if c.id == "entries"), None)
        if e and e.status == PASS:
            e.status = WARN
            e.evidence.append(f"entry count differs between extractors: {sig}")
            e.fix = e.fix or "See Entry count identical under every extractor."
    else:
        out.append(Check("entries_fragile", "Entry count identical under every extractor", PASS, [f"{max(sig.values(), default=0)} entries in every view"]))
    return out
