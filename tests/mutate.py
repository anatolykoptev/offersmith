"""Mutation proof: each mutant edits ONE call site and the named test must go RED.

Run: uv run python tests/mutate.py        (exit 0 only if every mutant is killed)
The source file is restored after each mutant, even on Ctrl-C.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "ats_check"
P = "tests/test_parse_health.py"
M = "tests/test_match.py"
J = "tests/test_jd_llm.py"
N = "tests/test_negation.py"
R = "tests/test_master_real_layout.py"
S = "tests/test_samples.py"
G = "tests/test_score_gates.py"
W = "tests/test_cli_wiring.py"
P3 = "tests/test_p3.py"
OR = "tests/test_openresume.py"
T = "tests/test_layout_rows.py"

# (file, anchor, replacement, test selector, what it proves)
MUTANTS = [
    ("health.py", "    if g.columns:\n        st = FAIL if low else WARN", "    if False and g.columns:\n        st = FAIL if low else WARN", f"{P}::test_bad_fixture_trips_its_check[two_column-columns-FAIL]", "columns check"),
    ("health.py", "    if g.tables:\n        st = FAIL if low else WARN", "    if False and g.tables:\n        st = FAIL if low else WARN", f"{P}::test_bad_fixture_trips_its_check[table_experience-tables-FAIL]", "tables check"),
    ("health.py", "if hf_contact and not fd.EMAIL.search(body_text)", "if False and hf_contact and not fd.EMAIL.search(body_text)", f"{P}::test_bad_fixture_trips_its_check[header_contact-header_footer-FAIL]", "header/footer check"),
    ("health.py", "    if lig:\n", "    if False and lig:\n", f"{P}::test_bad_fixture_trips_its_check[ligatures-ligatures-WARN]", "ligature check"),
    ("health.py", "    if bad:\n        checks.append(Check(\"tounicode\"", "    if False and bad:\n        checks.append(Check(\"tounicode\"", f"{P}::test_bad_fixture_trips_its_check[no_tounicode-tounicode-FAIL]", "ToUnicode check"),
    ("health.py", "    if big_empty:", "    if False and big_empty:", f"{P}::test_bad_fixture_trips_its_check[skills_image-images-FAIL]", "image-text check"),
    ("health.py", "    if icons:\n", "    if False and icons:\n", f"{P}::test_bad_fixture_trips_its_check[icon_contact-icons-WARN]", "icon check"),
    ("health.py", "    if unknown:\n", "    if False and unknown:\n", f"{P}::test_bad_fixture_trips_its_check[heading_renamed-headings-WARN]", "non-standard heading check"),
    ("fields.py", "    u = UNPARSEABLE.search(line)\n    if u:", "    u = None\n    if u:", f"{P}::test_season_dates_name_the_offending_text", "unparseable-date detection"),
    ("fields.py", '("experience", ("experience",', '("experience", ("journey", "experience",', f"{P}::test_bad_fixture_trips_its_check[heading_renamed-sec_experience-FAIL]", "experience heading recognition (mutant makes 'My Journey' parse)"),
    ("score.py", "    if fails:\n        label = \"FIX PARSING FIRST\"", "    if False:\n        label = \"FIX PARSING FIRST\"", f"{J}::test_failed_parse_gates_the_verdict", "parse gate in the verdict"),
    ("match.py", "STUFF_LIMIT = 3", "STUFF_LIMIT = 99", f"{M}::test_stuffing_detector_caps_score", "stuffing detector"),
    ("match.py", '"skills": 0.4', '"skills": 1.0', f"{M}::test_placement_weights_current_role_beats_skills_beats_nothing", "placement weights"),
    ("match.py", '"older_role": 0.5', '"older_role": 1.0', f"{M}::test_older_role_weighs_less_than_current", "older-role placement"),
    ("match.py", "        elif r.master_hit:\n            r.status = \"add_it\"", "        elif False:\n            r.status = \"add_it\"", f"{M}::test_truth_column_add_it_vs_gap", "truth column add-it"),
    ("match.py", 'text[b:b + 1] == ")"', 'text[b:b + 1] == "~"', f"{M}::test_acronym_and_spelled_form_both_present_is_one_mention_and_no_missing_form", "paired acronym = one mention"),
    ("match.py", "                if any(is_expansion(f, g) or is_expansion(g, f) for g in present):", "                if True:", f"{M}::test_synonym_that_is_not_an_expansion_is_not_a_missing_form", "form-missing needs a real expansion pair"),
    ("match.py", "or f.lower() not in jd_forms or", "or False or", f"{M}::test_only_forms_the_jd_uses_are_suggested", "only JD-literal forms are suggested"),
    ("match.py", 'UBIQUITOUS = {"api", "apis", "rest", "aws",', 'UBIQUITOUS = {"api", "apis", "rest", "awsx",', f"{M}::test_ubiquitous_acronyms_are_never_nagged", "ubiquitous-acronym exemption"),
    ("match.py", "    hard = [r for r in results if not r.soft]", "    hard = list(results)", f"{M}::test_soft_skills_are_classified_and_excluded_from_coverage", "soft skills out of the coverage denominator"),
    ("cli.py", 'if not r.soft and r.status == "gap"', 'if r.status == "gap"', f"{J}::test_report_lists_soft_separately_and_asks_the_candidate_about_absent_hard_terms", "ask-candidate block lists hard terms only"),
    ("match.py", "        r.master_hit = bool(mh) and not neg_line", "        r.master_hit = bool(mh)", f"{N}::test_negation_beats_a_loose_positive_mention_elsewhere", "negation beats a loose positive mention"),
    ("negation.py", "    tails = [(m.start(1), m.end(1)) for m in TAIL.finditer(line)]", "    tails = []", f"{N}::test_scope_offsets", "'TERM: none' tail"),
    ("negation.py", "    for ym in NOT_YET.finditer(line):", "    for ym in []:", f"{N}::test_dated_denials_are_no_support", "'GCP, Azure and Kubernetes not yet' list"),
    ("negation.py", "        if NOT_A_CUE_FOLLOWER.match(line, cm.end()):\n            continue", "        if False:\n            continue", f"{N}::test_not_only_is_not_a_negation", "'not only' is not a cue"),
    ("negation.py", ' and "dependenc" not in " ".join(text.split()[:4]).lower()', "", f"{N}::test_no_x_dependency_is_not_a_claim_negation", "'no X dependency' exemption"),
    ("negation.py", "    text = starts.get(a)\n    if text is None or", "    text = next((t for o, t in starts.items() if abs(o - a) < 12), None)\n    if text is None or", f"{N}::test_a_denial_of_a_compound_does_not_deny_its_last_word_when_that_word_is_not_the_item_start", "a denial governs only items that START with the term"),
    ("extract.py", 'read_text(encoding="utf-8-sig"', 'read_text(encoding="utf-8"', "tests/test_parse_health.py::test_filee_extractor_reads_txt_output_strips_bom_and_records_version", "Filee BOM stripped"),
    ("extract.py", 'return Extraction("filee", False, error="filee CLI not installed', 'raise RuntimeError("filee CLI not installed', "tests/test_parse_health.py::test_missing_filee_is_a_warn_not_a_fail", "missing Filee degrades to WARN"),
    ("jd_reqs.py", "    if tt <= ta or (ta < tt and len(ta) >= 2):", "    if tt <= ta or ta < tt:", f"{J}::test_llm_aliases_are_trusted_only_when_verifiable", "generic single-word alias rejected"),
    ("match.py", "    return (\"…\" if a else \"\") + line[a:b].strip()", "    return line[:140]", f"{M}::test_master_evidence_is_centred_on_the_match", "evidence snippet centred on the match"),
    ("match.py", "(?<![\\w/@])(?<!\\w-){body}", "(?<![\\w]){body}", f"{M}::test_term_inside_a_hyphenated_name_or_path_is_not_a_match", "hyphenated-compound / path guard"),
    ("jd_reqs.py", "        keep = [a for a in al if alias_ok(term, a, groups)]", "        keep = list(al)", f"{J}::test_unverifiable_alias_is_dropped_and_reported", "LLM alias verification"),
    ("llm.py", 'json.dumps({"permissions": {"deny": ["Read"]}})', 'json.dumps({"permissions": {"deny": []}})', f"{J}::test_sandbox_argv_denies_read_and_everything_else", "Read deny in the sandbox"),
    ("llm.py", "    safe = fruit not in out.lower()", "    safe = True", f"{J}::test_selfcheck_detects_a_leak_and_a_clean_run", "canary self-check"),
    ("jd_reqs.py", "            if not ok:\n                raise llm.LLMError(\"sandbox self-check failed", "            if False:\n                raise llm.LLMError(\"sandbox self-check failed", f"{J}::test_failed_sandbox_selfcheck_blocks_the_llm", "self-check gates the JD call"),
    # ---- 2026-11-19 audit fixes: each mutation edits ONE call site and the named test must go RED
    ("cli.py", "master_mod.load_files(args.master, args.guard)", "master_mod.load(args.master.read_text())", f"{R}::test_the_claim_guard_next_to_the_master_is_loaded_and_rejects", "B2/M1: CLI loads the sibling claim guard"),
    ("master.py", "    m.guard = parse_guard(text) +", "    m.support += [Line(l, \"bullet\") for l in text.splitlines() if l.strip()]\n    m.guard = parse_guard(text) +", f"{R}::test_words_outside_evidence_are_never_add_it", "B2: Rules / banks / PR tables / header are not evidence"),
    ("match.py", "        if find_all(forms, row.instead):\n            continue", "        if False:\n            continue", f"{M}::test_write_instead_wording_lets_an_unsupported_term_stay_a_plain_gap", "M1: a row's write-instead wording keeps a term usable"),
    ("match.py", "        core = _norm(claim_core(claim))\n        return bool(core) and any(_norm(f) == core for f in forms)", "        return True", f"{M}::test_a_guard_metric_rejects_the_requirement_that_names_it_and_nothing_else", "M1: a metric row rejects only the term that names it"),
    ("match.py", "        elif rej and (rej_exact or not r.master_hit):\n            r.status = \"rejected\"", "        elif False:\n            r.status = \"rejected\"", f"{M}::test_unqualified_rejected_phrase_rejects_the_same_phrase", "M1: guard rejection"),
    ("match.py", "            out.add(f)", "            pass", f"{R}::test_words_outside_evidence_are_never_add_it", "B2: proper nouns match the master case-sensitively"),
    ("match.py", "    guard = r\"(?!-[A-Za-z])\" if proper else \"\"", "    guard = \"\"", f"{R}::test_words_outside_evidence_are_never_add_it", "B2: 'OpenAI-compatible' is not 'OpenAI'"),
    ("negation.py", "    return all(w in DENY_REST or re.fullmatch(r\"[\\d\\-.]+\", w) for w in rest)", "    return True", f"{N}::test_a_denied_longer_phrase_does_not_deny_the_word_it_starts_with", "minor: negation vetoes only a line that denies the term itself"),
    ("ai.py", ".replace(\"{resume}\", resume_text)", ".replace(\"{resume}\", \"\")", f"{S}::test_the_screener_prompt_carries_both_texts", "screener prompt carries the resume"),
    ("cli.py", "jd_reqs.extract(jd_text, not args.no_llm,", "jd_reqs.extract(jd_text, False,", f"{S}::test_cli_runs_the_llm_extraction_and_the_screener", "CLI wires the LLM extractor"),
    ("cli.py", "        ai = ai_mod.screen(jd_text, resume_text, args.refresh)", "        ai = None", f"{S}::test_cli_runs_the_llm_extraction_and_the_screener", "CLI wires the AI screener"),
    ("cli.py", "args.refresh, samples=args.samples)", "False, samples=args.samples)", f"{S}::test_cli_runs_the_llm_extraction_and_the_screener", "--refresh reaches the extractor"),
    ("cli.py", "ai_mod.screen(jd_text, resume_text, args.refresh)", "ai_mod.screen(jd_text, resume_text, False)", f"{S}::test_cli_runs_the_llm_extraction_and_the_screener", "--refresh reaches the screener"),
    ("score.py", "    elif req >= 80:\n", "    elif req >= 0:\n", f"{G}::test_verdict_thresholds", "STRONG threshold"),
    ("score.py", "    elif req >= 60:\n", "    elif req >= 0:\n", f"{G}::test_verdict_thresholds", "MODERATE threshold"),
    ("score.py", "    elif risk:\n", "    elif False:\n", f"{G}::test_a_knockout_risk_outranks_a_strong_match", "knock-out risk verdict"),
    ("score.py", "    elif req >= 80 and gates:", "    elif req >= 80 and False:", f"{G}::test_strong_keywords_do_not_make_a_strong_match_while_the_years_gate_is_open", "M4: years gate caps STRONG"),
    ("score.py", "    req = cov.get(\"required_median\", cov.get(\"required\"))", "    req = cov.get(\"required\")", f"{G}::test_verdict_thresholds", "B1: verdict uses the median"),
    ("match.py", "\"required_found\": sum(1 for r in req if r.hits)", "\"required_found\": len(req)", f"{G}::test_coverage_counts_found_and_achievable", "required_found counts hits"),
    ("match.py", "\"required_achievable\": cov(req, \"achievable\")", "\"required_achievable\": cov(req)", f"{G}::test_coverage_counts_found_and_achievable", "required_achievable uses achievable"),
    ("match.py", "(0.7 if r.master_hit else 0.0)", "(0.0 if r.master_hit else 0.0)", f"{G}::test_coverage_counts_found_and_achievable", "an add_it row is worth 0.7"),
    ("report.py", "return f\"{cov['required_achievable']}% if the listed", "return f\"{cov['required']}% if the listed", f"{S}::test_report_prices_the_true_additions_not_the_current_coverage", "report prints the achievable number"),
    ("report.py", "    if cov.get(\"required_range\"):\n        lo, hi", "    if False:\n        lo, hi", f"{S}::test_cli_reports_the_median_and_the_range_of_required_coverage", "B1: report headline shows the range"),
    ("jd_reqs.py", "any(a in g for a in alts)", "any(t in g for t in tt)", f"{J}::test_llm_aliases_are_trusted_only_when_verifiable", "M2: alias gate"),
    ("synonyms.yaml", "  - [Docker, containerization]", "  - [Docker, containers, containerization]", f"{M}::test_matcher_does_not_find_a_different_thing", "M2: synonym tightening (Docker/containers)"),
    ("synonyms.yaml", "  - [Agentic AI, AI agents, agentic workflows, LLM agents]", "  - [Agentic AI, AI agents, agentic, agentic workflows, LLM agents]", f"{M}::test_matcher_does_not_find_a_different_thing", "M2: synonym tightening (bare agentic)"),
    ("match.py", "    if form == \"Go\":", "    if False:", f"{M}::test_matcher_does_not_find_a_different_thing", "M2: Go is not Go-to-Market"),
    ("match.py", "    return esc + \"(?:s|es)?\"", "    return esc", f"{M}::test_matcher_finds_plural_singular_and_wrapped_phrases", "M3: singular term matches a plural resume"),
    ("match.py", "        return re.escape(tok[:-1]) + \"s?\"", "        return esc", f"{M}::test_matcher_finds_plural_singular_and_wrapped_phrases", "M3: plural term matches a singular resume"),
    ("match.py", "        cont = (bool(offs) and", "        cont = (False and", f"{M}::test_wrapped_phrase_is_attributed_to_the_line_it_starts_on", "M3: wrapped phrases are joined"),
    ("match.py", "    case_sensitive = proper or form.isupper() or core.isupper() or", "    case_sensitive = proper or", f"{M}::test_acronyms_are_case_sensitive_but_prose_is_not", "case-sensitive acronyms"),
    ("match.py", "            specific = sum(1 for h in r.hits if len(h.form) > 3)", "            specific = len(r.hits)", f"{M}::test_short_acronyms_are_not_stuffing_but_long_terms_are", "short-acronym stuffing exemption"),
    ("match.py", "    if not core:      # 'N+ years of experience' with no area: the whole career counts", "    if True:", f"{G}::test_years_of_an_area_are_not_resolved_from_the_career_span", "M4: years of an area are not the career span"),
    ("jd_reqs.py", "(?<![A-Za-z])(bachelor|master|ph\\.?d|degree|(?-i:B\\.?S\\.?|M\\.?S\\.?))(?![A-Za-z])", "(bachelor|master|ph\\.?d|b\\.?s\\.?|m\\.?s\\.?|degree)", f"{G}::test_degree_regex_needs_word_boundaries", "degree regex word boundaries"),
    ("health.py", "lambda p: p.location, \"Add", "lambda p: True, \"Add", f"{P}::test_location_check_fails_soft_when_no_view_has_a_place", "M6: location check"),
    ("fields.py", "    contact = [l for l in prof if EMAIL.search(l) or PHONE.search(l)]\n    for line in contact:", "    contact = []\n    for line in []:", f"{P}::test_location_is_the_contact_line_not_a_headline", "M6: location from the contact line"),
    ("health.py", "                elif fd.looks_like_location(e.company):", "                elif False:", f"{P}::test_company_that_is_a_location_fragment_is_flagged", "M6: location-fragment company"),
    ("health.py", "    if len(set(sig.values())) > 1:\n        out.append(Check(\"entries_fragile\"", "    if False:\n        out.append(Check(\"entries_fragile\"", f"{P}::test_a_job_that_vanishes_in_one_view_is_a_fix_not_a_pass", "M6: entry loss across views"),
    ("score.py", "c.id not in (\"location\", \"phone\", \"name\", \"reading_order\",", "c.id not in (\"location\", \"phone\", \"name\", \"entries_fragile\", \"reading_order\",", f"{P}::test_a_job_that_vanishes_in_one_view_is_a_fix_not_a_pass", "M6: entries_fragile surfaces in fixes"),
    ("health.py", "    if not alpha or max(alpha.values()) < 150:", "    if False:", f"{P}::test_scanned_pdf_has_no_text_layer", "text-layer check"),
    ("health.py", "    if len(oks) < 3:\n        checks.append(Check(\"extractors\"", "    if False:\n        checks.append(Check(\"extractors\"", f"{P}::test_fewer_than_three_extractors_cannot_be_compared", "extractor-count check"),
    ("health.py", "lambda p: p.email, \"Put", "lambda p: True, \"Put", f"{P}::test_missing_email_fails_under_every_view", "email check"),
    ("health.py", "len(p.skills) >= 3", "len(p.skills) >= 0", f"{P}::test_two_item_skills_section_is_not_a_skills_section", "skills check"),
    ("health.py", "        if missing and not any(c.id in (\"tounicode\",)", "        if False and not any(c.id in (\"tounicode\",)", f"{P}::test_lost_words_in_one_extractor_warn", "chars_lost check"),
    ("jd_reqs.py", "[PROMPT_VERSION, text, f\"sample={i}\"]", "[PROMPT_VERSION, text]", f"{S}::test_consensus_keeps_terms_in_at_least_half_of_the_samples", "B1: a distinct cache key per sample"),
    ("jd_reqs.py", "    need = math.ceil(n / 2)", "    need = 1", f"{S}::test_consensus_keeps_terms_in_at_least_half_of_the_samples", "B1: recurrence threshold"),
    ("jd_reqs.py", "            if not refresh and path.exists():", "            if path.exists():", f"{S}::test_consensus_list_is_persisted_per_jd_and_refresh_regenerates", "B1: --refresh regenerates the stored list"),
    ("jd_reqs.py", "            if not refresh and path.exists():", "            if False:", f"{S}::test_consensus_list_is_persisted_per_jd_and_refresh_regenerates", "B1: the consensus list is persisted"),
    ("jd_reqs.py", "        imp = min((i for i, c in imp_counts.items() if c == top), key=lambda i: rank[i])", "        imp = \"required\"", f"{S}::test_consensus_unions_aliases_and_votes_importance_and_softness_by_majority", "B1: importance by majority"),
    ("cli.py", "\"required_median\": round(statistics.median(vals))", "\"required_median\": max(vals)", f"{S}::test_cli_reports_the_median_and_the_range_of_required_coverage", "B1: median"),
    ("match.py", "        if re.search(r\"[a-z][A-Z]|\\d|[.+#]\", f) or rq.kind in (\"tool\", \"certification\") or f.lower() in KNOWN_PROPER:", "        if True:", f"{M}::test_title_cased_generic_terms_match_lowercase_master_prose", "R2: generic Title-Cased terms are not proper nouns"),
    ("match.py", " or f.lower() in KNOWN_PROPER:", ":", f"{M}::test_a_product_that_is_also_a_common_word_still_needs_its_own_case_whatever_the_kind", "R2: known product names stay case-sensitive"),
    ("match.py", "        elif rej and (rej_exact or not r.master_hit):", "        elif rej:", f"{M}::test_a_looser_guard_hit_does_not_discard_real_support_but_the_exact_claim_is_rejected", "R2: a loose guard hit keeps real support"),
    ("match.py", "                exact = bool(re.search(r\"\\d\", p)) or any(_norm(f) == _norm(p) for f in forms)", "                exact = False", f"{M}::test_a_looser_guard_hit_does_not_discard_real_support_but_the_exact_claim_is_rejected", "R2: the exact guarded claim is rejected"),
    ("match.py", "        text = \" \".join(P.lines[e.first_line + 1: e.last_line + 1])", "        text = \" \".join([e.header, e.title, *P.lines[e.first_line: e.last_line + 1]])", f"{G}::test_years_come_from_bullets_not_from_a_header_that_names_the_area", "R2: years from bullets only"),
    ("match.py", "re.split(r\"\\s*,\\s*|\\s+or\\s+\", core)", "[core]", f"{G}::test_a_compound_area_is_a_list_of_alternatives", "R2: compound area split"),
    ("fields.py", "|,\\s*[A-Z]{2}$\")", "|(?i:,\\s*[A-Z]{2}$)\")", f"{P}::test_location_fragment_state_code_is_case_sensitive", "R2: state code case-sensitive"),
    ("jd_reqs.py", "f\"{sha}-{PROMPT_VERSION}-{CONSENSUS_VERSION}-n{n}.json\"", "f\"{sha}-{PROMPT_VERSION}-n{n}.json\"", f"{S}::test_consensus_list_is_persisted_per_jd_and_refresh_regenerates", "R2: consensus version in the store key"),
    ("cli.py", "        jd.warnings += master.warnings", "        pass", f"{W}::test_a_master_without_a_sibling_guard_warns_in_the_report", "R2: master warnings reach the report"),
    ("cli.py", "match.knockouts(jd, parsed, resume_text, master, groups)", "match.knockouts(jd, parsed, resume_text, master)", f"{W}::test_synonym_groups_reach_the_years_gate", "R2: groups reach the years gate"),
    ("cli.py", "score.build_fixes(H, results, kos)", "score.build_fixes(H, results, [])", f"{W}::test_knockouts_reach_the_fix_list", "R2: knock-outs reach the fix list"),
    # ---- P3 grader (phase 1)
    ("grade.py", "    return math.ceil(VOTE_SHARE * n)", "    return math.ceil(0.5 * n)", f"{P3}::test_vote_thresholds", "P3: a status needs ceil(0.8 N) of the requested runs"),
    ("grade.py", "    return top if cnt >= need(n) and top not in NOT_A_VOTE else \"undecided\"", "    return top if cnt >= need(len(statuses)) and top not in NOT_A_VOTE else \"undecided\"", f"{P3}::test_vote_thresholds", "P3: failed runs do not shrink the threshold"),
    ("grade.py", "    return top if cnt >= need(n) and top not in NOT_A_VOTE else \"undecided\"", "    return top if cnt >= need(n) else \"undecided\"", f"{P3}::test_ungrounded_runs_are_not_not_met_and_their_quotes_are_never_shown", "P3: an ungrounded majority is never a winning status"),
    ("grade.py", "    rx = [re.compile(r\"(?<!\\w)\" + re.escape(f) + r\"(?!\\w)\") for f in frags]", "    rx = [re.compile(re.escape(f)) for f in frags]", f"{P3}::test_quote_must_sit_inside_one_resume_segment_word_bounded", "P3: quotes are word-bounded"),
    ("grade.py", "< MIN_QUOTE_WORDS:", "< 1:", f"{P3}::test_quote_must_sit_inside_one_resume_segment_word_bounded", "P3: a quote needs >= 3 words"),
    ("grade.py", "    hits = [pl for t, pl in resume.segs if all(r.search(t) for r in rx)]", "    hits = [pl for t, pl in resume.segs if any(r.search(t) for r in rx)]", f"{P3}::test_quote_must_sit_inside_one_resume_segment_word_bounded", "P3: ellipsis fragments must share ONE segment"),
    ("grade.py", "    hits = [pl for t, pl in resume.segs if all(r.search(t) for r in rx)]", "    hits = [pl for t, pl in [(\" \".join(t for t, _ in resume.segs), \"other\")] if all(r.search(t) for r in rx)]", f"{P3}::test_quote_must_sit_inside_one_resume_segment_word_bounded", "P3: a quote cannot span two bullets"),
    ("grade.py", "out[c.id] = {\"status\": \"ungrounded\", \"claimed\": raw, \"quote\": \"\", \"grounded\": False,", "out[c.id] = {\"status\": \"not_met\", \"claimed\": raw, \"quote\": \"\", \"grounded\": False,", f"{P3}::test_a_quote_that_is_not_in_the_resume_is_ungrounded_not_not_met", "P3: a fabricated quote is ungrounded, not not_met"),
    ("grade.py", "out[c.id] = {\"status\": \"ungrounded\", \"claimed\": raw, \"quote\": \"\", \"grounded\": False,", "out[c.id] = {\"status\": \"ungrounded\", \"claimed\": raw, \"quote\": quote, \"grounded\": False,", f"{P3}::test_a_quote_that_is_not_in_the_resume_is_ungrounded_not_not_met", "P3: a rejected quote is never kept for display"),
    ("grade.py", "        capped = raw == \"met\" and skills_only and bool(EXPERIENCE.search(c.text))", "        capped = False", f"{P3}::test_a_skills_only_quote_caps_an_experience_criterion_at_partial", "P3: skills-only evidence caps an experience criterion at partial"),
    ("grade.py", "            out[c.id] = {\"status\": \"no_answer\"", "            out[c.id] = {\"status\": \"not_met\"", f"{P3}::test_missing_answer_is_no_answer_not_a_crash", "P3: a missing answer is not a not_met"),
    ("grade.py", "    elif any(r[\"status\"] == \"not_met\" for r in basic):", "    elif False:", f"{P3}::test_band_rule", "P3: any basic not_met -> C/D"),
    ("grade.py", "    elif met == len(basic):", "    elif True:", f"{P3}::test_band_rule", "P3: A/B needs every basic criterion met"),
    ("grade.py", "    basic = [r for r in rows if r[\"screenable\"] and r[\"level\"] == \"basic\"]", "    basic = [r for r in rows if r[\"screenable\"]]", f"{P3}::test_band_rule", "P3: preferred criteria never gate the band"),
    ("grade.py", "    screenable = [c for c in crit if c.screenable]\n\n    def one", "    screenable = list(crit)\n\n    def one", f"{P3}::test_only_screenable_criteria_reach_the_grader_and_the_band", "P3: non-screenable criteria are not graded"),
    ("grade.py", "    return [f\"sample={i}\"] + ([f\"salt={salt}\"] if salt else [])", "    return [f\"salt={salt}\"] if salt else []", f"{P3}::test_each_grader_sample_has_its_own_cache_key", "P3: a distinct cache key per grader sample"),
    ("grade.py", "        random.Random(i).shuffle(order)", "        pass", f"{P3}::test_criteria_are_shuffled_per_sample_and_the_cache_key_names_the_model", "P3: criteria are shuffled per sample"),
    ("grade.py", "    return re.sub(r\"\\{(criteria|resume)\\}\", lambda m: vals[m.group(1)], PROMPT)", "    return PROMPT.replace(\"{criteria}\", listing).replace(\"{resume}\", resume_text)", f"{P3}::test_prompt_substitution_is_single_pass", "P3: prompt substitution is single pass"),
    ("grade.py", "    return ref if best >= 0.5 else \"\"", "    return ref", f"{P3}::test_master_id_comes_from_the_bullet_the_quoted_line_is_cut_from", "P3: no master id below the overlap floor"),
    ("grade.py", "master_id(quote, master) if (master is not None and quote) else None", "None", f"{P3}::test_tally_attributes_master_only_when_given", "P3: master id attribution"),
    ("grade.py", "    tag = tag or uuid.uuid4().hex[:8]", "    tag = tag or \"stab\"", f"{P3}::test_each_stability_invocation_uses_its_own_salt", "P3: a new stability salt per invocation"),
    ("grade.py", "        samples, _ = run_samples(crit, resume, n, True, runner, salt=f\"{tag}-{j}\")", "        samples, _ = run_samples(crit, resume, n, False, runner, salt=\"\")", f"{P3}::test_stability_runs_are_fresh_each_and_leave_the_normal_cache_alone", "P3: stability runs are fresh"),
    ("grade.py", "\"sample_disagreement\": round(1 - dtop / len(d), 3) if d else None", "\"sample_disagreement\": 0.0", f"{P3}::test_stability_flip_rate_is_the_share_of_runs_off_the_modal_status", "P3: stability counts raw-draw disagreement"),
    ("criteria.py", "        if not ok and strict:", "        if False:", f"{P3}::test_generate_rejects_coined_and_keeps_verbatim", "P3: a coined criterion is rejected"),
    ("criteria.py", "    cands = [u for u in units if rx.search(u.text)]", "    cands = [u for u in units if rx.search(\" \".join(x.text for x in units))]", f"{P3}::test_a_criterion_must_be_a_piece_of_one_jd_bullet", "P3: a criterion sits inside ONE JD bullet"),
    ("criteria.py", "    rx = re.compile(r\"(?<!\\w)\" + re.escape(core) + r\"(?!\\w)\")", "    rx = re.compile(re.escape(core))", f"{P3}::test_verbatim_check_rules", "P3: the verbatim check is word-bounded"),
    ("criteria.py", "    if len(_words(core)) < 3 and not any(", "    if False and not any(", f"{P3}::test_verbatim_check_rules", "P3: a criterion is a whole bullet or >= 3 words"),
    ("criteria.py", "    if any(u.kind for u in units):\n        cands", "    if False:\n        cands", f"{P3}::test_verbatim_check_rules", "P3: a criterion must come from a qualification section"),
    ("criteria.py", "    ok = [u for u in cands if not ((set(_words(u.text)) & NEG) and not (cw & NEG))]", "    ok = cands", f"{P3}::test_verbatim_check_rules", "P3: a dropped negation is rejected"),
    ("criteria.py", "    if level and not any(u.kind in (\"\", level) for u in ok):", "    if False:", f"{P3}::test_level_is_cross_checked_against_the_jd_heading", "P3: level is cross-checked against the JD heading"),
    ("criteria.py", "    if path.exists() and not recriteria:", "    if False:", f"{P3}::test_pinned_file_is_written_next_to_the_jd_and_respected", "P3: a pinned criteria file is respected"),
    ("criteria.py", "    if path.exists() and not recriteria:", "    if path.exists():", f"{P3}::test_recriteria_regenerates_and_overwrites_the_edits", "P3: --recriteria regenerates"),
    ("criteria.py", "        shutil.copy2(path, bak)", "        pass", f"{P3}::test_recriteria_keeps_the_previous_file_as_bak", "P3: --recriteria keeps a .bak"),
    ("cli.py", "grade_mod.grade(crit, resume, args.grade_samples, master, args.refresh)", "grade_mod.grade(crit, resume, 5, master, args.refresh)", f"{P3}::test_grade_samples_and_recriteria_reach_the_steps", "P3: --grade-samples reaches the grader"),
    ("cli.py", "grade_mod.grade(crit, resume, args.grade_samples, master, args.refresh)", "grade_mod.grade(crit, resume, args.grade_samples, master, False)", f"{P3}::test_grade_samples_and_recriteria_reach_the_steps", "P3: --refresh reaches the grader"),
    ("cli.py", "grade_mod.grade(crit, resume, args.grade_samples, master, args.refresh)", "grade_mod.grade(crit, resume, args.grade_samples, None, args.refresh)", f"{P3}::test_master_reaches_the_grader_through_the_cli", "P3: --master reaches the grader"),
    ("cli.py", "crit_mod.get(jd_text, criteria_dir(args), args.recriteria)", "crit_mod.get(jd_text, criteria_dir(args), False)", f"{P3}::test_grade_samples_and_recriteria_reach_the_steps", "P3: --recriteria reaches the criteria step"),
    ("cli.py", "    return args.jd.resolve().parent if args.jd else llm.CACHE / \"criteria\"", "    return args.jd.resolve().parent if args.jd else out_dir(args)", f"{P3}::test_a_fetched_jd_is_pinned_by_its_sha_in_the_cache_not_in_the_output_dir", "P3: a fetched JD is pinned by sha, not per output dir"),
    ("cli.py", "        crit_mod.load_pinned(jd_text, criteria_dir(args))", "        None", f"{P3}::test_a_malformed_pinned_file_exits_2_before_any_llm_call", "P3: a malformed pin stops the run before any LLM call"),
    ("cli.py", "    if not llm.self_check():\n        return {\"error\": \"sandbox self-check failed (Read deny did not hold); P3 not run\"}", "    if False:\n        return {}", f"{P3}::test_no_llm_skips_p3_and_a_failed_selfcheck_blocks_it", "P3: the sandbox self-check gates the grader"),
    ("cli.py", "grade_mod.stability(crit, resume, args.stability, args.grade_samples)", "grade_mod.stability(crit, resume, 1, args.grade_samples)", f"{P3}::test_stability_flag_prints_and_writes_flip_rates", "P3: --stability K reaches the stability run"),
    ("report.py", "    if d.get(\"p3\") is not None:", "    if False:", f"{P3}::test_report_has_the_p3_block_above_the_keyword_sections", "P3: the report carries the P3 block at the top"),
    ("report.py", "withm = bool(p3.get(\"master\"))", "withm = False", f"{P3}::test_master_column_flags_a_line_with_no_master_bullet", "P3: master id column shown with --master"),
    ("report.py", "        flag = f\" ({r['note']})\" if r.get(\"note\") else \"\"", "        flag = \"\"", f"{P3}::test_the_report_names_ungrounded_claims_and_never_prints_the_rejected_quote", "P3: the report names an ungrounded majority"),
    ("jd_reqs.py", 'ABOUT_HEAD = re.compile(r"^about (?:us|the company|the team)\\b", re.I)', 'ABOUT_HEAD = re.compile(r"about (?:us|the company|the team)", re.I)', f"{J}::test_only_an_about_us_heading_line_stops_the_requirements", "only an About-us heading line stops the requirements"),
    ("cli.py", "    args.master = args.master or cfg.master\n", "    args.master = args.master\n", "tests/test_config.py::test_cli_takes_master_and_out_dir_from_the_file", "offersmith.toml master reaches the CLI"),
    ("cli.py", "        args.out = cfg.out_dir / args.resume.stem", "        pass", "tests/test_config.py::test_cli_takes_master_and_out_dir_from_the_file", "offersmith.toml out_dir reaches the CLI"),
    ("config.py", "    for k, var in ENV.items():", "    for k, var in ():", "tests/test_config.py::test_environment_beats_the_file", "environment overrides the file"),
    # ---- optional OpenResume layer (these rows need the layer installed: tools/openresume/install.sh)
    ("openresume.py", "    glued = glued_words(v, ref_text)", "    glued = []", f"{OR}::test_per_word_text_matrices_are_reported_as_glued_words_and_item_granularity", "OR (a): glued words"),
    ("openresume.py", "    gran_bad = total >= GRANULARITY_MIN_ITEMS and share >= GRANULARITY_SHARE", "    gran_bad = False", f"{OR}::test_per_word_text_matrices_are_reported_as_glued_words_and_item_granularity", "OR (b): one pdf.js item per word"),
    ("openresume.py", "    if bf:\n", "    if False:\n", f"{OR}::test_a_dash_bullet_is_named_with_the_parsers_own_glyph_list", "OR (c): unknown bullet glyph"),
    ("openresume.py", "    probs, n_cmp = entry_problems(v, parsed, skip)", "    probs, n_cmp = [], len(parsed.entries)", f"{OR}::test_a_vertical_gap_inside_one_role_is_reported_as_a_split_entry", "OR (d): split / empty-field entries"),
    ("openresume.py", "    ep = education_problems(v, parsed)", "    ep = []", f"{OR}::test_degree_and_school_on_one_bold_line_are_reported_empty", "OR (e): school / degree empty"),
    ("openresume.py", "    straddles = [s for s in page_straddles(v) if _is_header_like(s[\"after\"], parsed)]", "    straddles = []", f"{OR}::test_a_role_header_glued_onto_a_page_break_is_labelled_an_openresume_limitation_and_not_a_missing_role", "OR (f): header glued at a page break"),
    ("openresume.py", "    skip = [s[\"after\"] for s in straddles]", "    skip = []", f"{OR}::test_a_role_header_glued_onto_a_page_break_is_labelled_an_openresume_limitation_and_not_a_missing_role", "OR (f): a glued role is not also reported missing in (d)"),
    ("openresume.py", "    mail, other = contact_problems(v, parsed)", "    mail, other = [], []", f"{OR}::test_an_email_that_openresume_reads_wrongly_is_a_warn_never_a_fail", "OR (g): contact fields"),
    ("openresume.py", "\"NODE_OPTIONS\": NODE_FLAG}", "\"NODE_OPTIONS\": \"\"}", f"{OR}::test_the_runner_is_started_with_code_generation_from_strings_disabled_and_refuses_to_run_without_it", "OR: the runner runs with code generation from strings disabled (pdfjs CVE-2024-4367)"),
    ("openresume.py", "    finally:\n        _kill_group(p)\n        p.wait()", "    finally:\n        p.kill()\n        p.wait()", f"{OR}::test_a_timeout_kills_the_whole_process_group_not_just_the_launcher", "OR: a timeout kills and reaps the whole process group"),
    ("openresume.py", "            if len(bufs[key]) > cap:", "            if False:", f"{OR}::test_runner_output_is_capped_on_both_streams", "OR: runner output is capped"),
    ("openresume.py", "    env = {k: os.environ[k] for k in (\"PATH\", \"HOME\", \"TMPDIR\", \"LANG\", \"LC_ALL\") if k in os.environ}", "    env = dict(os.environ)", f"{OR}::test_the_runner_gets_a_minimal_environment_with_only_the_node_flag", "OR: the runner gets a minimal environment"),
    ("openresume.py", "    _validate(d)\n    return d", "    return d", f"{OR}::test_a_payload_missing_a_nested_field_is_one_warn", "OR: the payload is validated"),
    ("openresume.py", "    lines = [l for l in out.split(b\"\\n\") if l.strip()]", "    lines = [l.encode() for l in out.decode(\"utf-8\", \"replace\").splitlines() if l.strip()]", f"{OR}::test_json_with_a_unicode_line_separator_inside_a_string_is_framed_on_the_newline_only", "OR: output is framed on the real newline"),
    ("openresume.py", "    if (_git(h, \"rev-parse\", \"HEAD\") or \"\").strip() != PINNED_SHA:", "    if False:", f"{OR}::test_the_install_folder_must_be_the_pinned_untouched_checkout_owned_by_us", "OR: the checkout must be the pinned commit"),
    ("openresume.py", "    if _git(h, \"status\", \"--porcelain\", \"--untracked-files=all\") != \"\":", "    if False:", f"{OR}::test_the_install_folder_must_be_the_pinned_untouched_checkout_owned_by_us", "OR: the checkout must have no local change"),
    ("openresume.py", "    if st.st_uid != os.getuid() or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):", "    if False:", f"{OR}::test_the_install_folder_must_be_the_pinned_untouched_checkout_owned_by_us", "OR: the install folder is ours alone"),
    ("openresume.py", "    return (Path(v).expanduser() if v else cache / \"openresume\").absolute()", "    return (Path(v).expanduser() if v else cache / \"openresume\")", f"{OR}::test_install_sh_and_the_check_resolve_the_folder_identically", "OR: the folder is an absolute path"),
    ("openresume.py", "        single += sum(1 for t in items if not re.search(r\"\\s\", t))", "        single += sum(1 for t in items if len(t.split()) == 1)", f"{OR}::test_an_item_that_carries_its_own_space_is_not_a_word_on_its_own", "OR (b): an item with its own space is not a word"),
    ("openresume.py", "GRANULARITY_MIN_ITEMS = 24", "GRANULARITY_MIN_ITEMS = 12", f"{OR}::test_two_short_lines_of_single_word_items_are_not_enough_to_report", "OR (b): enough items before reporting"),
    ("openresume.py", "    for line in text.replace(\"\\f\", \"\\n\").splitlines():", "    for line in [text.replace(\"\\f\", \" \").replace(\"\\n\", \" \")]:", f"{OR}::test_glue_is_matched_within_one_line_and_from_six_letters", "OR (a): glue is matched within one line"),
    ("openresume.py", "GLUE_MIN_LETTERS = 6", "GLUE_MIN_LETTERS = 8", f"{OR}::test_glue_is_matched_within_one_line_and_from_six_letters", "OR (a): glue from six letters"),
    ("openresume.py", "sum(unknown.values()) >= nb / 2 and descs != nb:", "sum(unknown.values()) >= nb / 2:", f"{OR}::test_dash_bullets_that_came_out_as_one_description_each_are_not_reported", "OR (c): no WARN when every bullet came out as a description"),
    ("openresume.py", "        k = (named or same or [None])[0]", "        k = (same or [None])[0]", f"{OR}::test_concurrent_roles_with_the_same_years_are_paired_by_their_own_text", "OR (d): concurrent roles are paired by their text"),
    ("openresume.py", "    except Exception as e:      # an optional layer", "    except KeyError as e:      # an optional layer", f"{OR}::test_an_unexpected_failure_while_comparing_is_one_warn", "OR: a comparison bug is one WARN"),
    ("openresume.py", "    if not wrapper_took_effect(d, v):", "    if False:", f"{OR}::test_a_runner_whose_pdfjs_wrapper_did_not_take_effect_reports_nothing_as_verified", "OR: no PASS when the pdf.js wrapper did not take effect"),
    ("openresume.py", "    why = missing_reason(h)", "    why = \"\"", f"{OR}::test_a_missing_install_is_one_warn_that_names_the_install_command", "OR: a missing install is a WARN with the install command"),
    ("health.py", "    or_checks, or_raw = orl.checks(pdf, ref_text, parsed.get(match_view)) if ref_text else ([], None)", "    or_checks, or_raw = [], None", f"{OR}::test_the_clean_base_resume_passes_every_openresume_check", "OR: health.run calls the layer"),
    ("score.py", "\"or_layer\", \"or_page_boundary\")", "\"or_layer\")", f"{OR}::test_the_limitation_and_the_skipped_layer_are_not_listed_as_fixes_to_the_resume", "OR: the page-break limitation is not a resume fix"),
    ("report.py", "    if orc:\n", "    if False:\n", f"{OR}::test_the_report_and_report_json_carry_the_openresume_findings", "OR: report.md section"),
    ("cli.py", "\"openresume\": H.openresume and", "\"openresume\": None and", f"{OR}::test_the_report_and_report_json_carry_the_openresume_findings", "OR: report.json carries the layer output"),
    # ---- entry detection from page layout: a wrapped bullet row / a page footer is never a job header
    ("fields.py", '        if roles[i] == "footer":      # a page number', '        if False and roles[i] == "footer":      # a page number', f"{T}::test_a_page_footer_between_two_bullets_is_not_a_job", "a footer row between bullets is skipped, not an undated job"),
    ("fields.py", '        if roles[i] == "cont":        # the layout puts', '        if False and roles[i] == "cont":        # the layout puts', f"{T}::test_every_wrapped_row_shape_stays_inside_its_bullet_under_every_extractor", "a row the layout puts at the bullet text indent is not a header"),
    ("fields.py", '            while j >= ex.start and roles[j] == "footer":', '            while False:', f"{T}::test_a_date_only_row_after_a_footer_pairs_with_the_title_row_before_the_footer", "date-only lookback steps over a footer"),
    ("fields.py", ' and roles[j] != "cont"\n', '\n', f"{T}::test_a_date_only_row_after_a_wrapped_bullet_row_does_not_take_it_for_a_title", "date-only lookback never takes a wrapped row for a title"),
    ("fields.py", '(L[j][:1].isupper() or roles[j] in ("header", "plain"))', 'L[j][:1].isupper()', f"{T}::test_a_lowercase_brand_title_row_the_layout_places_pairs_with_its_date_row", "a lowercase-brand title row at the margin pairs with its date row"),
    ("fields.py", 'P.roles[sk.start: sk.end]) if r != "footer")', 'P.roles[sk.start: sk.end]))', f"{T}::test_a_page_footer_row_is_not_part_of_the_skills_list", "a footer row is not a skill"),
    ("fields.py", '        if i < 2 or P.roles[i] == "footer":', '        if i < 2:', f"{T}::test_a_running_footer_that_looks_like_a_heading_opens_no_section", "a footer row is not a section heading"),
    ("fields.py", '                        layout=roles[first] or "")', '                        layout="")', f"{T}::test_every_wrapped_row_shape_stays_inside_its_bullet_under_every_extractor", "an entry keeps the layout role of its header row"),
    ("layout.py", "    if not g.lines or g.columns or g.tables:", "    if not g.lines:", f"{T}::test_a_resume_with_columns_or_a_table_has_no_layout_to_project_onto", "no layout for columns or tables"),
    ("layout.py", "        if (id(r) in edge and repeats) or (id(r) in in_band and _stands_clear(r, by_page[r.page])):", "        if id(r) in in_band and _stands_clear(r, by_page[r.page]):", f"{T}::test_a_page_footer_between_two_bullets_is_not_a_job", "a footer above the band is found by its repeat"),
    ("layout.py", "        if (id(r) in edge and repeats) or (id(r) in in_band and _stands_clear(r, by_page[r.page])):", "        if id(r) in edge and repeats:", f"{T}::test_a_page_number_in_the_header_footer_band_is_a_footer_with_no_second_page", "a page number in the band needs no repeat"),
    ("layout.py", "        if (id(r) in edge and repeats) or (id(r) in in_band and _stands_clear(r, by_page[r.page])):", "        if id(r) in edge or (id(r) in in_band and _stands_clear(r, by_page[r.page])):", f"{T}::test_a_page_number_shape_ending_a_page_and_not_repeated_is_the_wrapped_text_it_looks_like", "a number at the foot of a page that does not repeat is not a footer"),
    ("layout.py", '    return re.sub(r"\\d+", "", r.key)', "    return r.key", f"{T}::test_a_page_footer_between_two_bullets_is_not_a_job", "a running footer is the same text on every page, number aside"),
    ("geometry.py", "    if len(ws) >= 2 and ws[0][4] in BULLETS:", "    if False:", f"{T}::test_roles_follow_the_indent_the_bullet_text_starts_at", "bullet text indent read from the first word after the marker"),
    ("health.py", "fd.parse(e.text, g.style_headings, page_layout)", "fd.parse(e.text, g.style_headings)", f"{T}::test_every_wrapped_row_shape_stays_inside_its_bullet_under_every_extractor", "the layout reaches the parser of every extractor"),
    ("layout.py", '        if (in_bullet and not at_margin and text_x is not None and abs(r.x0 - text_x) <= INDENT_TOL and not (r.all_bold or r.parts > 1)\n                and _at_leading(prev, r, leading)):', '        if (in_bullet and text_x is not None and abs(r.x0 - text_x) <= INDENT_TOL and not (r.all_bold or r.parts > 1)\n                and _at_leading(prev, r, leading)):', f"{T}::test_a_layout_with_no_bullet_indent_places_no_wrapped_row_and_the_parser_falls_back", "text starting at the margin is not a wrapped row"),
    ("layout.py", '        if (in_bullet and not at_margin and text_x is not None and abs(r.x0 - text_x) <= INDENT_TOL and not (r.all_bold or r.parts > 1)\n                and _at_leading(prev, r, leading)):', '        if (in_bullet and not at_margin and text_x is not None and not (r.all_bold or r.parts > 1)\n                and _at_leading(prev, r, leading)):', f"{T}::test_a_row_indented_somewhere_other_than_the_bullet_text_is_not_a_wrapped_row", "a wrapped row sits at the bullet text indent"),
    ("layout.py", 'not (r.all_bold or r.parts > 1)', 'not r.parts > 1', f"{T}::test_a_bold_or_right_aligned_row_at_the_bullet_text_indent_is_not_taken_for_a_wrapped_row", "a wholly bold or two-part row at the bullet text indent is a header, not wrapped text"),
    ("layout.py", 'not (r.all_bold or r.parts > 1)', 'not (r.bold or r.parts > 1)', f"{T}::test_a_wrapped_row_that_opens_with_a_bold_word_is_still_wrapped_text", "a bold first word does not make a wrapped row a header"),
    ("layout.py", '\n                and _at_leading(prev, r, leading)):', '):', f"{T}::test_a_plain_header_at_the_bullet_text_x_after_paragraph_spacing_is_a_job", "a wrapped row sits one line pitch below the row above, not a paragraph gap"),
    ("layout.py", '                if len(rk) >= 8 and k.startswith(rk):', '                if False:', f"{T}::test_an_extractor_that_joins_a_wrapped_bullet_into_one_row_is_still_located", "a paragraph an extractor joined is located by its first row"),
    ("layout.py", '                        return j, j, PART', '                        return j, j, EXACT', f"{T}::test_a_row_that_is_only_the_tail_of_a_visual_row_gets_no_role", "a tail of a visual row is no role"),
    ("layout.py", '            cursor = j if kind == PREFIX else last + 1', '            cursor = last', f"{T}::test_two_extractor_rows_with_one_text_take_two_visual_rows_in_order", "a visual row an extractor row used up is not matched again"),
    ("layout.py", '            for j in scan:\n                if self.keys[j] == k:\n                    return j, j, EXACT\n            if len(k) >= 4:\n                for j in scan:\n                    if self.keys[j].startswith(k):\n                        return j, j, PREFIX\n', '', f"{T}::test_a_row_equal_to_a_visual_row_beats_a_join_that_starts_on_an_earlier_one", "an exact or head match of a row beats a join that starts on an earlier row"),
    ("layout.py", '        if id(r) in in_band and _stem(r):', '        if id(r) in in_band:', f"{T}::test_a_date_row_in_the_footer_band_is_not_a_page_number", "digits alone are no running footer"),
    ("layout.py", ' and _stands_clear(r, by_page[r.page])):\n            r.role', '):\n            r.role', f"{T}::test_a_skills_row_that_is_only_a_number_in_the_footer_band_is_content", "a number in the band is a footer only when it stands clear of the body"),
]


def main() -> int:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    survived = []
    from ats_check import openresume
    or_off = bool(openresume.home() is None or openresume.missing_reason(openresume.home()))
    todo = [m for m in MUTANTS if not (or_off and m[3].startswith(OR))]
    if len(todo) != len(MUTANTS):
        print(f"SKIPPED {len(MUTANTS) - len(todo)} OpenResume rows: layer not installed (sh tools/openresume/install.sh, or set ATS_CHECK_OPENRESUME)")
    for fname, anchor, repl, test, what in todo:
        path = PKG / fname
        src = path.read_text()
        if src.count(anchor) != 1:
            print(f"BROKEN   {fname}: anchor not unique/found: {anchor!r}")
            survived.append((fname, what, "anchor"))
            continue
        try:
            path.write_text(src.replace(anchor, repl))
            r = subprocess.run(["uv", "run", "--quiet", "python", "-B", "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", test],
                               cwd=ROOT, env=env, capture_output=True, text=True)
        finally:
            path.write_text(src)
        killed = r.returncode != 0 and "FAILED" in r.stdout
        print(f"{'KILLED  ' if killed else 'SURVIVED'} {fname}: {what}")
        if not killed:
            survived.append((fname, what, r.stdout[-300:]))
    # baseline must be green again
    base = subprocess.run(["uv", "run", "--quiet", "python", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=ROOT, env=env, capture_output=True, text=True)
    print("baseline after restore:", "green" if base.returncode == 0 else "RED")
    print(f"{len(todo) - len(survived)}/{len(todo)} killed")
    return 0 if not survived and base.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
