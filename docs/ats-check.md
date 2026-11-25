# The ATS check (`offersmith`, also `honest-ats` and `ats-check`)

The engine behind the `ats-check` skill: it simulates an applicant tracking system on one resume PDF against one job description and refuses to suggest keywords you cannot back up with your master resume. The product overview, the plugin and the other skills are in the [README](../README.md); this page is the reference for the command.

```
offersmith --resume R.pdf (--jd jd.txt | --workday-req JR367656 | --jd-url URL) \
           [--master master.md] [--guard guard.md] [--samples N] [--out DIR] [--no-llm] [--refresh]
           [--grade-samples N] [--recriteria] [--stability K]
```

- `--jd`: plain text. `--workday-req JRxxxx`: fetched from a Workday tenant given by
  `--workday-base https://<tenant>.wdN.myworkdayjobs.com/<site>` (or `workday_base` in `offersmith.toml`, or the `OFFERSMITH_WORKDAY_BASE` / `ATS_CHECK_WORKDAY_BASE` environment variable; required).
  `--jd-url`: Workday job URL, Greenhouse, Ashby, Lever (public JSON), or any page (JSON-LD
  `JobPosting`, else stripped HTML).
- `--master`: the master resume markdown (a private bank of every true fact about the candidate; see [`examples/`](../examples/)). It switches on the **truth column** (below). The claim guard
  `<stem> — claim guard.md` next to it is loaded automatically (`--guard` overrides); without one the report says so. Both default to `master` and `guard` in `offersmith.toml` (see the README).
- `--samples N` (default 5): run the haiku term extraction N times and keep the terms listed by at least half of them
  (below). `--refresh` extracts again.
- `--no-llm`: deterministic term extractor, no AI screen, no `claude` calls at all.
- `--out`: output directory (default `<out_dir>/<resume stem>` from `offersmith.toml`, else `./ats-out/<resume stem>`): `report.md` (one page: verdict, five highest-value fixes) and `report.json`
  (everything, including per-extractor evidence). Exit 0 ok, 2 bad input, 3 JD fetch failed.

Run from any directory; `uv` resolves the pinned environment (`uv.lock`). Tests: `uv run pytest`.
Mutation proof: `uv run python tests/mutate.py`. Caches live in `~/.cache/ats-check/` (the directory kept its old name).

## Master resume and claim guard

The truth column needs two markdown files you write yourself, in the layout of the synthetic pair in
[`examples/`](../examples/): a master resume (id-carrying bullets under Experience / Projects / Open source,
a Skills table with an "Allowed wording" column) and a claim guard next to it, named `<stem> — claim guard.md`
for a master named `<stem> — master resume.md` (or pass `--guard FILE`). The examples are made up; there is no
real master in this repository. Keep your own outside the repository.

## What it does

1. **Parse health** (blocking). Five engine families (poppler `-layout` and `-raw`, PyMuPDF, pdfplumber, pypdfium2, Filee) plus PyMuPDF geometry, and optionally OpenResume's own parser on pdf.js items (below). Checks: extractor count, text
   layer, ToUnicode / `(cid:N)` junk, ligature code points, icon glyphs, reading-order agreement,
   column gutter, ruled tables, big images with no text (OCR shown as evidence when `tesseract` is
   present), contact only in the header/footer band, then fields modelled on OpenResume run on
   every extractor's text: name, email, phone, location, standard headings, per-job title +
   company + parseable dates, education, skills. Each is PASS / WARN / FAIL with evidence. **Any
   FAIL = verdict "FIX PARSING FIRST"**; nothing below it is trusted.

   Which extracted row is a job header, a wrapped bullet row or a page footer is decided from page layout, not from
   wording (`ats_check/layout.py`). The line-based extractors (poppler, pdfplumber, PDFium, PdfPig) hand over rows with no
   position, and a wrapped bullet row can carry a date and read like a header ("November 2024, and has been done by Jane..."),
   while a page number between two bullets reads like an undated one. PyMuPDF's visual rows are the authority: a row at the
   bullet's text indent (right of the margin) is that bullet's wrapped text; a page number that is the first or last row of
   its page and repeats at the same height on another page (or sits in the header/footer band), or a running footer repeating
   in the band, is a footer; a role header starts at the margin, usually in bold or with a right-aligned part. Each extractor's
   rows are projected onto these by their text (an extractor that joins a wrapped bullet into one paragraph takes the role of
   its first row). Page numbers are skipped only inside the experience, skills and heading reading; the text every other check
   and the matcher read keeps them (a phone split over rows, `SOC` / `2`). Rows the layout cannot place, a PDF with no text
   layer, columns or tables, and a layout with no bullet indent (wrapped rows back at the margin, or the bullet text at the
   margin) fall back to the line-shape reading as before. The layout only removes rows that cannot be headers (a wrapped row, a
   footer); it never softens a FAIL on a row that remains, so every entries FAIL origin/main gave stands. A row counts as wrapped
   only when it sits at the bullet's text x, one line pitch (the document's tightest) below the row above, and is not wholly bold
   or two-part; a page number in the band counts as a footer only when it stands clear of the body or repeats on another page, and
   digits alone are never a running footer.
2. **JD requirements.** `claude -p --model haiku` extracts requirements (term, aliases, importance,
   knock-outs). One extraction is one draw: fresh extractions of one JD can list different terms and move the required
   coverage of the same resume a lot. So it runs `--samples` times (a cache key per sample, in `~/.cache/ats-check/llm/`), keeps the terms
   listed by >= ceil(N/2) samples (aliases unioned; importance and soft/hard by majority) and stores that consensus list
   with its samples per JD in `~/.cache/ats-check/jdset/`, so a before/after run compares on one list. The resume is also
   matched against each sample's own list: the report shows the **median** required coverage with the **min-max range**,
   and the verdict uses the median. LLM aliases are kept only when
   verifiable (acronym/expansion, same synonym group, more specific phrase): "CRM" is not an alias of
   "Hubspot". Fallback: a deterministic extractor (headings give importance; noisier).
3. **Match** against the text the machine parsed (not the PDF): whole-word, hyphen/plural tolerant,
   acronym <-> spelled-out forms from `ats_check/synonyms.yaml` (edit it), placement weights, count,
   stuffing (a specific term > 3 mentions; `Model Context Protocol (MCP)` is one mention). Short
   acronyms (AI, ML, UX) are never counted as stuffing; a match inside `auto-identity-remove` or a path
   is not a match.
4. **AI screener** (advisory). `claude -p --model sonnet`, recruiter 30-second screen + AI-grader
   rubric, grade A-D with reasons and truthful moves. Printed under its own heading; never feeds the
   verdict.
5. **P3 qualification grader** (shown first in report.md; `--no-llm` skips it). Models the documented per-qualification
   grading (Workday HiredScore 2026, Ashby criteria, Greenhouse calibration). Step 1: sonnet splits the JD's basic and
   preferred bullets into singular criteria, wording verbatim, each `basic|preferred` and `screenable` (false = a resume
   cannot show it: "comfortable with ambiguity"). A generated criterion is rejected unless it sits word-bounded inside ONE
   JD bullet, is that whole bullet or >= 3 words, comes from a qualification section (Requirements / Qualifications /
   Who you are / Nice to have / Even better if...), and does not drop a not/no/without its bullet carries; a level that
   disagrees with the JD heading is flagged. For a JD with no recognisable sections the report says only "criteria text
   verified present in the JD". The split runs once per JD and is pinned in `criteria-<jd sha12>.yaml` **next to the JD
   file** (for a fetched JD: `~/.cache/ats-check/criteria/`, keyed by the JD's sha, so every resume shares one pin). The
   file is yours to edit; it is validated before any LLM call (malformed: exit 2) and never overwritten without
   `--recriteria`, which keeps the old file as `.yaml.bak`.
   Step 2: `--grade-samples N` (default 5) independent sonnet runs over the parsed resume text, criteria shuffled per run
   (seeded by the run index), each returning `met|partial|not_met` and one resume line. The quote is checked in code: >= 3
   words, word-bounded, inside ONE resume segment (a bullet; a bullet wrapped over PDF lines counts as one), after
   case / smart-quote / dash / middle-dot / whitespace normalisation; ellipsis-joined fragments must share a segment.
   A run whose quote fails is `ungrounded`: it is not counted as `not_met`, its quote is never shown, and when most runs
   are ungrounded the criterion is `undecided` with "model claimed met, quotes not found in resume". A `met` resting only
   on the Skills section for an experience-type criterion ("experience", "years", "built"...) is capped at `partial`.
   A status needs >= ceil(0.8 N) runs, else `undecided`. With `--master` the quoted line is traced to the id bullet /
   Skills row it is cut from by word overlap ("NOT TRACEABLE to one master bullet" for composite lines).
   Band, on the basic screenable criteria only: all `met` -> "A/B band", any `not_met` -> "C/D band", otherwise "band
   undecided". **Deviation from the plan's binary rule**: HiredScore documents A/B vs C/D; a basic criterion that is only
   partial or undecided (none not met) gets the third outcome here instead of a forced C/D. The rule is documented for
   HiredScore; whether an employer runs it is unknown, so the wording is conditional. The grader and the resume writer share
   a model family, which biases it upward (arXiv 2509.00462). It is a structured opinion, not a prediction. One call per
   run grades all criteria together (the platform grades each on its own).
   `--stability K` re-grades K times fresh (own salt per invocation) and prints and writes (`stability.json`) the
   per-criterion flip rate.
6. **Score.** See below.

### The truth column (needs `--master`)

Each requirement gets one of: `ok` (in the resume), `TRUE, ADD IT` (absent from the resume, present
in the master evidence, which is quoted), `add the other form`, `gap, not added until the master records it`
(absent from both), `not supported by master` (a claim-guard row).

- **Evidence is structural.** Support comes only from (a) id-carrying bullets `- **KPE-01** ...` under the
  Experience / Projects / Open source sections and (b) the "Allowed wording" cells of the Skills table. Rules,
  variant keyword banks, cut procedures, tables of PR titles, headers and prose notes are never evidence: a word found
  there is a coincidence ("text appears at the cursor" is not Cursor). A product or proper-noun term (a single
  Capitalised word that is not a synonym-group head: Cursor, French, LinkedIn, OpenAI) matches case-sensitively, and
  never as the head of a hyphenated modifier ("OpenAI-compatible" is not OpenAI).
- **The claim guard is a structure, not text.** Its "Claims not supported" and "Metrics not used" table rows become rejected
  claims; its text is never evidence. A years claim ("7+ years of software engineering") rejects a requirement only when the
  JD asks for years of that area, a metric ("350K MAU") only the requirement that names it ("MAU"), a plain claim the same
  phrase. A row's own "write instead" wording keeps a term usable ("English (professional working proficiency)").
  A rejected requirement is never `TRUE, ADD IT`.
- A master line that denies a term ("Java: none", "has NOT worked in Hubspot") never counts as support, but only when it
  denies the term itself ("events, not website visitors" denies "website visitors", not "website"). A cue covers items that start
  with the term, so "Hubspot CRM" is covered and the bare word CRM is not. If the resume itself has such a term, a top-ranked
  "Confirm" fix appears. Hard requirements absent from the master are listed in an "Ask the candidate" block.
- A word match is still only a word match: read the quoted master line before adding anything.
- "X% if the listed true additions are made" is **not a ceiling**: it prices only the `TRUE, ADD IT` rows (a flat 0.7 each); it
  does not model moving a present term to a better placement, nor a master fact worded differently from the JD.

### Score weights (all in code: `jd_reqs.IMPORTANCE_W`, `match.PLACEMENT_W`, `score.py`)

- Requirement importance: required 3, preferred 2, mentioned 1.
- Placement credit (best placement + 0.1 per extra distinct placement, cap 1.0): current/most recent
  role 1.0, headline 0.8, summary 0.7, recent role 0.7, projects 0.6, older role 0.5, other 0.5,
  Skills list 0.4, education 0.3. Stuffing caps a term at 0.5.
- Soft requirements (LLM kind `soft`, or a term like communication / collaboration / mentoring /
  stakeholder / mindset) are **not in coverage**: recruiter keyword search runs on hard skills, tools
  and titles. They get their own report section ("evidenced in a role bullet?") with zero weight.
- Coverage (hard requirements only) = importance-weighted mean of those credits, in whole percent, reported for the resume as
  is and "if the listed true additions are made" (every `TRUE, ADD IT` item at 0.7; not a ceiling). Required-only and
  overall are both shown. No decimals: the weights are judgment, not measurement.
- Verdict order: parse FAIL -> `FIX PARSING FIRST`; a knock-out marked `risk` -> `KNOCK-OUT RISK`;
  else the MEDIAN required coverage over the extraction samples: >= 80 strong, >= 60 moderate, else weak. Strong is held at
  `STRONG KEYWORDS, YEARS GATE TO CHECK` while a JD years requirement is `review` or `unknown`. A JD with only preferred terms
  is `NO REQUIRED KEYWORDS`.
- Fix ranking: parse FAIL (1000) > knock-out risk/add (200/150) > true additions
  (40 x importance x gain) > other-form (14 x importance) > use-in-role (10 x importance) >
  stuffing (20) > parse WARN (30).

## What the output can and cannot be trusted for

- **Trust:** parse failures (the extractors really disagree, and the evidence quotes the text);
  which JD terms are literally absent from what a parser reads; where a term sits; the master-based
  split of true additions vs gaps vs rejected claims.
- **Do not trust as a prediction:** the coverage percent or the AI grade. No public spec exists for
  Workday/HiredScore/Ashby ranking, so the AI layer is an LLM proxy and the coverage number is a
  relative guide for comparing two versions of the same resume against the same JD, not a
  probability of being shortlisted.
- Not modelled: knock-out questions asked inside the application form, recruiter sourcing outside
  the ATS, DOCX-specific parsing (headers in DOCX are dropped more reliably than in PDF; here the
  header check is positional, a heuristic), non-English resumes, OCR-based pipelines (image OCR via `tesseract` is
  evidence only, not scored).
- Knock-outs: "N+ years of <area>" is computed from the dated entries whose title or bullets name the area (never from the total
  career span); no such entry -> `review`. A years requirement without an area uses the career span and stays a human call.
  Location and clearance are surfaced for review, never decided.
- Deterministic JD extraction (`--no-llm`) is noisier: read its term list before acting.

## Safety of the LLM layers

Every call is `claude -p --tools "" --settings '{"permissions":{"deny":["Read"]}}'
--setting-sources "" --safe-mode --strict-mcp-config --disable-slash-commands`, prompt on stdin, empty
temp cwd, JSON out. `--tools ""` alone does not stop `@path` reads, and the deny fails open on a bad
value, so before the first LLM call per CLI version the tool plants a canary file naming a random
fruit and aborts the LLM layers (falls back to deterministic) if the model can name it. Positive
control measured on 2.1.325: without the deny the canary leaks, with it it does not.
Resume and JD text are inserted as data with an instruction not to follow them.

## Dependencies

Python 3.13 via `uv` (`pyproject.toml` + `uv.lock`): PyMuPDF, pdfplumber, PyYAML. System: poppler
(`pdftotext`), `curl` (JD fetch: Workday's edge answers 429 to Python's urllib on the detail call),
`claude` CLI (Claude Code; LLM layers, optional with `--no-llm`), optional `tesseract` (image OCR evidence), optional `filee` CLI, optional Node for the [OpenResume layer](#the-openresume-layer-optional). No Java,
no JVM, no download cache: everything is a Python wheel or a tool already installed.

### Extractors: why these engines

| Extractor | Engine | Family it stands for |
|---|---|---|
| `pdftotext-layout`, `pdftotext-raw` | poppler | Linux/server toolchains, many desktop viewers; `-layout` interleaves columns, `-raw` follows the content stream |
| `pymupdf` | MuPDF | fast commercial-grade extraction, block/stream order |
| `pdfplumber` | pdfminer.six | the Python ecosystem's default (resume parsers built on spaCy/NLTK usually start here) |
| `pypdfium2` | PDFium | Chrome / Edge PDF viewers, so what a browser-based parser sees |
| `filee` | PdfPig, the .NET port of Apache PDFBox (Filee's PDF to TXT, installed CLI `filee`, override `ATS_CHECK_FILEE`) | the Java / PDFBox family used by Tika-based pipelines, without a JVM |

If `filee` is missing the extractor is skipped with a WARN ("extractors" check), not a FAIL; the
other four engine families still compare. The version of each is in `report.json`.
Apache Tika was dropped (it needs a JVM, which flashes a Dock icon on macOS).

## The OpenResume layer (optional)

A second, independent reader of the same PDF: [OpenResume](https://github.com/xitanggg/open-resume)'s own parser (`readPdf` -> `groupTextItemsIntoLines` -> `groupLinesIntoSections` -> `extractResumeFromSections`), run unmodified on pdf.js text items and compared with the consensus of our extractors. It catches what text-only extractors cannot: our five engines return text, OpenResume works on pdf.js items, their order, positions and fonts, so a PDF can read perfectly in all five and still lose words, bullets or a role in OpenResume. It is one open-source parser, not a production ATS: its findings are evidence of fragility, not a prediction of any vendor's behaviour.

Install (needs `node` >= 20, `npm`, `git`; about 65 MB in `~/.cache/ats-check/openresume`, or `$ATS_CHECK_CACHE/openresume`, or the folder in `ATS_CHECK_OPENRESUME`; `sh tools/openresume/install.sh --print-dir` prints the absolute folder both the installer and the check use):

```
sh tools/openresume/install.sh        # from the offersmith checkout or ${CLAUDE_PLUGIN_ROOT}
```

It fetches OpenResume at one pinned commit (`4f8255a`, verified by `git rev-parse`), `pdfjs-dist` 3.7.107 and `tsx` from the lockfile in `tools/openresume/`, and `tools/openresume/run.ts` runs the parser and prints one JSON line. `ATS_CHECK_OPENRESUME=off` switches the layer off silently (it is never read as a folder). The folder holds code that is run, so the check refuses it (one WARN) unless it is owned by you and not group- or world-writable and its OpenResume checkout is the pinned commit with no local change; the installer creates it private. The runner runs in its own process group with a 120 s deadline and 32 MiB / 64 KiB caps on stdout / stderr (the whole group is killed on a timeout or a cap), with a minimal environment (`PATH`, `HOME`, `TMPDIR`, `LANG`, `LC_ALL` and its own `NODE_OPTIONS`), and its output is validated before any comparison. With the layer not installed, or Node missing, or the runner failing or answering with something unexpected, the report carries one WARN ("OpenResume parser layer": skipped, with the install command) and nothing else changes; it is never a FAIL. OpenResume is AGPL-3.0: nothing of it is stored in this repository or the wheel, it is fetched on the user's machine and run locally and unmodified (see [THIRD_PARTY.md](../THIRD_PARTY.md)). `pdfjs-dist` is pinned to the version in OpenResume's own lockfile so the layer sees the same text items OpenResume sees; that version has a known flaw (GHSA-wgrm-67xf-hhpq), so the runner runs with `--disallow-code-generation-from-strings` and refuses to start without it, and `run.ts` also passes `isEvalSupported: false` to pdf.js, the advisory's own workaround (pdf.js exports `getDocument` through a non-configurable getter, so `run.ts` swaps the module's entry in the require cache for a copy with a wrapped `getDocument`, which also records the page ends so the PDF is parsed once; no OpenResume source is edited).

| Check (id) | What it compares | Result |
|---|---|---|
| pdf.js item granularity (`or_granularity`) | share of pdf.js items without any whitespace on body lines (lines of >= 6 words) | WARN at >= 50% of >= 24 items: most words arrive as their own pdf.js item (LaTeX font expansion / microtype, per-word positioning); an item that carries a space of its own does not count |
| Glued words (`or_glued`) | an OpenResume token of >= 6 word characters (letters and digits) that no extractor has as a word but that equals 2-6 consecutive words of one consensus line | WARN, quotes `SeniorAIPlatformEngineer` against `Senior AI Platform Engineer` |
| Bullet glyph (`or_bullets`) | the glyph that starts the consensus bullet lines of Experience against OpenResume's own `BULLET_POINTS` (read from the parser, not copied), when it did not extract one description per bullet anyway | WARN names the glyph (code point and name) and the list |
| Work entries (`or_entries`) | per consensus entry with a recognised title, matched by its years (and, for concurrent roles, by title or company text): title, company, dates; entries with no company, title or date (a role split by a vertical gap > 1.4x the usual line gap); a role with no OpenResume entry | WARN (also when it finds none, which happens when it does not take the heading for work experience) |
| Education (`or_education`) | school or degree empty (for example `BBA, University of X` on one bold line scores as neither) | WARN |
| Page boundary (`or_page_boundary`) | a role header or section heading that OpenResume joined onto the previous page's last line | WARN, labelled a limitation of OpenResume; left out of `Top fixes` and not counted again as a missing role in `or_entries` |
| Contact (`or_contact`) | email, phone, name, location against the consensus parse | WARN |

Every finding is a WARN; this layer never produces a FAIL. A FAIL turns the verdict into "FIX PARSING FIRST", and OpenResume is one hobby parser: ordinary formatting (a comma after the email, a heading such as "Professional Background") makes it lose a field that the other five extractors read fine, and a verdict that depended on whether Node is installed would be wrong. A field every extractor loses is already a FAIL in the existing checks (`email`, `sec_experience`, `entries`); the layer adds the finding that this parser, which a real ATS may resemble, loses it. Page boundary is the weakest signal: in OpenResume's code `readPdf` concatenates the items of all pages, `groupTextItemsIntoLines` starts a new line only after an item with `hasEOL`, and pdf.js sets no `hasEOL` on the last retained item of a page in the PDFs tested (`lastHasEOL: false` on every page), so the first line of page N+1 is appended to the last line of page N. A parser that reads pages separately is unaffected; the check says so and offers the layout workaround (let the page break fall between two bullets of a role, not right before its header). The `Founder,` finding is likewise specific to OpenResume: it matches a job title only when a whitespace-separated word equals a title in its fixed list, so a comma after the title word loses the title.

Not covered: OpenResume's skills, projects and custom sections, and anything OpenResume does not parse. The thresholds (50% of items, 24 items, 6 characters) come from three real LaTeX resumes and the synthetic fixtures, not from a labelled corpus.

## Tests

`uv run pytest` needs `pdftotext` (poppler) and `tesseract`; `tests/test_openresume.py` also needs the OpenResume layer (`sh tools/openresume/install.sh`; it skips when Node or the install is missing, and fails in CI). The suite switches the layer off everywhere else. The suite replaces the Filee CLI with `tests/fake_filee` (poppler text behind Filee's argv), so results do not depend on a locally installed `filee`; the real PdfPig engine is therefore not exercised by the tests.

`tests/fixtures/*.pdf` (all about a made-up candidate, Jane Q. Example) are generated with `typst` (`uv run python tests/make_fixtures.py`):
clean (must pass everything), two-column, ruled table, contact only in page header, ligature code
points, "My Journey" heading, "Spring '22" dates, skills as an image, icon glyphs, and a copy of the
clean one with ToUnicode stripped. For the layout reading (`tests/test_layout_rows.py`): `wrap_shapes` (seven roles; wrapped rows that
end in a date or a range, open with a month or lowercase, wrap at `Acme Inc.` or `:`, hold `Product owner in Mar 2019`, a short undated
tail and a bare `2`; lowercase-brand, `macOS`, date-first and long single-date headers and a header whose date row ends in `| remote`; a phone split over rows, a skills list wrapped around a bare `2`), `break_page` (a bullet cut
by the page break), `foot_bare` / `foot_of` / `foot_page` / `foot_slash` / `foot_high` (above the band) / `foot_running` / `foot_single`
(page footers `1`, `1 of 2`, `Page 1 of 2`, `1/2` between two bullets), `undated_brand` and `season_brand` (a lowercase-brand header with no date, and with `Spring '19`: still FAIL), `indented_headers` / `centered_headers` (headers not at the section-heading x, `Spring` dates: FAIL), `header_repeats_wrapped_row`, `header_at_bullet_text_indent`, `bold_word_wrap`, `nested_bullets`, `digit_band` / `band_skill` (short bottom margin: a date row and a lone `808` in the footer band), and `flat_bullets` /
`hanging_marker` (no bullet indent: the line-shape fallback, FAIL as before). Rebuild a few with `uv run python tests/make_fixtures.py wrap_shapes foot_slash` (a newer typst changes the bytes of the rest). Each bad fixture trips its own check and a mutation proves it
`or_clean`, `or_wordwise` (one text matrix per word), `or_endash`, `or_gap`, `or_oneline_edu`, `or_pagebreak` and `or_background` (a comma after the email, a heading OpenResume does not know) are the OpenResume-layer set: the base reads cleanly and each other differs by one defect. Each bad fixture trips its own check and a mutation proves it
(`tests/mutate.py` edits one call site, the named test must go RED; every mutant is killed, run it to see the count). LLM layers are
mocked (the CLI path is exercised by patching `llm.subprocess`, where the default runner is bound); the sandbox flags, canary logic and alias verification are unit-tested.

Docs: [docs/prior-art.md](prior-art.md).

## License

Apache-2.0, see [LICENSE](../LICENSE).
