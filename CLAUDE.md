# Job Desk — agent instructions

This repo is Dhruv Patil's job-search agent. Claude (you) finds jobs in Gmail, scores them
against Dhruv's master CV, checks UK visa sponsorship, writes tailored Word CVs for jobs he
approves, and tracks applications. Dhruv applies himself; **never apply, and never email
anyone except `dhruvpatil979@gmail.com`.**

## Constants

| Thing | Value |
|---|---|
| Data branch (commit + push here) | `claude/ecstatic-bardeen-eu42vz` |
| Job Desk app (artifact) | https://claude.ai/artifact/TvnZz8V79YCEeZiV6RMg4Y |
| App database collections | `jobs/<job-id>` (one doc per job), `meta/status` |
| Scheduled task id | `trig_01KvhirXJELqob9k8JFahYbC` (daily 07:40 Europe/London) |
| Dhruv's email | dhruvpatil979@gmail.com |
| Preferences + visa thresholds | `config/profile.json` |
| Master CV | `cv/master_cv.pdf` (or `.docx`) → text in `cv/master_cv.md` |
| Tracker | `data/jobs.csv` (all jobs), `data/applied.csv` (derived) |
| Tailored CVs | `outputs/cvs/` |

Tools you need: Gmail connector, Firecrawl connector, `Artifact` / `ArtifactData`, Bash with
python3, git. Network: gov.uk and glassdoor are blocked in the container; the sponsor register
comes from the `sponsor-register` branch (refreshed daily by `.github/workflows/sponsor-register.yml`)
and adverts come through Firecrawl.

If the Gmail tools are missing, stop: write `meta/status.notice` = "The daily scan couldn't reach
Gmail. Add the Gmail and Firecrawl connectors to the 'Job Desk daily scan' scheduled task." and finish.

## Daily routine

Work from the repo root. Keep a scratch dir at `data/.dbsync/` (git-ignored).

### 1. Sync the repo
`git fetch origin claude/ecstatic-bardeen-eu42vz && git checkout claude/ecstatic-bardeen-eu42vz && git pull --rebase origin claude/ecstatic-bardeen-eu42vz`

### 2. Master CV
- If `cv/master_cv.pdf` or `cv/master_cv.docx` exists and `cv/master_cv.md` is missing or older
  (compare `git log -1 --format=%ct -- <file>`): extract text (`pdftotext -layout`, or python-docx),
  then write a clean `cv/master_cv.md` (sections: contact, profile, skills, experience with every
  bullet, education, projects, certifications, languages, visa status if stated). Keep every fact;
  invent nothing. Then re-score every job whose `profile_basis` is `provisional` and status is
  `new`/`approved` (step 5) and set `profile_basis` to `master`.
- If no CV file exists: score with what is known (titles of past applications, Newcastle University
  master's), set `profile_basis: provisional`, and keep the "upload your CV" notice in `meta/status`.

### 3. Pull decisions from the app
1. `ArtifactData list` collection `jobs`, `query.limit` 1000, `out_dir` `data/.dbsync/in`.
   Note each document's `version` from the result (needed for writes in step 9).
2. `python3 scripts/jobs_store.py import-db data/.dbsync/in` (merges Go ahead / Skip / I've applied /
   status changes into `data/jobs.csv`; approved → status `approved`, skipped → `skipped`).

### 4. Find new jobs (posted within 24 hours)
1. Gmail `search_threads` query `from:glassdoor.com newer_than:1d`. Read each thread once with
   `get_thread` `PLAIN_TEXT`.
2. Each listing is a markdown link `[| ... Company 3.7 ★ || Title || Location || £Xk - £Yk (…) || Easy Apply || | AGE |](URL)`.
   The URL holds `jobListingId=<digits>` and `utm_content=…-age<N>d-…` or `…-agejp-…` (just posted).
3. Keep a listing only if its age is "Just posted", `<N>h`, `24h` or `1d` (age ≤ 1 day). "Jobs for you"
   emails without an age chip: use the `age<N>d` in the URL. Drop anything older.
4. Job id = `gd-<jobListingId>`; skip ids already in `data/jobs.csv`. Canonical URL:
   `https://www.glassdoor.co.uk/job-listing/j?jl=<jobListingId>`.

### 5. Read the advert and score it
- Firecrawl `firecrawl_scrape` the canonical URL with `formats: ["markdown"]`, `onlyMainContent: true`,
  `timeout: 45000`. The advert text sits between "Sign in to apply"/"Apply now" and "Show more" /
  "## Base pay". If it fails, score from the title and mark `jd_summary` "Advert could not be loaded".
- Score 0-100 against `cv/master_cv.md` and `config/profile.json`:
  title/role fit 25 · skills & tools 30 · experience level 20 (heavy penalty when the advert asks for
  more than `max_years_experience_required`) · domain 10 · location/practicalities 5 · visa feasibility 10.
- `recommendation`: `apply` ≥ 70, `maybe` 50-69, `skip` < 50. Force `skip` when the advert needs
  5+ years, or says it cannot sponsor (Dhruv needs sponsorship).
- Fill: `verdict` (1-2 plain sentences), `match_reasons` (≤3, each tied to a CV fact),
  `gaps` (≤3), `jd_summary` (≤80 words, include how to apply and work pattern).
- `jd_sponsorship`: `offers` (mentions sponsorship / sponsor licence), `no_sponsorship`,
  `right_to_work_required` ("must already have the right to work", "no sponsorship"), or `silent`.

### 6. Sponsorship checks
- `python3 scripts/sponsor_check.py "<Company A>" "<Company B>" …` → `sponsor_register`
  (`licensed` / `licensed_other_route` / `possible` / `not_found`), `recruiter`, `sponsor_match`
  (copy the first match as `{name, town, rating, route}`).
- Recruiter posting that names the end client in the advert: `python3 scripts/sponsor_check.py --grep "<client>"`
  and use the client's Skilled Worker entry, adding " (end client)" to `sponsor_match.name`.
- `salary_check` is computed automatically from `salary` by `jobs_store.py`
  (general £41,700; new entrant £33,400 — values in `config/profile.json`).

### 7. Save
Write the new/updated jobs as a JSON list to `data/.dbsync/new.json` (fields as in
`scripts/jobs_store.py` FIELDS; `source: "glassdoor"`, `email_date`, `posted_age`, `easy_apply`, …) and run
`python3 scripts/jobs_store.py upsert data/.dbsync/new.json`.

### 8. Tailored CVs (jobs Dhruv approved)
For each item from `python3 scripts/jobs_store.py pending-cv`:
1. Re-read the advert (step 5 scrape) and `cv/master_cv.md`.
2. Write `outputs/cvs/<YYYY-MM-DD>_<Company>_<Title>.json` (ASCII, hyphens for spaces) in the
   shape documented at the top of `scripts/make_cv.py`. Rules:
   - Only facts from the master CV. Never invent employers, dates, grades, tools or numbers.
   - Mirror the advert's keywords where they are true for Dhruv; lead with the most relevant
     experience and projects; cut what doesn't help this job. One page if possible, two at most.
   - UK spelling, no photo, no date of birth. Contact line from `config/profile.json`.
   - Headline = the job's title family (e.g. "Business Analyst"). Summary = 3 sentences aimed at this job.
3. `python3 scripts/make_cv.py <json> <same name>.docx`.
4. Commit and push (step 10) so the file exists on GitHub, then set
   `cv_url` = `https://github.com/Drvptl2106/jobs/blob/claude/ecstatic-bardeen-eu42vz/outputs/cvs/<file>.docx`.
5. Email it with Gmail `send_message` to dhruvpatil979@gmail.com, subject
   `Tailored CV: <Title> at <Company>`, `htmlBody` with: link to the advert, how to apply,
   3 bullet points on what was tailored, the four sponsorship checks, and any gaps to address in a
   cover letter. Attach the .docx (`base64 -w0 <file>`, mimeType
   `application/vnd.openxmlformats-officedocument.wordprocessingml.document`).
6. Upsert `status: cv_ready`, `cv_file`, `cv_url`, `cv_emailed_at`.

### 9. Track applications
1. Gmail search (MINIMAL view first):
   `newer_than:2d -from:me -from:noreply@glassdoor.com -category:promotions ("thank you for applying" OR "application received" OR "received your application" OR "application was sent" OR "application submitted" OR "your application" OR "Indeed Application" OR interview OR assessment OR "unfortunately")`
2. Classify each relevant email: confirmation → `applied` (set `applied_at`); interview / assessment
   / phone screen invite → `interview`; rejection → `rejected`; offer → `offer`. Ignore bank, visa
   and newsletter mail.
3. Match to an existing job by company + title (case-insensitive, loose). If none, add a row with
   `id` `ap-<company>-<title-initials>-<MMDD>`, `source: gmail`, `decision: approved`.
4. Set `last_email` to a short note like "Interview invite (3 Nov)". Never move a job backwards
   (e.g. from `interview` to `applied`).
5. Expire stale reviews: status `new` with `first_seen` more than 3 days ago → `status: expired`.

### 10. Sync the app and GitHub
1. `python3 scripts/jobs_store.py export-db data/.dbsync/out` → list of changed job files.
2. `ArtifactData batch` (≤50 writes per call): `{op: "set", collection: "jobs", doc_id, file_path}`
   with `if_version` from step 3 for documents that already exist (omit it for new ones).
   If a pinned write fails because Dhruv changed the doc meanwhile, re-run steps 3 and 10.
3. `ArtifactData set` `meta/status` (read it first for its version): `last_scan` (now, ISO),
   `register_date` (from sponsor_check output), `trigger_id`, `repo_url`, `profile_basis`, `notice`
   (empty string when nothing needs Dhruv's attention).
4. Prune: delete app docs whose status is `skipped`/`expired` and `first_seen` > 30 days ago
   (the CSV keeps them).
5. `git add data/jobs.csv data/applied.csv outputs cv && git commit -m "Job Desk scan <date>: <n> new, <m> CVs, <k> updates" && git push origin claude/ecstatic-bardeen-eu42vz`
   (retry push up to 4 times with backoff on network errors; on rejection, `git pull --rebase` and retry).

### 11. Report
Finish with 3-5 lines: new jobs found (and how many were older than 24h and dropped), top picks with
scores, CVs written, application status changes, anything Dhruv must do.

## When Dhruv asks in chat
- "Go ahead with <job>" → set `decision: approved` for that job and run step 8 for it.
- "I applied to <job>" → status `applied`, `applied_at` today, then step 10.
- "Rescore" → step 2's re-score for all open jobs.
Always finish with step 10 so the app, the CSVs and GitHub agree.
