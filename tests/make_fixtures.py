"""Regenerate tests/fixtures/*.pdf with typst (+ PyMuPDF for the ToUnicode strip).

Run: uv run python tests/make_fixtures.py   (needs `typst` on PATH)
The fixtures are committed; this script is how they were made and how to change them.
"""
from __future__ import annotations

import subprocess
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


# Line shapes seen in a real 2-page LaTeX resume under the line-based extractors: a bullet whose wrapped
# continuation line carries a date (lowercase start, month-name start, year at the end), and a bare "1/2" page
# footer between two bullets of one role. Explicit line breaks pin the wrap points, so every extractor sees them.
WRAPPED_JOBS = [
    ("Senior AI Engineer", "Acme Robotics", "Jan 2022 – Present", [
        "In a benchmark of 15 buyer questions, an AI assistant named Acme in 15 of 15 answers, and\\ of them first in 10, in a November 2026 re-test; Jane built its site and profile.",
        "Ran a gap analysis of which buyer questions AI answers covered without Acme, then set the\\ content strategy for them: answer pages with linked supporting pages.",
        "Moved the outside writing and design work to AI agents under Jane's briefs and review: a\\ fact-checker and a readability editor check each page before it is published.",
        "Grew the docs site to 1.2M visits through a rewrite of its structure; the work started in\\ November 2024, and has been done by Jane hands-on for 10+ years.",
        "Led the editorial team of three to five as editor-in-chief from 2019 to 2021, briefing its writers\\ editing their work, and led editorial work again by 2022.",
        "Designed an evaluation harness that gates every release and a retrieval pipeline on pgvector.",
    ]),
    ("Software Engineer", "Globex Corporation", "Mar 2019 – Dec 2021", [
        "Owned the billing workflow service in Go; reduced incident count by half.",
        "Built a certified office-document pipeline for finance customers on PostgreSQL.",
    ]),
]


def wrapped():
    j1, j2 = WRAPPED_JOBS
    pre = PRE(False).replace('margin: (x: 18mm, y: 16mm))', 'margin: (x: 18mm, y: 16mm), footer: align(right)[#context counter(page).display("1/1", both: true)])')
    b1, b2 = j1[3][:3], j1[3][3:]
    role1 = f"#grid(columns: (1fr, auto), [*{j1[0]}*, {j1[1]}], [{j1[2]}])\n{bullets(b1)}\n#pagebreak()\n{bullets(b2)}\n"
    return pre + header() + summary() + "#sech[EXPERIENCE]\n" + role1 + job_block(j2) + education() + skills()


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
        "wrapped_bullets": wrapped(),
    }
    for name, src in jobs.items():
        compile_typ(src, OUT / f"{name}.pdf")
    strip_tounicode(OUT / "clean.pdf", OUT / "no_tounicode.pdf")
    tmp_lig = OUT / "_lig.pdf"
    (OUT / "ligatures.pdf").rename(tmp_lig)
    ligature_codepoints(tmp_lig, OUT / "ligatures.pdf")
    tmp_lig.unlink()
    print("ok", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
