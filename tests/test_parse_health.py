"""Every bad fixture must trip its OWN check (and the clean one must trip none)."""
from pathlib import Path

import pytest

from ats_check.health import FAIL, PASS, WARN


def status(h, cid):
    return next(c.status for c in h.checks if c.id == cid)


def test_clean_resume_passes_everything(run_health):
    h = run_health("clean")
    assert [(c.id, c.status) for c in h.checks if c.status != PASS] == []
    assert not h.gate_failed
    names = {e.name for e in h.extractions if e.ok}
    assert {"pdftotext-layout", "pdftotext-raw", "pymupdf", "pdfplumber", "pypdfium2"} <= names  # + filee when installed


@pytest.mark.parametrize("fixture,check,expected", [
    ("two_column", "columns", FAIL),
    ("table_experience", "tables", FAIL),
    ("header_contact", "header_footer", FAIL),
    ("ligatures", "ligatures", WARN),
    ("heading_renamed", "sec_experience", FAIL),
    ("heading_renamed", "headings", WARN),
    ("dates_season", "entries", FAIL),
    ("skills_image", "images", FAIL),
    ("no_tounicode", "tounicode", FAIL),
    ("icon_contact", "icons", WARN),
])
def test_bad_fixture_trips_its_check(run_health, fixture, check, expected):
    assert status(run_health(fixture), check) == expected


@pytest.mark.parametrize("fixture,gate", [
    ("two_column", True), ("table_experience", True), ("header_contact", True), ("heading_renamed", True),
    ("dates_season", True), ("skills_image", True), ("no_tounicode", True),
    ("ligatures", False), ("icon_contact", False),
])
def test_gate(run_health, fixture, gate):
    assert run_health(fixture).gate_failed is gate


def test_bad_fixtures_do_not_trip_unrelated_checks(run_health):
    # the ligature fixture must not look like an encoding failure, the icon one not like a layout failure
    h = run_health("ligatures")
    assert status(h, "tounicode") == PASS and status(h, "columns") == PASS
    h = run_health("heading_renamed")
    assert status(h, "tounicode") == PASS and status(h, "entries") != PASS  # entries cannot parse w/o a heading: consequence, not cause


def test_season_dates_name_the_offending_text(run_health):
    c = next(c for c in run_health("dates_season").checks if c.id == "entries")
    assert any("Spring" in e and "unparseable date format" in e for e in c.evidence)


def test_image_check_reports_what_ocr_reads(run_health):
    c = next(c for c in run_health("skills_image").checks if c.id == "images")
    assert any("Languages" in e for e in c.evidence)


def test_header_check_quotes_the_header_text(run_health):
    c = next(c for c in run_health("header_contact").checks if c.id == "header_footer")
    assert any("@" in e for e in c.evidence)


def _fake_filee(tmp_path, body):
    exe = tmp_path / "filee"
    exe.write_text("#!/bin/sh\nif [ \"$1\" = version ]; then echo 'filee 9.9.9'; exit 0; fi\n" + body)
    exe.chmod(0o755)
    return exe


def test_filee_extractor_reads_txt_output_strips_bom_and_records_version(monkeypatch, tmp_path):
    from ats_check import extract
    # args: convert SRC --to txt -o OUT --overwrite --quiet
    exe = _fake_filee(tmp_path, 'mkdir -p "$6"; printf \'\\357\\273\\277Jane\\tExample\\n\' > "$6/in.txt"\n')
    monkeypatch.setenv("ATS_CHECK_FILEE", str(exe))
    e = extract.filee_text(tmp_path / "a.pdf") if (tmp_path / "a.pdf").write_bytes(b"%PDF") else None
    assert e.ok and e.text.startswith("Jane") and "\t" not in e.text and e.version == "filee 9.9.9"


def test_missing_filee_is_a_warn_not_a_fail(monkeypatch, tmp_path):
    from ats_check import extract, health
    monkeypatch.setenv("ATS_CHECK_FILEE", str(tmp_path / "nope"))
    monkeypatch.setattr(extract.shutil, "which", lambda n: None)
    e = extract.filee_text(tmp_path / "a.pdf")
    assert not e.ok and "not installed" in e.error
    h = health.run(Path(__file__).parent / "fixtures" / "clean.pdf")
    c = next(c for c in h.checks if c.id == "extractors")
    assert c.status == WARN and not h.gate_failed


def test_no_java_anywhere():
    import ats_check
    src = (Path(ats_check.__file__).parent / "extract.py").read_text().lower()
    assert "-jar" not in src and "tika" not in src and "find_java" not in src
    assert "java" not in src.replace("java/pdfbox", "").replace("the java", "")


# ---- checks that were mutation-blind: synthetic views derived from the clean fixture's real extractions
import dataclasses
import re

from ats_check import extract as ex, fields as fd, health, score

CLEAN = Path(__file__).parent / "fixtures" / "clean.pdf"
HEADER = "Jane Q. Example\nSenior AI Platform Engineer\nSan Francisco, CA · jane.example@example.com · (415) 555-0142\n"


@pytest.fixture()
def views(monkeypatch, run_health):
    base = [e for e in run_health("clean").extractions]

    def make(transform=lambda name, t: t, keep=None):
        out = [dataclasses.replace(e, text=transform(e.name, e.text)) for e in base if keep is None or e.name in keep]
        monkeypatch.setattr(health.ex, "run_all", lambda pdf: out)
        return health.run(CLEAN)
    return make


def test_scanned_pdf_has_no_text_layer(views):
    assert status(views(lambda n, t: "Jane\n"), "text_layer") == FAIL


def test_fewer_than_three_extractors_cannot_be_compared(views):
    h = views(keep={"pymupdf", "pdfplumber"})
    assert status(h, "extractors") == FAIL and h.gate_failed


def test_missing_email_fails_under_every_view(views):
    assert status(views(lambda n, t: t.replace("jane.example@example.com", "")), "email") == FAIL


def test_two_item_skills_section_is_not_a_skills_section(views):
    def cut(n, t):
        i = t.index("SKILLS")
        return t[:i] + "SKILLS\nPython, Go\n"
    assert status(views(cut), "sec_skills") == FAIL


def test_lost_words_in_one_extractor_warn(views):
    h = views(lambda n, t: t.replace("evaluation", "").replace("retrieval", "").replace("pipeline", "").replace("workflow", "") if n == "pdfplumber" else t)
    assert status(h, "chars_lost") == WARN


def test_location_check_fails_soft_when_no_view_has_a_place(views):
    assert status(views(lambda n, t: t.replace("San Francisco, CA · ", "")), "location") == WARN


def test_location_is_the_contact_line_not_a_headline():
    text = ("Jane E\nAI Product Engineer · Agents, MCP servers, Large Language Models (LLM)\n"
            "San Francisco, CA · +1 (415) 555-0142 · jane@example.com\nEXPERIENCE\nEngineer, X  Jan 2022 – Present\n• Built it.\n")
    assert fd.parse(text).location == "San Francisco, CA"
    assert fd.parse("Jane E\nAgents, MCP servers, Large Language Models (LLM)\njane@example.com\nEXPERIENCE\n").location == ""


def test_company_that_is_a_location_fragment_is_flagged():
    p = fd.parse("Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nEXPERIENCE\n"
                 "Video Producer · Los Angeles and San Francisco Bay Area · 2020 – Present\n• Shot video.\nSKILLS\nPython, Go, Docker\n")
    assert p.entries and fd.looks_like_location(p.entries[0].company)
    c = next(c for c in health._field_checks({"v": p}) if c.id == "entries")
    assert c.status == WARN and any("location fragment" in e for e in c.evidence)


def test_a_job_that_vanishes_in_one_view_is_a_fix_not_a_pass(views):
    def glue(n, t):
        if n != "filee":
            return t
        return re.sub(r"release\.\s*Software Engineer, Globex Corporation\s+Mar 2019 – Dec 2021", "release. Software Engineer, Globex Corporation Mar 2019 – Dec 2021", t)
    h = views(glue)
    assert status(h, "entries_fragile") == WARN and status(h, "entries") == WARN
    fixes = score.build_fixes(h, [], [])
    assert any(f["kind"] == "parse" and "blank line" in f["action"] for f in fixes)


def test_entries_fragile_is_always_a_check(run_health):
    h = run_health("clean")
    assert status(h, "entries_fragile") == PASS and h.checks[-1].id == "entries_fragile"


def test_location_fragment_state_code_is_case_sensitive():
    assert fd.looks_like_location("Austin, TX") and not fd.looks_like_location("Acme Labs, ab")


# ---- line-based extractors leave a wrapped bullet line and a page footer on rows of their own ------------------

def test_wrapped_bullets_and_page_footer_do_not_become_jobs(run_health):
    """Real line shapes (a dated wrapped line, a '1/2' footer between two bullets of one role) from a resume every
    extractor read correctly: two jobs under every view, no parse FAIL, no entry-count WARN."""
    h = run_health("wrapped_bullets")
    assert {n: len(p.entries) for n, p in h.parsed.items()} == {n: 2 for n in h.parsed}
    assert status(h, "entries") == PASS and status(h, "entries_fragile") == PASS
    assert not h.gate_failed
    assert [e.bullets for e in h.parsed["pdftotext-layout"].entries] == [6, 2]


def _entries(*lines):
    text = "Jane Q. Example\nSan Francisco, CA · jane@example.com\nEXPERIENCE\n" + "\n".join(lines) + "\nSKILLS\nPython, Go, Docker\n"
    return fd.parse(text).entries


JOB1 = "Senior AI Engineer, Acme Robotics  Jan 2022 – Present"
JOB2 = "Software Engineer, Globex Corporation  Mar 2019 – Dec 2021"


@pytest.mark.parametrize("wrapped", [
    "of them first, in a November 2026 test of 15 questions; built its site and Google Business Profile.",  # lowercase, one date
    "November 2026, and has done its SEO hands-on for 15+ years.",                                          # month first, prose after it
    "editing their work, and led editorial work again by 2022.",                                            # lowercase, year at the end
    "from 2019 to 2021, briefing its writers and checking every page before it went live.",                 # lowercase, looks like a range
    "Nov 2026 GEO test of 15 car-owner questions named the shop first in ten of them, built by Jane.",      # capitalised, sentence-length
])
def test_a_wrapped_bullet_line_with_a_date_is_not_an_entry(wrapped):
    es = _entries(JOB1, "• Built a thing that did a useful and measurable job for the client in the", wrapped, "• Shipped another.")
    assert [e.header for e in es] == [JOB1] and es[0].bullets == 2 and es[0].dates_problem == ""


def test_a_short_undated_wrapped_tail_before_the_next_bullet_is_not_an_entry():
    """A bullet written without a closing full stop whose last wrapped row is short: no dates, next row a bullet."""
    es = _entries(JOB1, "• Built a thing that did a useful and measurable job for the client in the", "and the other regions", "• Shipped another.")
    assert [e.header for e in es] == [JOB1] and es[0].bullets == 2


def test_a_short_wrapped_line_that_opens_with_a_month_is_not_an_entry():
    es = _entries(JOB1, "• Built a thing that did a useful and measurable job for the client from", "November 2026, and she wrote.", "• Shipped another.")
    assert [e.header for e in es] == [JOB1] and es[0].bullets == 2


@pytest.mark.parametrize("footer", ["1/2", "2/2", "Page 1 of 2", "Page 3", "page 3"])
def test_a_page_footer_row_is_not_an_entry(footer):
    es = _entries(JOB1, "• Built a thing for a client.", footer, "• Shipped another.")
    assert [e.header for e in es] == [JOB1] and es[0].bullets == 2


def test_page_numbers_are_dropped_only_in_entry_detection_not_from_the_document():
    """A bare number row, '- 3 -', a year and a phone split over rows are content, not footers."""
    assert fd.clean_lines("2022\n1/2024\n05/2024\n415\n555-0142\n- 3 -\n808") == ["2022", "1/2024", "05/2024", "415", "555-0142", "- 3 -", "808"]
    p = fd.parse("Jane Q. Example\nSenior Engineer\n415\n555-0142\nEXPERIENCE\n" + JOB1 + "\n• Built a thing.\n- 3 -\n• Shipped another.\nSKILLS\nPython,\n808\n, Go\n")
    assert [e.bullets for e in p.entries] == [3]       # '- 3 -' is a literal bullet
    assert p.skills == ["Python", "808", "Go"]        # a skills row that is only a number survives


def test_a_phone_split_over_rows_survives_the_page_number_filter():
    assert "555-0142" in fd.parse("Jane Q. Example\n415\n555-0142\nEXPERIENCE\n").lines


@pytest.mark.parametrize("header", [
    JOB2,                                          # a full header right after a bullet, no blank line
    "iOS Engineer, Globex Corporation  2019 – 2021",   # a lowercase brand is not prose
    "Mar 2019 – Dec 2021  Software Engineer, Globex",  # date first
])
def test_a_role_header_right_after_a_bullet_is_still_an_entry(header):
    es = _entries(JOB1, "• Built a thing for a client.", header, "• Owned a service.")
    assert [e.header for e in es] == [JOB1, header]


def test_a_genuine_single_date_header_after_a_bullet_is_still_flagged():
    es = _entries(JOB1, "• Built a thing for a client.", "Software Engineer, Globex Corporation  Mar 2019", "• Owned a service.")
    assert len(es) == 2 and es[1].dates_problem == "single date, no range" and es[1].title == "Software Engineer"


def test_a_header_glued_onto_the_previous_bullet_still_makes_the_counts_differ():
    whole = _entries(JOB1, "• Built a thing for a client.", JOB2, "• Owned a service.")
    glued = _entries(JOB1, "• Built a thing for a client. " + JOB2, "• Owned a service.")
    assert (len(whole), len(glued)) == (2, 1)
    c = next(c for c in health._field_checks({"a": fd.Parsed(entries=whole), "b": fd.Parsed(entries=glued)}) if c.id == "entries_fragile")
    assert c.status == WARN


@pytest.mark.parametrize("after", ["• Built a thing for a client.", "• Built a thing for a client"])    # with and without a closing full stop
@pytest.mark.parametrize("header", [
    "dbt Labs, Software Engineer  Spring '19",                 # unparseable date, lowercase brand
    "dbt Labs, Software Engineer  2019 – 2021",                # valid range at the end
    "2019 – 2021  dbt Labs, Software Engineer",                # range first
    "dbt Labs, Software Engineer",                             # no dates at all
    "développeur logiciel, Acme  2019 – 2021",                 # lowercase, accented, no job word known
])
def test_a_real_header_after_a_bullet_is_never_taken_for_a_wrapped_line(after, header):
    es = _entries(JOB1, after, header, "• Owned a reliable service.")
    assert [e.header for e in es] == [JOB1, header]


def test_a_lowercase_header_with_unparseable_dates_still_fails_the_entries_check():
    p = fd.parse("Jane Q. Example\nEngineer\nSan Francisco, CA · j@example.com\nEXPERIENCE\n" + JOB1 + "\n• Built a thing for a client.\n"
                 "dbt Labs, Software Engineer  Spring '19\n• Owned a reliable service.\nSKILLS\nPython, Go, Docker\n")
    c = next(c for c in health._field_checks({"v": p}) if c.id == "entries")
    assert len(p.entries) == 2 and c.status == FAIL


@pytest.mark.parametrize("after", ["• Built a thing for a client.", "• Built a thing for a client"])
def test_a_long_single_date_header_ending_in_a_full_stop_is_still_an_entry(after):
    h = "Mar 2019  Senior Software Engineer, The Acme Research and Development Co."
    es = _entries(JOB1, after, h, "• Owned a reliable service.")
    assert [e.header for e in es] == [JOB1, h] and es[1].dates_problem == "single date, no range"


def test_a_non_bullet_row_between_the_bullet_and_the_dated_row_ends_the_wrap():
    """'Austin, TX' is not a wrap of the bullet, so what follows it is judged on its own, as before."""
    es = _entries(JOB1, "• Built a thing for a client", "Austin, TX", "and continued that work in November 2026.", "• Owned a service.")
    assert [e.header for e in es] == [JOB1, "and continued that work in November 2026."]


def test_a_page_break_ends_the_wrap():
    es = _entries(JOB1, "• Built a thing for a client in the", "1/2", "and continued that work in November 2026.", "• Owned a service.")
    assert len(es) == 2


def test_a_wrap_continues_only_while_the_row_before_it_has_no_sentence_end():
    """The same row is a header after a finished sentence and a wrapped line after an unfinished one."""
    row = "and continued that work in November 2026."
    assert [e.header for e in _entries(JOB1, "• Built a thing for a client.", row, "• Owned a service.")] == [JOB1, row]
    assert [e.header for e in _entries(JOB1, "• Built a thing for a client and", row, "• Owned a service.")] == [JOB1]


def test_a_lowercase_brand_row_after_an_unfinished_bullet_is_still_a_header():
    es = _entries(JOB1, "• Built a thing for a client", "iOS Developer", "• Owned a reliable service.")
    assert [e.header for e in es] == [JOB1, "iOS Developer"]
