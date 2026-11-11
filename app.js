"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  const state = { local: load("jd-local", { skip: {}, restore: {} }), tfilter: "all", jobs: [], meta: {}, cfg: {}, view: load("jd-view", "jobs"), filters: new Set(), q: "", pending: load("jd-pending", {}), tab: "analysis" };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m, undo) => {
    const t = $("#toast"); t.innerHTML = `<span>${esc(m)}</span>${undo ? `<button type="button">Undo</button>` : ""}`; t.hidden = false;
    if (undo) t.querySelector("button").onclick = () => { undo(); t.hidden = true; };
    clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), undo ? 6000 : 4200);
  };
  const time12 = (iso) => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true }).replace(/\b(am|pm)\b/i, (x) => x.toUpperCase()); };
  const fmtDate = (iso) => { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); };
  // Only allow http(s) links and same-site relative paths; anything else (javascript:, data:, ...) becomes inert.
  const safeUrl = (u) => { const v = String(u ?? "").trim(); return /^https?:\/\//i.test(v) || /^[A-Za-z0-9_][A-Za-z0-9_./%-]*$/.test(v) ? v : "#"; };
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const isFresh = (a) => /just posted|found on employer site|^\s*(\d{1,2}h|24h|[123]d)\s*$/i.test(a || "");
  const APPLIED = ["applied", "interview", "offer", "rejected", "withdrawn"];
  // A job waiting for review longer than review_window_days after it was found counts as expired, even before the next scan marks it.
  const daysSince = (d) => { const t = Date.parse(String(d || "").slice(0, 10)); return isNaN(t) ? 0 : Math.floor((Date.now() - t) / 864e5); };
  const reviewWindow = () => num(state.cfg.review_window_days) || 1;
  const isStale = (j) => (j.status === "new" || !j.status) && (!j.decision || j.decision === "pending") && Math.min(daysSince(j.first_seen), j.decided_at ? daysSince(j.decided_at) : Infinity) > reviewWindow();
  // Approved job whose CV has been ready longer than cv_apply_window_days without being marked applied.
  const cvWindow = () => num(state.cfg.cv_apply_window_days) || 3;
  const cvAge = (j) => Math.min(daysSince(j.cv_emailed_at || j.status_updated_at), j.decided_at ? daysSince(j.decided_at) : Infinity);
  const isStaleCv = (j) => j.status === "cv_ready" && cvAge(j) >= cvWindow();
  const isSkipped = (j) => j.decision === "skipped" || j.status === "skipped" || j.status === "expired" || isStale(j) || isStaleCv(j);
  // Live job age: the alert email's date minus the age Glassdoor showed in it ("Just posted", "5h", "1d"...).
  function postedDaysAgo(j) {
    const t = Date.parse(j.email_date || j.first_seen || ""); if (isNaN(t)) return null;
    const a = String(j.posted_age || "").toLowerCase(), m = a.match(/(\d+)\s*d/);
    const offset = m ? Number(m[1]) : 0;
    return Math.max(0, Math.floor((Date.now() - t) / 864e5) + offset);
  }
  const ageLabel = (j) => { const d = postedDaysAgo(j); return d == null ? (j.posted_age || "") : d === 0 ? "Today" : `${d}d ago`; };
  const ageLong = (j) => { const d = postedDaysAgo(j); return d == null ? "" : d === 0 ? "Posted today" : d === 1 ? "Posted 1 day ago" : `Posted ${d} days ago`; };
  function cvDeadline(j) {
    const left = cvWindow() - cvAge(j);
    return left <= 0 ? "today" : left === 1 ? "tomorrow" : `in ${left} days`;
  }
  function skipReason(j) {
    if (state.local.skip[j.id]) return "You skipped it (saved on this device only)";
    if (isStaleCv(j) || (j.status === "expired" && j.decision === "approved")) return `Expired: CV was ready for ${cvWindow()} days but not marked as applied`;
    if (j.status === "expired" || isStale(j)) return `Expired: not reviewed within ${reviewWindow()} day${reviewWindow() === 1 ? "" : "s"} of being found`;
    if (j.decision === "skipped" && j.decided_at) return "You skipped it on " + new Date(j.decided_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    if (j.decision === "skipped") return "Filtered by the scan: " + (j.verdict || "didn't pass the checks");
    return "";
  }
  const bucket = (j) => APPLIED.includes(j.status) ? "tracker"
    : state.local.skip[j.id] && !isSkipped(j) ? "skipped"
    : state.local.restore[j.id] && isSkipped(j) ? "jobs"
    : APPLIED.includes(j.status) ? "tracker"
    : isSkipped(j) ? "skipped"
    : (j.decision === "approved" || j.status === "approved" || j.status === "cv_ready") ? "cvs" : "jobs";

  const PALETTE = ["#10805a", "#2f5fa8", "#8a4bb0", "#b5552b", "#2d7f8a", "#9a3e5e", "#5b6b1f", "#4a5568"];
  const logo = (name, cls = "") => {
    const words = String(name || "?").replace(/\(.*?\)/g, "").replace(/\b(ltd|limited|plc|llp|group|the|uk)\b/gi, "").trim().split(/\s+/);
    const ini = ((words[0] || "?")[0] + (words[1] ? words[1][0] : "")).toUpperCase();
    let h = 0; for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return `<div class="logo ${cls}" style="background:${PALETTE[h % PALETTE.length]}" aria-hidden="true">${esc(ini)}</div>`;
  };
  const fitColor = (s) => s == null ? "var(--muted)" : s >= 70 ? "var(--good)" : s >= 50 ? "var(--warn)" : "var(--bad)";
  const recLabel = { apply: "Worth applying", maybe: "Maybe", skip: "Probably skip" };

  function checks(j) {
    const m = j.sponsor_match && typeof j.sponsor_match === "object" ? j.sponsor_match : null;
    const reg = j.sponsor_register || "unknown";
    return [
      { k: "Home Office sponsor register", c: { licensed: "good", licensed_other_route: "warn", possible: "warn", not_found: "bad" }[reg] || "unk",
        v: { licensed: "Licensed Skilled Worker sponsor", licensed_other_route: "Licensed, but not for Skilled Worker", possible: "Possible match, check the name", not_found: "Not on the register", unknown: "Not checked yet" }[reg] || reg,
        d: m ? `${m.name}${m.town ? ", " + m.town : ""}${m.rating ? " · " + m.rating : ""}` : "" },
      { k: "What the advert says", c: { offers: "good", silent: "warn", no_sponsorship: "bad", right_to_work_required: "bad" }[j.jd_sponsorship] || "unk",
        v: { offers: "Mentions visa sponsorship", silent: "Doesn't mention sponsorship", no_sponsorship: "Says no sponsorship", right_to_work_required: "Needs existing right to work" }[j.jd_sponsorship] || "Advert not read", d: "" },
      { k: "Salary vs Skilled Worker threshold", c: { meets_general: "good", range_crosses_general: "good", meets_new_entrant: "good", range_crosses_new_entrant: "warn", below_threshold: "bad" }[j.salary_check] || "unk",
        v: { meets_general: "Meets £41,700 general threshold", range_crosses_general: "Top of range reaches £41,700", meets_new_entrant: "Meets £33,400 new-entrant rate", range_crosses_new_entrant: "Only the top of the range reaches £33,400", below_threshold: "Below £33,400 new-entrant rate" }[j.salary_check] || "No salary given", d: j.salary || "" },
      { k: "Who posted it", c: j.recruiter ? "warn" : "good", v: j.recruiter ? "Recruitment agency" : "Direct employer", d: j.recruiter ? "The real employer may be hidden; ask the recruiter about sponsorship." : "" },
    ];
  }
  const SOURCES = { glassdoor: "Glassdoor", totaljobs: "Totaljobs", "hunt uk visa sponsors": "Hunt UK Visa Sponsors", huntukvisasponsors: "Hunt UK Visa Sponsors", "newcastle university": "Newcastle Uni", newcastle_university: "Newcastle Uni" };
  const sourceName = (j) => { const s = String(j.source || "").toLowerCase().replace(/^gmail-?/, ""); return SOURCES[s] || (s ? s.replace(/(^|[\s_-])\w/g, (c) => c.toUpperCase()).replace(/[_-]/g, " ") : ""); };
  const sourceTag = (j) => sourceName(j) ? `<span class="tag src">${esc(sourceName(j))}</span>` : "";
  const tagFor = (j) => {
    const c = checks(j)[0];
    return c.c === "good" ? `<span class="tag good">Sponsor licence</span>` : c.c === "bad" ? `<span class="tag bad">No sponsor licence</span>` : c.c === "warn" ? `<span class="tag warn">Check sponsor</span>` : "";
  };

  function issueUrl(verb, j) {
    const g = state.cfg.github || {};
    const body = `${j.title} at ${j.company}\n\nTap "Submit new issue" to record this. A GitHub Action updates the tracker and closes this issue within a minute.`;
    return `https://github.com/${encodeURIComponent(g.owner || "")}/${encodeURIComponent(g.repo || "")}/issues/new?title=${encodeURIComponent(`job-desk: ${verb} ${j.id}`)}&body=${encodeURIComponent(body)}`;
  }
  const act = (verb, j, label, cls = "") => `<a class="btn ${cls}" href="${esc(issueUrl(verb, j))}" target="_blank" rel="noopener" data-verb="${verb}" data-id="${esc(j.id)}">${label}</a>`;
  const chatUrl = (j) => {
    const p = `I'm looking at this job and want to talk it through before you tailor my CV.\n\n${j.title} at ${j.company} (${j.location || ""})\n${j.url || ""}\nJob id: ${j.id}\n\nUse my Job Desk repo (${(state.cfg.github || {}).owner}/${(state.cfg.github || {}).repo}): read CLAUDE.md, cv/master_cv.md and this job in data/jobs.csv.`;
    return "https://claude.ai/new?q=" + encodeURIComponent(p);
  };

  const saveLocal = () => save("jd-local", state.local);
  function skipLocal(id) {
    const j = state.jobs.find((x) => x.id === id); if (!j) return;
    if (state.local.restore[id]) delete state.local.restore[id]; else state.local.skip[id] = Date.now();
    saveLocal(); render(); if (!$("#sheet").hidden) history.back();
    toast(`Skipped ${j.company}`, () => { delete state.local.skip[id]; if (isSkipped(j)) state.local.restore[id] = Date.now(); saveLocal(); render(); });
  }
  function restoreLocal(id) {
    const j = state.jobs.find((x) => x.id === id); if (!j) return;
    if (state.local.skip[id]) delete state.local.skip[id]; else state.local.restore[id] = Date.now();
    saveLocal(); render(); toast(`Moved ${j.company} back to Jobs`);
  }
  function batchUrl(verb, ids) {
    const g = state.cfg.github || {};
    const names = ids.map((id) => { const j = state.jobs.find((x) => x.id === id); return j ? `- ${j.title} at ${j.company}` : `- ${id}`; }).join("\n");
    const body = `${verb === "skip" ? "Skipped" : "Restored"} on Job Desk:\n${names}\n\nids: ${ids.join(",")}\n\nTap "Submit new issue" to save this. A GitHub Action records it and closes this issue within a minute.`;
    return `https://github.com/${encodeURIComponent(g.owner || "")}/${encodeURIComponent(g.repo || "")}/issues/new?title=${encodeURIComponent(`job-desk: ${verb} batch`)}&body=${encodeURIComponent(body)}`;
  }
  function syncBar() {
    const sk = Object.keys(state.local.skip), rs = Object.keys(state.local.restore);
    if (!sk.length && !rs.length) return "";
    const parts = [sk.length ? `${sk.length} skipped` : "", rs.length ? `${rs.length} restored` : ""].filter(Boolean).join(" and ");
    return `<div class="sync"><span>${parts} on this device only. Save to GitHub so it sticks everywhere.</span>
      ${sk.length ? `<a class="btn primary" href="${esc(batchUrl("skip", sk))}" target="_blank" rel="noopener" data-sync>Save skips</a>` : ""}
      ${rs.length ? `<a class="btn" href="${esc(batchUrl("reopen", rs))}" target="_blank" rel="noopener" data-sync>Save restores</a>` : ""}</div>`;
  }

  function matches(j) {
    if (state.q) {
      const hay = `${j.company} ${j.title} ${j.location}`.toLowerCase();
      if (!state.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    const f = state.filters;
    if (f.has("apply") && j.recommendation !== "apply") return false;
    if (f.has("sponsor") && j.sponsor_register !== "licensed") return false;
    if (f.has("salary") && !["meets_general", "range_crosses_general", "meets_new_entrant"].includes(j.salary_check)) return false;
    if (f.has("direct") && j.recruiter) return false;
    if (f.has("easy") && !j.easy_apply) return false;
    return true;
  }

  function card(j) {
    const s = Number.isFinite(j.fit_score) ? j.fit_score : null;
    const p = state.pending[j.id];
    const b = bucket(j);
    const inner = `<div class="card" role="button" tabindex="0" data-open="${esc(j.id)}" aria-label="${esc(j.title)} at ${esc(j.company)}">
      ${logo(j.company)}
      <div style="min-width:0">
        <div class="co"><span>${esc(j.company)}</span>${s != null ? `<span class="fit" style="--fitc:${fitColor(s)}">${s} fit</span>` : ""}</div>
        <div class="t">${esc(j.title)}</div>
        <div class="loc">${esc(j.location || "")}</div>
        ${j.salary ? `<div class="pay">${esc(j.salary)}</div>` : ""}
        <div class="foot">${sourceTag(j)}${tagFor(j)}${j.easy_apply ? `<span class="tag">Easy Apply</span>` : ""}${j.status === "cv_ready" ? `<span class="tag info">CV ready</span>` : ""}${j.status === "expired" || isStale(j) ? `<span class="tag">Expired</span>` : ""}${p ? `<span class="tag info">Sent: ${esc(p.verb)}</span>` : ""}
          <span class="age ${(postedDaysAgo(j) ?? 9) <= 1 ? "fresh" : ""}">${esc(ageLabel(j))}</span></div>
        ${b === "skipped" ? `<div class="why-skip">${esc(skipReason(j))}</div>` : ""}
        ${b === "cvs" && j.status === "cv_ready" ? `<div class="why-skip ${(postedDaysAgo(j) ?? 0) > 3 ? "warn-txt" : ""}">${esc(ageLong(j))}. Moves to Skipped ${esc(cvDeadline(j))} unless you mark it applied.</div>` : ""}
      </div></div>`;
    if (b === "jobs" || b === "cvs") return `<div class="swipe" data-swipe="${esc(j.id)}">${inner}</div>`;
    if (b === "skipped") return `<div class="cardrow">${inner}<button class="restore" data-restore="${esc(j.id)}">↩ Restore to Jobs</button></div>`;
    return inner;
  }

  function trackerView(list) {
    const numbered = list.slice().sort((a, b) => String(a.applied_at || a.status_updated_at).localeCompare(String(b.applied_at || b.status_updated_at)))
      .map((j, i) => ({ j, n: i + 1 }));
    const groups = { all: null, waiting: ["applied"], interviews: ["interview", "offer"], rejected: ["rejected", "withdrawn"] };
    const count = (k) => groups[k] ? list.filter((j) => groups[k].includes(j.status)).length : list.length;
    const f = state.tfilter;
    const rows = numbered.filter(({ j }) => !groups[f] || groups[f].includes(j.status));
    const next = { applied: ["interview", "rejected", "withdrawn"], interview: ["offer", "rejected", "withdrawn"], offer: ["withdrawn"] };
    const moves = (j) => (next[j.status] || []).map((s) => `<a href="${esc(issueUrl(s, j))}" target="_blank" rel="noopener" data-verb="${s}" data-id="${esc(j.id)}">→ ${s}</a>`).join("");
    const tile = (k, label) => `<button class="tile" data-tf="${k}" aria-pressed="${f === k}"><b>${count(k)}</b><span>${label}</span></button>`;
    const newestFirst = rows.slice().reverse();
    return `<div class="stats">${tile("all", "All")}${tile("waiting", "Waiting")}${tile("interviews", "Interviews")}${tile("rejected", "Rejected")}</div>
      <div class="tcards">${newestFirst.map(({ j, n }) => `<article class="tcard">
          <div class="tc-top"><span class="tc-n">#${n}</span><span class="status s-${esc(j.status)}">${esc(j.status)}</span><span class="tc-date">${j.applied_at ? fmtDate(j.applied_at) : "Date not known"}</span></div>
          <div class="tc-co">${esc(j.company)}</div>
          <a class="tc-role" href="#job/${esc(j.id)}">${esc(j.title)}</a>
          ${j.location || j.salary ? `<div class="tc-meta">${[j.location, j.salary].filter(Boolean).map(esc).join(" · ")}</div>` : ""}
          ${j.last_email ? `<div class="tc-meta">✉ ${esc(j.last_email)}</div>` : ""}
          ${j.cv_url || moves(j) ? `<div class="tc-act">${j.cv_url ? `<a href="${esc(safeUrl(j.cv_url))}">CV used ↓</a>` : ""}${moves(j)}</div>` : ""}
        </article>`).join("") || `<div class="empty">Nothing in this group.</div>`}</div>
      <div class="tablewrap"><table><thead><tr><th>Sr No</th><th>Company Name</th><th>Role</th><th>Location</th><th>Applied On</th><th>Pay</th><th>CV Application</th><th>Status</th></tr></thead><tbody>
      ${rows.map(({ j, n }) => `<tr><td class="num">${n}</td><td>${esc(j.company)}</td><td><a href="#job/${esc(j.id)}">${esc(j.title)}</a></td><td>${esc(j.location || "—")}</td>
        <td>${j.applied_at ? fmtDate(j.applied_at) : "—"}</td><td>${esc(j.salary || "—")}</td>
        <td>${j.cv_url ? `<a href="${esc(safeUrl(j.cv_url))}">Download</a>` : "—"}</td>
        <td><span class="status s-${esc(j.status)}">${esc(j.status)}</span>${moves(j) ? `<div class="links tc-act" style="margin-top:6px">${moves(j)}</div>` : ""}</td></tr>`).join("")}
      </tbody></table></div>
      <p style="font-size:.8rem;color:var(--muted);margin:0">Also on GitHub as <a href="data/applied.csv">applied.csv</a>. Claude updates statuses from your Gmail each morning.</p>`;
  }

  function accountView(tracked) {
    const c = state.cfg, g = c.github || {}, m = state.meta;
    const repo = g.owner ? `https://github.com/${g.owner}/${g.repo}` : "";
    const tree = repo ? `${repo}/tree/${encodeURIComponent(g.branch || "main").replace(/%2F/g, "/")}` : "";
    const blob = repo ? `${repo}/blob/${encodeURIComponent(g.branch || "main").replace(/%2F/g, "/")}` : "";
    const ini = String(c.name || "?").split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2).toUpperCase();
    const item = (href, title, sub) => href ? `<a href="${esc(safeUrl(href))}" target="_blank" rel="noopener"><span>${esc(title)}</span><small>${esc(sub)}</small></a>` : "";
    return `<div class="profile"><div class="avatar" aria-hidden="true">${esc(ini)}</div><div style="min-width:0"><b>${esc(c.name || "Your profile")}</b><small>${esc(c.email || "")}</small></div></div>
      <section class="acct-sec"><h3>Application tracker</h3>${tracked.length ? trackerView(tracked) : `<div class="empty">Jobs you apply to through Job Desk appear here, and Claude updates them from your Gmail each morning.</div>`}</section>
      <section class="acct-sec"><h3>My setup</h3><div class="menu">
        ${item(tree && tree + "/cv", "Master CV", "Upload or replace cv/master_cv.pdf")}
        ${item(blob && blob + "/config/profile.json", "Job preferences", "Target roles, locations, visa settings")}
        ${item(blob && blob + "/config/scoring.json", "Scoring rubric", "How each job's score out of 100 is made")}
        ${item(tree && tree + "/outputs/cvs", "Tailored CVs", "Every CV Claude has written for you")}
        ${item(blob && blob + "/data/applied.csv", "Tracker spreadsheet", "applied.csv on GitHub")}
      </div></section>
      <section class="acct-sec"><h3>Status</h3><div class="menu">
        <a href="${esc(safeUrl(repo ? repo + "/actions" : ""))}" target="_blank" rel="noopener"><span>Last scan</span><small>${m.last_scan ? esc(time12(m.last_scan)) : "Not yet"}${m.register_date ? " · sponsor register " + esc(m.register_date) : ""}</small></a>
        ${item(repo && repo + "/issues?q=is%3Aissue+job-desk", "Button history", "Every Go ahead, skip and status change")}
      </div></section>`;
  }

  function funnel() {
    const m = state.meta;
    if (m.scan_listings === undefined || m.scan_listings === "") return "";
    const n = (k) => num(m[k]);
    const steps = [["scan_too_old", "older than 3 days"], ["scan_duplicates", "already seen"], ["scan_off_target", "outside your roles"], ["scan_not_sponsor", "employer can't sponsor"]]
      .filter(([k]) => n(k) > 0).map(([k, l]) => `<li><b>${n(k)}</b> ${l}</li>`).join("");
    return `<details class="funnel"><summary><span>Last scan: <b>${n("scan_listings")}</b> listings in ${n("scan_emails")} email${n("scan_emails") === 1 ? "" : "s"} → <b>${n("scan_new")}</b> new for you</span></summary>
      <ul>${steps || "<li>Nothing was filtered out.</li>"}<li><b>${n("scan_new")}</b> added to Jobs</li></ul>
      <p>Glassdoor alerts repeat the same jobs for weeks, so most listings are old or duplicates. Filtered jobs from your roles and sponsors land in Skipped, where you can restore them.</p></details>`;
  }

  function render() {
    const groups = { jobs: [], cvs: [], tracker: [], skipped: [] };
    for (const j of state.jobs) groups[bucket(j)].push(j);
    for (const k of ["jobs", "cvs", "skipped"]) $("#b-" + k).textContent = groups[k].length ? `(${groups[k].length})` : "";
    if (state.view === "tracker") state.view = "account";
    $("#account").setAttribute("aria-pressed", String(state.view === "account"));
    document.querySelectorAll("nav.bottom button").forEach((b) => { if (b.dataset.v === state.view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
    const v = state.view;
    $("#chips").hidden = v === "account";
    $(".search").hidden = v === "account";
    if (v === "account") { $("#view").innerHTML = `<div class="section-head"><h2>My account</h2></div>` + accountView(groups.tracker); return; }
    const list = groups[v].filter(matches);
    const by = (a, b) => (b.fit_score ?? -1) - (a.fit_score ?? -1) || String(b.first_seen).localeCompare(String(a.first_seen));
    const titles = { jobs: ["New for you", "Posted in the last 3 days, best fit first"], cvs: ["Approved", "Tailored CVs arrive here and by email"], tracker: ["Application tracker", ""], skipped: ["Skipped & expired", "Jobs you don't review within a few days move here too. Restore anything you want back."] };
    const empty = { jobs: "Nothing to review. New jobs arrive after the next daily scan.", cvs: "Approve a job and its tailored CV shows up here.", tracker: "Applications appear here when you mark them or a confirmation email arrives.", skipped: "Nothing skipped yet." };
    let html = syncBar() + (v === "jobs" ? funnel() : "") + `<div class="section-head"><h2>${titles[v][0]}</h2><span>${titles[v][1]}</span></div>`;
    if ((v === "jobs" || v === "cvs") && list.length) html += `<div class="hint">Swipe a card left to skip it. Skipped jobs can be restored from Skipped.</div>`;
    if (v === "tracker") html += list.length ? trackerView(list) : `<div class="empty">${empty[v]}</div>`;
    else html += list.length ? `<div class="feed">${list.sort(by).map(card).join("")}</div>` : `<div class="empty">${state.q || state.filters.size ? "No jobs match these filters." : empty[v]}</div>`;
    $("#view").innerHTML = html;
  }

  function openSheet(id) {
    const j = state.jobs.find((x) => x.id === id);
    const sh = $("#sheet");
    if (!j) { sh.hidden = true; document.body.style.overflow = ""; return; }
    const s = Number.isFinite(j.fit_score) ? Math.max(0, Math.min(100, j.fit_score)) : null;
    const b = bucket(j);
    const li = (a) => (a || []).map((x) => `<li>${esc(x)}</li>`).join("");
    const tabs = [["analysis", "Analysis"], ["job", "Job description"], ["visa", "Sponsorship"]];
    const panel = state.tab === "job"
      ? `<div class="box"><div class="jd">${esc(j.jd_full || j.jd_summary || "The advert hasn't been read yet.")}</div></div>${j.url ? `<a class="btn" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener">Open the full advert${sourceName(j) ? " on " + esc(sourceName(j)) : ""}</a>` : ""}`
      : state.tab === "visa"
      ? `<div class="checks">${checks(j).map((c) => `<div class="check"><div class="dot d-${c.c}">${{ good: "✓", warn: "!", bad: "✕", unk: "?" }[c.c]}</div><div><small>${esc(c.k)}</small><b>${esc(c.v)}</b>${c.d ? `<small>${esc(c.d)}</small>` : ""}</div></div>`).join("")}</div>
         <p style="font-size:.8rem;color:var(--muted);margin:0">A licensed sponsor can still decide not to sponsor a role. Check the job's occupation code going rate too.</p>`
      : `${j.verdict ? `<div class="box"><h3>Claude's take</h3><div>${esc(j.verdict)}</div></div>` : ""}
         ${(j.score_breakdown || []).length ? `<div class="box"><h3>How the ${s ?? ""}/100 is made up</h3><div class="breakdown">${j.score_breakdown.map((c) => {
            const sc = num(c.score), mx = num(c.max), pct = mx ? Math.max(0, Math.min(100, Math.round((sc / mx) * 100))) : 0;
            return `<div class="crit"><b>${esc(c.label)}</b><span class="pts">${sc}/${mx}</span><div class="bar"><i style="width:${pct}%;background:${pct >= 70 ? "var(--good)" : pct >= 40 ? "var(--warn)" : "var(--bad)"}"></i></div>${c.note ? `<small>${esc(c.note)}</small>` : ""}</div>`;
          }).join("")}</div>${j.confidence ? `<p class="conf">Confidence: <b>${esc(j.confidence)}</b>${j.confidence !== "high" ? " (scored before your master CV was uploaded, or from a short advert)" : ""}</p>` : ""}</div>` : ""}
         <div class="box pro"><h3>Why apply</h3><ul>${li(j.match_reasons) || "<li>No analysis yet.</li>"}</ul></div>
         <div class="box con"><h3>What could go wrong</h3><ul>${li(j.gaps) || "<li>Nothing flagged.</li>"}</ul></div>
         ${j.last_email ? `<div class="box"><h3>Latest email</h3><div>${esc(j.last_email)}</div></div>` : ""}
         <div class="links"><a class="btn ghost" href="${esc(chatUrl(j))}" target="_blank" rel="noopener">Chat with Claude about this job</a></div>`;
    let bar = "";
    if (b === "jobs") bar = `<button class="btn" data-skip="${esc(j.id)}">Skip</button>` + act("approve", j, "Go ahead: tailor CV", "primary");
    else if (b === "cvs") bar = (j.cv_url ? `<a class="btn" href="${esc(safeUrl(j.cv_url))}">Download CV</a>` : act("reopen", j, "Undo")) + act("applied", j, "Mark as applied", "primary");
    else if (b === "skipped") bar = `<button class="btn primary" data-restore="${esc(j.id)}">↩ Restore to Jobs</button>`;
    else bar = j.url ? `<a class="btn primary" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener">Open advert</a>` : "";
    sh.innerHTML = `<div class="sheet-top"><div class="wrap"><button class="back" data-close aria-label="Back">←</button><span class="ttl">${esc(j.company)}</span></div></div>
      <div class="hero"><div class="wrap">${logo(j.company)}
        <h2>${esc(j.title)}</h2><div class="co">${esc(j.company)} · ${esc(j.location || "")}</div>
        ${j.salary ? `<div class="pay">${esc(j.salary)}</div>` : ""}
        <div class="foot" style="display:flex;gap:6px;flex-wrap:wrap">${sourceTag(j)}${tagFor(j)}${j.easy_apply ? `<span class="tag">Easy Apply</span>` : ""}${ageLong(j) ? `<span class="tag ${(postedDaysAgo(j) ?? 9) <= 1 ? "good" : (postedDaysAgo(j) ?? 0) > 3 ? "warn" : ""}">${esc(ageLong(j))}</span>` : ""}${APPLIED.includes(j.status) ? `<span class="status s-${esc(j.status)}">${esc(j.status)}</span>` : ""}</div>
        ${s != null ? `<div class="scorebar" style="--fitc:${fitColor(s)}"><b>${s}/100</b><div class="meter"><i style="width:${s}%"></i></div><span class="tag ${s >= 70 ? "good" : s >= 50 ? "warn" : "bad"}">${esc(recLabel[j.recommendation] || "")}</span></div>` : ""}
      </div></div>
      <div class="tabs"><div class="wrap" role="tablist">${tabs.map(([k, l]) => `<button class="tab" role="tab" data-tab="${k}" aria-selected="${state.tab === k}">${l}</button>`).join("")}</div></div>
      <div class="wrap panel">${panel}</div>
      ${bar ? `<div class="actionbar"><div class="wrap">${bar}</div></div>` : ""}`;
    sh.hidden = false; document.body.style.overflow = "hidden";
  }

  function route() {
    const m = location.hash.match(/^#job\/(.+)$/);
    if (m) openSheet(decodeURIComponent(m[1]));
    else { $("#sheet").hidden = true; document.body.style.overflow = ""; }
  }

  document.addEventListener("click", (ev) => {
    if (ev.target.closest("#refresh")) { refresh(true); return; }
    if (ev.target.closest("#account")) { state.view = state.view === "account" ? "jobs" : "account"; save("jd-view", state.view); render(); window.scrollTo(0, 0); return; }
    const sk = ev.target.closest("[data-skip]");
    if (sk) { skipLocal(sk.dataset.skip); return; }
    const rs = ev.target.closest("[data-restore]");
    if (rs) { restoreLocal(rs.dataset.restore); if (!$("#sheet").hidden) history.back(); return; }
    if (ev.target.closest("[data-sync]")) { toast("On GitHub, tap “Submit new issue”. It's saved a minute later."); return; }
    const o = ev.target.closest("[data-open]");
    if (o && o.dataset.dragged) { delete o.dataset.dragged; return; }
    if (o) { state.tab = "analysis"; location.hash = "job/" + o.dataset.open; return; }
    if (ev.target.closest("[data-close]")) { history.length > 1 ? history.back() : (location.hash = ""); return; }
    const tf = ev.target.closest("[data-tf]");
    if (tf) { state.tfilter = tf.dataset.tf; render(); return; }
    const t = ev.target.closest(".tab");
    if (t) { state.tab = t.dataset.tab; route(); return; }
    const n = ev.target.closest("nav.bottom button");
    if (n) { state.view = n.dataset.v; save("jd-view", state.view); render(); window.scrollTo(0, 0); return; }
    const c = ev.target.closest(".chip");
    if (c) { const f = c.dataset.f; state.filters.has(f) ? state.filters.delete(f) : state.filters.add(f); c.setAttribute("aria-pressed", String(state.filters.has(f))); render(); return; }
    const a = ev.target.closest("a[data-verb]");
    if (a) {
      state.pending[a.dataset.id] = { verb: a.dataset.verb, at: Date.now() }; save("jd-pending", state.pending);
      toast("On GitHub, tap “Submit new issue”. Job Desk updates a minute or two later.");
    }
  });
  document.addEventListener("keydown", (e) => { const o = e.target.closest && e.target.closest(".card[data-open]"); if (o && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); o.click(); } });

  let drag = null;
  document.addEventListener("pointerdown", (e) => {
    const w = e.target.closest("[data-swipe]"); if (!w || e.button > 0) return;
    drag = { w, c: w.querySelector(".card"), x: e.clientX, y: e.clientY, dx: 0, on: false, pid: e.pointerId };
  });
  document.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.pid) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.on) {
      if (dx < -12 && Math.abs(dx) > Math.abs(dy) * 1.4) { drag.on = true; drag.c.classList.add("dragging"); try { drag.c.setPointerCapture(e.pointerId); } catch (_) {} }
      else if (Math.abs(dy) > 12 || dx > 12) { drag = null; return; }
    }
    if (drag.on) { drag.dx = Math.min(0, dx); drag.c.style.transform = `translateX(${drag.dx}px)`; }
  });
  const endDrag = () => {
    if (!drag) return;
    const { w, c, dx, on } = drag; drag = null;
    if (!on) return;
    c.classList.remove("dragging"); c.dataset.dragged = "1"; setTimeout(() => delete c.dataset.dragged, 350);
    if (dx < -Math.min(120, w.offsetWidth * 0.33)) { c.style.transform = "translateX(-110%)"; c.style.opacity = "0"; setTimeout(() => skipLocal(w.dataset.swipe), 170); }
    else c.style.transform = "";
  };
  document.addEventListener("pointerup", endDrag);
  document.addEventListener("pointercancel", endDrag);

  $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim(); render(); });
  window.addEventListener("hashchange", route);

  async function getJSON(p) { const r = await fetch(`${p}?t=${Date.now()}`, { cache: "no-store" }); if (!r.ok) throw new Error(p); return r.json(); }
  async function refresh(manual) {
    const rb = $("#refresh"); rb.classList.add("spin");
    try {
      const [cfg, jobs, meta] = await Promise.all([getJSON("config/profile.json"), getJSON("data/jobs.json"), getJSON("data/meta.json").catch(() => ({}))]);
      Object.assign(state, { cfg, jobs, meta });
      const done = { approve: (j) => j.decision === "approved", skip: (j) => j.decision === "skipped", reopen: (j) => j.status === "new" };
      for (const [id, p] of Object.entries(state.pending)) {
        const j = jobs.find((x) => x.id === id);
        if (!j || (done[p.verb] ? done[p.verb](j) : j.status === p.verb) || Date.now() - p.at > 20 * 60 * 1000) delete state.pending[id];
      }
      save("jd-pending", state.pending);
      for (const id of Object.keys(state.local.skip)) { const j = jobs.find((x) => x.id === id); if (!j || isSkipped(j)) delete state.local.skip[id]; }
      for (const id of Object.keys(state.local.restore)) { const j = jobs.find((x) => x.id === id); if (!j || !isSkipped(j)) delete state.local.restore[id]; }
      saveLocal();
      $("#stamp").textContent = meta.last_scan ? `Scanned ${time12(meta.last_scan)}` : "Waiting for first scan";
      if (manual) toast(`Up to date · ${time12(new Date().toISOString())}`);
      const n = $("#notice"); if (meta.notice) { n.innerHTML = `<b>Heads up.</b> ${esc(meta.notice)}`; n.hidden = false; } else n.hidden = true;
      render(); route();
      rb.classList.remove("spin");
    } catch (e) { rb.classList.remove("spin"); $("#stamp").textContent = "Couldn't load data"; $("#view").innerHTML = `<div class="empty">Couldn't load your tracker. Check your connection and reload.</div>`; }
  }
  refresh();
  setInterval(() => { if (document.visibilityState === "visible" && Object.keys(state.pending).length) refresh(); }, 30000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(); });
})();
