"""report.md (one page) + report.json."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .health import FAIL, PASS, WARN

ICON = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL"}


def to_json(d: dict) -> str:
    def default(o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if isinstance(o, set):
            return sorted(o)
        return str(o)
    return json.dumps(d, indent=2, ensure_ascii=False, default=default)


def coverage_text(cov: dict) -> str:
    """Required coverage as the median over the extraction samples with its range, never one draw."""
    if cov.get("required") is None:
        return "no hard required keywords in the JD"
    if cov.get("required_range"):
        lo, hi = cov["required_range"]
        return (f"required coverage {cov['required_median']}% median (range {lo}-{hi}% over {cov['samples']} extracted term lists; "
                f"the consensus list below: {cov['required']}%)")
    return f"required coverage {cov['required']}%"


def addition_text(cov: dict) -> str:
    """What the true additions are worth. It is not a ceiling: it prices only the add_it rows (a flat 0.7 each)
    and neither a better placement of a term already present nor a fact the master words differently."""
    if cov.get("required_achievable") is None:
        return "n/a"
    return f"{cov['required_achievable']}% if the listed true additions are made (not a ceiling)"


def _cell(s, n=140) -> str:
    t = str(s or "-").replace("|", "/").replace("\n", " ")
    return t if len(t) <= n else t[:n - 3].rstrip() + "..."


def p3_line(p3: dict) -> str:
    if p3.get("skipped") or p3.get("error"):
        return f"P3 qualification grader: {p3.get('skipped') and 'skipped (' + p3['skipped'] + ')' or p3['error']}"
    return (f"P3: {p3['band']}, basic {p3['basic_met']}/{p3['basic_total']} met"
            f" ({p3['basic_undecided']} undecided) over {p3['runs_ok']}/{p3['n']} grader runs; criteria {p3['criteria_file']['path']}")


def p3_md(p3: dict) -> list[str]:
    L = ["## P3 qualification grader (structured opinion from our sonnet, not a prediction)"]
    if p3.get("skipped") or p3.get("error"):
        L.append(p3.get("error") or f"Not run ({p3['skipped']}).")
        L.append("")
        return L
    n, need = p3["n"], p3["need"]
    L.append(f"**{p3['band']}**: basic criteria {p3['basic_met']}/{p3['basic_total']} met "
             f"({p3['basic_partial']} partial, {p3['basic_not_met']} not met, {p3['basic_undecided']} undecided; "
             f"a status needs {need} of {n} runs, {p3['runs_ok']} runs returned).  ")
    L.append("If this employer runs per-qualification grading (e.g. Workday HiredScore), the documented rule is: all basic screenable "
             "qualifications met puts the resume in the A/B band, any basic one not met in C/D. Whether this employer runs it is unknown; "
             "the grader here is our model, not theirs. This tool adds a third outcome the rule does not have: with no basic criterion not met but some "
             "partial or undecided, the band is undecided.  ")
    L.append("Grader and resume writer share a model family (Claude): measured LLM self-preference (arXiv 2509.00462) biases this upward.")
    for e in p3.get("errors", []):
        L.append(f"> {e}")
    L.append("")
    rows = [r for r in p3["rows"] if r["screenable"]]
    withm = bool(p3.get("master"))
    head = "| # | Criterion | Level | Votes | Status | Resume line (quoted) |" + (" Master id |" if withm else "")
    L.append(head)
    L.append("|---|---|---|---|---|---|" + ("---|" if withm else ""))
    for r in rows:
        v = r["votes"]
        win = v.get(r["status"], max(v.values())) if r["status"] != "undecided" else max(v.values())
        split = f"{r['status'] if r['status'] != 'undecided' else 'top'} {win}/{r['samples']}" + (f" ({', '.join(f'{k} {c}' for k, c in v.items() if c and k != r['status'])})" if sum(1 for c in v.values() if c) > 1 else "")
        q = f"\"{_cell(r['quote'], 120)}\"" if r["quote"] else "-"
        flag = f" ({r['note']})" if r.get("note") else ""
        fl = f" (flagged: {'; '.join(r['flags'])})" if r.get("flags") else ""
        line = f"| {r['id']} | {_cell(r['text'], 110)}{fl} | {r['level']} | {split} | {r['status']}{flag} | {q} |"
        if withm:
            line += f" {_cell(r['master_id'], 24) if r['master_id'] else ('NOT TRACEABLE to one master bullet' if r['quote'] else '-')} |"
        L.append(line)
    ns = [r for r in p3["rows"] if not r["screenable"]]
    if ns:
        L.append("")
        L.append("Not screenable (a resume cannot show these; not graded, not in the band): " + "; ".join(f"{r['text']} ({r['level']})" for r in ns) + ".")
    if p3.get("rejected_coined"):
        L.append("")
        L.append("Rejected at generation: " + "; ".join(f"{x['text']} ({x.get('reason', 'coined')})" for x in p3["rejected_coined"]) + ".")
    f = p3.get("criteria_file", {})
    L.append("")
    L.append(f"Criteria {f.get('source', '?')}: `{f.get('path', '?')}` (pinned; edit the file to change what is graded, `--recriteria` regenerates"
             f"{' and keeps the old file as .bak' if f.get('backup') else ''}). {f.get('verified', '')}. Criteria are shuffled per grader run.")
    L.append("")
    return L


def stability_text(st: dict) -> str:
    L = [f"P3 stability: {st['k']} fresh gradings x {st['n']} runs; band flip rate {st['band_flip_rate']:.0%} {st['bands']}"]
    for c in st["criteria"]:
        L.append(f"  {c['id']:>4} [{c['level'][:3]}] flip {c['flip_rate']:.0%}  raw-draw disagreement {c['sample_disagreement']:.0%}  voted {c['voted']}  {c['text'][:70]}")
    return "\n".join(L)


def render_md(d: dict) -> str:
    v, cov = d["verdict"], d["coverage"]
    L = []
    L.append(f"# ATS check: {d['inputs']['resume_name']} vs {d['jd']['title'] or d['inputs']['jd_label']}")
    L.append("")
    if d.get("p3") is not None:
        L += p3_md(d["p3"])
    ai = f"AI grade {v['ai_grade']} (advisory)" if v.get("ai_grade") else "AI screen not run"
    L.append(f"**Verdict: {v['label']}** - {v['why']}.  ")
    L.append(f"Parse {v['parse_pass']}/{v['parse_total']} checks pass ({v['parse_fail']} FAIL, {v['parse_warn']} WARN) | "
             f"hard required keywords {cov['required_found']}/{cov['required_total']} found on the consensus list, {coverage_text(cov)} "
             f"({addition_text(cov)}) | all hard {cov['overall']}% ({cov['overall_achievable']}% if the true additions are made) | soft evidenced {cov['soft_evidenced']}/{cov['soft_total']} (unweighted) | {ai}")
    L.append("")
    L.append("## Top fixes")
    for i, f in enumerate(d["fixes"][:5], 1):
        L.append(f"{i}. {f['action']}  _({f['why']})_")
    if not d["fixes"]:
        L.append("None found.")
    L.append("")
    L.append("## Parse health")
    L.append("| Check | Result | Evidence |")
    L.append("|---|---|---|")
    for c in d["health"]["checks"]:
        if c["status"] == PASS:
            continue
        ev = "; ".join(c["evidence"][:2]).replace("|", "/").replace("\n", " ")[:170]
        L.append(f"| {c['title']} | {c['status']} | {ev} |")
    passed = [c["title"] for c in d["health"]["checks"] if c["status"] == PASS]
    L.append(f"\nPASS: {', '.join(passed) if passed else 'none'}.  Matching view: `{d['health']['match_view']}`.")
    orc = [c for c in d["health"]["checks"] if c["id"].startswith("or_") and c["status"] != PASS]
    if orc:
        L.append("\nOpenResume layer (a second, independent PDF reader; see docs/ats-check.md):")
        for c in orc:
            L.append(f"- **{c['status']} {c['title']}**: " + "; ".join(c["evidence"]) + (f" Fix: {c['fix']}" if c["fix"] else ""))
    L.append("")
    L.append("## Hard requirements (truth column)")
    rows = [r for r in d["requirements"] if not r.get("soft")]
    soft = [r for r in d["requirements"] if r.get("soft")]
    order = {"add_it": 0, "add_form": 1, "rejected": 2, "gap": 3, "ok": 4}
    rows.sort(key=lambda r: (order[r["status"]], {"required": 0, "preferred": 1, "mentioned": 2}[r["importance"]]))
    L.append("| Requirement | Imp. | In resume | Where | Truth |")
    L.append("|---|---|---|---|---|")
    truth = {"ok": "ok", "add_form": "true, add the other form", "add_it": "TRUE, ADD IT", "gap": "gap, not added until the master records it", "rejected": "not supported by master (listed under rejected claims)"}
    shown = 0
    for r in rows:
        if r["status"] == "ok" and r["score"] >= 0.7 and shown >= 12:
            continue
        flag = (" " + "; ".join(r["flags"])) if r["flags"] else ""
        label = truth[r["status"]]
        if r["status"] == "rejected" and r.get("master_evidence"):
            flag += (' "' + r["master_evidence"][:110] + '"').replace("|", "/")
        L.append(f"| {r['term']} | {r['importance'][:3]} | {r['count']}x | {r['best'] or '-'} | {label}{flag} |")
        shown += 1
        if shown >= 28:
            L.append(f"| ... {len(rows) - shown} more in report.json | | | | |")
            break
    L.append("")
    if soft:
        ev = [x["term"] for x in soft if any(p in ("current_role", "recent_role", "older_role") for p in x["placements"])]
        no = [x["term"] for x in soft if x["term"] not in ev]
        L.append(f"## Soft requirements (evidenced in bullets? no weight in coverage): {len(ev)}/{len(soft)}")
        L.append("Evidenced: " + (", ".join(ev) or "none") + ".  Not evidenced: " + (", ".join(no) or "none") + ".")
        L.append("")
    if d.get("ask_candidate"):
        L.append("## Ask the candidate (hard requirements absent from the master: add only what the candidate can confirm)")
        L.append(", ".join(d["ask_candidate"]) + ".")
        L.append("")
    if d["knockouts"]:
        L.append("## Knock-outs")
        for k in d["knockouts"]:
            L.append(f"- **{k['kind']}** ({k['status']}): {k['requirement']} - {k['note']}")
        L.append("")
    a = d.get("ai")
    L.append("## AI screener (advisory, not the verdict)")
    if a and "error" not in a:
        L.append(f"Grade **{a['grade']}**: {a.get('one_line', '')}")
        for k, t in (("top_reasons", "Why"), ("would_move_up", "Moves it up"), ("risks", "Risks")):
            for x in (a.get(k) or [])[:4]:
                L.append(f"- {t}: {x}")
    else:
        L.append((a or {}).get("error", "not run (--no-llm)"))
    L.append("")
    for w in d["jd"].get("warnings", []):
        L.append(f"> {w}")
    L.append(f"\n_Scores are relative guides, not predictions; see README for what this tool cannot know._")
    return "\n".join(L) + "\n"


def write(out: Path, d: dict):
    out.mkdir(parents=True, exist_ok=True)
    text = to_json(d)
    d = json.loads(text)
    (out / "report.json").write_text(text)
    (out / "report.md").write_text(render_md(d))
