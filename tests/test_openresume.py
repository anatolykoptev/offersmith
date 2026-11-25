"""The optional OpenResume layer: OpenResume's own parser (fetched by tools/openresume/install.sh) run on real PDFs.

Fixtures are built by tests/make_fixtures.py: `or_clean` is read cleanly by OpenResume and every other `or_*` fixture differs from it by
exactly one defect. Tests that need the layer skip when Node or the install is missing; in CI that is a failure.
The install is looked for where the user would put it: $ATS_CHECK_OPENRESUME (saved by conftest before it switches the layer off), else the default.
"""
import os
import shutil
import stat
from pathlib import Path

import pytest

from ats_check import health, openresume as orl
from ats_check.health import FAIL, PASS, WARN
from conftest import FIX, OPENRESUME_HOME

HOME = Path(OPENRESUME_HOME).expanduser() if OPENRESUME_HOME and OPENRESUME_HOME.lower() != "off" else orl.CACHE / "openresume"


def need_layer():
    why = orl.missing_reason(HOME)
    if why:
        if os.environ.get("CI"):
            pytest.fail(f"the OpenResume layer is required in CI ({why}); run: {orl.install_command()}")
        pytest.skip(f"OpenResume layer unavailable: {why}")


_cache: dict = {}


@pytest.fixture()
def or_run(monkeypatch):
    def _run(name):
        need_layer()
        if name not in _cache:
            monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(HOME))
            _cache[name] = health.run(FIX / f"{name}.pdf")
        return _cache[name]
    return _run


def by_id(h):
    return {c.id: c for c in h.checks if c.id.startswith("or_")}


def non_pass(h):
    return {i: c.status for i, c in by_id(h).items() if c.status != PASS}


def test_the_clean_base_resume_passes_every_openresume_check(or_run):
    h = or_run("or_clean")
    assert non_pass(h) == {}
    assert set(by_id(h)) == {"or_layer", "or_granularity", "or_glued", "or_bullets", "or_page_boundary", "or_entries", "or_education", "or_contact"}
    assert not h.gate_failed
    assert h.openresume["resume"]["workExperiences"][0]["date"].startswith("Jan 2022")


def test_per_word_text_matrices_are_reported_as_glued_words_and_item_granularity(or_run):
    c = by_id(or_run("or_wordwise"))
    assert c["or_granularity"].status == WARN and "single word" in c["or_granularity"].evidence[0]
    assert "microtype" in c["or_granularity"].fix
    assert c["or_glued"].status == WARN
    assert any("OpenResume reads 'SeniorAIPlatformEngineer' where the text layer has 'Senior AI Platform Engineer'" in e for e in c["or_glued"].evidence)


def test_an_email_that_openresume_reads_wrongly_is_a_fail(or_run):
    # in the per-word PDF the contact line is glued, so OpenResume's email field swallows the neighbouring items
    h = or_run("or_wordwise")
    c = by_id(h)["or_contact"]
    assert c.status == FAIL and any(e.startswith("email: OpenResume read") and "consensus 'jane.example@example.com'" in e for e in c.evidence)
    assert h.gate_failed


def test_a_dash_bullet_is_named_with_the_parsers_own_glyph_list(or_run):
    h = or_run("or_endash")
    assert non_pass(h) == {"or_bullets": WARN}
    ev = by_id(h)["or_bullets"].evidence
    assert "U+2013 EN DASH" in ev[0] and "not in OpenResume's bullet list" in ev[0]
    assert "•" in ev[1] and "–" not in ev[1]                       # the list comes from OpenResume, not from us


def test_a_vertical_gap_inside_one_role_is_reported_as_a_split_entry(or_run):
    h = or_run("or_gap")
    assert non_pass(h) == {"or_entries": WARN}
    assert any("split a role" in e and "no company, title or date" in e and "Shipped an MCP server" in e for e in by_id(h)["or_entries"].evidence)


def test_degree_and_school_on_one_bold_line_are_reported_empty(or_run):
    h = or_run("or_oneline_edu")
    assert non_pass(h) == {"or_education": WARN}
    assert any("school ''" in e and "degree ''" in e and "BBA, State University" in e for e in by_id(h)["or_education"].evidence)


def test_a_role_header_glued_onto_a_page_break_is_labelled_an_openresume_limitation_and_not_a_missing_role(or_run):
    h = or_run("or_pagebreak")
    assert non_pass(h) == {"or_page_boundary": WARN}               # or_entries stays PASS: the glued role is explained, not reported twice
    c = by_id(h)["or_page_boundary"]
    assert "Software Engineer | Globex Corporation" in c.evidence[0] and "page 2 starts with" in c.evidence[0]
    assert "limitation of OpenResume, not a defect of the resume" in c.fix
    assert not h.gate_failed


def test_layer_off_adds_no_checks_and_no_warn(monkeypatch):
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", "off")
    assert by_id(health.run(FIX / "or_clean.pdf")) == {}


def test_a_missing_install_is_one_warn_that_names_the_install_command(monkeypatch, tmp_path):
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(tmp_path / "nowhere"))
    h = health.run(FIX / "or_clean.pdf")
    c = by_id(h)
    assert list(c) == ["or_layer"] and c["or_layer"].status == WARN and "not installed" in c["or_layer"].evidence[0]
    assert "install.sh" in c["or_layer"].fix and "ATS_CHECK_OPENRESUME=off" in c["or_layer"].fix
    assert not h.gate_failed


def test_missing_node_is_one_warn_not_a_fail(monkeypatch):
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(HOME))
    monkeypatch.setattr(orl.shutil, "which", lambda n: None)
    c = by_id(health.run(FIX / "or_clean.pdf"))
    assert c["or_layer"].status == WARN and "node is not on PATH" in c["or_layer"].evidence[0]


def test_the_runner_is_started_with_code_generation_from_strings_disabled_and_refuses_to_run_without_it(tmp_path):
    from subprocess import run
    need_layer()
    cmd = [str(HOME / "node_modules/.bin/tsx"), "--tsconfig", str(HOME / "open-resume/tsconfig.json"), str(HOME / "run.ts"), str(FIX / "or_clean.pdf")]
    bare = run(cmd, cwd=HOME, capture_output=True, text=True, env={**os.environ, "NODE_OPTIONS": ""})
    assert bare.returncode == 4 and "refusing to parse a PDF" in bare.stderr
    assert orl.run_runner(FIX / "or_clean.pdf", HOME)["resume"]["profile"]["name"] == "Jane Q. Example"
    assert orl.NODE_FLAG in orl._env()["NODE_OPTIONS"]


def test_a_failing_runner_is_one_warn_not_a_fail(monkeypatch, tmp_path):
    for sub in ("node_modules/.bin", "open-resume"):
        (tmp_path / sub).mkdir(parents=True)
    tsx = tmp_path / "node_modules/.bin/tsx"
    tsx.write_text("#!/bin/sh\necho 'boom: cannot read pdf' >&2\nexit 3\n")
    tsx.chmod(tsx.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "run.ts").write_text("")
    (tmp_path / "open-resume/tsconfig.json").write_text("{}")
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(tmp_path))
    real_which = shutil.which
    monkeypatch.setattr(orl.shutil, "which", lambda n: "/usr/bin/node" if n == "node" else real_which(n))
    h = health.run(FIX / "or_clean.pdf")
    c = by_id(h)["or_layer"]
    assert c.status == WARN and "runner failed: boom: cannot read pdf" in c.evidence[0] and not h.gate_failed


# ---- the comparison logic on small hand-made runner outputs (edge cases the real PDFs do not cover) ------------------------
def view(lines, raw=None, pages=None, resume=None):
    raw = raw or [[t, 0, 0, 1, 1, "F", 0] for t in lines]
    return orl.View({"bulletPoints": ["•"], "resume": resume or {"workExperiences": [], "educations": [], "profile": {}},
                     "pages": pages or [{"items": len(raw), "lastHasEOL": False}], "raw": raw,
                     "lines": [{"start": i, "items": [[t, 0, 0, 1, "F"]]} for i, t in enumerate(lines)]})


def test_a_long_word_that_is_in_the_text_layer_is_not_glue():
    v = view(["Generative Engine Optimization", "Kubernetes orchestration"])
    assert orl.glued_words(v, "Generative Engine Optimization and Kubernetes orchestration") == []
    assert [g[:2] for g in orl.glued_words(view(["GenerativeEngineOptimization"]), "Generative Engine Optimization")] == [("GenerativeEngineOptimization", "Generative Engine Optimization")]


def test_a_bullet_or_plain_line_after_a_page_break_is_not_a_role_header():
    v = view(["a", "b"], raw=[["a", 0, 0, 1, 1, "F", 0], ["b", 0, 0, 1, 1, "F", 0]], pages=[{"items": 1, "lastHasEOL": False}, {"items": 1, "lastHasEOL": False}])
    v.lines = [{"start": 0, "items": [["a b", 0, 0, 1, "F"]]}]
    v.ranges = [(0, 0, 2)]
    s = orl.page_straddles(v)
    assert len(s) == 1 and s[0]["before"] == "a" and s[0]["after"] == "b"
    assert orl._is_header_like("Built a service that cut cost 30%.", None) is False
    assert orl._is_header_like("Head of Marketing Feb 2023 - Oct 2024 Grew traffic", None) is True


def test_the_limitation_and_the_skipped_layer_are_not_listed_as_fixes_to_the_resume(or_run, monkeypatch, tmp_path):
    from ats_check import score
    fixes = score.build_fixes(or_run("or_pagebreak"), [], [])
    assert not any("OpenResume" in f["why"] for f in fixes)
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(tmp_path / "nowhere"))
    assert not any("OpenResume" in f["why"] for f in score.build_fixes(health.run(FIX / "or_clean.pdf"), [], []))
    assert any("OpenResume" in f["why"] for f in score.build_fixes(or_run("or_gap"), [], []))     # a real finding still is one


def test_the_report_and_report_json_carry_the_openresume_findings(or_run, monkeypatch, tmp_path):
    import json
    from ats_check import cli
    or_run("or_gap")
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(HOME))
    assert cli.main(["--resume", str(FIX / "or_gap.pdf"), "--jd", str(FIX / "jd.txt"), "--no-llm", "--out", str(tmp_path)]) == 0
    md = (tmp_path / "report.md").read_text()
    assert "OpenResume layer (a second, independent PDF reader" in md and "split a role" in md
    j = json.loads((tmp_path / "report.json").read_text())["health"]["openresume"]
    assert len(j["resume"]["workExperiences"]) == 3 and j["text_items"] > 0
