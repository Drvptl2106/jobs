# Job Desk

A job-search agent that lives entirely in this GitHub repo, run daily by Claude.

**Website:** https://drvptl2106.github.io/jobs/ (works on any phone; add it to your home screen)

## What it does

Every morning Claude:

1. Reads your **Glassdoor alert emails** and keeps only jobs **posted in the last 24 hours**.
2. Opens each advert and scores it **0-100 against your master CV** (Apply / Maybe / Skip, with matches and gaps).
3. Runs four **UK visa checks** on each job:
   - is the employer on the **Home Office Register of Licensed Sponsors** (Skilled Worker route)?
   - what does the **advert say about sponsorship**?
   - does the **salary** meet the Skilled Worker thresholds (£41,700 general, £33,400 new entrant)?
   - is it a **direct employer or a recruitment agency**?
4. For jobs you approve, writes a **tailored Word CV** (facts from your master CV only), saves it here and **emails it to you**. You read it and apply yourself.
5. Reads "application received", interview and rejection emails and **updates the tracker**.

On the website, tapping **Go ahead**, **Skip**, **I've applied**, **Interview** and so on opens a pre-filled GitHub issue. Tap **Submit new issue**; a GitHub Action records it in `data/jobs.csv` and closes the issue within a minute. Only issues opened by the repo owner count.

## Files

| Path | What |
|---|---|
| `index.html` | The website (GitHub Pages) |
| `config/profile.json` | Your name, email, repo, target roles, visa settings |
| `cv/master_cv.pdf` | Your master CV (you upload it) |
| `data/jobs.csv` | Every job: scores, checks, decisions, status |
| `data/applied.csv` | Just your applications |
| `outputs/cvs/` | Tailored CVs (.docx) |
| `CLAUDE.md` | The exact routine Claude follows |

## Give it to a friend (about 10 minutes)

Your friend needs a GitHub account, a Claude account with Claude Code, and Glassdoor job alerts going to Gmail.

1. **Copy the repo:** on GitHub, **Fork** this repo (or download it and push it to a new repo of their own).
2. **Clear your data:** in their copy, delete `data/jobs.csv`, `data/applied.csv`, `data/jobs.json`, `data/meta.json`, everything in `outputs/cvs/` and `cv/master_cv.*`.
3. **Edit `config/profile.json`:** `name`, `email`, `github.owner` / `repo` / `branch`, `site_url`, `target_roles`, `max_years_experience_required`, and the `visa` section (set `needs_sponsorship` to false if they don't need it).
4. **Upload their CV** to `cv/master_cv.pdf`.
5. **Turn on GitHub Pages:** Settings → Pages → Branch = their branch, folder `/ (root)` → Save.
6. **Turn on Actions** (forks start with them off): Actions tab → enable. Run **Refresh UK sponsor register** once by hand.
7. **Connect Claude:** at claude.ai, connect **Gmail** and **Firecrawl**, and the GitHub repo.
8. **Schedule it:** in Claude Code (claude.ai/code), start a session on their repo and say:
   *"Set up a daily scheduled task at 07:40 UK time that runs the Daily routine in CLAUDE.md, with the Gmail and Firecrawl connectors."*

## Notes

- A licensed sponsor can still decline to sponsor a particular role. Check the role's SOC code going rate too.
- "Glassdoor Est." salaries are estimates.
- This repo is public, so the job list and tailored CVs (name and email, no phone number) are visible to anyone who looks.
