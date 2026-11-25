"""Header vs wrapped bullet row vs page footer, decided from page layout (ats_check/layout.py), on PDFs that put each
shape of the review of the first fix (PR #4) in real layout. Synthetic Jane Example text; tests/make_fixtures.py builds them."""
from pathlib import Path

import pytest

from ats_check import extract as ex
from ats_check import fields as fd
from ats_check import geometry as geo
from ats_check import health, layout
from ats_check import jd_reqs as jr
from ats_check import match as m
from ats_check.health import FAIL, PASS, WARN

FIX = Path(__file__).parent / "fixtures"
TITLES = ["Senior AI Engineer", "iOS Engineer", "Software Engineer", "macOS Engineer", "Mobile Engineer", "Software Engineer", "Senior Software Engineer"]
BULLETS = [10, 2, 2, 2, 1, 1, 1]


def status(h, cid):
    return next(c.status for c in h.checks if c.id == cid)


def check(h, cid):
    return next(c for c in h.checks if c.id == cid)


def rows(name):
    g = geo.analyze(FIX / f"{name}.pdf")
    return layout.build(g).rows


def role_of(rs, start):
    return next(r.role for r in rs if r.text.startswith(start))


# ---- every wrapped-row shape of the review, in one resume --------------------------------------------------------

def test_every_wrapped_row_shape_stays_inside_its_bullet_under_every_extractor(run_health):
    """Wrapped rows ending in a date or a date range, starting with a month or lowercase, 'Acme Inc.' and ':' wraps, 'Product owner in
    Mar 2019', a short undated tail and a bare '2' (SOC / 2), next to lowercase-brand, 'macOS', date-first and long single-date
    headers and a header whose date row ends in '| remote': seven jobs in every view, with the bullets the layout shows."""
    h = run_health("wrap_shapes")
    assert len(h.parsed) == 6
    for view, p in h.parsed.items():
        assert [e.title for e in p.entries] == TITLES, view
        assert [e.bullets for e in p.entries] == BULLETS, view
        assert [e.layout in layout.AT_MARGIN for e in p.entries] == [True] * 7, view   # each header row was placed at the margin
        assert (p.entries[4].start, p.entries[4].end) == ("2008", "2013"), view         # '2008 – 2013 | remote' stays the Mobile Engineer's, not the job before it's
    assert status(h, "entries_fragile") == PASS and not h.gate_failed


def test_the_one_remaining_entry_note_is_the_real_single_date_header(run_health):
    """'Mar 2010  Senior Software Engineer, ... Inc.' has one date and a full stop at its end: still a job, still flagged, not a FAIL."""
    c = check(run_health("wrap_shapes"), "entries")
    assert c.status == WARN and len(c.evidence) == 1 and "single date, no range" in c.evidence[0] and "Mar 2010" in c.evidence[0]


def test_roles_follow_the_indent_the_bullet_text_starts_at():
    rs = rows("wrap_shapes")
    for wrapped in ("in a November 2026 re-test", "organic clicks between Jul 2025", "Product owner in Mar 2019", "and improved conversion in Nov 2026.",
                    "engineering and sales in Nov 2026.", "from 2019 to 2021", "Nov 2026 GEO test", "the other regions", "2"):
        assert role_of(rs, wrapped) == layout.CONT, wrapped
    for header in ("Senior AI Engineer", "iOS Engineer", "dbt Labs", "macOS Engineer"):
        assert role_of(rs, header) == layout.HEADER, header
    for plain in ("Mar 2012", "Mar 2010"):
        assert role_of(rs, plain) == layout.PLAIN, plain
    assert role_of(rs, "• Tracked") == layout.BULLET


def test_without_the_layout_the_parser_keeps_its_line_shape_behaviour(run_health):
    """What origin/main does with the same text: every dated wrapped row and the bare number becomes a job. The layout is the fix."""
    h = run_health("wrap_shapes")
    text = next(e.text for e in h.extractions if e.name == "pdftotext-layout")
    assert len(fd.parse(text, h.geometry.style_headings).entries) == 16
    assert len(fd.parse(text, h.geometry.style_headings, layout.build(h.geometry)).entries) == 7


# ---- page footers -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("fixture,bullets", [
    ("foot_bare", [48, 2]),      # '1'
    ("foot_of", [48, 2]),        # '1 of 2'
    ("foot_page", [48, 2]),      # 'Page 1 of 2'
    ("foot_slash", [48, 2]),     # '1/2'
    ("foot_high", [43, 2]),      # '1/2' above the header/footer band, found by its repeat on page 2
    ("foot_running", [48, 2]),   # 'Jane Q. Example · Page 1 of 2'
])
def test_a_page_footer_between_two_bullets_is_not_a_job(run_health, fixture, bullets):
    h = run_health(fixture)
    for view, p in h.parsed.items():
        assert [e.title for e in p.entries] == ["Senior AI Engineer", "Software Engineer"], view
        assert [e.bullets for e in p.entries] == bullets, view
    assert status(h, "entries") == PASS and status(h, "entries_fragile") == PASS and not h.gate_failed


def test_a_bullet_wrapped_across_a_page_break_stays_one_bullet(run_health):
    """Page 1 ends inside a bullet; its dated third row opens page 2 after the footer."""
    h = run_health("break_page")
    for view, p in h.parsed.items():
        assert [e.title for e in p.entries] == ["Senior AI Engineer", "Software Engineer"], view
        assert [e.bullets for e in p.entries] == [46, 2], view
    assert status(h, "entries") == PASS


def test_a_page_number_alone_in_the_band_of_a_one_page_resume_is_a_footer(run_health):
    """No second page to repeat on: the band alone places it. It is not a skill."""
    h = run_health("foot_single")
    for view, p in h.parsed.items():
        assert not any("Page 1 of 1" in s for s in p.skills), view
        assert [e.title for e in p.entries] == ["Senior AI Engineer", "Software Engineer"], view


def test_footer_rows_stay_in_the_text_and_numbers_in_content_are_untouched(run_health):
    """Page numbers are skipped inside the parser's fields only: the lines every other check and the matcher read still hold them, a
    phone split over rows still parses, a skills list wrapped around a bare '2' still reads 'SOC 2', and SOC / 2 still matches."""
    h = run_health("wrap_shapes")
    for view, p in h.parsed.items():
        assert any("Page 1 of 2" in l for l in p.lines), view
        assert "415" in p.lines and "SOC 2" in p.skills and not any("Page" in s for s in p.skills), view
        assert p.phone.split() == ["415", "555-0142"], view
        req = jr.Requirement("SOC 2", [], "skill", "required")
        G, _ = jr.load_synonyms()
        assert m.match(jr.JD(requirements=[req]), p, None, G)[0].status == "ok", view
    assert status(h, "phone") == PASS


# ---- fallbacks: no layout, no indent -------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["two_column", "table_experience"])
def test_a_resume_with_columns_or_a_table_has_no_layout_to_project_onto(name):
    assert layout.build(geo.analyze(FIX / f"{name}.pdf")) is None


def test_a_pdf_with_no_text_has_no_layout():
    assert layout.build(geo.Geometry()) is None


def test_a_layout_with_no_bullet_indent_places_no_wrapped_row_and_the_parser_falls_back(run_health):
    """Wrapped rows return to the margin (flat_bullets) or the bullet's text starts at the margin (hanging_marker): nothing tells a wrapped
    row from a header, so no row is a wrapped row and the parser reads the line shape exactly as origin/main does: the dated wrapped rows
    pass as jobs (11 entries) and the entries check keeps its FAIL. The layout does not claim what it cannot see."""
    for name in ("flat_bullets", "hanging_marker"):
        rs = rows(name)
        assert layout.CONT not in {r.role for r in rs}, name
        assert role_of(rs, "iOS Engineer") == layout.HEADER and role_of(rs, "Senior AI Engineer") == layout.HEADER, name
        h = run_health(name)
        assert {len(p.entries) for p in h.parsed.values()} == {11}, name    # the line-shape count: 2 jobs + 9 wrapped rows
        assert status(h, "entries") == FAIL and h.gate_failed, name


def test_a_bold_or_right_aligned_row_at_the_bullet_text_indent_is_not_taken_for_a_wrapped_row():
    """A role nested under an employer starts at the bullet's text indent too; bold, or a right-aligned part, marks it a header."""
    g = _resume()
    g.lines += [geo.Line(0, 65, 114, 365, 124, "Staff Engineer, Initech", 10.0, True, [(65, 365, "Staff Engineer, Initech")], True, None),
                geo.Line(0, 400, 114, 500, 124, "2019 – 2021", 10.0, False, [(400, 500, "2019 – 2021")], False, None)]
    r = _roles(g)
    assert r["Staff Engineer, Initech 2019 – 2021"] == layout.OTHER


def test_a_row_the_layout_cannot_locate_gets_no_role_and_is_parsed_by_line_shape(run_health):
    h = run_health("clean")
    p = fd.parse("Jane Q. Example\nEngineer\nEXPERIENCE\nStaff Engineer, Initech  Jan 2020 – Present\n• Built a thing.\nSKILLS\nPython, Go, Docker\n",
                 layout=layout.build(h.geometry))
    assert p.roles[3:5] == [None, None] and [e.title for e in p.entries] == ["Staff Engineer"] and p.entries[0].layout == ""


def test_a_row_that_is_only_the_tail_of_a_visual_row_gets_no_role(run_health):
    """PyMuPDF reads a header's right-aligned date as a row of its own; that row is a part of the header row, not a header: no role, and the
    title row before it carries the header role the entry keeps."""
    h = run_health("wrap_shapes")
    p = h.parsed["pymupdf"]
    i = p.lines.index("Mar 2019 – Dec 2021")
    assert p.roles[i] is None and p.roles[i - 1] == layout.HEADER and p.lines[i - 1].startswith("iOS Engineer")


def test_an_extractor_that_joins_a_wrapped_bullet_into_one_row_is_still_located(run_health):
    """PdfPig (Filee) emits a whole paragraph as one row: it takes the role of the first visual row it covers."""
    h = run_health("wrap_shapes")
    text = next(e.text for e in h.extractions if e.name == "pdftotext-layout")
    joined: list[str] = []
    for ln in text.splitlines():
        if joined and ln[:1] in " \t" and ln.strip() and fd.is_bullet(joined[-1].strip()) and not fd.is_bullet(ln.strip()):
            joined[-1] += " " + ln.strip()
        else:
            joined.append(ln)
    p = fd.parse("\n".join(joined), h.geometry.style_headings, layout.build(h.geometry))
    assert [e.title for e in p.entries] == TITLES and p.layout_share >= 0.95


# ---- the entries check: a FAIL needs more than a line-shape reading -----------------------------------------------

def _p(*headers, layout_share=0.0, role=""):
    ents = [fd.Entry(header=h, title=t, company=c, dates_raw=d, start=d, dates_ok=bool(d), layout=role, first_line=i)
            for i, (h, t, c, d) in enumerate(headers)]
    return fd.Parsed(entries=ents, layout_share=layout_share)


JOB = ("Senior AI Engineer, Acme  Jan 2022 – Present", "Senior AI Engineer", "Acme", "2022")
SPURIOUS = ("2", "", "", "")


def _entries(parsed):
    return next(c for c in health._field_checks(parsed) if c.id == "entries")


def test_a_view_that_alone_reads_a_job_with_no_title_is_a_warn_not_a_fail():
    c = _entries({"a": _p(JOB, SPURIOUS), "b": _p(JOB), "c": _p(JOB)})
    assert c.status == WARN and "only 1 of 3 extractors read it so" in c.evidence[0] and "line-shape" in c.evidence[0]


def test_the_same_missing_title_in_every_view_with_no_layout_is_still_a_fail():
    assert _entries({"a": _p(JOB, SPURIOUS), "b": _p(JOB, SPURIOUS)}).status == FAIL


def test_a_row_the_layout_places_at_the_margin_keeps_its_fail_even_when_one_view_sees_it():
    c = _entries({"a": _p(JOB, SPURIOUS, layout_share=1.0, role=layout.HEADER), "b": _p(JOB, layout_share=1.0, role=layout.HEADER)})
    assert c.status == FAIL


def test_a_row_the_layout_does_not_place_at_the_margin_is_a_warn_even_when_every_view_agrees():
    """Every extractor shows the same wrapped row, so agreement proves nothing about it; the layout is the evidence."""
    c = _entries({"a": _p(JOB, SPURIOUS, layout_share=1.0, role=layout.OTHER), "b": _p(JOB, SPURIOUS, layout_share=1.0, role=layout.OTHER)})
    assert c.status == WARN and "page layout does not place a role header" in c.evidence[0]


# ---- the date-only row pairs with the row before it, past a footer, never with a wrapped row ----------------------------

class Roles:
    """The interface fields.parse reads from a Layout, with the roles given."""
    usable = True

    def __init__(self, roles):
        self.roles = roles

    def classes_for(self, lines):
        return self.roles, 1.0


def _stacked(*body_roles):
    """Title row, then a date-only row (a stream-order extractor splits a header so), a bullet after it."""
    lines = ["Jane Q. Example", "Engineer", "EXPERIENCE", *[ln for ln, _ in body_roles], "• Built a thing.", "SKILLS", "Python, Go, Docker"]
    roles = [None, None, "header", *[r for _, r in body_roles], "bullet", "header", "plain"]
    return fd.parse("\n".join(lines) + "\n", layout=Roles(roles)).entries


def test_a_date_only_row_after_a_footer_pairs_with_the_title_row_before_the_footer():
    es = _stacked(("Software Engineer, Globex", "header"), ("Page 1 of 2", "footer"), ("Mar 2019 – Dec 2021", "plain"))
    assert [(e.title, e.company) for e in es] == [("Software Engineer", "Globex")] and es[0].header.startswith("Software Engineer, Globex")


def test_a_date_only_row_after_a_wrapped_bullet_row_does_not_take_it_for_a_title():
    es = _stacked(("Product owner", "cont"), ("Mar 2019 – Dec 2021", "plain"))
    assert [e.title for e in es] == [""] and es[0].header == "Mar 2019 – Dec 2021"


def test_a_lowercase_brand_title_row_the_layout_places_pairs_with_its_date_row():
    es = _stacked(("iOS Engineer, Globex", "header"), ("Mar 2019 – Dec 2021", "plain"))
    assert [e.title for e in es] == ["iOS Engineer"]


def test_a_running_footer_that_looks_like_a_heading_opens_no_section():
    lines = ["Jane Q. Example", "Engineer", "EXPERIENCE", "Senior AI Engineer, Acme  Jan 2022 – Present", "• Built a thing.", "CONFIDENTIAL RESUME", "• Shipped another.", "SKILLS", "Python, Go, Docker"]
    p = fd.parse("\n".join(lines) + "\n", layout=Roles([None, None, "header", "header", "bullet", "footer", "bullet", "header", "plain"]))
    assert [s.title for s in p.sections] == ["EXPERIENCE", "SKILLS"] and [e.bullets for e in p.entries] == [2]


def test_a_page_footer_row_is_not_part_of_the_skills_list():
    p = fd.parse("Jane Q. Example\nEngineer\nSKILLS\nPython, Go,\nPage 1 of 2\nDocker\n", layout=Roles([None, None, "header", "plain", "footer", "plain"]))
    assert p.skills == ["Python", "Go", "Docker"]


# ---- layout.py on a hand-built geometry: the boundaries a PDF fixture would need a new file for ------------------------

def _g(*rows, pages=2, page_h=792.0):
    """rows: (page, x0, y0, text[, bold[, text_x]]) -> a Geometry; a row is 10pt high, 300pt wide."""
    g = geo.Geometry(pages=pages, page_h=page_h)
    for pg, x0, y0, text, *rest in rows:
        bold = rest[0] if rest else False
        tx = rest[1] if len(rest) > 1 else None
        g.lines.append(geo.Line(pg, x0, y0, x0 + 300, y0 + 10, text, 10.0, bold, [(x0, x0 + 300, text)], bold, tx))
    return g


def _roles(g):
    return {r.text: r.role for r in layout.build(g).rows}


def _resume(*extra, **kw):
    base = [(0, 50, 50, "EXPERIENCE", True), (0, 50, 70, "Senior Engineer, Acme", True), (0, 56, 90, "• Built a thing", False, 65.0), (0, 65, 102, "and then wrapped it")]
    return _g(*base, *extra, **kw)


def test_a_row_indented_somewhere_other_than_the_bullet_text_is_not_a_wrapped_row():
    r = _roles(_resume((0, 90, 114, "indented elsewhere, Mar 2019")))
    assert r["and then wrapped it"] == layout.CONT and r["indented elsewhere, Mar 2019"] == layout.OTHER


def test_a_page_number_shape_ending_a_page_and_not_repeated_is_the_wrapped_text_it_looks_like():
    """'SOC' at the end of page 1 and '2' wrapped onto the next row at the foot of the page, no footer anywhere: a bare number, not a footer."""
    g = _resume((0, 65, 700, "2"), (1, 50, 50, "SKILLS", True))
    assert _roles(g)["2"] == layout.CONT


def test_a_page_number_shape_at_the_same_height_on_two_pages_is_a_footer_wherever_it_sits():
    g = _resume((0, 300, 600, "1/2"), (1, 50, 50, "SKILLS", True), (1, 300, 600, "2/2"))
    assert layout.build(g) and [r.role for r in layout.build(g).rows if r.text.endswith("/2")] == [layout.FOOTER, layout.FOOTER]


def test_a_page_number_in_the_header_footer_band_is_a_footer_with_no_second_page():
    g = _resume((0, 300, 760, "Page 1"), pages=1)
    assert _roles(g)["Page 1"] == layout.FOOTER


# ---- the cases the layout must not weaken ----------------------------------------------------------------------------

def test_a_header_with_no_date_right_after_a_bullet_is_still_a_job_and_still_a_fail(run_health):
    """'eBay, Staff Engineer' and 'iOS Developer': lowercase brands, no date. They are jobs; a job with no date is what the check is for."""
    h = run_health("undated_brand")
    for view, p in h.parsed.items():
        assert [e.title for e in p.entries] == ["Senior AI Engineer", "Staff Engineer", "iOS Developer"], view
        assert [e.dates_problem for e in p.entries][1:] == ["no dates found"] * 2, view
    assert status(h, "entries") == FAIL and h.gate_failed


def test_a_lowercase_brand_header_with_a_date_nobody_reads_still_fails(run_health):
    h = run_health("season_brand")
    for view, p in h.parsed.items():
        assert [(e.title, e.company) for e in p.entries] == [("Senior AI Engineer", "Acme Robotics"), ("Software Engineer", "dbt Labs")], view
    assert status(h, "entries") == FAIL and "Spring" in " ".join(check(h, "entries").evidence)


def test_a_header_glued_onto_the_row_before_it_still_makes_the_extractors_disagree(run_health):
    """An extractor that fuses the last bullet of one job with the next job's header loses that job: the entry-count WARN is how a
    candidate sees it, and the layout does not paper over it."""
    h = run_health("clean")
    text = next(e.text for e in h.extractions if e.name == "pdftotext-layout")
    last, head = "that gate every release.", "Software Engineer, Globex Corporation"
    assert last in text and head in text
    rows_ = text.splitlines()
    i = next(n for n, ln in enumerate(rows_) if ln.rstrip().endswith(last))
    j = next(n for n, ln in enumerate(rows_) if ln.strip().startswith(head))
    rows_[i] = rows_[i].rstrip() + "  " + rows_[j].strip()
    del rows_[j]
    lay = layout.build(h.geometry)
    whole, fused = fd.parse(text, h.geometry.style_headings, lay), fd.parse("\n".join(rows_), h.geometry.style_headings, lay)
    assert (len(whole.entries), len(fused.entries)) == (2, 1)
    assert next(c for c in health._field_checks({"a": whole, "b": fused}) if c.id == "entries_fragile").status == WARN
