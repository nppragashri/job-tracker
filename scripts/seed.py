#!/usr/bin/env python3
"""Write the initial data/jobs.json.

Every role below was opened by hand and checked against two hard rules:

  * the posting asks for no more than 2 years of experience, and
  * the job is in Bengaluru — remote-only postings are excluded even when the
    company itself is Bengaluru-based.

Run once. After that the GitHub Action overwrites this file daily and carries
`first_seen` forward, so these roles keep their original first-seen date until
they disappear from the source boards.
"""
import datetime as dt
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE = "2026-08-05"

# company, title, url, source, location, comp, experience, note
SEED = [
    ("NOVA Labs", "Founding Engineer — AI for institutional finance",
     "https://wellfound.com/jobs/4489527-ai-product-engineer", "Wellfound",
     "Onsite or remote · Bengaluru", "", "No experience required",
     "The posting says 'No experience required' outright — the only one found that does. "
     "Agentic AI for financial institutions; stack is Python, TypeScript, PostgreSQL, AWS. "
     "Lists LLM orchestration, RAG and evaluations under bonus points, which is the shape of "
     "the Arize work."),
    ("Xeliport", "Founding Product Engineer (Backend AI Systems)",
     "https://wellfound.com/jobs/4538881-founding-product-engineer-backend-ai-systems", "Wellfound",
     "Onsite or remote · Bengaluru", "", "2 yrs asked",
     "'Backend AI systems' is the literal name of what she already does. AI-native cross-border "
     "commerce platform, hiring fast, posting is a week old."),
    ("Evam Labs", "AI Engineer",
     "https://wellfound.com/jobs/4544682-ai-engineer", "Wellfound",
     "In office · Bengaluru", "", "1 yr asked (band 1–3)",
     "Verified in the posting: '1 to 3 years of professional experience', minimum 6 months "
     "hands-on GenAI. Backend services, APIs and data pipelines for AI applications. Singapore "
     "holding company with the engineering office in Bangalore; founders IIT/IIM/CMU."),
    ("Nexera", "Founding Engineer — answer engine for traders",
     "https://wellfound.com/jobs/2833521-founding-engineer", "Wellfound",
     "In office · Bengaluru", "₹30L – ₹50L + 0.5–5% equity", "1 yr asked",
     "Highest comp and equity in the band by a distance. Posting is six months old — confirm it "
     "is still live before investing effort in the answers."),
    ("Flipr Innovation Labs", "AI Product Engineer",
     "https://wellfound.com/jobs/4493183-ai-product-engineer", "Wellfound",
     "In office · Bengaluru", "₹16L – ₹17L", "1 yr asked",
     "Early-stage AI product work, comp above current, and the experience bar actually matches "
     "where she is."),
    ("Leucine", "Full-Stack Software Engineer",
     "https://wellfound.com/jobs/4523751-full-stack-software-engineer", "Wellfound",
     "In office · Bengaluru", "₹8L – ₹15L", "2 yrs asked",
     "AI for compliant pharma manufacturing, 51-200 people, growth stage. Regulated-domain work "
     "rhymes with the Voice Opt-Out project. Comp band starts below current — treat ₹15L as the "
     "number to aim at, not ₹8L."),
    ("MediaMelon", "SDE (C++, JavaScript, DSA)",
     "https://wellfound.com/jobs/4037889-sde-c-javascript-and-dsa", "Wellfound",
     "In office · Bengaluru", "₹10L – ₹14L", "1 yr asked",
     "Video streaming analytics platform. C++ is on the resume and the bar fits, though this is "
     "more algorithms-and-fundamentals than the systems work she has been doing."),
    ("Canopi", "Software Engineer (Python backend)",
     "https://wellfound.com/jobs/4034395-software-engineer-python-backend", "Wellfound",
     "In office · Bengaluru", "₹8L – ₹14L", "2 yrs asked",
     "Trade finance and supply-chain finance marketplace — fintech backend, the Changejar "
     "lineage. Comp is the weak point."),
]

# Kept out of the board on purpose, with the reason. Shown in the README and in
# the note field so nothing looks like an oversight.
EXCLUDED = [
    ("vaiu.ai", "Full Stack Engineer — Voice AI", "remote-only, no Bengaluru office option"),
    ("Toddle", "Software Engineer, Backend", "remote-only India"),
    ("ITILITE", "Senior Software Engineer — Backend", "titled Senior, band runs 2–5 years"),
    ("zaimler.ai", "Backend Engineer", "posting asks 4+ years — verified in the description"),
    ("100ms", "Backend Software Engineer — Live Video", "no experience band stated and the "
                                                        "posting is 8 months old; unverifiable"),
    ("Kawa Space", "Machine Learning Engineer I", "location listed as India, not Bengaluru"),
    ("senzcraft technologies", "Data Scientist — NLP & Agentic AI", "location listed as India"),
    ("Vobiz AI", "Telephony Engineer", "asks 5 years"),
    ("Cartesia", "Software Engineer, Platform (India)", "asks 3–5 years; already applied 5 Aug"),
]


# The number each posting actually asks for, read from the posting itself.
# scripts/audit.py checks this against MAX_YEARS on every run.
YEARS = {
    "NOVA Labs": 0,          # "No experience required"
    "Xeliport": 2,
    "Evam Labs": 1,          # "1 to 3 years" — floor of 1
    "Nexera": 1,
    "Flipr Innovation Labs": 1,
    "Leucine": 2,
    "MediaMelon": 1,
    "Canopi": 2,
}


def jid(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


jobs = []
for company, title, url, source, loc, comp, exp, note in SEED:
    jobs.append(dict(id=jid(url), company=company, title=title, url=url, source=source,
                     location=loc, comp=comp, years_required=YEARS[company],
                     experience=exp, posted="", note=note,
                     first_seen=DATE, is_new=False))

payload = dict(
    generated_at=f"{DATE}T00:00:00+00:00",
    generated_date=DATE,
    counts=dict(total=len(jobs), new_today=0, closed_since_last_run=0,
                by_source=dict(Wellfound=len(jobs))),
    rules=dict(max_years=2, location="Bengaluru only", remote="excluded",
               internships="excluded"),
    excluded=[dict(company=c, title=t, reason=r) for c, t, r in EXCLUDED],
    note=("Hand-verified seed list: Bengaluru only, nothing asking more than 2 years. "
          "The GitHub Action replaces this daily using the same rules."),
    jobs=jobs,
)

os.makedirs(os.path.join(ROOT, "data", "archive"), exist_ok=True)
for path in (os.path.join(ROOT, "data", "jobs.json"),
             os.path.join(ROOT, "data", "archive", f"{DATE}.json")):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

print(f"seeded {len(jobs)} roles -> data/jobs.json")
print(f"excluded {len(EXCLUDED)} (reasons recorded in the file)")
