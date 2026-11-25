"""Field extraction from extracted text, modelled on OpenResume's pipeline (lines -> sections by
heading -> per-section field rules; its algorithm is AGPL, only the ideas are reused).
Runs on the plain text of ANY extractor, so a field is only trustworthy when it parses under all."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BULLETS = "•●▪■◦‣∙*-–—·◆▶►"
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december"
DATE = rf"(?:\d{{4}}-\d{{1,2}}|\d{{1,2}}/\d{{4}}|(?:{MONTHS})\.?,?\s+\d{{4}}|\d{{4}})"
NOW = r"(?:present|current|now|today|ongoing|to date)"
RANGE = re.compile(rf"(?P<a>{DATE})\s*(?:–|—|-|to|until|through)\s*(?P<b>{DATE}|{NOW})", re.I)
ONE_DATE = re.compile(DATE, re.I)
UNPARSEABLE = re.compile(r"\b(?:spring|summer|fall|autumn|winter|q[1-4]|h[12]|early|mid|late)\b[\s-]*['’‘]?\d{2,4}\b|['’‘]\d{2}\b|\b(?:spring|summer|fall|autumn|winter)\b", re.I)

CANON = [
    ("experience", ("experience", "employment", "work history", "career history", "professional background")),
    ("education", ("education", "academic", "qualifications")),
    ("skills", ("skill", "technologies", "tech stack", "competenc", "expertise", "technical proficiency")),
    ("summary", ("summary", "profile", "objective", "about me", "about")),
    ("projects", ("project",)),
    ("certifications", ("certif", "licens")),
    ("awards", ("award", "honor", "honour")),
    ("publications", ("publication",)),
]
JOB_WORDS = re.compile(r"\b(engineer|manager|developer|lead|director|analyst|scientist|architect|consultant|designer|producer|founder|co-founder|intern|specialist|strategist|officer|head|president|vp|owner|administrator|researcher|associate|technician|product|programmer|editor|writer|advisor|executive|coordinator|partner|principal|staff|fellow)\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+?\d{1,2}[\s.-])?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}")
URL = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}/[\w./%#?=&-]*", re.I)
# 'City, ST' / 'City, Country': Title-Case words only, so 'MCP servers, Large' (a headline) is not a place
LOC = re.compile(r"[A-Z][a-z.]+(?:[ \-][A-Z][a-z.]+)*,\s*(?:[A-Z]{2}\b|[A-Z][a-z]+(?: [A-Z][a-z]+)*)")
LOC_FRAGMENT = re.compile(r"(?i:\b(?:Bay Area|Area|Remote|Hybrid|On-?site|Metro)$|^(?:in |and )|\band\b.*\b(?:Area|Remote)\b)|,\s*[A-Z]{2}$")
DEGREE = re.compile(r"\b(b\.?s\.?c?\.?|b\.?a\.?|bachelor[’']?s?|master[’']?s?|m\.?s\.?c?\.?|m\.?b\.?a|ph\.?d|doctorate|associate|diploma|degree|b\.?eng|m\.?eng)\b", re.I)
SCHOOL = re.compile(r"\b(university|college|institute|school|academy|polytechnic)\b", re.I)
# a page footer alone on its line: '1/2', 'Page 1 of 2', 'Page 1', '1', '- 1 -' (not a year: '2022' has four digits)
PAGE_NUMBER = re.compile(r"(?:(?:page\s+)?\d{1,3}(?:\s*(?:/|of)\s*\d{1,3})?|[-–—]\s*\d{1,3}\s*[-–—])", re.I)


@dataclass
class Entry:
    header: str
    title: str = ""
    company: str = ""
    dates_raw: str = ""
    start: str = ""
    end: str = ""
    dates_ok: bool = False
    dates_problem: str = ""
    current: bool = False
    first_line: int = 0
    last_line: int = 0
    bullets: int = 0


@dataclass
class Section:
    title: str
    canon: str  # canonical key or "other"
    start: int
    end: int
    from_style: bool = False


@dataclass
class Parsed:
    lines: list[str] = field(default_factory=list)
    name: str = ""
    email: str = ""
    phone: str = ""
    links: list[str] = field(default_factory=list)
    location: str = ""
    sections: list[Section] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    profile_end: int = 0

    def section(self, canon: str) -> Section | None:
        return next((s for s in self.sections if s.canon == canon), None)


def clean_lines(text: str) -> list[str]:
    out = []
    for raw in text.replace("\f", "\n").splitlines():
        t = re.sub(r"\s{2,}", "  ", raw.replace("\xa0", " ")).strip()
        if t and not PAGE_NUMBER.fullmatch(t):
            out.append(t)
    return out


def is_bullet(line: str) -> bool:
    return bool(line) and line[0] in BULLETS and (len(line) == 1 or line[1] in " \t") or line.startswith("• ")


def canon_of(title: str) -> str:
    t = title.lower()
    for key, kws in CANON:
        if any(k in t for k in kws):
            return key
    return "other"


def _heading_like(line: str, style_headings: set[str]) -> tuple[bool, bool]:
    """(is_heading, via_style)"""
    t = line.strip()
    words = t.split()
    if not t or len(words) > 5 or is_bullet(t) or t.endswith(".") or EMAIL.search(t):
        return False, False
    if re.search(r"\d", t) or any(c in t for c in ",·|•@"):
        return False, False
    letters = [c for c in t if c.isalpha()]
    if letters and t.upper() == t and len(letters) >= 4:
        return True, False
    if canon_of(t) != "other" and len(words) <= 3 and t[0].isupper():
        return True, False
    if t in style_headings:
        return True, True
    return False, False


def split_dates(line: str):
    """-> (text_without_dates, raw_dates, start, end, ok, problem)"""
    m = RANGE.search(line)
    if m:
        rest = (line[: m.start()] + " " + line[m.end():]).strip(" ·|,–—-")
        end = m.group("b")
        return rest, m.group(0), m.group("a"), end, True, ""
    u = UNPARSEABLE.search(line)
    if u:
        raw_s = line[u.start():].strip()
        rest = line[: u.start()].strip(" ·|,–—-")
        return rest, raw_s, "", "", False, f"unparseable date format '{raw_s}'"
    d = ONE_DATE.search(line)
    if d:
        rest = (line[: d.start()] + " " + line[d.end():]).strip(" ·|,–—-")
        return rest, d.group(0), d.group(0), "", True, "single date, no range"
    return line, "", "", "", False, ""


def _title_company(rest: str) -> tuple[str, str]:
    rest = re.sub(r"\([^)]*\)", " ", rest)
    parts = [p.strip() for p in re.split(r"\s*(?:,| · |\||@| at | — | – | - )\s*", rest) if p.strip()]
    title = next((p for p in parts if JOB_WORDS.search(p)), "")
    others = [p for p in parts if p != title]
    company = others[0] if others else ""
    if len(company) > 60 or LOC.fullmatch(company or ""):
        company = ""
    return title, company


def _location(prof: list[str]) -> str:
    """The place from the CONTACT line (the one with the email or phone), segment by segment; a headline
    line is never searched ('Agents, MCP servers, Large Language Models' is not a place)."""
    contact = [l for l in prof if EMAIL.search(l) or PHONE.search(l)]
    for line in contact:
        for seg in re.split(r"\s*[·|•]\s*", line):
            seg = seg.strip()
            if LOC.fullmatch(seg):
                return seg
    for line in prof[1:]:
        if line not in contact and len(line.split()) <= 6:
            for seg in re.split(r"\s*[·|•]\s*", line):
                if LOC.fullmatch(seg.strip()):
                    return seg.strip()
    return ""


def looks_like_location(s: str) -> bool:
    """A parsed 'company' that is really the job's location ('Los Angeles and San Francisco Bay Area')."""
    t = s.strip(" ·|,–—-")
    return bool(t) and (bool(LOC.fullmatch(t)) or bool(LOC_FRAGMENT.search(t)))


def parse(text: str, style_headings: set[str] | None = None) -> Parsed:
    style_headings = style_headings or set()
    P = Parsed(lines=clean_lines(text))
    L = P.lines
    # --- sections
    heads: list[tuple[int, str, bool]] = []
    for i, ln in enumerate(L):
        if i < 2:
            continue
        ok, via = _heading_like(ln, style_headings)
        if ok:
            heads.append((i, ln, via))
    P.profile_end = heads[0][0] if heads else min(3, len(L))
    for k, (i, t, via) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(L)
        P.sections.append(Section(t, canon_of(t), i + 1, end, via))
    # --- profile
    prof = L[: P.profile_end]
    prof_text = "\n".join(prof)
    m = EMAIL.search(prof_text) or EMAIL.search("\n".join(L))
    P.email = m.group(0) if m else ""
    m = PHONE.search(prof_text) or PHONE.search("\n".join(L))
    P.phone = m.group(0) if m else ""
    P.links = sorted({u.group(0) for u in URL.finditer(prof_text)})
    P.location = _location(prof)
    for ln in prof[:4]:
        w = ln.split()
        if 2 <= len(w) <= 4 and re.fullmatch(r"[A-Za-z.\-' ]+", ln) and not JOB_WORDS.search(ln):
            P.name = ln
            break
    # --- experience entries
    ex = P.section("experience")
    if ex:
        P.entries = _entries(L, ex)
    ed = P.section("education")
    if ed:
        P.education = [l for l in L[ed.start: ed.end] if DEGREE.search(l) or SCHOOL.search(l)]
    sk = P.section("skills")
    if sk:
        body = " ".join(L[sk.start: sk.end])
        items = [x.strip(" .•") for x in re.split(r"[,;|•\n]|\s{2,}", re.sub(r"^[^:]{2,40}:", "", body)) if x.strip(" .•")]
        P.skills = [i for i in items if 1 < len(i) < 60]
        if not body.strip():
            P.skills = []
    return P


def _lowercase_start(s: str) -> bool:
    """Prose starts lowercase; a brand does not count ('iOS Engineer', 'eBay Analyst': second letter upper)."""
    return s[:1].islower() and not s[1:2].isupper()


def _continues_bullet(ln: str, rest: str, raw: str, prob: str) -> bool:
    """A non-bullet line right after a bullet that reads as more words of that bullet's sentence, not a role header:
    the wrapped line a line-based extractor leaves on its own row ('of them first, in a November 2026 test',
    'November 2026, and has done its SEO ...', 'Nov 2026 GEO test of 15 questions; built its site.')."""
    if _lowercase_start(ln):
        return True
    if not raw:
        return False
    if _lowercase_start(rest):  # the text beside the date is prose, not 'Title, Company'
        return True
    return prob == "single date, no range" and ln.endswith(".") and len(rest.split()) >= 8


def _entries(L: list[str], ex: Section) -> list[Entry]:
    out: list[Entry] = []
    i = ex.start
    cur: Entry | None = None
    in_bullet = False  # the previous line is a bullet or a wrapped line of one
    while i < ex.end:
        ln = L[i]
        if is_bullet(ln):
            if cur:
                cur.bullets += 1
                cur.last_line = i
            in_bullet = True
            i += 1
            continue
        rest, raw, a, b, ok, prob = split_dates(ln)
        if in_bullet and cur and _continues_bullet(ln, rest, raw, prob):
            cur.last_line = i
            i += 1
            continue
        has_date = bool(raw)
        words = len(ln.split())
        if has_date and words <= 25:
            title_line = ln
            first = i
            # date-only line (stream-order extractors): title/company is the previous line
            if (len(rest.split()) <= 1 and i - 1 >= ex.start and not is_bullet(L[i - 1])
                    and not split_dates(L[i - 1])[1] and len(L[i - 1].split()) <= 12
                    and not L[i - 1].endswith('.') and L[i - 1][:1].isupper()):
                rest = L[i - 1]
                title_line = L[i - 1] + " " + ln
                first = i - 1
            t, c = _title_company(rest)
            if first < i and out and out[-1].last_line >= first:
                out[-1].last_line = first - 1
            cur = Entry(header=title_line, title=t, company=c, dates_raw=raw, start=a, end=b, dates_ok=ok and not prob.startswith("unparse"),
                        dates_problem=prob, current=bool(re.fullmatch(NOW, (b or "").strip(), re.I)), first_line=first, last_line=i)
            out.append(cur)
            in_bullet = False
        elif (not has_date and words <= 12 and not ln.endswith(".") and i + 1 < ex.end and is_bullet(L[i + 1])
              and (cur is None or cur.bullets > 0)):
            # undated header followed by bullets
            t, c = _title_company(ln)
            cur = Entry(header=ln, title=t, company=c, dates_problem="no dates found", first_line=i, last_line=i)
            out.append(cur)
            in_bullet = False
        elif cur:
            cur.last_line = i
        i += 1
    return out
