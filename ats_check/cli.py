"""offersmith CLI (also installed as honest-ats and ats-check)."""
from __future__ import annotations

import argparse
import hashlib
import os
import statistics
import sys
from pathlib import Path

from . import ai as ai_mod
from . import master as master_mod
from . import health as hl
from . import criteria as crit_mod
from . import llm
from . import grade as grade_mod
from . import config as config_mod
from . import jd_fetch, jd_reqs, match, report, score


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="offersmith", description="Local ATS simulation for a resume PDF against a job description.")
    p.add_argument("--resume", required=True, type=Path, help="resume PDF")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--jd", type=Path, help="job description text file")
    g.add_argument("--workday-req", metavar="JRxxxxx", help="Workday requisition id (see --workday-base)")
    g.add_argument("--jd-url", help="Workday / Greenhouse / Ashby / Lever / any job page URL")
    p.add_argument("--workday-base", help="https://<tenant>.wdN.myworkdayjobs.com/<site> (default: workday_base in offersmith.toml, $OFFERSMITH_WORKDAY_BASE or $ATS_CHECK_WORKDAY_BASE; required with --workday-req)")
    p.add_argument("--master", type=Path, help="master resume markdown (truth column; default: master in offersmith.toml or $OFFERSMITH_MASTER)")
    p.add_argument("--guard", type=Path, help="claim guard markdown (default: '<stem> — claim guard.md' next to --master)")
    p.add_argument("--out", type=Path, help="output dir (default: <out_dir>/<resume stem> from offersmith.toml, else ./ats-out/<resume stem>)")
    p.add_argument("--no-llm", action="store_true", help="deterministic JD extraction, no AI screen")
    p.add_argument("--refresh", action="store_true", help="ignore the LLM cache and the stored term list: extract again")
    p.add_argument("--samples", type=int, default=jd_reqs.DEFAULT_SAMPLES, metavar="N",
                   help=f"JD term extractions to run and combine (default {jd_reqs.DEFAULT_SAMPLES}; terms in >= half of them are kept; ignored with --no-llm)")
    p.add_argument("--grade-samples", type=int, default=grade_mod.DEFAULT_SAMPLES, metavar="N",
                   help=f"P3 grader runs per criterion (default {grade_mod.DEFAULT_SAMPLES}; a status needs >= ceil(0.8 N) of them, else undecided; ignored with --no-llm)")
    p.add_argument("--recriteria", action="store_true", help="regenerate the pinned criteria-<jd sha12>.yaml (overwrites hand edits)")
    p.add_argument("--stability", type=int, metavar="K", help="after the report, run the P3 grader K more times fresh and print the per-criterion flip rate")
    p.add_argument("--synonyms", type=Path, help="alternate synonyms.yaml")
    return p


def sample_coverage(jd, parsed, master, groups) -> dict:
    """Required coverage of the SAME resume against each extraction's own term list: the median is the
    number the verdict uses, the range is how much the extraction alone moves it."""
    if len(jd.samples) < 2 or not parsed:
        return {}
    per = [match.coverage(match.match(sj, parsed, master, groups))["required"] for sj in jd.samples]
    vals = [v for v in per if v is not None]
    if not vals:
        return {"required_samples": per}
    return {"required_samples": per, "required_median": round(statistics.median(vals)), "required_range": [min(vals), max(vals)], "samples": len(per)}


def out_dir(args) -> Path:
    return args.out or Path("ats-out") / args.resume.stem


def criteria_dir(args) -> Path:
    """Next to the JD file; a fetched JD has no file, so its pin lives in the cache keyed by the JD's sha (not in the
    per-resume output dir, where a second resume would regenerate and drift)."""
    return args.jd.resolve().parent if args.jd else llm.CACHE / "criteria"


def p3_stage(args, jd_text: str, parsed, master) -> dict:
    """P3: pinned criteria -> N-sample grader -> band."""
    if args.no_llm:
        return {"skipped": "--no-llm"}
    if parsed is None or not parsed.lines:
        return {"skipped": "no resume text"}
    if not llm.self_check():
        return {"error": "sandbox self-check failed (Read deny did not hold); P3 not run"}
    try:
        crit, rejected, info = crit_mod.get(jd_text, criteria_dir(args), args.recriteria)
    except crit_mod.CriteriaError as e:
        return {"error": f"criteria step failed: {e}"}
    resume = grade_mod.from_parsed(parsed)
    g = grade_mod.grade(crit, resume, args.grade_samples, master, args.refresh)
    out = {"criteria_file": info, "rejected_coined": rejected, **g, "master": bool(master)}
    if args.stability:
        out["stability"] = grade_mod.stability(crit, resume, args.stability, args.grade_samples)
    return out


def analyze(args) -> dict:
    # JD text
    if args.jd:
        jd_text, label = args.jd.read_text(), str(args.jd)
    elif args.workday_req:
        if not args.workday_base:
            print("offersmith: --workday-req needs --workday-base, workday_base in offersmith.toml or ATS_CHECK_WORKDAY_BASE", file=sys.stderr)
            raise SystemExit(2)
        jd_text, label = jd_fetch.fetch_workday(args.workday_base, req=args.workday_req), f"workday:{args.workday_req}"
    else:
        jd_text, label = jd_fetch.fetch_url(args.jd_url), args.jd_url
    if not args.no_llm and not args.recriteria:
        crit_mod.load_pinned(jd_text, criteria_dir(args))     # a malformed pinned file stops the run before any LLM call
    groups, vocab = jd_reqs.load_synonyms(args.synonyms)
    master = master_mod.load_files(args.master, args.guard) if args.master else None

    H = hl.run(args.resume)
    jd = jd_reqs.extract(jd_text, not args.no_llm, groups, vocab, args.refresh, samples=args.samples)
    if master:
        jd.warnings += master.warnings
    view = next((e for e in H.extractions if e.name == H.match_view), None)
    parsed = H.parsed.get(H.match_view)
    resume_text = view.text if view else ""
    results = match.match(jd, parsed, master, groups) if parsed else []
    cov = match.coverage(results) if results else {k: None for k in ("overall", "overall_achievable", "required", "required_achievable")} | {"found": 0, "total": 0, "required_found": 0, "required_total": 0, "soft_total": 0, "soft_evidenced": 0}
    if cov.get("required") is not None or cov.get("overall") is not None:
        cov.update(sample_coverage(jd, parsed, master, groups))
    kos = match.knockouts(jd, parsed, resume_text, master, groups) if parsed else []
    ai = None
    if not args.no_llm and resume_text:
        ai = ai_mod.screen(jd_text, resume_text, args.refresh)
    p3 = p3_stage(args, jd_text, parsed, master)
    fixes = score.build_fixes(H, results, kos)
    verdict = score.verdict(H, cov, kos, ai)
    return {
        "inputs": {"resume": str(args.resume), "resume_name": args.resume.name, "jd_label": label, "master": str(args.master) if args.master else None,
                   "jd_sha256": hashlib.sha256(jd_text.encode()).hexdigest()[:16]},
        "verdict": verdict, "p3": p3, "coverage": cov, "fixes": fixes,
        "health": {"checks": H.checks, "match_view": H.match_view, "agreement": H.agreement,
                   "extractors": [{"name": e.name, "ok": e.ok, "error": e.error, "version": e.version, "chars": len(e.text)} for e in H.extractions],
                   "geometry": {"pages": H.geometry.pages, "columns": H.geometry.columns, "tables": H.geometry.tables, "images": H.geometry.images},
                   "openresume": H.openresume and {"resume": H.openresume["resume"], "pages": H.openresume["pages"], "text_items": len(H.openresume["raw"])}},
        "parsed": parsed and {"name": parsed.name, "email": parsed.email, "phone": parsed.phone, "location": parsed.location, "links": parsed.links,
                              "sections": [(s.title, s.canon) for s in parsed.sections],
                              "entries": [{"title": e.title, "company": e.company, "dates": e.dates_raw, "ok": e.dates_ok, "problem": e.dates_problem} for e in parsed.entries],
                              "skills": parsed.skills},
        "jd": {"title": jd.title, "location": jd.location, "source": jd.source, "cached": jd.cached, "warnings": jd.warnings, "knockouts": jd.knockouts,
               "samples": jd.n_samples, "stability": jd.stability},
        "requirements": [{**{k: getattr(r, k) for k in ("term", "aliases", "kind", "importance", "count", "placements", "best", "score", "flags", "forms_present", "forms_missing", "votes", "master_hit", "master_usage", "master_evidence", "master_negated", "soft", "status", "achievable")}} for r in results],
        "knockouts": kos, "ai": ai,
        "ask_candidate": [r.term for r in results if not r.soft and r.status == "gap" and r.importance in ("required", "preferred")][:15] if master else [],
    }


def apply_config(args, cfg: config_mod.Config) -> None:
    """Flag > environment > offersmith.toml (config.load already put the environment above the file)."""
    args.master = args.master or cfg.master
    args.guard = args.guard or cfg.guard
    args.workday_base = args.workday_base or cfg.workday_base
    if args.out is None and cfg.out_dir is not None:
        args.out = cfg.out_dir / args.resume.stem


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        apply_config(args, config_mod.load())
    except config_mod.ConfigError as e:
        print(f"offersmith: {e}", file=sys.stderr)
        return 2
    if not args.resume.exists():
        print(f"offersmith: no such resume: {args.resume}", file=sys.stderr)
        return 2
    try:
        d = analyze(args)
    except jd_fetch.FetchError as e:
        print(f"offersmith: could not fetch the JD: {e}", file=sys.stderr)
        return 3
    except crit_mod.PinnedFileError as e:
        print(f"offersmith: {e}", file=sys.stderr)
        return 2
    out = out_dir(args)
    report.write(out, d)
    st = d["p3"].get("stability")
    if st:
        (out / "stability.json").write_text(grade_mod.to_json(st))
        print(report.stability_text(st))
    v = d["verdict"]
    cov = d["coverage"]
    print(f"{v['label']}: {v['why']}\nparse {v['parse_pass']}/{v['parse_total']}  {report.coverage_text(cov)}"
          f" ({report.addition_text(cov)})  AI {v['ai_grade'] or '-'}\n{report.p3_line(d['p3'])}\n-> {out}/report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
