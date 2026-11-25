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


def test_an_email_that_openresume_reads_wrongly_is_a_warn_never_a_fail(or_run):
    # in the per-word PDF the contact line is glued, so OpenResume's email field swallows the neighbouring items
    h = or_run("or_wordwise")
    c = by_id(h)["or_contact"]
    assert c.status == WARN and any(e.startswith("email: OpenResume read") and "consensus 'jane.example@example.com'" in e for e in c.evidence)
    assert not h.gate_failed


def test_a_parser_specific_disagreement_never_blocks_the_verdict(or_run):
    # a comma right after the email and a heading OpenResume does not take for work experience: the other five extractors read both fine
    h = or_run("or_background")
    c = by_id(h)
    assert c["or_entries"].status == WARN and "heading here is 'PROFESSIONAL BACKGROUND'" in c["or_entries"].evidence[0]
    assert c["or_contact"].status == WARN and "jane.example@example.com,'" in c["or_contact"].evidence[0]
    assert not any(x.status == FAIL for x in h.checks) and not h.gate_failed


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
    d = orl.run_runner(FIX / "or_clean.pdf", HOME)
    assert d["resume"]["profile"]["name"] == "Jane Q. Example"
    assert d["getDocumentParams"] == [{"isEvalSupported": False}]       # the second layer: pdf.js is told not to use eval, whatever the node flag does
    assert orl.NODE_FLAG in orl._env()["NODE_OPTIONS"]


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


# ---- the runner process: a fake `tsx` stands in so none of this needs Node -----------------------------------------------------
def fake_install(tmp_path, monkeypatch, tsx_body, **consts):
    for sub in ("node_modules/.bin", "open-resume"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    tsx = tmp_path / "node_modules/.bin/tsx"
    tsx.write_text("#!/bin/sh\n" + tsx_body)
    tsx.chmod(0o755)
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", str(tmp_path))
    monkeypatch.setattr(orl, "missing_reason", lambda h: "")
    for k, v in consts.items():
        monkeypatch.setattr(orl, k, v)
    return tmp_path


def layer_check(pdf="or_clean"):
    return by_id(health.run(FIX / f"{pdf}.pdf"))["or_layer"]


def payload(**over):
    d = {"bulletPoints": ["•"], "getDocumentParams": [], "pages": [{"items": 0, "lastHasEOL": False}], "raw": [], "lines": [],
         "resume": {"profile": {"name": "", "email": "", "phone": "", "location": ""}, "workExperiences": [], "educations": []}}
    return {**d, **over}


def test_a_timeout_kills_the_whole_process_group_not_just_the_launcher(tmp_path, monkeypatch):
    import time
    mark = tmp_path / "survivor"
    fake_install(tmp_path, monkeypatch, f"(sleep 2; touch '{mark}') &\nsleep 30\n", TIMEOUT=1)
    c = layer_check()
    assert c.status == WARN and "timed out after 1s" in c.evidence[0]
    time.sleep(3)
    assert not mark.exists(), "the parser kept running after the timeout"


def test_runner_output_is_capped_on_both_streams(tmp_path, monkeypatch):
    fake_install(tmp_path, monkeypatch, "head -c 5000 /dev/zero\n", MAX_STDOUT=1000)
    assert "stdout exceeds" in layer_check().evidence[0]
    fake_install(tmp_path, monkeypatch, "head -c 5000 /dev/zero >&2\nsleep 5\n", MAX_STDERR=1000)
    assert "stderr exceeds" in layer_check().evidence[0]


def test_the_runner_gets_a_minimal_environment_with_only_the_node_flag(tmp_path, monkeypatch):
    out = tmp_path / "env.txt"
    fake_install(tmp_path, monkeypatch, f"env > '{out}'\nexit 3\n")
    monkeypatch.setenv("FOO_SECRET", "hunter2")
    monkeypatch.setenv("NODE_OPTIONS", "--require=/tmp/evil.js")
    layer_check()
    env = out.read_text().splitlines()
    assert "NODE_OPTIONS=--disallow-code-generation-from-strings" in env
    assert not any("hunter2" in l or "evil.js" in l for l in env)


def test_invalid_utf8_from_the_runner_is_one_warn(tmp_path, monkeypatch):
    fake_install(tmp_path, monkeypatch, "printf '\\377\\376\\n'\n")
    c = layer_check()
    assert c.status == WARN and "not JSON" in c.evidence[0]


def test_a_payload_missing_a_nested_field_is_one_warn(tmp_path, monkeypatch):
    import json
    d = payload()
    del d["resume"]["profile"]["email"]
    (tmp_path / "out.json").write_text(json.dumps(d))
    fake_install(tmp_path, monkeypatch, f"cat '{tmp_path / 'out.json'}'\n")
    c = layer_check()
    assert c.status == WARN and "no valid resume.profile" in c.evidence[0]


def test_json_with_a_unicode_line_separator_inside_a_string_is_framed_on_the_newline_only(tmp_path, monkeypatch):
    import json
    item = "a\u2028b"
    d = payload(pages=[{"items": 1, "lastHasEOL": False}], raw=[[item, 0, 0, 1, 1, "F", 0]], lines=[{"start": 0, "items": [[item, 0, 0, 1, "F"]]}])
    (tmp_path / "out.json").write_bytes(("warning from pdf.js\n" + json.dumps(d, ensure_ascii=False) + "\n").encode())
    fake_install(tmp_path, monkeypatch, f"cat '{tmp_path / 'out.json'}'\n")
    c = layer_check()
    assert c.status == PASS and "read 1 pdf.js text items" in c.evidence[0]


def test_an_unexpected_failure_while_comparing_is_one_warn(tmp_path, monkeypatch):
    import json
    (tmp_path / "out.json").write_text(json.dumps(payload()))
    fake_install(tmp_path, monkeypatch, f"cat '{tmp_path / 'out.json'}'\n")
    monkeypatch.setattr(orl, "granularity", lambda v: 1 / 0)
    assert "comparison failed: ZeroDivisionError" in layer_check().evidence[0]


# ---- the install folder: one resolver for install.sh and the check, and code that is run must be the pinned, untouched checkout ----
INSTALL_SH = Path(__file__).resolve().parent.parent / "tools" / "openresume" / "install.sh"


def print_dir(env, cwd):
    import subprocess
    r = subprocess.run(["sh", str(INSTALL_SH), "--print-dir"], cwd=cwd, capture_output=True, text=True, env={**os.environ, "ATS_CHECK_OPENRESUME": "", "ATS_CHECK_CACHE": "", **env})
    return r.returncode, r.stdout.strip()


def test_install_sh_and_the_check_resolve_the_folder_identically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for env in ({"ATS_CHECK_OPENRESUME": "rel/dir"}, {"ATS_CHECK_OPENRESUME": str(tmp_path / "abs")}, {"ATS_CHECK_CACHE": str(tmp_path / "cache")}, {}):
        for k in ("ATS_CHECK_OPENRESUME", "ATS_CHECK_CACHE"):
            monkeypatch.setenv(k, env.get(k, ""))
        rc, out = print_dir(env, tmp_path)
        assert rc == 0 and out == str(orl.home()) and orl.home().is_absolute(), env
    monkeypatch.setenv("ATS_CHECK_OPENRESUME", "rel/dir")
    assert orl.home() == tmp_path / "rel" / "dir"


def test_off_is_never_a_folder_for_the_installer(tmp_path):
    for off in ("off", "OFF", "0", "false", "no"):
        rc, _ = print_dir({"ATS_CHECK_OPENRESUME": off}, tmp_path)
        assert rc == 2 and not (tmp_path / off).exists()


def test_the_pin_in_install_sh_is_the_pin_the_check_verifies():
    import re
    assert re.search(r"^SHA=(\w{40})\b", INSTALL_SH.read_text(), re.M).group(1) == orl.PINNED_SHA


def test_the_install_folder_must_be_the_pinned_untouched_checkout_owned_by_us(tmp_path, monkeypatch):
    import subprocess
    home = tmp_path / "home"
    repo = home / "open-resume"
    (home / "node_modules/.bin").mkdir(parents=True)
    repo.mkdir()
    (home / "node_modules/.bin/tsx").write_text("")
    (home / "run.ts").write_text("")
    (repo / "tsconfig.json").write_text("{}")
    git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "x")
    monkeypatch.setattr(orl, "PINNED_SHA", git("rev-parse", "HEAD"))
    monkeypatch.setattr(orl.shutil, "which", lambda n: "/usr/bin/node")
    home.chmod(0o700)
    assert orl.missing_reason(home) == ""
    (repo / "tsconfig.json").write_text('{"x": 1}')
    assert "local changes" in orl.missing_reason(home)
    git("checkout", "--", "tsconfig.json")
    (repo / "extra.ts").write_text("evil()")
    assert "local changes" in orl.missing_reason(home)
    (repo / "extra.ts").unlink()
    monkeypatch.setattr(orl, "PINNED_SHA", "0" * 40)
    assert "not the pinned commit" in orl.missing_reason(home)
    monkeypatch.setattr(orl, "PINNED_SHA", git("rev-parse", "HEAD"))
    home.chmod(0o770)
    assert "writable by someone else" in orl.missing_reason(home)


# ---- heuristics on hand-made runner output --------------------------------------------------------------------------------
def test_an_item_that_carries_its_own_space_is_not_a_word_on_its_own():
    raw = [["alpha ", 0, 0, 1, 1, "F", 0] for _ in range(40)]
    v = orl.View({"bulletPoints": [], "resume": {}, "pages": [{"items": 40, "lastHasEOL": False}], "raw": raw,
                  "lines": [{"start": i * 8, "items": [["w", 0, 0, 1, "F"]]} for i in range(5)]})
    assert orl.granularity(v)[:2] == (0, 40)


def test_two_short_lines_of_single_word_items_are_not_enough_to_report(tmp_path, monkeypatch):
    import json
    words = [[w, i * 10, 0, 8, 1, "F", 0] for i, w in enumerate("one two three four five six".split())]
    raw = words + [[w, i * 10, 12, 8, 1, "F", 0] for i, w in enumerate("one two three four five six".split())]
    d = payload(pages=[{"items": 12, "lastHasEOL": False}], raw=raw, lines=[{"start": 0, "items": [["x", 0, 0, 1, "F"]]}, {"start": 6, "items": [["x", 0, 0, 1, "F"]]}])
    (tmp_path / "out.json").write_text(json.dumps(d))
    fake_install(tmp_path, monkeypatch, f"cat '{tmp_path / 'out.json'}'\n")
    assert by_id(health.run(FIX / "or_clean.pdf"))["or_granularity"].status == PASS


def test_glue_is_matched_within_one_line_and_from_six_letters():
    assert orl.glued_words(view(["DataPipes"]), "Data\nPipes\nteam") == []        # two lines of the reference are not one run of words
    assert [g[:2] for g in orl.glued_words(view(["SiteOps"]), "Site Ops team")] == [("SiteOps", "Site Ops")]


def test_dash_bullets_that_came_out_as_one_description_each_are_not_reported(tmp_path, monkeypatch):
    import json
    out = {}
    for name, n in (("same", 9), ("fewer", 3)):
        descs = [f"d{i}" for i in range(n)]
        d = payload(resume={**payload()["resume"], "workExperiences": [{"company": "c", "jobTitle": "t", "date": "Jan 2022 – Present", "descriptions": descs}]})
        (tmp_path / "out.json").write_text(json.dumps(d))
        fake_install(tmp_path, monkeypatch, f"cat '{tmp_path / 'out.json'}'\n")
        out[name] = by_id(health.run(FIX / "or_endash.pdf"))["or_bullets"].status
    assert out == {"same": PASS, "fewer": WARN}


def test_concurrent_roles_with_the_same_years_are_paired_by_their_own_text():
    from ats_check import fields as fd
    mk = lambda t, c: fd.Entry(header=f"{t}, {c} 2020 – Present", title=t, company=c, dates_raw="2020 – Present")
    parsed = fd.Parsed(entries=[mk("Engineer", "Acme"), mk("Designer", "Beta")])
    w = lambda t, c: {"company": c, "jobTitle": t, "date": "2020 – Present", "descriptions": []}
    v = view([], resume={"workExperiences": [w("Designer", "Beta"), w("Engineer", "Acme")], "educations": [], "profile": {}})
    assert orl.entry_problems(v, parsed, [])[0] == []
