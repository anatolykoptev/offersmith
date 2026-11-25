"""Regenerate tests/fixtures/*.pdf with typst (+ PyMuPDF for the ToUnicode strip).

Run: uv run python tests/make_fixtures.py   (needs `typst` on PATH)
The fixtures are committed; this script is how they were made and how to change them.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

OUT = Path(__file__).parent / "fixtures"

NAME = "Jane Q. Example"
HEAD = "Senior AI Platform Engineer"
EMAIL = "jane.example\\@example.com"
PHONE = "(415) 555-0142"
LINKS = "linkedin.com/in/janeexample · github.com/janeexample"
CITY = "San Francisco, CA"

SUMMARY = ("Engineer who ships LLM agents and Model Context Protocol (MCP) servers to production. "
           "Led workflow automation, retrieval pipelines and evaluation harnesses for enterprise customers.")

JOBS = [
    ("Senior AI Engineer", "Acme Robotics", "Jan 2022 – Present", [
        "Built a tool-calling agent platform on Python and Go serving 40 internal teams.",
        "Shipped an MCP server exposing 35 tools to coding agents; cut review time 30%.",
        "Designed retrieval with pgvector and evaluation sets that gate every release.",
    ]),
    ("Software Engineer", "Globex Corporation", "Mar 2019 – Dec 2021", [
        "Owned the billing workflow service in Go; reduced incident count by half.",
        "Built a certified office-document pipeline for finance customers on PostgreSQL.",
    ]),
]
EDU = [("B.S. Computer Science", "State University", "2015 – 2019")]
SKILLS = ["Languages: Python, Go, TypeScript, SQL",
          "AI: LLM agents, MCP, retrieval, evaluation, prompt engineering",
          "Infra: PostgreSQL, Docker, AWS, Kubernetes"]


def esc(s: str) -> str:
    return s.replace("#", "\\#").replace("$", "\\$").replace("@", "\\@")


PRE = lambda lig: f"""#set page(paper: "us-letter", margin: (x: 18mm, y: 16mm))
#set text(size: 10pt, ligatures: {str(lig).lower()})
#set par(leading: 0.55em, spacing: 0.8em)
#set list(indent: 6pt)
#let sech(t) = block(above: 1.1em, below: 0.5em)[#text(weight: "bold", size: 11pt)[#t] #v(-0.4em) #line(length: 100%, stroke: 0.5pt)]
"""


def bullets(bs):
    return "\n".join(f"- {esc(b)}" for b in bs)


def header(contact=True, icons=False):
    s = f"#text(size: 18pt, weight: \"bold\")[{NAME}]\n\n{HEAD}\n\n"
    if contact:
        if icons:
            s += f"✉ {EMAIL} ☎ {PHONE} · {CITY}\n\n"
        else:
            s += f"{CITY} · {EMAIL} · {PHONE} · {LINKS}\n\n"
    return s


def job_block(j, season=False):
    t, c, d, bs = j
    if season:
        d = d.replace("Jan 2022", "Spring '22").replace("Present", "Fall '24").replace("Mar 2019", "Spring '19").replace("Dec 2021", "Fall '21")
    return f"#grid(columns: (1fr, auto), [*{t}*, {c}], [{d}])\n{bullets(bs)}\n"


def experience(heading="EXPERIENCE", season=False, table=False):
    s = f"#sech[{heading}]\n"
    if table:
        rows = ",\n".join(f"[{j[2]}], [*{j[0]}*, {j[1]}\n{bullets(j[3])}\n]" for j in JOBS)
        return s + f"#table(columns: (30mm, 1fr), stroke: 0.5pt, inset: 6pt, {rows})\n"
    return s + "".join(job_block(j, season) for j in JOBS)


def education():
    return "#sech[EDUCATION]\n" + "".join(f"#grid(columns: (1fr, auto), [*{d}*, {s}], [{y}])\n" for d, s, y in EDU)


def skills():
    return "#sech[SKILLS]\n" + "\n\n".join(esc(x) for x in SKILLS) + "\n"


def summary():
    return f"#sech[SUMMARY]\n{SUMMARY}\n"


def clean(lig=False, heading="EXPERIENCE", season=False, icons=False):
    return PRE(lig) + header(icons=icons) + summary() + experience(heading, season) + education() + skills()


def two_col():
    left = header(contact=True) .replace(f"{CITY} · {EMAIL} · {PHONE} · {LINKS}", f"{CITY}\n\n{EMAIL}\n\n{PHONE}\n\n{LINKS.split(' · ')[0]}") + education() + skills()
    right = summary() + experience()
    return PRE(False) + f"#grid(columns: (58mm, 1fr), column-gutter: 10mm, [\n{left}\n], [\n{right}\n])\n"


def table():
    return PRE(False) + header() + summary() + experience(table=True) + education() + skills()


def header_contact():
    body = f"#text(size: 18pt, weight: \"bold\")[{NAME}]\n\n{HEAD}\n\n" + summary() + experience() + education() + skills()
    pre = PRE(False).replace('#set page(paper: "us-letter", margin: (x: 18mm, y: 16mm))',
        f'#set page(paper: "us-letter", margin: (x: 18mm, top: 24mm, bottom: 16mm), header: [{CITY} · {EMAIL} · {PHONE} · {LINKS}])')
    return pre + body


def skills_image():
    return PRE(False) + header() + summary() + experience() + education() + '#sech[SKILLS]\n#image("skills.png", width: 70%)\n'


# ---- layout shapes the line-based extractors flatten: a wrapped bullet row beside a role header, a page footer -----------
# Every row break is forced (`\\ `), so each extractor gets the same rows. A wrapped row sits at the bullet's text indent;
# a role header at the margin. Synthetic Jane Example text only.
SHAPE_JOBS = [
    ("Senior AI Engineer", "Acme Robotics", "Jan 2022 – Present", [
        "Built a benchmark of 15 buyer questions that named Acme in 15 of 15 answers, first in 10,\\ in a November 2026 re-test; Jane built its site and profile.",
        "Grew the docs site to 1.2M visits after a rewrite of its structure that started in\\ November 2024, and has been done by Jane hands-on for 10+ years.",
        "Tracked\\ organic clicks between Jul 2025 – Nov 2026",
        "Coordinated with the\\ Product owner in Mar 2019, keeping the team aligned throughout the rollout.",
        "Led integrations for Acme Inc.\\ and improved conversion in Nov 2026.",
        "Coordinated across three teams:\\ engineering and sales in Nov 2026.",
        "Led the editorial team as editor-in-chief\\ from 2019 to 2021, briefing its writers and checking every page before it went live.",
        "Ran a gap analysis of the buyer questions AI answers covered without Acme, and set the\\ Nov 2026 GEO test of 15 questions named Acme first in ten of them, built by Jane.",
        "Moved the outside writing to agents under briefs for the US, the UK and\\ the other regions",
        "Helped the company prepare for SOC\\ 2",
    ]),
    ("iOS Engineer", "Globex Corporation", "Mar 2019 – Dec 2021", [
        "Owned the billing workflow service in Go; reduced incident count by half.",
        "Built a certified office-document pipeline for finance customers on PostgreSQL.",
    ]),
    ("dbt Labs", "Software Engineer", "Jun 2016 – Feb 2019", [
        "Wrote the models behind the revenue dashboards in SQL.",
        "Cut warehouse cost by a third with incremental builds.",
    ]),
    ("macOS Engineer", "Initech", "Mar 2014 – Jan 2016", [
        "Shipped a menu-bar sync client in Swift.",
        "Rewrote the updater so releases roll out in stages.",
    ]),
    ("Mobile Engineer", "Globex Corporation", "2008 – 2013 | remote", [
        "Shipped a Swift app used by 2M people.",
    ]),
]
# plain one-line headers (no grid, no bold): the date first, and one date with a long company name ending in a full stop
PLAIN_JOBS = [
    ("Mar 2012 – Dec 2013  Software Engineer, Hooli", ["Built the ad-ranking service in Java."]),
    ("Mar 2010  Senior Software Engineer, Example Research and Development Inc.", ["Owned the build system for 40 engineers."]),
]


def shapes_experience(jobs=SHAPE_JOBS, plain=PLAIN_JOBS):
    s = "#sech[EXPERIENCE]\n"
    for t, c, d, bs in jobs:
        s += f"#grid(columns: (1fr, auto), [*{t}*, {c}], [{d}])\n{bullets(bs)}\n"
    for head, bs in plain:
        s += f"{head}\n\n{bullets(bs)}\n"
    return s


def with_footer(pre: str, shape: str, bottom: str = "16mm", lead: str = "") -> str:
    """A page footer centred in the bottom margin: shape 'N', 'N of M', 'Page N of M' or 'N/M'; lead is text before it (a
    running footer); a bottom margin of 35mm lifts it out of the 6.5% band a header/footer check looks at."""
    n, m = "#context counter(page).display()", "#context counter(page).final().first()"
    body = lead + {"bare": n, "of": f"{n} of {m}", "page": f"Page {n} of {m}", "slash": f"{n}/{m}"}[shape]
    return pre.replace('margin: (x: 18mm, y: 16mm))', f'margin: (x: 18mm, top: 16mm, bottom: {bottom}), footer: align(center)[{body}])')


def wrap_shapes(footer="page"):
    """Six roles and every wrapped-row shape of the review of the first fix; the number of pages is two."""
    contact = f"{CITY} · {EMAIL}\n\n415\\ 555-0142 · {LINKS}\n\n"
    head = f"#text(size: 18pt, weight: \"bold\")[{NAME}]\n\n{HEAD}\n\n{contact}"
    skills_s = "#sech[SKILLS]\n" + "\n\n".join(esc(x) for x in SKILLS[:1] + ["Cloud: AWS, GCP, Azure, SOC\\ 2\\ , ISO 27001"] + SKILLS[1:]) + "\n"
    return with_footer(PRE(False), footer) + head + summary() + shapes_experience() + education() + skills_s


# Page breaks. `break_page`: a bullet is cut by the break (its third row opens page 2, the footer sits between). `foot_*`: the break
# falls between two plain bullets, so the footer is a row between a bullet and the next bullet. The filler counts are tuned for typst 0.15.
KEY_BULLET = "Built a benchmark of 15 buyer questions that named Acme in 15 of 15 answers, first in 10,\\ wrote up the method and shared it with the whole team,\\ in a November 2026 re-test that Jane built,\\ then ran it again each quarter."


def break_shapes(footer: str, filler: int, key: bool = True, **kw):
    fill = [f"Filler line {i + 1} that keeps the first page full of ordinary work for the client in the quarter." for i in range(filler)]
    role1 = ("Senior AI Engineer", "Acme Robotics", "Jan 2022 – Present", fill + ([KEY_BULLET] if key else []) + ["Shipped another service."])
    return (with_footer(PRE(False), footer, **kw) + header() + summary() + "#sech[EXPERIENCE]\n"
            + job_block(role1) + job_block(JOBS[1]) + education() + skills())


def undated_brand():
    """Two headers with no date, a lowercase brand and a title alone, each right after a bullet: still jobs, and a job with no dates still FAILs."""
    jobs = [("eBay, Staff Engineer", ["Cut checkout latency by a quarter."]), ("iOS Developer", ["Built the first version of the mobile client."])]
    s = PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n" + job_block(JOBS[0])
    for head, bs in jobs:
        s += f"{head}\n\n{bullets(bs)}\n\n"
    return s + education() + skills()


def season_brand():
    """A lowercase-brand header after a bullet with a date no parser reads: the entries check must still FAIL."""
    j = ("Software Engineer", "dbt Labs", "Spring '19 – Fall '21", JOBS[1][3])
    return PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n" + job_block(JOBS[0]) + job_block(j) + education() + skills()


# ---- review of the layout reading (PR #6): layouts where a header is not where the section headings are, and numbers near the page edge
def indented_headers():
    """Role headers padded in under the section rule, with 'Spring' dates nobody reads: the entries check must still FAIL."""
    return (PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n"
            + "".join("#pad(left: 12pt)[" + job_block(j, season=True) + "]\n" for j in JOBS) + education() + skills())


def centered_headers():
    """Role headers centred, one line each (title, company, dates), 'Spring' dates nobody reads."""
    s = PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n"
    for t, c, d, bs in JOBS:
        d = d.replace("Jan 2022", "Spring '22").replace("Present", "Fall '24").replace("Mar 2019", "Spring '19").replace("Dec 2021", "Fall '21")
        s += f"#align(center)[*{t}*, {c}  {d}]\n{bullets(bs)}\n\n"
    return s + education() + skills()


def header_repeats_wrapped_row():
    """The last bullet wraps onto a row that is a company name, and the next job's header opens with the same words."""
    j1 = ("Senior AI Engineer", "Acme Robotics", "Jan 2022 – Present", ["Shipped an MCP server.", "Moved the billing integration over to\\ Globex Corporation"])
    return (PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n" + job_block(j1)
            + "#grid(columns: (1fr, auto), [*Globex Corporation*, Software Engineer], [Mar 2019 – Dec 2021])\n" + bullets(JOBS[1][3]) + "\n" + education() + skills())


def header_at_bullet_text_indent():
    """A plain one-line header indented to the bullets' text x, after a bullet list with paragraph spacing between it and the bullet."""
    return (PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n" + job_block(JOBS[0])
            + "#pad(left: 14.5pt)[Software Engineer, Globex Corporation, Mar 2019 – Dec 2021]\n" + bullets(JOBS[1][3]) + "\n" + education() + skills())


def bold_word_wrap():
    """A wrapped bullet row that opens with a bold word and carries a date."""
    j1 = ("Senior AI Engineer", "Acme Robotics", "Jan 2022 – Present",
          ["Migrated the billing service and its queue workers to\\ *Kubernetes* in Mar 2019, cutting the hosting cost by a third.\\ and then the report jobs too.", "Shipped an MCP server."])
    return PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n" + job_block(j1) + job_block(JOBS[1]) + education() + skills()


def nested_bullets():
    return (PRE(False) + header() + summary() + "#sech[EXPERIENCE]\n#grid(columns: (1fr, auto), [*Senior AI Engineer*, Acme Robotics], [Jan 2022 – Present])\n"
            "- Led the platform team.\n  - Rebuilt the onboarding funnel for the\\ Product owner in Mar 2019, keeping the team aligned.\n"
            "  - Tracked\\ organic clicks between Jul 2025 – Nov 2026\n- Shipped an MCP server.\n" + job_block(JOBS[1]) + education() + skills())


def digit_band(fill=44, bottom="12mm"):
    """A short bottom margin: the body runs into the 6.5% footer band and a stacked date row '2016 – 2019' sits in it."""
    jobs = [("Senior AI Engineer", "Acme Robotics", "2019 – 2024", [f"Filler line {i + 1} that keeps the first page full of ordinary work for the client." for i in range(fill)]),
            ("Software Engineer", "Globex Corporation", "2016 – 2019", ["Owned the billing workflow service in Go.", "Built a pipeline on PostgreSQL."]),
            ("Engineer", "Initech", "2012 – 2016", ["Shipped a sync client."])]
    s = with_footer(PRE(False), "bare", bottom=bottom) + header() + summary() + "#sech[EXPERIENCE]\n"
    for t, c, d, bs in jobs:
        s += f"*{t}*, {c}\n\n{d}\n\n" + bullets(bs) + "\n\n"
    return s + education() + skills()


def band_skill(fill=38, bottom="10mm"):
    """A short bottom margin again: a skills row that is only '808' (a wrapped 'Roland TR 808') falls in the footer band."""
    jobs = [("Senior AI Engineer", "Acme Robotics", "Jan 2019 – Present", [f"Filler line {i + 1} that keeps the page full of ordinary work for the client." for i in range(fill)])]
    s = with_footer(PRE(False), "page", bottom=bottom) + header() + summary() + "#sech[EXPERIENCE]\n" + "".join(job_block(j) for j in jobs)
    s += "Mar 2010  Senior Software Engineer, Example Manufacturing Co.\n\n" + bullets(["Owned the build system."]) + "\n\n"
    return s + education() + "#sech[SKILLS]\nLanguages: Python, Go\n\nDrum machines: Roland TR-909, Roland TR\\ 808\n"


def flat_bullets():
    """Bullets as plain paragraphs: a wrapped row goes back to the margin, so layout has no indent to tell it from a header."""
    s = PRE(False).replace("#set list(indent: 6pt)", "#set par(first-line-indent: 0pt)") + header() + summary() + "#sech[EXPERIENCE]\n"
    for t, c, d, bs in SHAPE_JOBS[:2]:
        s += f"#grid(columns: (1fr, auto), [*{t}*, {c}], [{d}])\n" + "\n\n".join(esc("• " + b) for b in bs) + "\n"
    return s + education() + skills()


def hanging_marker():
    """The bullet marker hangs in the left margin: the bullet's text starts AT the margin, where a role header starts too."""
    s = PRE(False).replace("#set list(indent: 6pt)", "#set list(indent: -9pt, body-indent: 6pt)") + header() + summary() + "#sech[EXPERIENCE]\n"
    for j in SHAPE_JOBS[:2]:
        s += job_block(j)
    return s + education() + skills()


def compile_typ(src: str, out: Path, fmt="pdf", ppi=None):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.typ"
        p.write_text(src)
        if (OUT / "skills.png").exists():
            (Path(d) / "skills.png").write_bytes((OUT / "skills.png").read_bytes())
        cmd = ["typst", "compile", str(p), str(out)]
        if ppi:
            cmd += ["--ppi", str(ppi)]
        subprocess.run(cmd, check=True)


def strip_tounicode(src: Path, dst: Path):
    doc = pymupdf.open(src)
    n = 0
    for xref in range(1, doc.xref_length()):
        if doc.xref_get_key(xref, "ToUnicode")[0] != "null":
            doc.xref_set_key(xref, "ToUnicode", "null")
            n += 1
    assert n, "no ToUnicode found"
    doc.save(dst, garbage=4, deflate=True)


LIG = {"00660066": "FB00", "00660069": "FB01", "0066006C": "FB02", "006600660069": "FB03", "0066006600 6C".replace(" ", ""): "FB04", "00660074": "FB05"}


def ligature_codepoints(src: Path, dst: Path):
    """Rewrite ToUnicode so ligature glyphs extract as U+FB0x (what many Word / LaTeX PDFs do)."""
    import re
    doc = pymupdf.open(src)
    n = 0
    for xref in range(1, doc.xref_length()):
        k = doc.xref_get_key(xref, "ToUnicode")
        if k[0] == "null":
            continue
        ref = int(k[1].split()[0])
        s = doc.xref_stream(ref).decode("latin1")
        def sub(m):
            nonlocal n
            d = m.group(2).upper()
            if d in LIG:
                n += 1
                return f"{m.group(1)}<{LIG[d]}>"
            return m.group(0)
        s2 = re.sub(r"(<[0-9A-Fa-f]+>\s*)<([0-9A-Fa-f]+)>", sub, s)
        doc.update_stream(ref, s2.encode("latin1"))
    assert n, "no ligature mapping found"
    doc.save(dst, garbage=4, deflate=True)


# ---- fixtures for the optional OpenResume layer (tests/test_openresume.py) --------------------------------------------------
# Base "or_clean": a resume OpenResume reads fully (title word without a comma, school and degree on two lines, round bullets).
# Every other or_* fixture differs from it by exactly one defect.
EXTRA = ["Mentored four engineers and ran the weekly architecture review.", "Wrote the on-call runbook adopted by three teams."]
OR_JOBS = [(t, c, d, bs + EXTRA) for t, c, d, bs in JOBS]    # enough bullet gaps that the usual line gap is the mode, as in a real resume


def or_job(j, gap=False):
    t, c, d, bs = j
    body = "\n".join(f"- {esc(b)}" for b in bs)
    if gap:                                   # a vertical gap inside one role, larger than 1.4x the usual line gap
        first, rest = bs[0], bs[1:]
        body = f"- {esc(first)}\n#v(0.9em)\n" + "\n".join(f"- {esc(b)}" for b in rest)
    return f"#grid(columns: (1fr, auto), [*{t}* | {c}], [{d}])\n{body}\n"


def or_education(oneline=False):
    d, sch, y = EDU[0]
    if oneline:
        return f"#sech[EDUCATION]\n#grid(columns: (1fr, auto), [*BBA, {sch}*], [{y}])\n"
    return f"#sech[EDUCATION]\n#grid(columns: (1fr, auto), [*{sch}*], [{y}])\n{d}\n"


def or_resume(gap=False, dash=False, oneline_edu=False, pagebreak=False, background=False):
    pre = PRE(False)
    if dash:
        pre += '#set list(marker: [–])\n'
    jobs = [or_job(OR_JOBS[0], gap=gap), ("#pagebreak()\n" if pagebreak else "#v(0.9em)\n") + or_job(OR_JOBS[1])]
    head = header()
    if background:   # a heading OpenResume does not take for work experience, and a comma right after the email
        head = head.replace(f"{EMAIL} · {PHONE}", f"{EMAIL}, +1 {PHONE}")
    return (pre + head + summary() + f"#sech[{'PROFESSIONAL BACKGROUND' if background else 'EXPERIENCE'}]\n" + "".join(jobs) + or_education(oneline_edu) + skills())


def wordwise(src: Path, dst: Path):
    """Re-typeset every word of `src` at its own absolute position, so each word gets its own text matrix (what LaTeX font expansion
    does): pdf.js then returns one item per word and a distance-based joiner such as OpenResume's glues them."""
    doc = pymupdf.open(src)
    placed = []
    for b in doc[0].get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                cur = []
                for ch in sp["chars"] + [{"c": " "}]:
                    if ch["c"] == " ":
                        if cur:
                            w = "".join(c["c"] for c in cur).replace("\\", "\\\\").replace('"', '\\"')
                            placed.append(f'#place(top + left, dx: {cur[0]["origin"][0]:.2f}pt, dy: {cur[0]["origin"][1]:.2f}pt, '
                                          f'text(size: {sp["size"]:.2f}pt, weight: "{"bold" if sp["flags"] & 16 else "regular"}", "{w}"))')
                        cur = []
                    else:
                        cur.append(ch)
    typ = ('#set page(paper: "us-letter", margin: 0pt)\n#set text(ligatures: false, top-edge: "baseline", bottom-edge: "baseline")\n'
           + "\n".join(placed) + "\n")
    compile_typ(typ, dst)


def main():
    OUT.mkdir(exist_ok=True)
    # skills image first (a PNG of the skills block)
    tmp = PRE(False).replace('margin: (x: 18mm, y: 16mm)', 'width: 120mm, height: auto, margin: 4mm') + "\n\n".join(esc(x) for x in SKILLS)
    compile_typ(tmp, OUT / "skills.png", ppi=200)
    jobs = {
        "clean": clean(),
        "two_column": two_col(),
        "table_experience": table(),
        "header_contact": header_contact(),
        "ligatures": clean(lig=True),
        "heading_renamed": clean(heading="My Journey"),
        "dates_season": clean(season=True),
        "skills_image": skills_image(),
        "icon_contact": clean(icons=True),
        "wrap_shapes": wrap_shapes("page"),
        "break_page": break_shapes("page", 44),
        "foot_bare": break_shapes("bare", 47, key=False),
        "foot_of": break_shapes("of", 47, key=False),
        "foot_page": break_shapes("page", 47, key=False),
        "foot_slash": break_shapes("slash", 47, key=False),
        "foot_high": break_shapes("slash", 42, key=False, bottom="35mm"),
        "foot_running": break_shapes("page", 47, key=False, lead="Jane Q. Example · "),
        "foot_single": with_footer(PRE(False), "page") + header() + summary() + experience() + education() + skills(),
        "indented_headers": indented_headers(),
        "centered_headers": centered_headers(),
        "header_repeats_wrapped_row": header_repeats_wrapped_row(),
        "header_at_bullet_text_indent": header_at_bullet_text_indent(),
        "bold_word_wrap": bold_word_wrap(),
        "nested_bullets": nested_bullets(),
        "digit_band": digit_band(),
        "band_skill": band_skill(),
        "season_brand": season_brand(),
        "undated_brand": undated_brand(),
        "flat_bullets": flat_bullets(),
        "hanging_marker": hanging_marker(),
    }
    jobs.update({
        "or_clean": or_resume(),
        "or_endash": or_resume(dash=True),
        "or_gap": or_resume(gap=True),
        "or_oneline_edu": or_resume(oneline_edu=True),
        "or_pagebreak": or_resume(pagebreak=True),
        "or_background": or_resume(background=True),
    })
    only = set(sys.argv[1:])   # `make_fixtures.py wrap_shapes break_of` rebuilds just those (a newer typst changes the bytes of the others)
    for name, src in jobs.items():
        if not only or name in only:
            compile_typ(src, OUT / f"{name}.pdf")
    if not only or "or_wordwise" in only:
        wordwise(OUT / "or_clean.pdf", OUT / "or_wordwise.pdf")
    if only:
        print("ok", sorted(only))
        return
    strip_tounicode(OUT / "clean.pdf", OUT / "no_tounicode.pdf")
    tmp_lig = OUT / "_lig.pdf"
    (OUT / "ligatures.pdf").rename(tmp_lig)
    ligature_codepoints(tmp_lig, OUT / "ligatures.pdf")
    tmp_lig.unlink()
    print("ok", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
