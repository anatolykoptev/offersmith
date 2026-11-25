"""P3: pinned criteria, the quote-checked N-sample grader, the vote and the HiredScore band."""
import json
import re
import subprocess
import threading
import types
from pathlib import Path

import pytest

from ats_check import cli, criteria as cr, grade as gr, llm, report
from ats_check.criteria import Criterion
from ats_check.master import Line, Master

FX = Path(__file__).parent / "fixtures"
JD = """Platform Engineer
Remote

Who You Are
- 5+ years of professional software development
- Hands-on experience applying AI/ML in product (LLMs, embeddings, or similar)
- Independent and comfortable with ambiguity
- Experience with modern web frameworks (Rails/React/Postgres/AWS is a plus)

Nice to Have
- Startup experience
- Hubspot/CRM integrations
"""
RESUME = """Jane Doe
Senior Engineer, Acme 2016-Present
- Built RAG pipelines with embeddings and LLMs for 40 customers
- Led a React and Postgres web app used by 10k people
Startup co-founder, 2012-2016
"""


RES = gr.from_text(RESUME)
Q = "Built RAG pipelines with embeddings and LLMs for 40 customers"


@pytest.fixture()
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(llm, "self_check", lambda *a, **k: True)
    return tmp_path


class Scripted:
    """A runner whose k-th call (any thread) pops the next scripted answer; the multiset of answers is deterministic."""
    def __init__(self, answers):
        self.answers, self.calls, self.lock = list(answers), 0, threading.Lock()

    def __call__(self, prompt, model, timeout=300):
        with self.lock:
            self.calls += 1
            a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return json.dumps(a)


def crit(*rows):
    return [Criterion(f"c{i + 1}", t, lvl, scr) for i, (t, lvl, scr) in enumerate(rows)]


def res(cid, status, quote=""):
    return {"id": cid, "status": status, "quote": quote}


# ---- vote
@pytest.mark.parametrize("statuses,n,want", [
    (["met"] * 5, 5, "met"),
    (["met"] * 4 + ["not_met"], 5, "met"),                 # 4/5 = ceil(0.8 * 5): wins
    (["met"] * 3 + ["not_met"] * 2, 5, "undecided"),        # 3/5 is not enough
    (["met"] * 2 + ["partial"] * 2 + ["not_met"], 5, "undecided"),
    (["not_met"] * 4 + ["partial"], 5, "not_met"),
    (["met"] * 4, 5, "met"),                                # one run failed: 4 of the REQUESTED 5 still wins
    (["met"] * 3, 5, "undecided"),
    (["met"] * 7 + ["not_met"] * 3, 10, "undecided"),       # need ceil(8.0) = 8
    (["met"] * 8 + ["not_met"] * 2, 10, "met"),
    (["met"] * 2 + ["not_met"], 3, "undecided"),            # need ceil(2.4) = 3
    ([], 5, "undecided"),
])
def test_vote_thresholds(statuses, n, want):
    assert gr.vote(statuses, n) == want


# ---- band
def row(level, status, screenable=True):
    return {"id": "x", "text": "t", "level": level, "screenable": screenable, "status": status}


@pytest.mark.parametrize("rows,want", [
    ([row("basic", "met"), row("basic", "met")], "A/B band"),
    ([row("basic", "met"), row("basic", "not_met")], "C/D band"),
    ([row("basic", "met"), row("basic", "undecided")], "band undecided"),
    ([row("basic", "met"), row("basic", "partial")], "band undecided"),
    ([row("basic", "undecided"), row("basic", "not_met")], "C/D band"),     # a decided not_met beats undecided
    ([row("basic", "met"), row("preferred", "not_met")], "A/B band"),       # preferred never gates
    ([row("basic", "met"), {**row("basic", None, False), "status": None}], "A/B band"),  # non-screenable is outside the band
    ([row("preferred", "met")], "no basic screenable criteria"),
])
def test_band_rule(rows, want):
    assert gr.band(rows)["band"] == want


def test_band_counts():
    b = gr.band([row("basic", "met"), row("basic", "not_met"), row("basic", "undecided"), row("basic", "partial"), row("preferred", "met")])
    assert (b["basic_total"], b["basic_met"], b["basic_not_met"], b["basic_undecided"], b["basic_partial"]) == (4, 1, 1, 1, 1)


# ---- quote check
def test_a_quote_that_is_not_in_the_resume_is_ungrounded_not_not_met():
    c = crit(("AI/ML in product", "basic", True))
    ok = gr.check_sample({"results": [res("c1", "met", Q)]}, c, RES)["c1"]
    bad = gr.check_sample({"results": [res("c1", "met", "Shipped production LLM agents at Hubspot")]}, c, RES)["c1"]
    none = gr.check_sample({"results": [res("c1", "partial", "")]}, c, RES)["c1"]
    assert ok["status"] == "met" and ok["grounded"] and ok["quote"] == Q
    assert bad["status"] == "ungrounded" and bad["claimed"] == "met" and bad["quote"] == ""      # never shown as a resume line
    assert none["status"] == "ungrounded"


@pytest.mark.parametrize("quote,want", [
    ("Built RAG pipelines with embeddings", True),
    ("built rag pipelines with EMBEDDINGS", True),                               # case
    ("Led a React and Postgres web app used by 10k people", True),
    ("Built RAG pipel", False),                                                  # not word-bounded
    ("pipelines with embeddings and LLMs for 4", False),                         # ends inside a number
    ("ai", False),                                                               # fewer than 3 words, a substring of 'maintain'
    ("RAG pipelines", False),                                                    # 2 words
    ("Built RAG pipelines with embeddings and LLMs for 40 customers Led a React", False),   # crosses two bullets
    ("Built RAG ... Led a React and Postgres", False),                           # ellipsis stitching two bullets
    ("Built RAG pipelines ... LLMs for 40 customers", True),                     # ellipsis inside ONE bullet
    ("Built RAG pipelines with embeddings and LLMs for 40 customers and 90 partners", False),   # invented tail
    ("", False),
])
def test_quote_must_sit_inside_one_resume_segment_word_bounded(quote, want):
    assert gr.ground(quote, RES)[0] is want


def test_formatting_alone_never_downgrades_a_quote():
    r = gr.from_text("Senior Engineer \u00b7 Acme \u2013 2016\u2013Present\nShe\u2019s built \u201cRAG\u201d pipelines for 40 customers")
    assert gr.ground("Senior Engineer, Acme - 2016-Present".replace(",", " \u00b7"), r)[0]
    assert gr.ground("She's built \"RAG\" pipelines for 40 customers", r)[0]
    assert gr.ground("Senior Engineer Acme \u2014 2016\u2013Present", r)[0]            # separator dropped, another dash


def test_a_wrapped_bullet_is_one_segment_but_two_bullets_are_not():
    r = gr.Resume("x", [(gr.norm("Built RAG pipelines with embeddings and LLMs for 40 customers across two continents"), "current_role"),
                        (gr.norm("Led a React app"), "current_role")])
    assert gr.ground("embeddings and LLMs for 40 customers across two continents", r)[0]
    assert not gr.ground("customers across two continents Led a React app", r)[0]


def test_a_skills_only_quote_caps_an_experience_criterion_at_partial():
    r = gr.Resume("x", [(gr.norm("Languages: Python, Go, SQL, TypeScript"), "skills")])
    c = crit(("3+ years of experience with Python in production", "basic", True), ("Python", "basic", True))
    out = gr.check_sample({"results": [res("c1", "met", "Languages: Python, Go, SQL"), res("c2", "met", "Languages: Python, Go, SQL")]}, c, r)
    assert out["c1"]["status"] == "partial" and out["c1"]["capped"] and out["c1"]["claimed"] == "met"
    assert out["c2"]["status"] == "met" and not out["c2"]["capped"]               # a plain skill criterion may rest on the Skills list
    both = gr.Resume("x", [(gr.norm("Languages: Python, Go, SQL"), "skills"), (gr.norm("Languages: Python, Go, SQL in production at Acme"), "current_role")])
    assert gr.check_sample({"results": [res("c1", "met", "Languages: Python, Go, SQL")]}, c[:1], both)["c1"]["status"] == "met"


def test_missing_answer_is_no_answer_not_a_crash():
    c = crit(("a", "basic", True), ("b", "basic", True))
    out = gr.check_sample({"results": [res("c1", "not_met")]}, c, RES)
    assert out["c2"]["status"] == "no_answer" and not out["c2"]["answered"]


def test_ungrounded_runs_are_not_not_met_and_their_quotes_are_never_shown(cache):
    c = crit(("AI/ML in product", "basic", True))
    fake = Scripted([{"results": [res("c1", "met", "Shipped production LLM agents at Hubspot")]}])
    g = gr.grade(c, RES, 5, runner=fake)
    r = g["rows"][0]
    assert r["status"] == "undecided" and r["ungrounded"] == 5 and r["votes"]["not_met"] == 0 and r["votes"]["met"] == 0
    assert r["claimed"] == {"met": 5} and r["quote"] == ""
    assert "claimed met, quotes not found in resume" in r["note"]
    assert g["band"] == "band undecided"                                          # not C/D: nothing was shown to be missing


def test_some_ungrounded_runs_do_not_hide_the_grounded_majority(cache):
    c = crit(("AI/ML in product", "basic", True))
    good, bad = {"results": [res("c1", "met", Q)]}, {"results": [res("c1", "met", "Invented line about Kubernetes operators")]}
    g = gr.grade(c, RES, 5, runner=Scripted([good, good, good, good, bad]))
    r = g["rows"][0]
    assert r["status"] == "met" and r["ungrounded"] == 1 and "1 of 5" in r["note"] and r["quote"] == Q
    g3 = gr.grade(c, RES, 5, refresh=True, runner=Scripted([good, good, good, bad, bad]))
    assert g3["rows"][0]["status"] == "undecided"                                 # 3 of 5 < 4


# ---- grader runs
def test_one_independent_draw_per_sample_cached_and_refreshable(cache):
    c = crit(("AI/ML in product", "basic", True))
    fake = Scripted([{"results": [res("c1", "met", "Built RAG pipelines with embeddings and LLMs for 40 customers")]}])
    g = gr.grade(c, RES, 5, runner=fake)
    assert fake.calls == 5 and g["rows"][0]["status"] == "met" and g["band"] == "A/B band"
    gr.grade(c, RES, 5, runner=fake)
    assert fake.calls == 5                                      # all five from the cache
    gr.grade(c, RES, 5, refresh=True, runner=fake)
    assert fake.calls == 10                                     # --refresh bypasses


def test_each_grader_sample_has_its_own_cache_key():
    """The keys, not the call count: the samples run in threads, and with one shared key the call count depends on which thread writes first."""
    assert len({tuple(gr._sample_key(i, "")) for i in range(5)}) == 5 and len({tuple(gr._sample_key(0, s)) for s in ("a", "b")}) == 2


def test_only_screenable_criteria_reach_the_grader_and_the_band(cache):
    c = crit(("AI/ML in product", "basic", True), ("comfortable with ambiguity", "basic", False))
    seen = []

    def runner(prompt, model, timeout=300):
        seen.append(prompt)
        return json.dumps({"results": [res("c1", "met", "Built RAG pipelines with embeddings and LLMs for 40 customers")]})
    g = gr.grade(c, RES, 2, runner=runner)
    assert "ambiguity" not in seen[0] and "c1: AI/ML" in seen[0] and RESUME in seen[0]
    assert g["band"] == "A/B band" and g["basic_total"] == 1
    assert g["rows"][1]["screenable"] is False and "status" not in g["rows"][1]


def test_too_few_runs_succeed_means_undecided_and_says_why(cache):
    c = crit(("AI/ML in product", "basic", True))
    n = [0]

    def flaky(prompt, model, timeout=300):
        n[0] += 1
        if n[0] > 3:
            raise llm.LLMError("rate limited")
        return json.dumps({"results": [res("c1", "not_met")]})
    g = gr.grade(c, RES, 5, runner=flaky)
    assert g["rows"][0]["status"] == "undecided" and g["runs_ok"] == 3 and any("3 of 5" in e for e in g["errors"])


# ---- master attribution
def test_master_id_comes_from_the_bullet_the_quoted_line_is_cut_from():
    m = Master(support=[Line("Built RAG pipelines on embeddings and LLMs serving 40 enterprise customers", "bullet", "KPE-03"),
                        Line("Led React and Postgres web apps", "bullet", "KPE-07"),
                        Line("Python, Go, SQL", "skills", "Languages")])
    assert gr.master_id("Built RAG pipelines with embeddings and LLMs for 40 customers", m) == "KPE-03"
    assert gr.master_id("Led a React and Postgres web app used by 10k people", m) == "KPE-07"
    assert gr.master_id("Climbed Everest twice", m) == ""
    assert gr.master_id("Spoke about React at a gardening conference", m) == ""       # one shared word is below the floor
    assert gr.master_id("anything", None) == ""


def test_tally_attributes_master_only_when_given(cache):
    c = crit(("AI/ML in product", "basic", True))
    q = Q
    m = Master(support=[Line("Built RAG pipelines on embeddings and LLMs serving 40 enterprise customers", "bullet", "KPE-03")])
    fake = Scripted([{"results": [res("c1", "met", q)]}])
    assert gr.grade(c, RES, 3, master=m, runner=fake)["rows"][0]["master_id"] == "KPE-03"
    assert gr.grade(c, RES, 3, runner=fake)["rows"][0]["master_id"] is None


# ---- criteria: verbatim check, pinning
def test_a_criterion_must_be_a_piece_of_one_jd_bullet():
    u = cr.jd_units(JD)
    assert cr.is_verbatim("5+ years of professional software development", u)
    assert cr.is_verbatim("  HANDS-ON experience   applying AI/ML in product ", u)             # case + whitespace
    assert cr.is_verbatim("Hands-on experience applying AI/ML in product", u)                  # without the parenthesis: a clause
    assert cr.is_verbatim("Rails/React/Postgres/AWS is a plus", u)
    assert not cr.is_verbatim("Experience building agentic copilots", u)                       # coined
    assert not cr.is_verbatim("software development Hands-on experience", u)                   # spans two bullets
    assert not cr.is_verbatim("professional software development", [cr.Unit(cr.norm("something else"), "")])


def gen_runner(rows):
    r = Scripted([{"criteria": rows}])
    return r


def test_generate_rejects_coined_and_keeps_verbatim(cache):
    rows = [{"text": "5+ years of professional software development", "level": "basic", "screenable": True},
            {"text": "Proven track record of agentic copilots", "level": "basic", "screenable": True},
            {"text": "Independent and comfortable with ambiguity", "level": "basic", "screenable": False},
            {"text": "Startup experience", "level": "preferred", "screenable": True}]
    crit, rejected = cr.generate(JD, runner=gen_runner(rows), safe=True)
    assert [c.text for c in crit] == ["5+ years of professional software development", "Independent and comfortable with ambiguity", "Startup experience"]
    assert [c.id for c in crit] == ["c1", "c2", "c3"] and not crit[1].screenable
    assert len(rejected) == 1 and "agentic copilots" in rejected[0]["text"]


def test_generate_fails_closed_without_a_sandbox_or_without_usable_rows(cache):
    with pytest.raises(cr.CriteriaError, match="self-check"):
        cr.generate(JD, runner=gen_runner([]), safe=False)
    with pytest.raises(cr.CriteriaError, match="no usable"):
        cr.generate(JD, runner=gen_runner([{"text": "invented", "level": "basic", "screenable": True}]), safe=True)


ROWS = [{"text": "5+ years of professional software development", "level": "basic", "screenable": True},
        {"text": "Startup experience", "level": "preferred", "screenable": True}]


def test_pinned_file_is_written_next_to_the_jd_and_respected(cache):
    d = cache / "jds"
    d.mkdir()
    fake = gen_runner(ROWS)
    c1, _, info = cr.get(JD, d, runner=fake, safe=True)
    f = Path(info["path"])
    assert f.parent == d and f.name == f"criteria-{cr.jd_sha12(JD)}.yaml" and info["source"] == "generated" and fake.calls == 1
    f.write_text(f.read_text().replace("Startup experience", "Startup experience").replace("5+ years of professional", "5+ years of professional"))
    # a hand edit: drop the preferred one, flip the first to not screenable
    import yaml
    doc = yaml.safe_load(f.read_text())
    doc["criteria"] = [{**doc["criteria"][0], "screenable": False, "id": "mine"}]
    f.write_text(yaml.safe_dump(doc))
    c2, _, info2 = cr.get(JD, d, runner=fake, safe=True)
    assert fake.calls == 1 and info2["source"] == "pinned"            # no regeneration without the flag
    assert [(c.id, c.screenable) for c in c2] == [("mine", False)] and len(c2) == 1


def test_recriteria_regenerates_and_overwrites_the_edits(cache):
    d = cache / "jds"
    d.mkdir()
    fake = gen_runner(ROWS)
    _, _, info = cr.get(JD, d, runner=fake, safe=True)
    Path(info["path"]).write_text("criteria: [{text: 'Startup experience', level: preferred}]\n")
    _, _, info2 = cr.get(JD, d, recriteria=True, runner=fake, safe=True)
    assert fake.calls == 2 and info2["source"] == "regenerated"
    assert "5+ years" in Path(info["path"]).read_text()


def test_a_coined_criterion_in_a_hand_edited_file_is_kept_and_flagged(cache):
    d = cache / "jds"
    d.mkdir()
    cr.path_for(d, JD).write_text("criteria:\n- {text: 'Owns the roadmap for agentic copilots', level: basic}\n")
    c, _, _ = cr.get(JD, d, runner=gen_runner(ROWS), safe=True)
    assert len(c) == 1 and c[0].coined


@pytest.mark.parametrize("body", ["criteria: [{text: x, level: maybe}]", "just: text", "criteria: []", "criteria: [: bad"])
def test_a_malformed_pinned_file_is_a_bad_input_not_a_regeneration(cache, body):
    d = cache / "jds"
    d.mkdir()
    cr.path_for(d, JD).write_text(body)
    fake = gen_runner(ROWS)
    with pytest.raises(cr.PinnedFileError):
        cr.get(JD, d, runner=fake, safe=True)
    assert fake.calls == 0


# ---- stability
def test_stability_flip_rate_is_the_share_of_runs_off_the_modal_status(cache):
    c = crit(("a", "basic", True), ("b", "basic", True))
    q = "Built RAG pipelines with embeddings and LLMs for 40 customers"
    # every draw says met for c1; for c2 the draws alternate so a 5-run vote is mostly undecided
    seq = []
    for i in range(30):
        seq.append({"results": [res("c1", "met", q), res("c2", "met", q) if i % 2 else res("c2", "not_met")]})
    st = gr.stability(c, RES, 3, 5, runner=Scripted(seq))
    by = {x["id"]: x for x in st["criteria"]}
    assert by["c1"]["flip_rate"] == 0 and by["c1"]["modal"] == "met" and by["c1"]["sample_disagreement"] == 0
    assert by["c2"]["sample_disagreement"] > 0 and st["k"] == 3 and sum(st["bands"].values()) == 3


def test_stability_runs_are_fresh_each_and_leave_the_normal_cache_alone(cache):
    c = crit(("a", "basic", True))
    fake = Scripted([{"results": [res("c1", "not_met")]}])
    gr.grade(c, RES, 2, runner=fake)
    base = fake.calls
    gr.stability(c, RES, 3, 2, runner=fake)
    assert fake.calls == base + 6                                # 3 runs x 2 draws, none served from cache
    gr.grade(c, RES, 2, runner=fake)
    assert fake.calls == base + 6                                # the ordinary cache entries survived


# ---- CLI + report
def cli_run(tmp_path, runner, *extra, resume="clean.pdf", jd_text=JD):
    jd = tmp_path / "jds" / "jd.txt"
    jd.parent.mkdir(exist_ok=True)
    jd.write_text(jd_text)
    out = tmp_path / "out"

    def fake_run(argv, input=None, **kw):
        # patch where the default runner is BOUND (see test_samples.fake_claude): jd_reqs/ai bind llm.run_claude at import
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": runner(input, "m") or "{}", "is_error": False}), stderr="")
    shim = types.SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(llm, "subprocess", shim)
        rc = cli.main(["--resume", str(FX / resume), "--jd", str(jd), "--out", str(out), *extra])
    return rc, out


def p3_runner(resume_quote):
    def run(prompt, model, timeout=300):
        if "screening criteria" in prompt:
            return json.dumps({"criteria": ROWS + [{"text": "Independent and comfortable with ambiguity", "level": "basic", "screenable": False}]})
        if "qualification grader" in prompt:
            return json.dumps({"results": [res("c1", "met", resume_quote), res("c2", "not_met")]})
        if "extract hiring requirements" in prompt:
            return json.dumps({"title": "T", "location": "x", "requirements": [{"term": f"t{i}", "aliases": [], "kind": "skill", "importance": "required"} for i in range(6)], "knockouts": {}})
        return json.dumps({"grade": "B", "top_reasons": []})
    return run


def clean_line():
    return "Built a tool-calling agent platform on Python and Go serving 40 internal teams."


def test_report_has_the_p3_block_above_the_keyword_sections(cache):
    rc, out = cli_run(cache, p3_runner(clean_line()), "--grade-samples", "3")
    assert rc == 0
    md = (out / "report.md").read_text()
    assert "## P3 qualification grader" in md and md.index("## P3") < md.index("## Top fixes") < md.index("## Hard requirements")
    assert "A/B band" in md and "If this employer runs per-qualification grading" in md and "arXiv 2509.00462" in md
    assert "comfortable with ambiguity" in md.split("Not screenable")[1] and "Startup experience" in md
    d = json.loads((out / "report.json").read_text())
    p3 = d["p3"]
    assert p3["band"] == "A/B band" and p3["basic_total"] == 1 and p3["n"] == 3 and p3["need"] == 3
    assert (cache / "jds" / f"criteria-{cr.jd_sha12(JD)}.yaml").exists()


def test_grade_samples_and_recriteria_reach_the_steps(cache):
    calls = {"criteria": 0, "grade": 0}
    inner = p3_runner(clean_line())

    def run(prompt, model, timeout=300):
        for k, marker in (("criteria", "screening criteria"), ("grade", "qualification grader")):
            if marker in prompt:
                calls[k] += 1
        return inner(prompt, model, timeout)
    cli_run(cache, run, "--grade-samples", "4")
    assert calls == {"criteria": 1, "grade": 4}
    cli_run(cache, run, "--grade-samples", "4")
    assert calls == {"criteria": 1, "grade": 4}                       # pinned + cached
    cli_run(cache, run, "--grade-samples", "4", "--recriteria")
    assert calls["criteria"] == 2
    cli_run(cache, run, "--grade-samples", "4", "--refresh")
    assert calls["grade"] == 8


def test_no_llm_skips_p3_and_a_failed_selfcheck_blocks_it(cache, monkeypatch):
    seen = []
    rc, out = cli_run(cache, lambda *a, **k: seen.append(1), "--no-llm")
    assert rc == 0 and not seen and json.loads((out / "report.json").read_text())["p3"] == {"skipped": "--no-llm"}
    # a PINNED file skips the generation step, so the grader must run its own sandbox check
    d = cache / "jds"
    cr.path_for(d, JD).write_text("criteria: [{text: 'Startup experience', level: preferred}]\n")
    monkeypatch.setattr(llm, "self_check", lambda *a, **k: False)
    graded = []
    rc, out = cli_run(cache, lambda p, m, t=0: graded.append(p) or p3_runner("x")(p, m))
    p3 = json.loads((out / "report.json").read_text())["p3"]
    assert "self-check" in p3["error"] and not any("qualification grader" in p for p in graded)


def test_a_malformed_pinned_file_exits_2_before_any_llm_call(cache):
    d = cache / "jds"
    d.mkdir()
    cr.path_for(d, JD).write_text("criteria: []")
    seen = []
    rc, _ = cli_run(cache, lambda p, m, t=0: seen.append(p) or p3_runner("x")(p, m))
    assert rc == 2 and seen == []


def test_stability_flag_prints_and_writes_flip_rates(cache, capsys):
    rc, out = cli_run(cache, p3_runner(clean_line()), "--grade-samples", "2", "--stability", "2")
    assert rc == 0
    printed = capsys.readouterr().out
    assert "P3 stability: 2 fresh gradings" in printed and "flip 0%" in printed
    assert json.loads((out / "stability.json").read_text())["k"] == 2


def test_master_column_flags_a_line_with_no_master_bullet(cache, tmp_path):
    master = tmp_path / "Me — master resume.md"
    master.write_text("# Master\n\n## 4. Experience\n### R\n- **KPE-01** Something unrelated about quantum gardening\n")
    rc, out = cli_run(cache, p3_runner(clean_line()), "--grade-samples", "2", "--master", str(master))
    md = (out / "report.md").read_text()
    assert "Master id" in md and "NOT TRACEABLE" in md


# ---- review round: criteria verification, pins, prompt hygiene, wiring
SECTIONED = """Engineer

What You'll Do
- Build agents for customers and own them from design to launch

Required Qualifications
- 5+ years of professional software development
- No degree is required but you must have shipped production systems
- Experience with Kubernetes

Even Better If You Have:
- Startup experience
"""


def v(text, jd=SECTIONED, level=None):
    return cr.verify(text, cr.jd_units(jd), level)


def test_jd_units_know_the_qualification_sections():
    kinds = {u.text: u.kind for u in cr.jd_units(SECTIONED)}
    assert kinds["5+ years of professional software development"] == "basic" and kinds["startup experience"] == "preferred"
    assert kinds["build agents for customers and own them from design to launch"] == ""


@pytest.mark.parametrize("text,ok", [
    ("5+ years of professional software development", True),
    ("Experience with Kubernetes", True),
    ("Startup experience", True),                          # 2 words but the whole bullet
    ("software development", False),                       # 2 words, a fragment
    ("5+ years of professional", True),                    # 4 words, word-bounded clause
    ("5+ years of profession", False),                     # not word-bounded
    ("own them from design to launch", False),             # a duty, not in a qualification section
    ("must have shipped production systems", False),       # drops "No degree is required but"
    ("No degree is required but you must have shipped production systems", True),
    ("Experience with Rust", False),
])
def test_verbatim_check_rules(text, ok):
    assert v(text)[0] is ok


def test_level_is_cross_checked_against_the_jd_heading():
    assert v("Startup experience", level="preferred")[2] == []
    flags = v("Startup experience", level="basic")[2]
    assert flags and flags[0].startswith("level_mismatch")
    assert v("Experience with Kubernetes", level="preferred")[2]


def test_a_jd_without_qualification_sections_is_verified_as_present_only(cache):
    flat = "Great job\n- Build things with Python every day\n- Be nice\n"
    assert cr.sectioned(cr.jd_units(flat)) is False and v("Build things with Python every day", flat)[0]
    d = cache / "j"
    _, _, info = cr.get(flat, d, runner=gen_runner([{"text": "Build things with Python every day", "level": "basic", "screenable": True}]), safe=True)
    assert "present in the JD only" in info["verified"]
    d2 = cache / "j2"
    _, _, info2 = cr.get(JD, d2, runner=gen_runner(ROWS), safe=True)
    assert "inside a qualification section" in info2["verified"]


def test_generate_rejects_short_fragments_and_dropped_negations(cache):
    rows = [{"text": "software development", "level": "basic", "screenable": True},
            {"text": "must have shipped production systems", "level": "basic", "screenable": True},
            {"text": "Experience with Kubernetes", "level": "basic", "screenable": True}]
    crit_, rej = cr.generate(SECTIONED, runner=gen_runner(rows), safe=True)
    assert [c.text for c in crit_] == ["Experience with Kubernetes"]
    assert {r["text"] for r in rej} == {"software development", "must have shipped production systems"}


def test_recriteria_keeps_the_previous_file_as_bak(cache):
    d = cache / "jds"
    d.mkdir()
    fake = gen_runner(ROWS)
    _, _, info = cr.get(JD, d, runner=fake, safe=True)
    f = Path(info["path"])
    f.write_text(f.read_text() + "# my hand edit\n")
    _, _, info2 = cr.get(JD, d, recriteria=True, runner=fake, safe=True)
    bak = Path(info2["backup"])
    assert bak.name.endswith(".yaml.bak") and "# my hand edit" in bak.read_text() and "# my hand edit" not in f.read_text()


def test_prompt_substitution_is_single_pass():
    p = gr.render_prompt("c1: mentions {resume} literally", "RESUME BODY {criteria}")
    assert "c1: mentions {resume} literally" in p and p.count("RESUME BODY") == 1 and "RESUME BODY {criteria}" in p


def test_criteria_are_shuffled_per_sample_and_the_cache_key_names_the_model(cache, monkeypatch):
    c = crit(*[(f"criterion number {i}", "basic", True) for i in range(8)])
    prompts = []

    def runner(prompt, model, timeout=300):
        prompts.append(prompt)
        return json.dumps({"results": []})
    gr.grade(c, RES, 4, runner=runner)
    orders = {tuple(re.findall(r"^(c\d+):", p, re.M)) for p in prompts}
    assert len(orders) > 1 and all(sorted(o) == sorted(f"c{i}" for i in range(1, 9)) for o in orders)
    n = len(prompts)
    gr.grade(c, RES, 4, runner=runner)
    assert len(prompts) == n                                      # same seeds, same keys: cached
    monkeypatch.setattr(gr, "MODEL", "opus")
    gr.grade(c, RES, 4, runner=runner)
    assert len(prompts) == n + 4                                  # another model never reads sonnet's draws


def test_each_stability_invocation_uses_its_own_salt(cache):
    c = crit(("a", "basic", True))
    fake = Scripted([{"results": [res("c1", "not_met")]}])
    gr.stability(c, RES, 2, 2, runner=fake)
    files = len(list((llm.CACHE / "llm").glob("grade-*.json")))
    gr.stability(c, RES, 2, 2, runner=fake)
    assert len(list((llm.CACHE / "llm").glob("grade-*.json"))) == 2 * files and files == 4


def test_master_reaches_the_grader_through_the_cli(cache, tmp_path):
    master = tmp_path / "Me — master resume.md"
    master.write_text("# Master\n\n## 4. Experience\n### R\n- **KPE-42** Built a tool-calling agent platform on Python and Go serving 40 internal teams.\n")
    rc, out = cli_run(cache, p3_runner(clean_line()), "--grade-samples", "2", "--master", str(master))
    p3 = json.loads((out / "report.json").read_text())["p3"]
    assert p3["rows"][0]["master_id"] == "KPE-42" and "KPE-42" in (out / "report.md").read_text()


def test_a_fetched_jd_is_pinned_by_its_sha_in_the_cache_not_in_the_output_dir(cache, monkeypatch):
    monkeypatch.setattr(cli.jd_fetch, "fetch_url", lambda url: JD)
    jd_calls = []
    inner = p3_runner(clean_line())

    def run(prompt, model, timeout=300):
        jd_calls.append(prompt)
        return inner(prompt, model, timeout)
    shim_run = lambda argv, input=None, **kw: subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": run(input, "m"), "is_error": False}), stderr="")
    outs = []
    for name in ("out1", "out2"):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(llm, "subprocess", types.SimpleNamespace(run=shim_run, TimeoutExpired=subprocess.TimeoutExpired))
            assert cli.main(["--resume", str(FX / "clean.pdf"), "--jd-url", "https://x.test/job", "--out", str(cache / name), "--grade-samples", "2"]) == 0
        outs.append(cache / name)
    pin = llm.CACHE / "criteria" / f"criteria-{cr.jd_sha12(JD)}.yaml"
    assert pin.exists() and not list(outs[0].glob("criteria-*")) and not list(outs[1].glob("criteria-*"))
    assert sum("screening criteria" in p for p in jd_calls) == 1          # the second resume reused the pin
    assert str(pin) in json.loads((outs[1] / "report.json").read_text())["p3"]["criteria_file"]["path"]


def test_the_report_names_ungrounded_claims_and_never_prints_the_rejected_quote(cache):
    fabricated = "Architected the Kubernetes operator fleet at Hubspot for 90 teams"
    rc, out = cli_run(cache, p3_runner(fabricated), "--grade-samples", "3")
    md = (out / "report.md").read_text()
    assert rc == 0 and "model claimed met, quotes not found in resume" in md and fabricated not in md
    p3 = json.loads((out / "report.json").read_text())["p3"]
    assert p3["rows"][0]["status"] == "undecided" and p3["band"] == "band undecided" and p3["shuffled_per_sample"] is True
