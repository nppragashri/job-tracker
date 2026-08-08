#!/usr/bin/env python3
"""Write the initial data/jobs.json from the roles verified by hand on 5 Aug 2026.

Run once. After that the GitHub Action overwrites this file daily and carries
`first_seen` forward, so nothing here is lost — these roles keep their original
first-seen date until they disappear from the source boards.
"""
import datetime as dt
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE = "2026-08-05"

# company, title, url, source, location, comp, experience, note
SEED = [
    ("vaiu.ai", "Full Stack Engineer — Voice AI",
     "https://wellfound.com/jobs/3940248-full-stack-engineer-voice-ai", "Wellfound",
     "Remote only · India", "", "2 yrs listed",
     "Closest match found anywhere. Their bullets: build voice AI agents handling real-time, "
     "low-latency conversations at scale, and orchestrate LLMs (OpenAI, Gemini, Anthropic) as "
     "the reasoning backbone. That is the Sense job description."),
    ("NOVA Labs", "Founding Engineer — AI for institutional finance",
     "https://wellfound.com/jobs/4489527-ai-product-engineer", "Wellfound",
     "Bengaluru / Mumbai / remote", "", "No experience required",
     "The posting says 'No experience required' outright. Agentic AI for financial institutions; "
     "stack is Python, TypeScript, PostgreSQL, AWS. Lists LLM orchestration, RAG and evaluations "
     "under bonus points."),
    ("Xeliport", "Founding Product Engineer (Backend AI Systems)",
     "https://wellfound.com/jobs/4538881-founding-product-engineer-backend-ai-systems", "Wellfound",
     "Bengaluru / remote", "", "2 yrs listed",
     "'Backend AI systems' is the literal name of what she already does. AI-native cross-border "
     "commerce platform, hiring fast."),
    ("Nexera", "Founding Engineer — answer engine for traders",
     "https://wellfound.com/jobs/2833521-founding-engineer", "Wellfound",
     "In office · Bengaluru", "₹30L – ₹50L + 0.5–5% equity", "1 yr listed",
     "Highest comp and equity in the band by a distance. Posting is old — confirm it is live "
     "before investing effort."),
    ("Flipr Innovation Labs", "AI Product Engineer",
     "https://wellfound.com/jobs/4493183-ai-product-engineer", "Wellfound",
     "In office · Bengaluru", "₹16L – ₹17L", "1 yr listed",
     "Early-stage AI product work, comp above current, and the experience bar actually matches."),
    ("Evam Labs", "AI Engineer",
     "https://wellfound.com/jobs/4544682-ai-engineer", "Wellfound",
     "In office · Bengaluru", "", "not stated",
     "No years requirement stated at all, which is unusual and helps. Venture lab building "
     "enterprise AI products."),
    ("ITILITE", "Software Engineer — Backend (Python, B2B SaaS/AI)",
     "https://wellfound.com/jobs/4446034-senior-software-engineer-backend-python-b2b-saas-ai-2-5-years",
     "Wellfound", "In office · Bengaluru", "₹25L – ₹30L", "posting says 2–5 yrs",
     "Titled Senior but the posting opens the band at two years. Growth stage, top investors, "
     "roughly double current comp."),
    ("Toddle", "Software Engineer, Backend",
     "https://wellfound.com/jobs/4399843-software-engineer-backend", "Wellfound",
     "Remote only · India", "₹14L – ₹18L", "2 yrs listed",
     "Most stable company in the band, 201-500 people, fully remote, comp above current."),
    ("100ms", "Backend Software Engineer — Live Video",
     "https://wellfound.com/jobs/3373265-backend-software-engineer-live-video", "Wellfound",
     "In office · Bengaluru", "₹15L – ₹30L + equity", "not stated",
     "Live video infrastructure — WebRTC, already on her skills list. Posting is old; check "
     "their own careers page too."),
    ("Kawa Space", "Machine Learning Engineer I",
     "https://wellfound.com/jobs/2999817-machine-learning-engineer-i", "Wellfound",
     "India", "₹20L", "level I role",
     "An explicit Engineer I title paying above current comp, which is rare. ELINT/SIGINT from "
     "space; ML side lines up with the IEEE risk-modelling work."),
    ("Leucine", "Full-Stack Software Engineer",
     "https://wellfound.com/jobs/4523751-full-stack-software-engineer", "Wellfound",
     "In office · Bengaluru", "₹8L – ₹15L", "2 yrs listed",
     "AI for compliant pharma manufacturing. Regulated-domain work rhymes with the Voice Opt-Out "
     "project. Comp band starts low — treat it as a floor."),
    ("MediaMelon", "SDE (C++, JavaScript, DSA)",
     "https://wellfound.com/jobs/4037889-sde-c-javascript-and-dsa", "Wellfound",
     "In office · Bengaluru", "₹10L – ₹14L", "1 yr listed",
     "Video streaming analytics. C++ is on the resume and the bar fits, but this is more "
     "algorithms than systems."),
    ("Canopi", "Software Engineer (Python backend)",
     "https://wellfound.com/jobs/4034395-software-engineer-python-backend", "Wellfound",
     "In office · Bengaluru", "₹8L – ₹14L", "2 yrs listed",
     "Trade finance marketplace — fintech backend, the Changejar lineage. Comp is the weak point."),
    ("senzcraft technologies", "Data Scientist — NLP & Agentic AI",
     "https://wellfound.com/jobs/3162328-data-scientist-with-nlp-agentic-ai", "Wellfound",
     "India", "₹10L – ₹18L", "not stated",
     "NLP plus agentic AI — the overlap between the Sense agent work and the ML projects."),
    ("zaimler.ai", "Backend Engineer",
     "https://wellfound.com/jobs/3716879-backend-engineer", "Wellfound",
     "Bengaluru", "", "not stated",
     "Tiny team, actively hiring, no stated years requirement. Low information — worth a quick "
     "application rather than a crafted one."),
    ("Vobiz AI", "Telephony Engineer  [stretch — asks 5 yrs]",
     "https://wellfound.com/jobs/4473381-telephony-engineer", "Wellfound",
     "In office · Bengaluru", "", "5 yrs listed",
     "Outside the filter, kept deliberately. 'Telephony infrastructure built for the AI era' — the "
     "company most likely in Bengaluru to understand what the Voice Stage work involved."),
    ("Cartesia", "Software Engineer, Platform (India)",
     "https://jobs.ashbyhq.com/cartesia/9d9c6cc0-218c-4fd4-a478-3e4b37de1d76", "Ashby",
     "Bangalore", "₹70L – ₹90L + equity", "asks 3–5 yrs",
     "Already submitted on 5 Aug 2026."),
]


def jid(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


jobs = []
for company, title, url, source, loc, comp, exp, note in SEED:
    jobs.append(dict(id=jid(url), company=company, title=title, url=url, source=source,
                     location=loc, comp=comp, experience=exp, posted="", note=note,
                     first_seen=DATE, is_new=False))

payload = dict(
    generated_at=f"{DATE}T00:00:00+00:00",
    generated_date=DATE,
    counts=dict(total=len(jobs), new_today=0, closed_since_last_run=0,
                by_source=dict(Wellfound=len(jobs) - 1, Ashby=1)),
    note="Hand-verified seed list. The GitHub Action replaces this daily.",
    jobs=jobs,
)

os.makedirs(os.path.join(ROOT, "data", "archive"), exist_ok=True)
for path in (os.path.join(ROOT, "data", "jobs.json"),
             os.path.join(ROOT, "data", "archive", f"{DATE}.json")):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

print(f"seeded {len(jobs)} roles -> data/jobs.json")
