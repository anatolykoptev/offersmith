# Changelog

## Unreleased

- Fix: the experience parser no longer counts a wrapped bullet row that carries a date (only while the bullet row before it has not ended its sentence, and never a `Title, Company` row), or a page-footer row (`1/2`, `Page 1`, `Page 1 of 2`), as a job under the line-based extractors. It had raised a false parse FAIL ("FIX PARSING FIRST") and an entry-count WARN on resumes every extractor read correctly.

- Offersmith: the project and repository are now `offersmith` (earlier names honest-ats, ats-check). The `offersmith` command is the main one; `honest-ats` and `ats-check` stay as aliases, and the `ats_check` Python package and the `~/.cache/ats-check/` cache keep their names.
- Claude Code plugin: `.claude-plugin/plugin.json` and `marketplace.json`, and five skills (`master-resume`, `tailor-resume`, `cover-letter`, `ats-check`, `application-answers`) generalised from personal ones, with the scripts they call (`check_master.py`, `check_resume.py`, `render_resume.sh`, `check_letter.py`, `render_letter.sh`), a Typst resume and letter template, and a shipped kill-list.
- `offersmith.toml` and `OFFERSMITH_*` variables set the master, claim guard, output directory and Workday base. A new "Never mention in a letter" list in the claim guard replaces the immigration regex that was hard-coded in the letter checker.
- `examples/` is now a complete lint-clean set (master, claim guard, provenance, change log, open questions) plus a resume and a letter for the made-up candidate.
- `report.json` key `ask_owner` is now `ask_candidate`, and the report heading says "Ask the candidate".
- Removed product-specific rows from `synonyms.yaml` (two CRM-vendor synonym groups) and from the tests; the deterministic JD extractor now stops at an "About us / the company / the team" heading instead of a company-specific one.
- Version 0.2.0.

## 0.1.0

- Initial public release: parse health across five PDF engine families, JD requirement extraction, match with truth column against a master resume and claim guard, advisory AI screen and qualification grader.
- `--workday-req` needs `--workday-base` or `ATS_CHECK_WORKDAY_BASE`; there is no built-in tenant.
