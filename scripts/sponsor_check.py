#!/usr/bin/env python3
"""Check employers against the UK Home Office Register of Licensed Sponsors (Workers).

The register is downloaded daily by the GitHub Action
`.github/workflows/sponsor-register.yml` and stored (gzipped) on the
`sponsor-register` branch, because cloud sessions cannot reach gov.uk directly.

Usage:
    python scripts/sponsor_check.py "DECITI HOMES LIMITED" "Addleshaw Goddard"
    python scripts/sponsor_check.py --json companies.json      # ["A", "B"]

Prints a JSON list, one result per company:
    {"company", "status": licensed|possible|not_found|register_unavailable,
     "recruiter": bool, "matches": [{"name","town","rating","route"}], "register_date"}
"""
import csv
import difflib
import gzip
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", ".cache", "sponsors.csv.gz")
CONFIG = os.path.join(ROOT, "config", "profile.json")

SUFFIXES = r"\b(limited|ltd|plc|llp|lp|llc|inc|incorporated|corp|corporation|co|company|uk|u\.k|gb|group|holdings|the|services|solutions|international|europe|t/a|trading as)\b"
RECRUITER_WORDS = ("recruit", "staffing", "talent", "resourcing", "personnel", "search", "headhunt", "outsourcing")


def norm(name):
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(SUFFIXES, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_register():
    if not os.path.exists(CACHE):
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        try:
            subprocess.run(["git", "-C", ROOT, "fetch", "-q", "origin", "sponsor-register"], check=True,
                           capture_output=True, timeout=120)
            blob = subprocess.run(["git", "-C", ROOT, "show", "FETCH_HEAD:sponsors.csv.gz"], check=True,
                                  capture_output=True, timeout=60).stdout
            with open(CACHE, "wb") as f:
                f.write(blob)
            stamp = subprocess.run(["git", "-C", ROOT, "show", "FETCH_HEAD:updated.txt"],
                                   capture_output=True, text=True, timeout=60).stdout.strip()
            with open(CACHE + ".date", "w") as f:
                f.write(stamp)
        except Exception as e:  # noqa: BLE001
            print(f"[sponsor_check] register unavailable: {e}", file=sys.stderr)
            return None, None
    with gzip.open(CACHE, "rt", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    rows = list(csv.DictReader(io.StringIO(text)))
    date = None
    if os.path.exists(CACHE + ".date"):
        with open(CACHE + ".date") as f:
            date = f.read().strip() or None
    return rows, date


def col(row, *names):
    for n in names:
        for k in row:
            if k and k.strip().lower() == n:
                return (row[k] or "").strip()
    return ""


def build_index(rows):
    idx = {}
    for r in rows:
        name = col(r, "organisation name", "organization name", "name")
        idx.setdefault(norm(name), []).append({
            "name": name,
            "town": col(r, "town/city", "town"),
            "rating": col(r, "type & rating", "type and rating", "rating"),
            "route": col(r, "route"),
        })
    return idx


def known_recruiters():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return [x.lower() for x in json.load(f).get("known_recruiters", [])]
    except Exception:  # noqa: BLE001
        return []


def check(companies):
    rows, date = load_register()
    recs = known_recruiters()
    out = []
    idx = build_index(rows) if rows else None
    keys = list(idx) if idx else []
    for c in companies:
        lc = c.lower()
        recruiter = any(w in lc for w in RECRUITER_WORDS) or any(r in lc for r in recs)
        res = {"company": c, "recruiter": recruiter, "matches": [], "register_date": date}
        if idx is None:
            res["status"] = "register_unavailable"
            out.append(res)
            continue
        n = norm(c)
        if n in idx:
            res["status"] = "licensed"
            res["matches"] = idx[n][:5]
        else:
            close = difflib.get_close_matches(n, keys, n=3, cutoff=0.88)
            starts = [k for k in keys if n and len(n) > 4 and (k.startswith(n + " ") or n.startswith(k + " "))][:3]
            cands = list(dict.fromkeys(close + starts))[:4]
            res["status"] = "possible" if cands else "not_found"
            for k in cands:
                res["matches"].extend(idx[k][:1])
        out.append(res)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--json"]:
        with open(args[1], encoding="utf-8") as f:
            args = json.load(f)
    if not args:
        sys.exit(__doc__)
    print(json.dumps(check(args), indent=1))
