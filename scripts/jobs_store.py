#!/usr/bin/env python3
"""The job tracker. data/jobs.csv is the source of truth; data/applied.csv and
data/jobs.json (read by the website, index.html) are regenerated on every write.

Commands
  upsert FILE.json        merge a list of job dicts into data/jobs.csv
  act VERB ID[,ID...]     apply a button press / swipe batch from the website (via a GitHub issue):
                          approve | skip | applied | interview | offer | rejected | withdrawn | reopen
  remove ID ...           delete jobs from the tracker entirely
  meta KEY=VALUE ...      update data/meta.json (last_scan, register_date, notice, profile_basis)
  expire [R] [C]          expire jobs unreviewed for R days and CV-ready jobs not applied to within C days
                          (defaults: review_window_days / cv_apply_window_days in config/profile.json)
  pending-cv              list approved jobs that still need a tailored CV
  summary                 counts by status
  id URL_OR_JOBLISTINGID  print the canonical job id

Run from the repo root. Python 3.9+, stdlib only.
"""
import csv
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
JOBS_JSON = os.path.join(ROOT, "data", "jobs.json")
META = os.path.join(ROOT, "data", "meta.json")

FIELDS = [
    "id", "source", "title", "company", "location", "salary", "salary_min", "salary_max",
    "posted_age", "first_seen", "email_date", "url", "easy_apply",
    "fit_score", "score_breakdown", "confidence", "recommendation", "verdict", "match_reasons", "gaps", "jd_summary", "jd_full",
    "sponsor_register", "sponsor_match", "jd_sponsorship", "salary_check", "recruiter",
    "decision", "decided_at", "status", "cv_file", "cv_url", "cv_emailed_at", "applied_at", "status_updated_at",
    "last_email", "notes", "profile_basis", "updated_at",
]
LIST_FIELDS = {"match_reasons", "gaps"}
# Fields the user controls from the app; never overwritten by an automated upsert
USER_FIELDS = {"decision"}
STATUS_ORDER = ["new", "approved", "cv_ready", "applied", "interview", "offer", "rejected", "withdrawn", "expired", "skipped"]
APPLIED_STATUSES = {"applied", "interview", "offer", "rejected", "withdrawn"}
# Tracker columns, exactly as Dhruv asked for them
TRACKER_COLUMNS = ["Sr No", "Company Name", "Role", "Location", "Applied On", "Pay", "CV Application", "Status"]


def xl_safe(v):
    """Stop spreadsheet formula injection: a job title like '=HYPERLINK(...)' must open as text."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


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
    site = ""
    try:
        site = load_config().get("site_url", "")
    except Exception:  # noqa: BLE001
        pass
    applied = sorted((r for r in rows if r.get("status") in APPLIED_STATUSES),
                     key=lambda r: (r.get("applied_at") or r.get("status_updated_at") or "")[:10])
    with open(APPLIED, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(TRACKER_COLUMNS)
        for i, r in enumerate(applied, 1):
            cv = r.get("cv_url", "")
            if cv and not cv.startswith("http"):
                cv = site.rstrip("/") + "/" + cv.lstrip("/")
            w.writerow([xl_safe(x) for x in (
                i, r.get("company", ""), r.get("title", ""), r.get("location", ""),
                (r.get("applied_at") or "")[:10], r.get("salary", ""), cv,
                (r.get("status") or "").capitalize())])
    with open(JOBS_JSON, "w", encoding="utf-8") as f:
        json.dump([to_doc(r) for r in rows], f, ensure_ascii=False, indent=0)


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
    return "ap-" + hashlib.sha1(str(value).lower().encode(), usedforsecurity=False).hexdigest()[:10]


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
            row["status_updated_at"] = it.get("status_updated_at") or it.get("applied_at") or now()
        row["updated_at"] = now()
        jobs[jid] = row
        changed += 1
    write_jobs(jobs)
    print(f"upserted {changed} job(s); total {len(jobs)}")


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
        elif k == "score_breakdown":
            try:
                v = json.loads(v) if v else []
            except ValueError:
                v = []
        elif k == "sponsor_match" and v.startswith("{"):
            try:
                v = json.loads(v)
            except ValueError:
                pass
        doc[k] = v
    return doc


VERBS = {
    "approve": {"decision": "approved", "status": "approved"},
    "skip": {"decision": "skipped", "status": "skipped"},
    "reopen": {"decision": "pending", "status": "new"},
    "applied": {"status": "applied"},
    "interview": {"status": "interview"},
    "offer": {"status": "offer"},
    "rejected": {"status": "rejected"},
    "withdrawn": {"status": "withdrawn"},
}


def act(verb, ids):
    """Apply website button presses (one id or a comma-separated batch). Returns a short message."""
    verb = verb.lower()
    if verb not in VERBS:
        raise ValueError(f"unknown action '{verb}'")
    id_list = [i.strip() for i in str(ids).split(",") if i.strip()]
    if not id_list or len(id_list) > 100:
        raise ValueError("expected 1-100 job ids")
    for jid in id_list:
        if not re.fullmatch(r"[a-z]{2}-[A-Za-z0-9-]{1,80}", jid):
            raise ValueError(f"bad job id '{jid}'")
    jobs = read_jobs()
    done, missing = [], []
    for jid in id_list:
        if jid not in jobs:
            missing.append(jid)
            continue
        done.append(_act_one(jobs[jid], verb))
    if not done:
        raise ValueError(f"no job with id {', '.join(missing)}")
    write_jobs(jobs)
    msg = done[0] if len(done) == 1 else f"{verb}: {len(done)} jobs"
    return msg + (f" ({len(missing)} id(s) not found)" if missing else "")


def _act_one(row, verb):
    ts = now()
    for k, v in VERBS[verb].items():
        row[k] = v
    if "decision" in VERBS[verb]:
        row["decided_at"] = ts
    if verb == "approve" and row.get("cv_file"):
        row["status"] = "cv_ready"
    if verb == "applied" and not row.get("applied_at"):
        row["applied_at"] = ts
    if "status" in VERBS[verb]:
        row["status_updated_at"] = ts
    row["updated_at"] = ts
    return f"{verb}: {row.get('title')} at {row.get('company')} -> status {row['status']}"


def remove(ids):
    jobs = read_jobs()
    n = sum(1 for i in ids if jobs.pop(i, None) is not None)
    write_jobs(jobs)
    print(f"removed {n} job(s); total {len(jobs)}")


def set_meta(pairs):
    meta = {}
    if os.path.exists(META):
        with open(META, encoding="utf-8") as f:
            meta = json.load(f)
    for p in pairs:
        k, _, v = p.partition("=")
        meta[k] = v
    with open(META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(json.dumps(meta, indent=1))


def _latest_day(*dates):
    days = []
    for d in dates:
        try:
            days.append(datetime.fromisoformat(str(d)[:10]).date().toordinal())
        except ValueError:
            pass
    return max(days) if days else None


def expire(review_days=None, cv_days=None):
    """Move stale jobs to Skipped (status 'expired'):
    - waiting for review longer than review_window_days (default 1) after being found/restored
    - CV ready but not marked applied within cv_apply_window_days (default 3)"""
    cfg = load_config()
    review_days = int(review_days if review_days is not None else cfg.get("review_window_days", 1))
    cv_days = int(cv_days if cv_days is not None else cfg.get("cv_apply_window_days", 3))
    today = datetime.now(timezone.utc).date().toordinal()
    jobs, n_review, n_cv = read_jobs(), 0, 0
    for r in jobs.values():
        if r.get("status") == "new" and r.get("decision") in ("", "pending"):
            day = _latest_day(r.get("first_seen", ""), r.get("decided_at", ""))
            if day is not None and day < today - review_days:
                r["status"], r["status_updated_at"], n_review = "expired", now(), n_review + 1
        elif r.get("status") == "cv_ready":
            day = _latest_day(r.get("cv_emailed_at") or r.get("status_updated_at", ""), r.get("decided_at", ""))
            if day is not None and day <= today - cv_days:
                r["status"], r["status_updated_at"], n_cv = "expired", now(), n_cv + 1
                r["notes"] = (r.get("notes", "") + " CV ready but not marked applied in time.").strip()
    write_jobs(jobs)
    print(f"expired {n_review} unreviewed job(s) and {n_cv} approved job(s) not applied to")


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
    elif cmd == "act":
        try:
            print(act(a[1], a[2]))
        except (ValueError, IndexError) as e:
            sys.exit(f"error: {e}")
    elif cmd == "remove":
        remove(a[1:])
    elif cmd == "meta":
        set_meta(a[1:])
    elif cmd == "expire":
        expire(*a[1:3])
    elif cmd == "pending-cv":
        pending_cv()
    elif cmd == "summary":
        summary()
    elif cmd == "id":
        print(job_id(a[1]))
    else:
        sys.exit(__doc__)
