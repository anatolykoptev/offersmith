"""Layer 5: verdict + ranked fixes. Weights are explained in the README; no fake precision."""
from __future__ import annotations

from .health import FAIL, PASS, WARN, Health
from .jd_reqs import IMPORTANCE_W
from .match import ReqResult


def build_fixes(h: Health, results: list[ReqResult], kos: list[dict]) -> list[dict]:
    fixes: list[dict] = []
    for c in h.checks:
        if c.status == FAIL:
            fixes.append({"value": 1000, "kind": "parse", "action": c.fix or c.title, "why": f"{c.title}: FAIL", "evidence": c.evidence[:2], "truthful": True})
        elif c.status == WARN and c.id not in ("location", "phone", "name", "reading_order", "or_layer", "or_page_boundary"):
            fixes.append({"value": 30, "kind": "parse", "action": c.fix or c.title, "why": f"{c.title}: WARN", "evidence": c.evidence[:2], "truthful": True})
    for r in results:
        w = IMPORTANCE_W[r.importance] * (0.1 if r.soft else 1.0)   # soft skills barely rank as fixes
        if r.status == "add_it":
            fixes.append({"value": 40 * w * max(r.achievable - r.score, 0.3), "kind": "add_it", "term": r.term,
                          "action": f"Add '{r.term}' to a role bullet or the summary (true: master says \"{r.master_evidence}\")",
                          "why": f"{r.importance} requirement missing from the parsed resume", "truthful": True})
        elif r.status == "add_form":
            fixes.append({"value": 14 * w, "kind": "add_form", "term": r.term,
                          "action": f"Write both forms: also use '{', '.join(r.forms_missing)}' next to '{', '.join(r.forms_present)}'",
                          "why": "recruiter boolean search matches one literal form", "truthful": True})
        elif r.hits and r.best in ("skills", "education") and r.master_usage:
            fixes.append({"value": 10 * w, "kind": "move_up", "term": r.term,
                          "action": f"Use '{r.term}' in a role bullet (master has usage context), not only in Skills",
                          "why": "keyword in a skills list scores low; in the current role it scores high", "truthful": True})
        for f in r.flags:
            if f.startswith("conflict"):
                fixes.append({"value": 900, "kind": "conflict", "term": r.term, "action": f"Confirm '{r.term}': a master line denies it ({r.master_negated}); drop it from the resume unless the master is updated",
                              "why": "the resume has a claim the master does not support", "truthful": True})
            if f.startswith("stuffing"):
                fixes.append({"value": 20, "kind": "stuffing", "term": r.term, "action": f"Cut repetitions: {f}", "why": "stuffing is penalised by humans and some ranking models", "truthful": True})
    for k in kos:
        if k["status"] in ("risk", "add_it"):
            fixes.append({"value": 200 if k["status"] == "risk" else 150, "kind": "knockout", "action": f"{k['kind']}: {k['requirement']} - {k['note']}",
                          "why": "knock-out filters reject before any ranking", "truthful": k["status"] == "add_it"})
    fixes.sort(key=lambda f: -f["value"])
    seen, out = set(), []
    for f in fixes:
        key = (f["kind"], f.get("term", f["action"]))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def verdict(h: Health, cov: dict, kos: list[dict], ai: dict | None) -> dict:
    statuses = [c.status for c in h.checks]
    n_pass = statuses.count(PASS)
    fails = [c.title for c in h.checks if c.status == FAIL]
    risk = [k for k in kos if k["status"] == "risk"]
    req = cov.get("required_median", cov.get("required"))
    gates = [k for k in kos if k["kind"] == "years" and k["status"] in ("review", "unknown")]
    if fails:
        label = "FIX PARSING FIRST"
        why = "parse FAIL: " + "; ".join(fails[:3])
    elif risk:
        label = "KNOCK-OUT RISK"
        why = "; ".join(f"{k['kind']}: {k['note']}" for k in risk[:2])
    elif req is None and cov.get("overall") is not None:
        label, why = "NO REQUIRED KEYWORDS", f"the JD lists no hard required keyword; preferred/mentioned ones cover {cov['overall']}%"
    elif req is None:
        label, why = "NO REQUIREMENTS FOUND", "the JD yielded no requirements; check the JD text"
    elif req >= 80 and gates:
        label = "STRONG KEYWORDS, YEARS GATE TO CHECK"
        why = "required keywords are well covered, but the JD's years requirement is not confirmed by the resume: " + "; ".join(f"{k['requirement']} ({k['note']})" for k in gates[:2])
    elif req >= 80:
        label, why = "STRONG MATCH", "required keywords are well covered and well placed"
    elif req >= 60:
        label, why = "MODERATE MATCH", "room to move up with true additions"
    else:
        label, why = "WEAK MATCH", "required keywords are thin; some may be genuine gaps"
    return {"label": label, "why": why, "parse_pass": n_pass, "parse_total": len(statuses),
            "parse_fail": len(fails), "parse_warn": statuses.count(WARN),
            "ai_grade": (ai or {}).get("grade") if ai and "error" not in ai else None}
