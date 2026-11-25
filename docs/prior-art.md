# Prior art (pass of 2026-11-19, time-boxed)

What I opened and read is marked **read**; what rests only on a search snippet or a secondary
write-up is marked **snippet** and is treated as a hint, not a fact.

## Open-source resume parsers / ATS simulators

| Project | What it is | What we took | Status |
|---|---|---|---|
| [OpenResume](https://github.com/xitanggg/open-resume) `src/app/lib/parse-resume-from-pdf/` (**read**: `group-lines-into-sections.ts`, `extract-profile.ts`) | Browser PDF parser with a documented 5-step algorithm: read text items (pdf.js) -> group into lines -> group lines into sections by *heading line* (bold + ALL CAPS, else a keyword fallback: experience / education / project / skill + a few secondary ones) -> per-section extractors that score each text item by features (email has `@`, phone matches `(xxx) xxx-xxxx`, location `City, ST`, name = bold/caps near the top). | The pipeline shape and the feature-scoring idea for contact fields; heading keyword table (`fields.CANON`); "first lines are profile, a heading owns every line until the next heading". We run it on the plain text of EVERY extractor instead of one pdf.js read, so a field is trusted only when it parses under all of them. | AGPL-3.0, 9.0k stars, last push 2024-10: ideas reused, **no code copied**; also run unmodified as an optional second reader, fetched on the user's machine and never stored here (see [ats-check](ats-check.md#the-openresume-layer-optional)). |
| [Resume-Matcher](https://github.com/srbhr/Resume-Matcher) (**snippet**) | LLM-assisted resume tailoring; README says the ATS score (`services/ats.py`) and an `ats_parse/` check are plain code with no LLM call, and the check runs the PDF through real extractors. | Confirms the split we use: deterministic gate, LLM only as an advisor. Not read in depth. | Apache-2.0 per repo; not vendored. |
| [sunnypatell/ats-screener research](https://github.com/sunnypatell/ats-screener/blob/main/research/ats-parsing-scoring-research.md) (**read**, secondary, dated 2026-02) | Write-up of ATS vendors. Claims: Textkernel (ex-Sovren) is the parser behind Oracle, Lever, Bullhorn, **Salesforce**; Workday's parser is proprietary, Workday bought **HiredScore** in 2024 (AI ranking, explainable, not generative), historically keyword search + manual filters; nontraditional headings, columns, tables, graphics "may not parse"; Greenhouse does not auto-score; Taleo has criteria-based scoring. | Parser failure classes (columns, tables, headers/footers, text boxes, images, headings) as the checklist; "AI grader is advisory, human + keyword search is the base". | Vendor-neutral-ish blog-grade source; treat vendor attributions as unverified. |
| Jobscan / resume-adapter / onflycv style posts (**snippet**) | Marketing pages: single column, standard headings, `MM/YYYY` dates, no tables/text boxes/headers, contact in the body. | Same list; consistent with OpenResume's heading and date handling. | Marketing; nothing here is measured. |
| [Apache Tika](https://tika.apache.org/) 4.2.0 (**read**, tried locally, later dropped) | Content extraction toolkit; PDF via PDFBox. | Was the Java-family extractor; replaced by Filee (PdfPig, a .NET port of PDFBox) so the tool needs no JVM. | Apache-2.0. |
| pyresparser / spaCy-based parsers (not opened) | NLTK/spaCy NER over text. | Nothing: they assume clean linear text and do not model layout failure, which is the point of this tool. | Skipped deliberately. |

## What commercial parsers are known to choke on (consistent across the sources above)

Multi-column and sidebar layouts (read across the gutter), tables and text boxes (cells linearised
out of order, dates detach from titles), content in headers/footers (often dropped; the main
contact-loss risk), text in images/icons (needs OCR; Textkernel does it, many ATS parsers do not),
non-standard headings ("My Journey" is not mapped to Experience), unparseable dates (seasons,
`'23`), fonts without a ToUnicode map (glyph IDs instead of letters), and ligature code points
(`workﬂow` does not match `workflow`).

## Decisions taken from this

1. Layer 1 compares **five engine families** (poppler layout + raw, MuPDF, pdfminer.six, PDFium, PdfPig via Filee) and reports
   disagreement as evidence instead of picking one "the ATS".
2. Field extraction follows OpenResume's section-first approach but runs per extractor.
3. Recruiter search is modelled as literal phrase matching on the parsed text, with a synonym table,
   because that is what boolean search does; the AI grader is a separate, labelled-advisory layer.
4. Not modelled (no public spec to ground it): the real Workday/HiredScore ranking function.
   The README says so; the AI layer is an LLM proxy for it, not a replica.
