"""Optional layer: OpenResume's PDF parser (github.com/xitanggg/open-resume, AGPL-3.0) run unmodified, then compared with the
consensus of our own extractors. It is a second, independent reader of the same file: it works on pdf.js text items, so it sees
defects the text-only extractors do not (glued words, bullets it does not know, a role split in two, a header glued onto a page break).

The parser is fetched by `tools/openresume/install.sh` (never vendored here) and run by `tools/openresume/run.ts`. Absent Node or the
install = the layer is skipped with a WARN naming the install command, never a FAIL, and none of its findings is a FAIL either (see docs/ats-check.md). `ATS_CHECK_OPENRESUME=off` disables it silently.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import threading
import unicodedata
from collections import Counter
from pathlib import Path

from . import fields as fd
from .health import PASS, WARN, Check

ENV = "ATS_CHECK_OPENRESUME"
OFF = ("off", "0", "false", "no")
PINNED_SHA = "4f8255a2c763479837f69f1dccf2a3338730cd79"       # the same commit as SHA in tools/openresume/install.sh (a test compares them)
TIMEOUT = 120
MAX_STDOUT = 32 * 1024 * 1024
MAX_STDERR = 64 * 1024
# a PDF whose body lines are mostly one pdf.js item per word (font expansion, per-word text matrices) is read by parsers that join items by distance as glued text
GRANULARITY_SHARE = 0.5
GRANULARITY_MIN_ITEMS = 24
BODY_LINE_WORDS = 6
GLUE_MIN_LETTERS = 6
GLUE_MAX_WORDS = 6
INSTALL_SH = Path(__file__).resolve().parents[1] / "tools" / "openresume" / "install.sh"


class RunnerError(Exception):
    pass


def home() -> Path | None:
    """The install folder as an absolute path, or None when the layer is switched off. `off` is never a path. install.sh --print-dir
    resolves the same way (a test compares them)."""
    v = (os.environ.get(ENV) or "").strip()
    if v.lower() in OFF:
        return None
    cache = Path(os.environ.get("ATS_CHECK_CACHE") or Path.home() / ".cache" / "ats-check")
    return (Path(v).expanduser() if v else cache / "openresume").absolute()


def install_command() -> str:
    sh = str(INSTALL_SH) if INSTALL_SH.exists() else "tools/openresume/install.sh (in the offersmith repository)"
    return f"sh {sh}"


def _git(h: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(h / "open-resume"), *args], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def missing_reason(h: Path) -> str:
    """"" when the layer can run, else why not. The install folder is code we execute, so it must be ours alone and the upstream checkout must be
    the pinned commit with no local change."""
    if not shutil.which("node"):
        return "node is not on PATH"
    if not (h / "node_modules" / ".bin" / "tsx").exists() or not (h / "run.ts").exists() or not (h / "open-resume" / "tsconfig.json").exists():
        return f"not installed in {h}"
    try:
        st = h.stat()
    except OSError:
        return f"not installed in {h}"
    if st.st_uid != os.getuid() or st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return f"{h} is writable by someone else (or not owned by you); it holds code that is run"
    if (_git(h, "rev-parse", "HEAD") or "").strip() != PINNED_SHA:
        return f"the OpenResume checkout in {h} is not the pinned commit {PINNED_SHA[:12]}"
    if _git(h, "status", "--porcelain", "--untracked-files=all") != "":
        return f"the OpenResume checkout in {h} has local changes"
    return ""


def version(h: Path) -> str:
    return PINNED_SHA[:12]


# pdfjs-dist 3.7.107 (pinned to OpenResume's) runs JavaScript from a crafted PDF font through `new Function` (GHSA-wgrm-67xf-hhpq):
# with code generation from strings disabled pdf.js cannot take that path, and run.ts refuses to start without the flag. run.ts also passes
# isEvalSupported: false to pdf.js (the advisory's own workaround), so the flag is the second layer, not the only one.
NODE_FLAG = "--disallow-code-generation-from-strings"


def _env() -> dict:
    """Only what node needs: no inherited NODE_OPTIONS (a --require/--import there runs before the runner's guard) and no credentials."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL") if k in os.environ}
    return {**env, "NODE_NO_WARNINGS": "1", "NODE_OPTIONS": NODE_FLAG}


def _kill_group(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)       # the launcher (tsx) and the node it started share the group
    except (ProcessLookupError, PermissionError):
        pass


def _run_bounded(cmd: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
    """Run `cmd` in its own process group with a deadline and byte caps on both streams. Whatever happens, the whole group is killed and reaped."""
    p = subprocess.Popen(cmd, cwd=cwd, env=_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    bufs = {"out": bytearray(), "err": bytearray()}
    over: list[str] = []

    def pump(stream, key: str, cap: int) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            bufs[key] += chunk
            if len(bufs[key]) > cap:
                over.append(key)
                _kill_group(p)
                return

    threads = [threading.Thread(target=pump, args=(p.stdout, "out", MAX_STDOUT), daemon=True),
               threading.Thread(target=pump, args=(p.stderr, "err", MAX_STDERR), daemon=True)]
    for t in threads:
        t.start()
    try:
        p.wait(timeout=TIMEOUT)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        _kill_group(p)
        p.wait()
        for t in threads:
            t.join(timeout=5)
        p.stdout.close()
        p.stderr.close()
    if timed_out:
        raise RunnerError(f"timed out after {TIMEOUT}s")
    if over:
        raise RunnerError(f"{'stdout' if over[0] == 'out' else 'stderr'} exceeds the {(MAX_STDOUT if over[0] == 'out' else MAX_STDERR) // 1024} KiB limit")
    return p.returncode, bytes(bufs["out"]), bytes(bufs["err"])


def _validate(d) -> None:
    """The payload shape the comparisons rely on; anything else is a RunnerError, not an exception later."""
    def need(ok: bool, what: str) -> None:
        if not ok:
            raise RunnerError(f"runner output has no valid {what}")
    need(isinstance(d, dict), "object")
    res = d.get("resume")
    need(isinstance(res, dict), "resume")
    prof = res.get("profile")
    need(isinstance(prof, dict) and all(isinstance(prof.get(k), str) for k in ("name", "email", "phone", "location")), "resume.profile")
    need(isinstance(res.get("workExperiences"), list) and all(
        isinstance(w, dict) and all(isinstance(w.get(k), str) for k in ("company", "jobTitle", "date"))
        and isinstance(w.get("descriptions"), list) and all(isinstance(x, str) for x in w["descriptions"]) for w in res["workExperiences"]), "resume.workExperiences")
    need(isinstance(res.get("educations"), list) and all(
        isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("school", "degree")) for e in res["educations"]), "resume.educations")
    need(isinstance(d.get("bulletPoints"), list) and all(isinstance(x, str) for x in d["bulletPoints"]), "bulletPoints")
    need(isinstance(d.get("pages"), list) and all(isinstance(x, dict) and isinstance(x.get("items"), int) for x in d["pages"]), "pages")
    need(isinstance(d.get("raw"), list) and all(isinstance(r, list) and len(r) >= 7 and isinstance(r[0], str) for r in d["raw"]), "raw items")
    need(isinstance(d.get("lines"), list) and all(
        isinstance(l, dict) and (l.get("start") is None or isinstance(l["start"], int)) and isinstance(l.get("items"), list)
        and all(isinstance(i, list) and len(i) >= 5 and isinstance(i[0], str) for i in l["items"]) for l in d["lines"]), "lines")


def wrapper_took_effect(d: dict, v: "View") -> bool:
    """run.ts swaps pdf.js for a wrapped copy (isEvalSupported: false, page bookkeeping). If that did not take effect nothing derived from it,
    page checks or the safety claim, may be reported as verified."""
    calls = d.get("getDocumentParams")
    return calls == [{"isEvalSupported": False}] and bool(d["pages"]) and v.pages_ok


def run_runner(pdf: Path, h: Path) -> dict:
    cmd = [str(h / "node_modules" / ".bin" / "tsx"), "--tsconfig", str(h / "open-resume" / "tsconfig.json"), str(h / "run.ts"), str(pdf.resolve())]
    try:
        code, out, err = _run_bounded(cmd, h)
    except OSError as e:
        raise RunnerError(str(e)[:200])
    if code != 0:
        tail = err.decode("utf-8", "replace").strip().splitlines()
        raise RunnerError((tail[-1] if tail else f"exit {code}")[:200])
    lines = [l for l in out.split(b"\n") if l.strip()]       # frame on the real newline: JSON may hold U+2028; pdf.js prints its warnings to stdout, the JSON is the last line
    try:
        d = json.loads(lines[-1].decode("utf-8"))
    except (ValueError, IndexError) as e:                    # UnicodeDecodeError is a ValueError
        raise RunnerError(f"runner output is not JSON: {e}"[:200])
    _validate(d)
    return d


# ---- helpers ---------------------------------------------------------------------------------------------------------
def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", _nfkc(s).lower())


def _words(s: str) -> list[str]:
    return re.findall(r"[^\W_]+", _nfkc(s).lower())


def _q(s: str, n: int = 70) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 3] + "..."


def _glyph(c: str) -> str:
    return f"U+{ord(c):04X} {unicodedata.name(c, '?')} '{c}'"


class View:
    """The runner's output with the line <-> raw item bookkeeping done once."""

    def __init__(self, d: dict):
        self.d = d
        self.raw = d["raw"]
        self.lines = d["lines"]
        self.resume = d["resume"]
        self.bullets = d["bulletPoints"]
        starts = [(i, l["start"]) for i, l in enumerate(self.lines) if l["start"] is not None]
        self.ranges: list[tuple[int, int, int]] = []        # (line index, first raw item, one past last raw item)
        for k, (li, s) in enumerate(starts):
            self.ranges.append((li, s, starts[k + 1][1] if k + 1 < len(starts) else len(self.raw)))
        self.bounds: list[int] = []                          # raw index where page 2, 3, ... start
        total = 0
        for p in d["pages"][:-1]:
            total += p["items"]
            self.bounds.append(total)
        self.pages_ok = sum(p["items"] for p in d["pages"]) == len(self.raw)

    def line_text(self, li: int) -> str:
        return " ".join(i[0] for i in self.lines[li]["items"])


# ---- (a) glued words -------------------------------------------------------------------------------------------------
def _consensus_concats(text: str) -> tuple[set[str], dict[str, str]]:
    """(every word of the text, every run of 2-6 consecutive words of ONE line joined together -> the words as written)."""
    singles: set[str] = set()
    cat: dict[str, str] = {}
    for line in text.replace("\f", "\n").splitlines():
        shown = re.findall(r"[^\W_]+", _nfkc(line))
        toks = [t.lower() for t in shown]
        singles.update(toks)
        for i in range(len(toks)):
            joined = toks[i]
            for j in range(i + 1, min(i + GLUE_MAX_WORDS, len(toks))):
                joined += toks[j]
                if len(joined) >= GLUE_MIN_LETTERS:
                    cat.setdefault(joined, " ".join(shown[i:j + 1]))
    return singles, cat


def glued_words(v: View, ref_text: str) -> list[tuple[str, str, str]]:
    """(word as OpenResume read it, the words the text layer has, its line). A token OpenResume produced that no extractor has as a
    word, but that equals 2-6 consecutive words of one consensus line, is words glued together."""
    singles, cat = _consensus_concats(ref_text)
    out, seen = [], set()
    for li, l in enumerate(v.lines):
        for it in l["items"]:
            for m in re.finditer(r"[^\W_]{%d,}" % GLUE_MIN_LETTERS, _nfkc(it[0])):
                w = m.group().lower()
                if w not in singles and w in cat and w not in seen:
                    seen.add(w)
                    out.append((m.group(), cat[w], v.line_text(li)))
    return out


# ---- (b) item granularity --------------------------------------------------------------------------------------------
def granularity(v: View) -> tuple[int, int, float]:
    """(items without any whitespace, all items with a letter or digit, share) over body lines, i.e. lines of >= BODY_LINE_WORDS words."""
    single = total = 0
    for _, s, e in v.ranges:
        items = [r[0] for r in v.raw[s:e] if re.search(r"\w", r[0])]
        if sum(len(t.split()) for t in items) < BODY_LINE_WORDS:
            continue
        total += len(items)
        single += sum(1 for t in items if not re.search(r"\s", t))      # an item that carries its own space is not a word on its own
    return single, total, (single / total if total else 0.0)


# ---- (c) bullets -----------------------------------------------------------------------------------------------------
def consensus_bullets(parsed: fd.Parsed) -> Counter:
    ex = parsed.section("experience")
    lines = parsed.lines[ex.start:ex.end] if ex else parsed.lines
    return Counter(l[0] for l in lines if fd.is_bullet(l))


def bullet_finding(bl: Counter, known: set[str], descs: int) -> tuple[str, int, int] | None:
    """(glyph, its count, bullet lines) when most bullet lines start with a glyph OpenResume does not know AND it did not come out with one
    description per bullet anyway; else None."""
    nb = sum(bl.values())
    unknown = {g: n for g, n in bl.items() if g not in known}
    if nb >= 2 and unknown and sum(unknown.values()) >= nb / 2 and descs != nb:
        g, n = max(unknown.items(), key=lambda kv: kv[1])
        return g, n, nb
    return None


# ---- (f) page boundary -----------------------------------------------------------------------------------------------
def page_straddles(v: View) -> list[dict]:
    """Lines OpenResume built from items of two pages: readPdf concatenates the pages and groupTextItemsIntoLines starts a new line only
    after an item with hasEOL, which pdf.js does not set on the last item of a page."""
    out = []
    if not v.pages_ok:
        return out
    for pno, b in enumerate(v.bounds, 1):
        for li, s, e in v.ranges:
            if s < b < e:
                out.append({"page": pno, "line": li, "before": " ".join(r[0] for r in v.raw[s:b]), "after": " ".join(r[0] for r in v.raw[b:e])})
    return out


def _is_header_like(after: str, parsed: fd.Parsed | None) -> bool:
    n = _norm(after)
    if parsed:
        for e in parsed.entries:
            h = _norm(e.header)[:20]
            if len(h) >= 8 and h in n:
                return True
        for s in parsed.sections:
            if _norm(s.title) and n.startswith(_norm(s.title)):
                return True
    return bool(fd.RANGE.search(after))


# ---- (d) entries -----------------------------------------------------------------------------------------------------
def _sig(dates: str) -> tuple:
    return (tuple(re.findall(r"\b(?:19|20)\d{2}\b", dates)), bool(re.search(r"present|current|now", dates, re.I)))


def entry_problems(v: View, parsed: fd.Parsed, skip_headers: list[str]) -> tuple[list[str], int]:
    """-> (problems, consensus entries compared). Entries whose header is glued onto a page boundary are not compared (see (f))."""
    work = v.resume["workExperiences"]
    # an entry without a recognised title, or whose header starts lower-case, is as likely a wrapped bullet that mentions a date as a job:
    # it is not a ground truth to compare with
    cons = [e for e in parsed.entries if e.title and e.header[:1].isupper() and not any(_norm(e.header)[:20] and _norm(e.header)[:20] in _norm(a) for a in skip_headers)]
    probs: list[str] = []
    used: set[int] = set()
    for ce in cons:
        sig = _sig(ce.dates_raw)
        if not sig[0]:
            continue
        same = [i for i, w in enumerate(work) if i not in used and _sig(w["date"]) == sig]
        # concurrent roles share a year signature: prefer the entry whose own text names this role's title or company
        named = [i for i in same if any(t and _norm(t) in _norm(work[i]["jobTitle"] + work[i]["company"]) for t in (ce.title, ce.company))]
        k = (named or same or [None])[0]
        if k is None:
            probs.append(f"no OpenResume entry has the dates of '{_q(ce.header, 60)}'")
            continue
        used.add(k)
        w = work[k]
        if not w["jobTitle"].strip() and ce.title:
            glued_comma = re.search(re.escape(ce.title.split()[-1]) + r"[,;:]", w["company"] + " " + w["jobTitle"])
            probs.append(f"job title empty for '{_q(ce.header, 60)}' (consensus title '{_q(ce.title, 40)}'; OpenResume company: '{_q(w['company'], 50)}')"
                         + ("; it matches a title only as a whole word of its list, so '" + glued_comma.group() + "' with punctuation is not one" if glued_comma else ""))
        elif ce.title and _norm(ce.title) not in _norm(w["jobTitle"] + w["company"]):
            probs.append(f"job title differs for '{_q(ce.header, 60)}': consensus '{_q(ce.title, 40)}', OpenResume '{_q(w['jobTitle'], 40)}'")
        if not w["company"].strip() and ce.company:
            probs.append(f"company empty for '{_q(ce.header, 60)}' (consensus company '{_q(ce.company, 40)}')")
    for i, w in enumerate(work):
        if i in used:
            continue
        if not any(re.search(r"\w", w[k]) for k in ("company", "jobTitle", "date")):      # a stray bullet glyph is not a field
            first = (w["descriptions"] or [""])[0]
            probs.append(f"OpenResume split a role: entry #{i + 1} has no company, title or date and starts '{_q(first, 60)}' "
                         f"(a vertical gap inside one role larger than 1.4x its usual line gap starts a new entry)")
    return probs, len(cons)


# ---- (e) education ---------------------------------------------------------------------------------------------------
def education_problems(v: View, parsed: fd.Parsed) -> list[str]:
    if not parsed.education and not parsed.section("education"):
        return []
    eds = v.resume["educations"]
    if not eds:
        return ["OpenResume found no education entry"]
    out = []
    for i, e in enumerate(eds, 1):
        if not e["school"].strip() or not e["degree"].strip():
            lead = parsed.education[min(i - 1, len(parsed.education) - 1)] if parsed.education else ""
            out.append(f"education #{i}: school '{_q(e['school'], 40)}', degree '{_q(e['degree'], 40)}' (text layer: '{_q(lead, 70)}')")
    return out


# ---- (g) contact -----------------------------------------------------------------------------------------------------
def contact_problems(v: View, parsed: fd.Parsed) -> tuple[list[str], list[str]]:
    """-> (email problems, other problems)."""
    prof = v.resume["profile"]
    digits = lambda s: re.sub(r"\D", "", s)[-10:]
    pairs = [("email", parsed.email, prof["email"], lambda s: s.strip().lower()),
             ("phone", parsed.phone, prof["phone"], digits),
             ("name", parsed.name, prof["name"], _norm),
             ("location", parsed.location, prof["location"], _norm)]
    mail, other = [], []
    for field, ours, theirs, norm in pairs:
        if not ours:
            continue
        if not theirs.strip():
            msg = f"{field}: OpenResume found none (consensus '{_q(ours, 40)}')"
        elif norm(ours) != norm(theirs):
            msg = f"{field}: OpenResume read '{_q(theirs, 50)}', consensus '{_q(ours, 40)}'"
        else:
            continue
        (mail if field == "email" else other).append(msg)
    return mail, other


# ---- the layer -------------------------------------------------------------------------------------------------------
def checks(pdf: Path, ref_text: str, parsed: fd.Parsed | None) -> tuple[list[Check], dict | None]:
    """-> (checks, the runner's output or None). Never raises: a missing install or a runner failure is one WARN."""
    h = home()
    if h is None:
        return [], None
    why = missing_reason(h)
    title = "OpenResume parser layer"
    if why:
        return [Check("or_layer", title, WARN, [f"skipped: {why}"],
                      f"Optional second parser (OpenResume). Install: {install_command()}  (needs node >= 20, npm, git). Silence with {ENV}=off.")], None
    try:
        d = run_runner(pdf, h)
        v = View(d)
    except (RunnerError, KeyError, TypeError) as e:
        return [Check("or_layer", title, WARN, [f"OpenResume runner failed: {e}"], f"Reinstall: {install_command()}; or silence with {ENV}=off.")], None
    if not wrapper_took_effect(d, v):
        return [Check("or_layer", title, WARN, ["OpenResume ran without the pdf.js wrapper; page and safety checks unverified"],
                      f"run.ts could not wrap pdf.js (one getDocument call with isEvalSupported false, page counts that sum to the item count); reinstall: {install_command()}.")], None
    out = [Check("or_layer", title, PASS, [f"OpenResume {version(h)} read {len(v.raw)} pdf.js text items in {len(v.lines)} lines"])]
    if parsed is None:
        return out, d
    try:
        return out + _compare(v, ref_text, parsed), d
    except Exception as e:      # an optional layer must not take the check down; the payload was validated, so this would be a bug here
        return [Check("or_layer", title, WARN, [f"OpenResume comparison failed: {type(e).__name__}: {e}"[:200]], f"Report it; silence with {ENV}=off.")], None


def _compare(v: View, ref_text: str, parsed: fd.Parsed) -> list[Check]:
    out: list[Check] = []

    # (b) granularity first: it is the root cause the other findings point at
    single, total, share = granularity(v)
    gran_bad = total >= GRANULARITY_MIN_ITEMS and share >= GRANULARITY_SHARE
    glued = glued_words(v, ref_text)
    if gran_bad:
        ex = next((" | ".join(r[0] for r in v.raw[s:e]) for _, s, e in v.ranges if len([r for r in v.raw[s:e] if re.search(r"\w", r[0])]) >= BODY_LINE_WORDS), "")
        out.append(Check("or_granularity", "pdf.js reads whole lines, not one item per word", WARN,
                         [f"{single} of {total} text items on body lines are a single word ({share:.0%}); one line as pdf.js items: {_q(ex, 110)}"],
                         "Most words arrive as separate pdf.js items (font expansion / microtype, per-word positioning), so a parser that joins items by distance can glue or split words"
                         + ("" if glued else " (none are glued in this file, but it depends on the gaps)") + ". "
                         "Turn font expansion off (LaTeX: microtype `expansion=false`) or re-export with line-level text runs."))
    else:
        out.append(Check("or_granularity", "pdf.js reads whole lines, not one item per word", PASS, [f"{single} of {total} items on body lines are a single word ({share:.0%})"] if total else []))

    # (a) glued words
    if glued:
        out.append(Check("or_glued", "Words stay separate in OpenResume's text", WARN,
                         [f"{len(glued)} words glued together; first {min(3, len(glued))}:"] +
                         [f"OpenResume reads '{a}' where the text layer has '{b}' (line: '{_q(l, 80)}')" for a, b, l in glued[:3]],
                         "Words are positioned so close that a distance-based joiner drops the space. "
                         + ("This is the item-granularity problem above." if gran_bad else "Check word spacing / kerning / font expansion in the typesetter.")))
    else:
        out.append(Check("or_glued", "Words stay separate in OpenResume's text", PASS))

    # (c) bullets
    bl = consensus_bullets(parsed)
    known = set(v.bullets)
    nb = sum(bl.values())
    descs = sum(len(w["descriptions"]) for w in v.resume["workExperiences"])
    bf = bullet_finding(bl, known, descs)
    if bf:
        g, n, nb = bf
        out.append(Check("or_bullets", "OpenResume recognises the bullet glyph", WARN,
                         [f"{n} of {nb} bullet lines in Experience start with {_glyph(g)}, which is not in OpenResume's bullet list; it found {descs} descriptions for {nb} bullets",
                          "OpenResume's list: " + " ".join(v.bullets)],
                         "Use a bullet glyph from its list (the round bullet U+2022 is the common one). Dashes, hyphens, squares and arrows are not recognised, so bullets run together."))
    else:
        out.append(Check("or_bullets", "OpenResume recognises the bullet glyph", PASS, [f"{nb} bullet lines; glyphs {''.join(bl)}"] if nb else []))

    # (f) page boundary (computed before (d): a glued role header is not compared there)
    straddles = [s for s in page_straddles(v) if _is_header_like(s["after"], parsed)]
    skip = [s["after"] for s in straddles]
    if straddles:
        out.append(Check("or_page_boundary", "No role header glued onto a page break (OpenResume limitation)", WARN,
                         [f"page {s['page']} ends with '{_q(s['before'], 40)}' and page {s['page'] + 1} starts with '{_q(s['after'], 50)}': OpenResume joined them into one line" for s in straddles[:2]],
                         "A limitation of OpenResume, not a defect of the resume: its reader concatenates pages and breaks a line only after an item with an end-of-line flag, which pdf.js does not set on the last item of a page. "
                         "Only a parser that reads pages the same way is affected; to avoid it, let the page break fall between two bullets of a role instead of right before its header."))
    else:
        out.append(Check("or_page_boundary", "No role header glued onto a page break (OpenResume limitation)", PASS))

    # (d) entries
    probs, n_cmp = entry_problems(v, parsed, skip)
    n_or = len(v.resume["workExperiences"])
    if n_cmp and n_or == 0:
        sec = parsed.section("experience")
        probs[:] = [f"OpenResume found no work entry; the consensus parse has {n_cmp}"
                     + (f" (it finds the work section only by the words work, experience, employment, history or job in its heading; the heading here is '{_q(sec.title, 40)}')" if sec else "")]
    elif n_or != n_cmp and not probs:
        probs.append(f"OpenResume found {n_or} work entries; the consensus parse has {n_cmp}")
    if probs:
        out.append(Check("or_entries", "OpenResume reads each job's title, company and dates", WARN,
                         probs[:4] + ([f"(+{len(probs) - 4} more)"] if len(probs) > 4 else []),
                         "Keep the lines of one role at one line spacing, put the job title on the header line as a plain word from a standard title (no trailing comma on it), then dates on the same line."))
    else:
        out.append(Check("or_entries", "OpenResume reads each job's title, company and dates", PASS,
                         [f"{n_or} work entries read, title, company and dates match the consensus parse" + (" (a role header glued at a page break is left out, see above)" if skip else "")]))

    # (e) education
    ep = education_problems(v, parsed)
    out.append(Check("or_education", "OpenResume reads school and degree", WARN, ep[:3],
                     "Put the degree and the school on two lines (or separate text runs): 'BBA' and 'University of X' in one bold line score as neither.") if ep
               else Check("or_education", "OpenResume reads school and degree", PASS))

    # (g) contact
    mail, other = contact_problems(v, parsed)
    if mail or other:
        out.append(Check("or_contact", "OpenResume reads the contact fields", WARN, mail + other,
                         "Put the email on its own line or separate contact items with ' | ' so each is its own text run; a parser that cannot read the email cannot show it to a recruiter."))
    else:
        out.append(Check("or_contact", "OpenResume reads the contact fields", PASS))
    return out
