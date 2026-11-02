#!/usr/bin/env python3
"""The job tracker: data/jobs.csv is the source of truth, data/applied.csv is
derived from it, and the web app's database mirrors it.

Commands
  upsert FILE.json        merge a list of job dicts into data/jobs.csv
  import-db DIR           merge app decisions/status from ArtifactData JSON files
  export-db OUTDIR [--all] write one JSON per job changed since last export
                          (for ArtifactData batch writes via file_path)
  pending-cv              list approved jobs that still need a tailored CV
  summary                 counts by status / recommendation
  id URL_OR_JOBLISTINGID  print the canonical job id

Run from the repo root. Python 3.9+, stdlib only.
"""
import csv
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "data", "jobs.csv")
APPLIED = os.path.join(ROOT, "data", "applied.csv")
CONFIG = os.path.join(ROOT, "config", "profile.json")
EXPORT_STATE = os.path.join(ROOT, "data", ".export_state.json")

FIELDS = [
    "id", "source", "title", "company", "location", "salary", "salary_min", "salary_max",
    "posted_age", "first_seen", "email_date", "url", "easy_apply",
    "fit_score", "recommendation", "verdict", "match_reasons", "gaps", "jd_summary",
    "sponsor_register", "sponsor_match", "jd_sponsorship", "salary_check", "recruiter",
    "decision", "status", "cv_file", "cv_url", "cv_emailed_at", "applied_at", "status_updated_at",
    "last_email", "notes", "profile_basis", "updated_at",
]
LIST_FIELDS = {"match_reasons", "gaps"}
# Fields the user controls from the app; never overwritten by an automated upsert
USER_FIELDS = {"decision"}
STATUS_ORDER = ["new", "approved", "cv_ready", "applied", "interview", "offer", "rejected", "withdrawn", "expired", "skipped"]
APPLIED_STATUSES = {"applied", "interview", "offer", "rejected", "withdrawn"}
APPLIED_FIELDS = ["id", "company", "title", "location", "salary", "applied_at", "status",
                  "status_updated_at", "last_email", "sponsor_register", "url", "cv_file", "notes"]


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def read_jobs():
    if not os.path.exists(JOBS):
        return {}
    with open(JOBS, newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def write_jobs(jobs):
    os.makedirs(os.path.dirname(JOBS), exist_ok=True)
    rows = sorted(jobs.values(), key=lambda r: (r.get("first_seen", ""), r.get("fit_score", "")), reverse=True)
    with open(JOBS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    with open(APPLIED, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=APPLIED_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted((r for r in rows if r.get("status") in APPLIED_STATUSES),
                        key=lambda r: r.get("applied_at", ""), reverse=True):
            w.writerow({k: r.get(k, "") for k in APPLIED_FIELDS})


def to_cell(k, v):
    if v is None:
        return ""
    if k in LIST_FIELDS and isinstance(v, (list, tuple)):
        return " | ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def job_id(value):
    m = re.search(r"(?:jl=|jobListingId=)(\d+)", str(value)) or re.fullmatch(r"\d{8,}", str(value))
    if m:
        return "gd-" + (m.group(1) if m.groups() else m.group(0))
    return "ap-" + hashlib.sha1(str(value).lower().encode()).hexdigest()[:10]


def parse_salary(s):
    """'£35k - £38k (Employer Est.)' -> (35000, 38000). Hourly/daily rates are ignored."""
    if not s or re.search(r"(per hour|/hr|an hour|per day|/day)", s, re.I):
        return None, None
    nums = []
    for n, k in re.findall(r"£\s*([\d,.]+)\s*(k?)", s, re.I):
        try:
            v = float(n.replace(",", ""))
        except ValueError:
            continue
        nums.append(int(v * 1000) if k else int(v))
    nums = [n for n in nums if 5000 <= n <= 500000]
    if not nums:
        return None, None
    return min(nums), max(nums)


def salary_check(row, cfg):
    t = cfg["visa"]["salary_thresholds"]
    lo, hi = row.get("salary_min"), row.get("salary_max")
    try:
        lo, hi = int(lo), int(hi)
    except (TypeError, ValueError):
        return "unknown"
    if lo >= t["general"]:
        return "meets_general"
    if hi >= t["general"]:
        return "range_crosses_general"
    if lo >= t["new_entrant"]:
        return "meets_new_entrant"
    if hi >= t["new_entrant"]:
        return "range_crosses_new_entrant"
    return "below_threshold"


def upsert(items):
    cfg = load_config()
    jobs = read_jobs()
    changed = 0
    for it in items:
        it = dict(it)
        jid = it.get("id") or job_id(it.get("url") or f'{it.get("company")}|{it.get("title")}')
        it["id"] = jid
        row = jobs.get(jid, {})
        is_new = not row
        for k, v in it.items():
            if k not in FIELDS:
                continue
            if k in USER_FIELDS and row.get(k) and not it.get("_force"):
                continue
            row[k] = to_cell(k, v)
        if is_new:
            row.setdefault("first_seen", now()[:10])
            row.setdefault("decision", "pending")
            row.setdefault("status", "new")
        if row.get("salary") and not row.get("salary_min"):
            lo, hi = parse_salary(row["salary"])
            row["salary_min"], row["salary_max"] = (lo or ""), (hi or "")
        row["salary_check"] = salary_check(row, cfg)
        if row.get("status") and "status" in it:
            row["status_updated_at"] = it.get("status_updated_at") or now()
        row["updated_at"] = now()
        jobs[jid] = row
        changed += 1
    write_jobs(jobs)
    print(f"upserted {changed} job(s); total {len(jobs)}")


def import_db(directory):
    """Merge fields the app writes (decision, status, applied_at, notes)."""
    jobs = read_jobs()
    n = 0
    for p in glob.glob(os.path.join(directory, "**", "*.json"), recursive=True):
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        data = doc.get("data", doc) if isinstance(doc, dict) else {}
        jid = data.get("id") or os.path.splitext(os.path.basename(p))[0]
        if jid not in jobs:
            continue
        row = jobs[jid]
        for k in ("decision", "status", "applied_at", "notes"):
            v = data.get(k)
            if v not in (None, "") and str(v) != row.get(k, ""):
                # never move status backwards from what the tracker already knows,
                # except when the user explicitly skips / re-opens
                if k == "status" and row.get(k) in APPLIED_STATUSES and v in ("new", "approved", "cv_ready"):
                    continue
                row[k] = to_cell(k, v)
                if k == "status":
                    row["status_updated_at"] = data.get("status_updated_at") or now()
                row["updated_at"] = now()
                n += 1
        if row.get("decision") == "approved" and row.get("status") == "new":
            row["status"] = "approved"
        if row.get("decision") == "skipped" and row.get("status") in ("new", "approved"):
            row["status"] = "skipped"
    write_jobs(jobs)
    print(f"imported {n} field change(s) from app")


def to_doc(row):
    doc = {}
    for k in FIELDS:
        v = row.get(k, "")
        if k in LIST_FIELDS:
            v = [x.strip() for x in v.split("|") if x.strip()] if v else []
        elif k in ("fit_score", "salary_min", "salary_max"):
            try:
                v = int(float(v))
            except (TypeError, ValueError):
                v = None
        elif k in ("easy_apply", "recruiter"):
            v = v == "yes"
        elif k == "sponsor_match" and v.startswith("{"):
            try:
                v = json.loads(v)
            except ValueError:
                pass
        doc[k] = v
    return doc


def export_db(outdir, everything=False):
    jobs = read_jobs()
    state = {}
    if os.path.exists(EXPORT_STATE) and not everything:
        with open(EXPORT_STATE, encoding="utf-8") as f:
            state = json.load(f)
    os.makedirs(outdir, exist_ok=True)
    written = []
    for jid, row in jobs.items():
        doc = to_doc(row)
        h = hashlib.sha1(json.dumps(doc, sort_keys=True).encode()).hexdigest()
        if state.get(jid) == h:
            continue
        path = os.path.join(outdir, f"{jid}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        state[jid] = h
        written.append(path)
    with open(EXPORT_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f)
    print(json.dumps(written, indent=0))


def pending_cv():
    out = [{"id": r["id"], "company": r["company"], "title": r["title"], "url": r["url"]}
           for r in read_jobs().values()
           if r.get("decision") == "approved" and not r.get("cv_file")]
    print(json.dumps(out, indent=1))


def summary():
    jobs = read_jobs().values()
    by = {}
    for r in jobs:
        by.setdefault(r.get("status") or "new", 0)
        by[r.get("status") or "new"] += 1
    print(json.dumps({"total": len(jobs), "by_status": by}, indent=1))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "upsert":
        with open(a[1], encoding="utf-8") as f:
            data = json.load(f)
        upsert(data if isinstance(data, list) else [data])
    elif cmd == "import-db":
        import_db(a[1])
    elif cmd == "export-db":
        export_db(a[1], "--all" in a)
    elif cmd == "pending-cv":
        pending_cv()
    elif cmd == "summary":
        summary()
    elif cmd == "id":
        print(job_id(a[1]))
    else:
        sys.exit(__doc__)
