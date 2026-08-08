# Job tracker — 0–2 year backend & AI roles, India

A two-page static site that keeps an up-to-date list of junior backend and AI
engineering roles in India, and tracks which ones I've applied to.

- **`index.html`** — the board. Filter, open a posting, mark it applied.
- **`applied.html`** — every application, with status, resume variant and notes.

A GitHub Action refreshes the listings every morning and commits the result, so
opening the page shows whatever the last run found. Roles that turned up in the
most recent run are badged **new**.

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

`scripts/fetch_jobs.py` keeps a role only if it:

- has a backend / platform / AI / ML / data / founding-flavoured title,
- is **not** senior, staff, principal, lead, manager, architect, or a II/III level,
- is **not** an internship,
- is located in India or remote.

Explicitly junior words — *graduate, new grad, junior, associate, SDE 1,
Engineer I, founding* — override the seniority filter, so "Associate Software
Engineer" survives but "Senior Software Engineer" does not.

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
