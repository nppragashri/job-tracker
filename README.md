# Job tracker — 0–2 year backend & AI roles, India

A two-page static site that keeps an up-to-date list of junior backend and AI
engineering roles in India, and tracks which ones I've applied to.

- **`index.html`** — the board. Filter, open a posting, mark it applied.
- **`applied.html`** — every application, with status, resume variant and notes.

A GitHub Action refreshes the listings every morning and commits the result, so
opening the page shows whatever the last run found. Roles that turned up in the
most recent run are badged **new**.

---

## Refreshing the list

**Right now, before anything is pushed** — run it locally:

```bash
cd job-tracker
python3 scripts/fetch_jobs.py     # fetches, filters, rewrites data/jobs.json
python3 -m http.server 8000       # then open http://localhost:8000
```

The fetch takes two to four minutes; most of that is polite pauses between
requests. It prints each source and how many roles survived the filter, and
names anything it dropped for asking too many years. No dependencies — Python 3
and nothing else.

**Once it's on GitHub** — the Action runs itself every morning at 06:00 IST. To
force a run: **Actions** tab → *Refresh job list* → **Run workflow** → pick
`main` → **Run workflow**. Give it two minutes, then hit **Refresh** on the page.

The **Refresh** button on the board only re-reads `data/jobs.json`. It cannot
scrape live — a page on GitHub Pages isn't allowed to fetch other sites. So the
button shows you the newest committed list; the Action is what actually goes and
looks.

### Loading applications already sent

`data/applications-seed.json` holds the two applications submitted before this
tracker existed — Cartesia and vaiu.ai. On the applications page, click
**Import backup** and choose that file. After that, everything is tracked
through the board.

---

## Getting it live

```bash
cd job-tracker
git init
git add .
git commit -m "Job tracker"
git branch -M main
git remote add origin git@github.com:<your-username>/<repo-name>.git
git push -u origin main
```

Then in the repo on GitHub:

1. **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main`, folder `/ (root)` → Save.
   The site appears at `https://<your-username>.github.io/<repo-name>/` within a minute or two.
2. **Settings → Actions → General** → under *Workflow permissions* choose
   **Read and write permissions** → Save. Without this the daily job can fetch
   listings but cannot commit them.
3. **Actions** tab → *Refresh job list* → **Run workflow**. This does the first
   real fetch instead of waiting for tomorrow morning.

If the repo is private, GitHub Pages needs a paid plan. A public repo is
simplest — nothing here contains personal data. Application history lives in
your browser, not in the repo.

---

## How the refresh actually works

A page served from GitHub Pages cannot fetch wellfound.com or an ATS API
directly — the browser blocks cross-origin requests it hasn't been given
permission for. So the fetching happens server-side:

```
GitHub Action (daily, 06:00 IST)
   → scripts/fetch_jobs.py
       → Greenhouse / Lever / Ashby public job feeds   [reliable]
       → Wellfound listing pages                       [best effort]
   → filters, de-duplicates, preserves first_seen dates
   → writes data/jobs.json + data/archive/YYYY-MM-DD.json
   → commits back to the repo
```

The **Refresh** button on the board re-fetches `data/jobs.json` with a
cache-buster, so it picks up the newest commit immediately. It does not scrape
live — nothing in a static page can.

### Sources

| Source | Method | Reliability |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{token}/jobs` | Documented, unauthenticated. Stable. |
| Lever | `api.lever.co/v0/postings/{token}?mode=json` | Documented, unauthenticated. Stable. |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{token}` | Public posting API. Stable. |
| Wellfound | HTML parsing of role listing pages | **Fragile.** May be blocked from GitHub's runners, and breaks if they change markup. The run logs a warning and continues. |

If Wellfound stops returning results, the ATS feeds still work and the board
keeps updating — you'll just see fewer small startups.

### The filter

Three hard rules. `scripts/fetch_jobs.py` keeps a role only if:

1. **It asks for no more than 2 years.** `MAX_YEARS = 2` at the top of the file.
2. **It is in Bengaluru.** Remote-only postings are dropped even when the company
   is Bengaluru-based. Hyderabad, Mumbai, Delhi and "Remote · Everywhere" are all out.
3. **It is full-time.** Internships are dropped.

Plus the usual shape checks: a backend / platform / AI / ML / data / founding
flavoured title, and not senior, staff, principal, lead, manager, architect, or
a II/III level. Explicitly junior words — *graduate, new grad, junior, associate,
SDE 1, Engineer I, founding* — override the seniority check, so "Associate
Software Engineer" survives but "Senior Software Engineer" does not.

**Years are read from the posting body, not the listing tag.** This matters more
than it sounds. A Wellfound listing showed "Backend Engineer" at a Bengaluru
startup with no experience tag at all; the posting itself asked for 4+ years.
Another listed no band and wanted 5. So:

- Greenhouse is fetched with `?content=true`, Lever with `descriptionPlain` and
  its bullet lists, Ashby with `descriptionPlain`.
- Wellfound listings that state no band get the individual posting opened and
  read, up to `WF_DEEP_CHECK_BUDGET` per run.
- `min_years_required()` takes the **lowest** figure stated anywhere in the text,
  since that is the floor that actually gates an application, and ignores numbers
  that aren't near an experience-flavoured word so company ages and team sizes
  don't count.
- If a posting's requirement cannot be verified, it is left out rather than
  included on the assumption it might be fine.

**A posting that never states a number is dropped**, unless the title itself is
explicitly junior (Engineer I, Associate, Graduate, Founding, SDE-1). This is
`REQUIRE_EXPLICIT_YEARS = True`, and it is the setting that stops senior roles
leaking: plenty of them simply never print a figure, and "no number" used to be
read as "probably fine". If the board ever feels too thin, set it to `False` —
but expect four- and five-year roles back.

To loosen any of this, change `MAX_YEARS`, flip `REQUIRE_EXPLICIT_YEARS`, or
edit `BENGALURU` / `REMOTE_ONLY` near the top of the file.

### Three layers, so nothing gets through by accident

1. **The fetcher** applies the rules and logs every drop with its reason.
2. **`scripts/audit.py`** re-checks the finished `data/jobs.json` and exits
   non-zero if anything violates. The Action runs it right after the fetch, so a
   leak turns the build red instead of quietly appearing on the board.
3. **The page itself** hides any role whose `years_required` exceeds the cap,
   regardless of what the data says, and prints how many it hid. Each card shows
   the requirement as a chip, so you can always see what a role is asking for.

Run the audit by hand any time:

```bash
python3 scripts/audit.py
```

To widen or narrow it, edit `WANT`, `TOO_SENIOR` and `JUNIOR_HINT` near the top
of that file. To add companies, append to the `GREENHOUSE`, `LEVER` or `ASHBY`
lists — the token is the path segment right after the ATS domain in any live
posting URL:

```
job-boards.greenhouse.io/TOKEN/jobs/123   →  Greenhouse
jobs.lever.co/TOKEN/uuid                  →  Lever   (case-sensitive)
jobs.ashbyhq.com/TOKEN/uuid               →  Ashby
```

---

## Application tracking

Marking a role applied stores it in your browser's `localStorage` under the key
`jobtracker.v1`. There is no server and no account — nothing is uploaded.

That means: **clearing site data, switching browser, or moving machine loses the
history.** Use **Export backup** on the applications page now and then, and
**Import backup** to restore or merge it elsewhere. **Export CSV** gives you a
spreadsheet-friendly version.

---

## Running it locally

Opening `index.html` straight off disk won't work — browsers block `fetch` on
`file://` URLs. Serve it instead:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

To regenerate the data by hand:

```bash
python3 scripts/fetch_jobs.py     # the real fetch
python3 scripts/seed.py           # restores the original hand-checked list
```

`scripts/seed.py` is only needed if you want to reset to the starting set — the
17 roles verified by hand on 5 August 2026. Everything else is generated.

No dependencies beyond the Python standard library.

---

## Things worth knowing

- **`first_seen` is preserved across runs.** A role keeps the date it first
  appeared, so the *new* badge means genuinely new, not just "in today's file".
- **Disappeared roles are dropped**, and the count of them shows in
  `data/jobs.json` under `counts.closed_since_last_run`. Dated snapshots live in
  `data/archive/` if you want to look back.
- **Years-of-experience figures are the source's own tags.** Startups in this
  band generally count internship work as experience, which is why 2-year
  listings are still worth applying to.
- **Wellfound needs you logged in** before its Apply button does anything, and
  its desired-salary field is in **USD** — ₹13–15L is roughly $15,500–18,000.
