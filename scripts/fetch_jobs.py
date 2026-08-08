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

# Seniority we do NOT want. This is the important filter.
TOO_SENIOR = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|head|director|vp|architect|"
    r"manager|distinguished|sde ?(?:2|3|ii|iii)|engineer ?(?:2|3|ii|iii)|"
    r"^ii\b|level ?(?:2|3))\b", re.I)

# Explicitly junior signals — these override a lot of noise.
JUNIOR_HINT = re.compile(
    r"\b(intern(?!ational)|graduate|new ?grad|junior|entry|associate|"
    r"campus|trainee|university|fresher|sde ?(?:1|i)\b|engineer ?(?:1|i)\b|"
    r"founding)\b", re.I)

INDIA = re.compile(r"\b(india|bengaluru|bangalore|hyderabad|mumbai|pune|delhi|"
                   r"gurugram|gurgaon|noida|chennai|remote)\b", re.I)

# Internships are excluded — Pragashri asked for full-time roles only.
IS_INTERNSHIP = re.compile(r"\bintern(ship)?\b", re.I)


def wanted(title: str, location: str = "") -> bool:
    if not title:
        return False
    if IS_INTERNSHIP.search(title):
        return False
    if not WANT.search(title):
        return False
    if TOO_SENIOR.search(title) and not JUNIOR_HINT.search(title):
        return False
    if location and not INDIA.search(location):
        return False
    return True


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


def from_greenhouse() -> list[dict]:
    out = []
    for name, tok in GREENHOUSE:
        raw = get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs")
        if not raw:
            continue
        try:
            jobs = json.loads(raw).get("jobs", [])
        except json.JSONDecodeError:
            continue
        for j in jobs:
            loc = (j.get("location") or {}).get("name", "")
            title = j.get("title", "")
            if not wanted(title, loc):
                continue
            url = j.get("absolute_url", "")
            out.append(dict(id=jid(url), company=name, title=title, url=url,
                            source="Greenhouse", location=loc, comp="",
                            experience="", posted=(j.get("first_published") or "")[:10]))
        time.sleep(0.4)
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
            if not wanted(title, loc):
                continue
            url = j.get("hostedUrl", "")
            posted = ""
            if j.get("createdAt"):
                posted = dt.datetime.utcfromtimestamp(j["createdAt"] / 1000).date().isoformat()
            out.append(dict(id=jid(url), company=name, title=title, url=url,
                            source="Lever", location=loc, comp="",
                            experience="", posted=posted))
        time.sleep(0.4)
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
            if not wanted(title, loc):
                continue
            url = j.get("jobUrl") or j.get("applyUrl") or ""
            if not url:
                continue
            out.append(dict(id=jid(url), company=name, title=title, url=url,
                            source="Ashby", location=loc, comp="",
                            experience="", posted=(j.get("publishedAt") or "")[:10]))
        time.sleep(0.4)
    return out


# Wellfound listing markup, as of Aug 2026:
#   <a href="/company/SLUG">NAME</a> ... <a href="/jobs/ID-slug">TITLE</a>
#   followed by comp / location / "N years of exp" in sibling text.
WF_JOB = re.compile(r'href="(/jobs/(\d+)-[^"]+)"[^>]*>([^<]{3,120})</a>')
WF_EXP = re.compile(r"(\d+)(?:-\d+)?\s*years?\s*of\s*exp", re.I)
WF_COMP = re.compile(r"(₹[\d,.]+\s*[LK]?\s*[–-]\s*₹?[\d,.]+\s*[LK]?|\$[\d]+k\s*[–-]\s*\$?[\d]+k)")


def from_wellfound() -> list[dict]:
    """Best effort. Wellfound may block CI runners; failure is not fatal."""
    out, seen = [], set()
    for page in WELLFOUND_PAGES:
        html = get(page, timeout=30)
        if not html:
            print(f"  ! wellfound page unavailable: {page}", file=sys.stderr)
            continue
        # Strip tags to a flat text stream we can scan for the metadata that
        # trails each job link.
        for m in WF_JOB.finditer(html):
            path, num, title = m.group(1), m.group(2), m.group(3).strip()
            if num in seen:
                continue
            tail = html[m.end():m.end() + 700]
            flat = re.sub(r"<[^>]+>", " ", tail)
            exp_m = WF_EXP.search(flat)
            years = int(exp_m.group(1)) if exp_m else None
            if years is not None and years > 2:
                continue
            if not wanted(title):
                continue
            seen.add(num)
            comp_m = WF_COMP.search(flat)
            out.append(dict(
                id=jid("https://wellfound.com" + path),
                company="", title=title,
                url="https://wellfound.com" + path,
                source="Wellfound",
                location="Bengaluru / remote India",
                comp=comp_m.group(1) if comp_m else "",
                experience=f"{years} yrs listed" if years is not None else "not stated",
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
