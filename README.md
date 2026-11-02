# Job Desk

A job-search agent for Dhruv Patil, run by Claude in the cloud.

**Open the app:** https://claude.ai/artifact/TvnZz8V79YCEeZiV6RMg4Y (pinned in the claude.ai sidebar; works in the Claude mobile app too)

## What happens every day (07:40 UK time)

1. Claude reads your **Glassdoor alert emails** from the last 24 hours and keeps only jobs **posted within 1 day**.
2. It opens each advert and scores it **0-100 against your master CV** (Apply / Maybe / Skip, with matches and gaps).
3. It runs four **visa checks** on every job:
   - Employer on the **Home Office Register of Licensed Sponsors** (Skilled Worker route, A/B rating)
   - What the **advert says about sponsorship**
   - **Salary vs Skilled Worker thresholds** (£41,700 general, £33,400 new entrant)
   - **Direct employer or recruitment agency**
4. You open the app and tap **Go ahead: tailor my CV** or **Skip**.
5. For approved jobs Claude writes a **tailored Word CV** (facts from your master CV only), saves it in `outputs/cvs/`, and **emails it to you**.
6. You review the CV and apply yourself. Tap **I've applied**, or just wait: when the "application received" email arrives, Claude moves the job to **Applied**.
7. Interview invites, rejections and offers in Gmail update the tracker automatically.

**Scan Gmail now** in the app runs the routine on demand.

## Files

| Path | What it is |
|---|---|
| `cv/master_cv.pdf` | Your master CV (**upload it here**) |
| `data/jobs.csv` | Every job seen, with scores, checks, decisions and status |
| `data/applied.csv` | Applications only (applied / interview / offer / rejected) |
| `outputs/cvs/*.docx` | Tailored CVs (the matching `.json` is the content used) |
| `config/profile.json` | Target roles, max experience, visa thresholds, known recruiters |
| `CLAUDE.md` | The exact routine Claude follows |
| `scripts/` | `sponsor_check.py`, `jobs_store.py`, `make_cv.py` |
| `.github/workflows/sponsor-register.yml` | Downloads the Home Office sponsor register daily |

## Caveats

- A licensed sponsor can still decline to sponsor a particular role; the checks tell you where it's *possible*, not guaranteed. Also check the role's SOC code going rate before applying.
- Glassdoor salaries marked "Glassdoor Est." are estimates.
