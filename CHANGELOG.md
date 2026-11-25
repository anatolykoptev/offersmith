# Changelog

## Unreleased

- Optional OpenResume layer in the ATS check: OpenResume's own PDF parser (pinned commit, fetched by `tools/openresume/install.sh`, run unmodified under Node) is compared with the consensus of the five extractors. New parse-health checks `or_granularity`, `or_glued`, `or_bullets`, `or_entries`, `or_education`, `or_page_boundary`, `or_contact`, each with quoted evidence; every finding is a WARN, never a FAIL. Not installed, no Node, an install folder that is not the pinned untouched checkout owned by you, or a runner failure is one WARN; `ATS_CHECK_OPENRESUME=off` disables it. `report.json` gains `health.openresume`. OpenResume is AGPL-3.0 and is not distributed with this repository ([THIRD_PARTY.md](THIRD_PARTY.md)).
- Fix: a wrapped bullet row and a page footer are no longer counted as jobs. The experience parser took a wrapped row that carries a date, and a page number between two bullets (`1/2`, `1 of 2`, `Page 1 of 2`, `2`), for role headers under the line-based extractors: a false "single date" / "no job title" parse FAIL ("FIX PARSING FIRST"), an entry-count WARN and a skewed placement weight on resumes every extractor read correctly. Header, wrapped bullet row and footer are now told apart from page layout (`ats_check/layout.py`): a row at the bullet's text indent is that bullet's text, a repeated page number is a footer, a role header starts at the margin. Rows the layout cannot place, and PDFs with no usable layout (no text, columns, tables, no bullet indent), are read as before; the layout only removes rows that cannot be headers and never softens a FAIL on one that remains. Page numbers are skipped only while reading entries, skills and headings; the text the matcher reads is untouched.
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
