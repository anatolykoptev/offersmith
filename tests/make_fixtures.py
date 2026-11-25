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
    }
    jobs.update({
        "or_clean": or_resume(),
        "or_endash": or_resume(dash=True),
        "or_gap": or_resume(gap=True),
        "or_oneline_edu": or_resume(oneline_edu=True),
        "or_pagebreak": or_resume(pagebreak=True),
        "or_background": or_resume(background=True),
    })
    for name, src in jobs.items():
        compile_typ(src, OUT / f"{name}.pdf")
    wordwise(OUT / "or_clean.pdf", OUT / "or_wordwise.pdf")
    strip_tounicode(OUT / "clean.pdf", OUT / "no_tounicode.pdf")
    tmp_lig = OUT / "_lig.pdf"
    (OUT / "ligatures.pdf").rename(tmp_lig)
    ligature_codepoints(tmp_lig, OUT / "ligatures.pdf")
    tmp_lig.unlink()
    print("ok", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
