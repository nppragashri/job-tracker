#!/usr/bin/env python3
"""Daily job refresh for the 0-2 year backend / AI search.

Pulls from two kinds of source:

  1. ATS public job feeds (Greenhouse, Lever, Ashby). These are documented,
     unauthenticated endpoints that serve exactly what each company publishes
     on its own careers page. Reliable; this is the backbone.
  2. Wellfound role listing pages, parsed from HTML. Best effort only —
     Wellfound may block CI traffic, in which case the run logs a warning and
     carries on with whatever the ATS feeds returned.

Writes data/jobs.json and archives a dated copy under data/archive/.
`first_seen` is carried over from the previous run so the page can badge
genuinely new postings.

Usage:  python scripts/fetch_jobs.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ARCHIVE = os.path.join(DATA, "archive")
OUT = os.path.join(DATA, "jobs.json")

TODAY = dt.date.today().isoformat()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# --------------------------------------------------------------------------
# What counts as a match
# --------------------------------------------------------------------------

# Titles we want. Deliberately broad — the seniority filter does the real work.
WANT = re.compile(
    r"\b(backend|back-end|software|platform|infrastructure|distributed|api|"
    r"ai|ml|machine learning|data|llm|voice|founding|full[ -]?stack|sde)\b", re.I)

# Seniority we do NOT want. Levels may be written "SDE 2", "SDE-2", "SDE-II",
# "Engineer III", "L3", "IC3" — the separator class matters, an earlier version
# missed "SDE-2" because it only allowed a space.
_SEP = r"[\s\-–—_]?"
TOO_SENIOR = re.compile(
    r"\b(senior|snr|sr\.?|staff|principal|lead|head|director|vp|architect|"
    r"manager|distinguished|expert|specialist|"
    rf"sde{_SEP}(?:2|3|4|ii|iii|iv)|"
    rf"sdet{_SEP}(?:2|3|ii|iii)|"
    rf"engineer{_SEP}(?:2|3|4|ii|iii|iv)|"
    rf"developer{_SEP}(?:2|3|4|ii|iii|iv)|"
    rf"scientist{_SEP}(?:2|3|ii|iii)|"
    rf"level{_SEP}(?:2|3|4)|l[34]|ic[34])\b", re.I)

# Explicitly junior signals. These override the seniority check, and are also
# what lets a posting through when it states no years at all.
JUNIOR_HINT = re.compile(
    r"\b(graduate|new{_SEP}?grad|junior|jr\.?|entry{_SEP}?level|associate|"
    r"campus|trainee|apprentice|university|fresher|"
    rf"sde{_SEP}(?:1|i)|engineer{_SEP}(?:1|i)|developer{_SEP}(?:1|i)|"
    r"founding)\b".replace("{_SEP}", _SEP), re.I)

# Bengaluru only. A role is kept if Bengaluru/Bangalore appears in its location.
BENGALURU = re.compile(r"\b(bengaluru|bangalore|bangalore urban|whitefield|"
                       r"garudachar\s*palya)\b", re.I)

# Remote-only postings are excluded even when the company is Bengaluru-based.
REMOTE_ONLY = re.compile(r"remote\s*only|\bwork from home\b|\bwfh\b|"
                         r"remote\s*[·\-•]\s*everywhere|^remote$", re.I)

# Internships are excluded — full-time roles only.
IS_INTERNSHIP = re.compile(r"\bintern(ship)?\b", re.I)

# The hard ceiling. A posting whose *minimum* stated requirement is above this
# is dropped, however junior the title sounds.
MAX_YEARS = 2

# When a posting never states a number of years, do we keep it?
# False would mean "give it the benefit of the doubt" — which is exactly how
# 4- and 5-year roles leaked through, because senior postings often omit the
# figure entirely. True means an unstated level is only acceptable if the title
# is explicitly junior. Set to False if the board ever feels too empty.
REQUIRE_EXPLICIT_YEARS = True

# "4+ years", "3-5 years", "1 to 3 years", "minimum of 3 years", "4-6 YOE".
YEARS = re.compile(
    r"(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:to|-|–|—)\s*(\d{1,2})\s*)?\+?\s*"
    r"(?:yrs?\b|years?\b|yoe\b)", re.I)
# "YOE" already carries the meaning, so it counts as its own context.
YEARS_CONTEXT = re.compile(r"experien|yoe|background|track record", re.I)


def min_years_required(text: str) -> int | None:
    """Smallest number of years the text asks for, or None if it never says.

    A description usually states several figures ("4+ years backend", "2+ years
    with Python"). The floor is what actually gates an application, so we take
    the minimum across all of them. Numbers not near an experience-flavoured
    word are ignored, which keeps team sizes and founding dates out of it.
    """
    if not text:
        return None
    floors = []
    for m in YEARS.finditer(text):
        window = text[max(0, m.start() - 90):m.end() + 90]
        if not YEARS_CONTEXT.search(window):
            continue
        try:
            floors.append(int(m.group(1)))
        except (TypeError, ValueError):
            continue
    return min(floors) if floors else None


def assess(title: str, location: str = "", description: str = ""):
    """Return (keep, years_required, reason).

    `years_required` is None when the posting never says. That case used to be
    treated as "probably fine" and it is how four- and five-year roles kept
    reaching the board: plenty of senior postings simply never print a number.
    Now an unverifiable posting is kept only when the title itself is explicitly
    junior — Engineer I, Associate, Graduate, Founding. Otherwise it is dropped.
    """
    if not title:
        return False, None, "no title"
    if IS_INTERNSHIP.search(title):
        return False, None, "internship"
    if not WANT.search(title):
        return False, None, "title not a backend/AI role"

    junior = bool(JUNIOR_HINT.search(title))
    if TOO_SENIOR.search(title) and not junior:
        return False, None, "senior-level title"

    if location:
        if not BENGALURU.search(location):
            return False, None, ("remote-only" if REMOTE_ONLY.search(location)
                                 else f"not Bengaluru ({location})")

    # Title first — some postings put the band right in it ("... | 4-6 YOE |").
    years = min_years_required(title)
    if years is None:
        years = min_years_required(description)

    if years is not None and years > MAX_YEARS:
        return False, years, f"asks {years}+ years"

    if years is None and REQUIRE_EXPLICIT_YEARS and not junior:
        return False, None, "no experience level stated and title is not junior"

    return True, years, "ok"


def wanted(title: str, location: str = "", description: str = "") -> bool:
    return assess(title, location, description)[0]


def jid(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def get(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"  ! {url} -> {e}", file=sys.stderr)
        return None


# --------------------------------------------------------------------------
# ATS boards. Tokens verified live on 5 Aug 2026.
# --------------------------------------------------------------------------

GREENHOUSE = [
    ("Postman", "postman"), ("Razorpay", "razorpaysoftwareprivatelimited"),
    ("Observe.AI", "observeai"), ("AssemblyAI", "assemblyai"),
    ("Databricks", "databricks"), ("MongoDB", "mongodb"), ("Elastic", "elastic"),
    ("Twilio", "twilio"), ("GitLab", "gitlab"), ("Temporal", "temporaltechnologies"),
    ("Rubrik", "rubrik"), ("Zscaler", "zscaler"), ("Cloudflare", "cloudflare"),
    ("Glean", "gleanwork"), ("Sigmoid", "sigmoid"), ("Atomicwork", "atomicwork"),
    ("Sezzle", "sezzle"), ("Scale AI", "scaleai"), ("Anthropic", "anthropic"),
    ("Degreed", "degreed"), ("Capco", "capco"), ("Meltplan", "meltplan"),
]

LEVER = [
    ("CRED", "cred"), ("Meesho", "meesho"), ("Stable Money", "stable-money1"),
    ("Onehouse", "Onehouse"), ("Zimperium", "zimperium"), ("Level AI", "levelai"),
    ("Upscale AI", "upscale-ai"), ("RapidAI", "rapidai"),
]

ASHBY = [
    ("Sarvam AI", "sarvam"), ("ElevenLabs", "elevenlabs"), ("LiveKit", "livekit"),
    ("Sierra", "sierra"), ("Cartesia", "cartesia"), ("Bespoke Labs", "bespokelabs"),
    ("Broccoli AI", "broccoli"), ("Known", "Known"), ("Outmarket AI", "outmarket"),
]

WELLFOUND_PAGES = [
    "https://wellfound.com/role/l/backend-engineer/bangalore",
    "https://wellfound.com/role/l/backend-engineer/bangalore?page=2",
    "https://wellfound.com/role/l/backend-engineer/bangalore?page=3",
    "https://wellfound.com/role/l/software-engineer/bangalore",
    "https://wellfound.com/role/l/machine-learning-engineer/bangalore",
]


def strip_html(s: str) -> str:
    import html as _html
    return _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))


def exp_label(years: int | None) -> str:
    if years is None:
        return "junior title, no band stated"
    if years == 0:
        return "no experience required"
    return f"{years} yr{'s' if years != 1 else ''} asked"


def from_greenhouse() -> list[dict]:
    out = []
    for name, tok in GREENHOUSE:
        # content=true so we can read the requirements, not just the title.
        raw = get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=true")
        if not raw:
            continue
        try:
            jobs = json.loads(raw).get("jobs", [])
        except json.JSONDecodeError:
            continue
        for j in jobs:
            loc = (j.get("location") or {}).get("name", "")
            title = j.get("title", "")
            desc = strip_html(j.get("content", ""))
            keep, years, why = assess(title, loc, desc)
            if not keep:
                if "years" in why:
                    print(f"    dropped {name} '{title}' — {why}")
                continue
            url = j.get("absolute_url", "")
            out.append(dict(id=jid(url), company=name, title=title, url=url,
                            source="Greenhouse", location=loc, comp="",
                            years_required=years, experience=exp_label(years),
                            posted=(j.get("first_published") or "")[:10]))
        time.sleep(0.5)
    return out


def from_lever() -> list[dict]:
    out = []
    for name, tok in LEVER:
        raw = get(f"https://api.lever.co/v0/postings/{tok}?mode=json")
        if not raw:
            continue
        try:
            jobs = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for j in jobs:
            cats = j.get("categories") or {}
            loc = cats.get("location") or ""
            title = j.get("text", "")
            desc = j.get("descriptionPlain", "") + " " + " ".join(
                strip_html(l.get("content", "")) for l in (j.get("lists") or []))
            keep, years, why = assess(title, loc, desc)
            if not keep:
                if "years" in why:
                    print(f"    dropped {name} '{title}' — {why}")
                continue
            url = j.get("hostedUrl", "")
            posted = ""
            if j.get("createdAt"):
                posted = dt.datetime.utcfromtimestamp(j["createdAt"] / 1000).date().isoformat()
            out.append(dict(id=jid(url), company=name, title=title, url=url,
                            source="Lever", location=loc, comp="",
                            years_required=years, experience=exp_label(years),
                            posted=posted))
        time.sleep(0.5)
    return out


def from_ashby() -> list[dict]:
    out = []
    for name, tok in ASHBY:
        raw = get(f"https://api.ashbyhq.com/posting-api/job-board/{tok}")
        if not raw:
            continue
        try:
            jobs = json.loads(raw).get("jobs", [])
        except (json.JSONDecodeError, AttributeError):
            continue
        for j in jobs:
            loc = j.get("location") or ""
            title = j.get("title", "")
            desc = j.get("descriptionPlain") or strip_html(j.get("descriptionHtml", ""))
            keep, years, why = assess(title, loc, desc)
            if not keep:
                if "years" in why:
                    print(f"    dropped {name} '{title}' — {why}")
                continue
            url = j.get("jobUrl") or j.get("applyUrl") or ""
            if not url:
                continue
            out.append(dict(id=jid(url), company=name, title=title, url=url,
                            source="Ashby", location=loc, comp="",
                            years_required=years, experience=exp_label(years),
                            posted=(j.get("publishedAt") or "")[:10]))
        time.sleep(0.5)
    return out


# Wellfound listing markup, as of Aug 2026:
#   <a href="/company/SLUG">NAME</a> ... <a href="/jobs/ID-slug">TITLE</a>
#   followed by comp / location / "N years of exp" in sibling text.
WF_JOB = re.compile(r'href="(/jobs/(\d+)-[^"]+)"[^>]*>([^<]{3,120})</a>')
WF_EXP = re.compile(r"(\d+)(?:-\d+)?\s*years?\s*of\s*exp", re.I)
WF_COMP = re.compile(r"(₹[\d,.]+\s*[LK]?\s*[–-]\s*₹?[\d,.]+\s*[LK]?|\$[\d]+k\s*[–-]\s*\$?[\d]+k)")


WF_LOC = re.compile(r"(Remote only|In office|Onsite or remote|Remote)\s*[•·]?\s*"
                    r"([A-Za-z ]+(?:\+\d+)?)", re.I)

# How many individual postings we're willing to open per run to check an
# experience requirement the listing page didn't state. Keeps runtime sane.
WF_DEEP_CHECK_BUDGET = 25


def from_wellfound() -> list[dict]:
    """Best effort. Wellfound may block CI runners; failure is not fatal.

    Listing pages state years-of-experience only sometimes. When they don't we
    open the posting itself and read the requirements — a title like "Backend
    Engineer" with no tag turned out to want 4+ years, which is exactly the
    kind of thing that must not reach the board.
    """
    out, seen = [], set()
    budget = WF_DEEP_CHECK_BUDGET

    for page in WELLFOUND_PAGES:
        html = get(page, timeout=30)
        if not html:
            print(f"  ! wellfound page unavailable: {page}", file=sys.stderr)
            continue

        for m in WF_JOB.finditer(html):
            path, num, title = m.group(1), m.group(2), m.group(3).strip()
            if num in seen:
                continue
            tail = re.sub(r"<[^>]+>", " ", html[m.end():m.end() + 700])

            loc_m = WF_LOC.search(tail)
            location = " · ".join(loc_m.groups()).strip() if loc_m else ""

            # Location gate first — it is the cheapest test.
            if location:
                if REMOTE_ONLY.search(location) and not BENGALURU.search(location):
                    continue
                if not BENGALURU.search(location):
                    continue

            # Structural checks that don't need the description.
            if IS_INTERNSHIP.search(title) or not WANT.search(title):
                continue
            junior = bool(JUNIOR_HINT.search(title))
            if TOO_SENIOR.search(title) and not junior:
                continue

            exp_m = WF_EXP.search(tail)
            years = int(exp_m.group(1)) if exp_m else None
            if years is None:
                years = min_years_required(title)
            if years is not None and years > MAX_YEARS:
                continue

            url = "https://wellfound.com" + path
            company = ""

            # No stated band on the listing: open the posting and read it.
            if years is None:
                if budget <= 0:
                    print(f"    skipped '{title}' — deep-check budget spent")
                    continue
                budget -= 1
                detail = get(url, timeout=25)
                time.sleep(1.0)
                if not detail:
                    print(f"    skipped '{title}' — could not open posting")
                    continue
                body = re.sub(r"<[^>]+>", " ", detail)
                years = min_years_required(body)
                if years is not None and years > MAX_YEARS:
                    print(f"    dropped '{title}' — posting asks {years}+ yrs")
                    continue
                if not BENGALURU.search(body[:5000]):
                    continue
                t_m = re.search(r"<title>([^<]+)</title>", detail)
                if t_m and " at " in t_m.group(1):
                    company = t_m.group(1).split(" at ", 1)[1].split("•")[0].strip()

            # Still no number anywhere, and the title isn't explicitly junior.
            # Leaving it in is how four- and five-year roles got through before.
            if years is None and REQUIRE_EXPLICIT_YEARS and not junior:
                print(f"    dropped '{title}' — no experience level stated anywhere")
                continue

            seen.add(num)
            comp_m = WF_COMP.search(tail)
            out.append(dict(
                id=jid(url), company=company, title=title, url=url,
                source="Wellfound", location=location or "Bengaluru",
                comp=comp_m.group(1) if comp_m else "",
                years_required=years, experience=exp_label(years),
                posted=""))
        time.sleep(1.5)
    return out


# --------------------------------------------------------------------------

def main() -> int:
    os.makedirs(ARCHIVE, exist_ok=True)

    previous, first_seen = {}, {}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                prev = json.load(f)
            for j in prev.get("jobs", []):
                previous[j["id"]] = j
                first_seen[j["id"]] = j.get("first_seen", TODAY)
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    collected, status = [], {}
    for label, fn in (("Greenhouse", from_greenhouse), ("Lever", from_lever),
                      ("Ashby", from_ashby), ("Wellfound", from_wellfound)):
        print(f"fetching {label} ...")
        try:
            got = fn()
        except Exception as e:                                  # noqa: BLE001
            print(f"  ! {label} failed entirely: {e}", file=sys.stderr)
            got, = ([],)
        status[label] = len(got)
        print(f"  {len(got)} matching roles")
        collected.extend(got)

    # De-duplicate on id, preferring the entry with the most detail.
    merged: dict[str, dict] = {}
    for j in collected:
        cur = merged.get(j["id"])
        if cur is None or len(json.dumps(j)) > len(json.dumps(cur)):
            merged[j["id"]] = j

    jobs = []
    for j in merged.values():
        j["first_seen"] = first_seen.get(j["id"], TODAY)
        j["is_new"] = j["first_seen"] == TODAY
        jobs.append(j)

    jobs.sort(key=lambda x: (not x["is_new"], x["company"] or "zzz", x["title"]))

    gone = [j for jid_, j in previous.items() if jid_ not in merged]

    payload = dict(
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        generated_date=TODAY,
        counts=dict(total=len(jobs), new_today=sum(1 for j in jobs if j["is_new"]),
                    closed_since_last_run=len(gone), by_source=status),
        note=("Roles filtered to non-senior, non-internship titles in India or remote. "
              "Wellfound entries are best-effort scrapes and may be missing if the "
              "run was blocked."),
        jobs=jobs,
    )

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    with open(os.path.join(ARCHIVE, f"{TODAY}.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n{len(jobs)} roles written "
          f"({payload['counts']['new_today']} new, {len(gone)} disappeared)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
