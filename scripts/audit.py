#!/usr/bin/env python3
"""Check data/jobs.json against the rules and fail loudly if anything violates.

Runs in the GitHub Action straight after the fetch, so a leak breaks the build
instead of quietly appearing on the board. Also useful by hand:

    python3 scripts/audit.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_jobs import (BENGALURU, IS_INTERNSHIP, JUNIOR_HINT, MAX_YEARS,  # noqa: E402
                        REMOTE_ONLY, TOO_SENIOR, min_years_required)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "jobs.json")


def main() -> int:
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)

    problems = []
    for j in data.get("jobs", []):
        who = f"{j.get('company') or '?'} — {j.get('title')}"

        yrs = j.get("years_required")
        if isinstance(yrs, int) and yrs > MAX_YEARS:
            problems.append(f"{who}: years_required is {yrs}, cap is {MAX_YEARS}")

        # Re-derive from the stored label in case the field was hand-edited.
        from_label = min_years_required(j.get("experience", ""))
        if from_label is not None and from_label > MAX_YEARS:
            problems.append(f"{who}: label says '{j.get('experience')}'")

        loc = j.get("location", "")
        if loc and not BENGALURU.search(loc):
            problems.append(f"{who}: location '{loc}' is not Bengaluru")
        if loc and REMOTE_ONLY.search(loc) and not BENGALURU.search(loc):
            problems.append(f"{who}: remote-only")

        title = j.get("title", "")
        if IS_INTERNSHIP.search(title):
            problems.append(f"{who}: internship")
        if TOO_SENIOR.search(title) and not JUNIOR_HINT.search(title):
            problems.append(f"{who}: senior-level title")

        if yrs is None and not JUNIOR_HINT.search(title):
            problems.append(f"{who}: no experience level and title is not junior")

    total = len(data.get("jobs", []))
    if problems:
        print(f"AUDIT FAILED — {len(problems)} problem(s) across {total} roles:\n")
        for p in problems:
            print(f"  ✗ {p}")
        print("\nFix scripts/fetch_jobs.py, or correct the data, then re-run.")
        return 1

    print(f"Audit passed: {total} roles, all Bengaluru, none above "
          f"{MAX_YEARS} years, no internships.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
