# Offersmith

**Offersmith: from your real experience to a job offer.**

A local job-application toolkit for a coding agent, packaged as a Claude Code plugin. You keep one private bank of your true facts (the master resume). The agent cuts a tailored resume and a cover letter from it, checks the resume the way an applicant tracking system reads it, and drafts form answers, and every sentence traces back to a fact you recorded. Nothing is invented, and the ATS check never suggests claiming something you have not done.

It prepares the application. It does not find postings or submit anything: a job-search service finds the posting, Offersmith gets your application ready for it.

## Workflow

1. **Master resume** (`master-resume`): your fact bank. Every bullet has an id, every number has one home and a source, a claim guard lists what you must not claim, and a linter keeps it consistent.
2. **Tailored resume** (`tailor-resume`): a one-to-two page cut from the master for one posting, in a parser-safe format, rendered to PDF and checked against format rules.
3. **Cover letter** (`cover-letter`): one page, PDF plus plain text. A fact map ties every factual sentence to a master id or a file, and a checker rejects untraced numbers, stock phrases and anything your claim guard forbids.
4. **ATS check** (`ats-check`): runs the PDF through five text extractors, matches the posting's requirements, and sorts every missing keyword into "true, add it", "gap, not yours to claim" or "rejected by your guard".
5. **Form answers** (`application-answers`): drafts the short fields from the master and leaves legal and personal questions (work authorization, salary, demographics) to you.

## Install

### As a Claude Code plugin

```
/plugin marketplace add anatolykoptev/offersmith
/plugin install offersmith@offersmith
```

On Claude Code 2.1.275 or later one step does both: `/plugin install offersmith --marketplace anatolykoptev/offersmith`.

Then ask for what you want ("start my master resume", "tailor my resume for this posting", "run the ATS check"). The skills carry the procedure; the scripts they call ship in the plugin.

Tools the skills use: `uv` and Python 3.13 (resolved by `uv`), poppler (`pdftotext`, `pdfinfo`), and for the resume and letter rendering `pandoc`, `typst` and `jq`. The LLM layers of the ATS check call the `claude` CLI and are optional (`--no-llm`).

### As a command line tool

```
uv tool install git+https://github.com/anatolykoptev/offersmith
offersmith --resume resume.pdf --jd posting.txt --master "Your Name — master resume.md"
```

`offersmith` is the main command; `honest-ats` and `ats-check` are the same command under its earlier names. From a checkout, `./offersmith` runs the pinned environment from any directory. Reference: [docs/ats-check.md](docs/ats-check.md).

## Configuration

Put an `offersmith.toml` in the directory you work in, or in `~/.config/offersmith/`, or point `OFFERSMITH_CONFIG` at one:

```toml
master       = "~/offersmith/master/Your Name — master resume.md"   # the fact bank
guard        = ""                                                    # default: "<stem> — claim guard.md" next to the master
out_dir      = "~/offersmith/out"                                    # ATS reports go to <out_dir>/<resume stem>
workday_base = ""                                                    # https://<tenant>.wdN.myworkdayjobs.com/<site>, for --workday-req
```

`OFFERSMITH_MASTER`, `OFFERSMITH_GUARD`, `OFFERSMITH_OUT` and `OFFERSMITH_WORKDAY_BASE` override the file; a command-line flag overrides both. Keep your master outside this repository.

A synthetic master, its sidecars, a resume and a letter for a made-up candidate (Jane Example) are in [`examples/`](examples/). Copy them as the starting point.

## The honesty principle

- Every claim in a resume, letter or answer comes from a master bullet, a metrics row or a file you can open. A fact the master lacks is a question for you, never a sentence.
- The claim guard is binding: wording you cannot support, numbers you decided not to use, names that must stay out of a letter.
- The master has no absence notes ("never used X"): a skill you lack simply does not appear, and the one negative list is the guard.
- The ATS check marks a missing keyword "true, add it" only when an id-carrying master bullet or the Skills table supports it, and it quotes that line so you can confirm the exact claim. A word found in a rule or a note is a coincidence, not evidence.
- You say once how the work was done (for example that AI coding agents wrote the code under your review) and never hide it. See [docs/voice-and-truth.md](docs/voice-and-truth.md).

## What the ATS check can and cannot tell you

- **Trust:** parse failures (the extractors really disagree, and the evidence quotes the text); which posting terms are literally absent from what a parser reads; where a term sits; the master-based split of true additions, gaps and rejected claims.
- **Do not trust as a prediction:** the coverage percent or the AI grade. No public spec exists for Workday, HiredScore or Ashby ranking, so the AI layer is an LLM proxy and the coverage number is a relative guide for comparing two versions of the same resume against the same posting, not a probability of being shortlisted.
- **Not modelled:** knock-out questions inside the application form, recruiter sourcing outside the ATS, DOCX-specific parsing, non-English resumes, OCR-based pipelines.
- **Optional second parser:** with Node installed (`sh tools/openresume/install.sh`) the check also runs OpenResume's own PDF parser and reports what it loses: glued words, bullets it does not know, a role split in two, an empty degree. It is one open-source parser on pdf.js text items, a fragility signal and not a model of any vendor's ATS.
- Knock-outs (years, degree, location, clearance) are surfaced for you to answer, never decided.

The scoring rules, the extractors and the safety of the LLM calls are documented in [docs/ats-check.md](docs/ats-check.md).

## Privacy

Everything runs on your machine: the master, resumes, letters and reports are files you own, and nothing is uploaded. The only data that leaves is what the ATS check's optional LLM layers send to the `claude` CLI (the posting text and your resume text, sandboxed, with no tools and no file access), and the posting fetch when you pass `--jd-url` or `--workday-req`. Run with `--no-llm` and a saved posting file to send nothing at all. This repository holds no real resume, master or posting.

## Development

`uv sync --locked`, then `uv run pytest` (the letter and resume tests also need `pandoc`, `typst`, `jq` and poppler; in CI a missing tool fails the run). `uv run python tests/mutate.py` runs the mutation proof for the matching, scoring and config call sites. `claude plugin validate .` checks the manifests. Documents: [docs/INDEX.md](docs/INDEX.md).

## License

Apache-2.0, see [LICENSE](LICENSE).
