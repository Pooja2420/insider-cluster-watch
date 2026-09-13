# Insider Cluster Watch

Built for the Multi-App AI Agent Hackathon (Sep 13, 2026).

**Team:**
- Pooja Venugopal Baskaran ([pooja.vb2000@gmail.com](mailto:pooja.vb2000@gmail.com))
- Madhavan Panneerselvam Kumar ([pkmadhavan9802@gmail.com](mailto:pkmadhavan9802@gmail.com))

**Demo video (2 min):** ADD_YOUR_LINK_HERE

---

## The problem

Insider stock purchases are public record the moment they're filed (SEC
Form 4) — but the specific pattern that matters, multiple *distinct*
insiders at the same company buying in the same short window, is buried
across thousands of filings a day across the entire market. Academic
research ties clustered insider buying to outsized forward returns.
Institutions pay for terminals that watch this in real time. Retail
investors have no practical way to notice it themselves — not because the
data is hidden, but because nobody is watching the whole feed for them.

This tool watches SEC EDGAR's live public filings feed and surfaces the
cluster pattern the moment it appears, escalating it to a human across
four apps rather than acting on it.

**This is not investment advice.** It surfaces a public disclosure signal
faster than it would otherwise be noticed. It does not recommend a trade,
and it never places one — every escalation says so explicitly.

## External apps used

| App | What it's used for | Status |
|---|---|---|
| **Slack** | Real-time alert the moment a cluster is detected | ✅ Live (Incoming Webhook) |
| **Discord** | Mirrors the same real-time alert to a second audience | ✅ Live (channel Webhook) |
| **Gmail** | Drafts (never auto-sends) a digest for high-severity clusters, held for human review | ✅ Live (Gmail API, `gmail.compose` scope) |
| **Google Sheets** | Full audit log of every flagged cluster | Mock mode (documented live path below, not connected for this submission) |

Slack and Discord both use plain incoming webhooks — no OAuth or bot setup
required. All four connectors run in a documented mock mode by default
(mock mode writes to local files under `insider_watch_output/`) so the repo
is fully runnable with zero credentials, and each swaps to its live API via
a single environment variable — see below.

## Setup instructions

```bash
pip install -r requirements.txt
python main.py
```

That's it — the ingestion is **live and real from the first run**: it
pulls the actual current SEC EDGAR Form 4 feed, no credentials required for
that part. Only the four escalation connectors default to mock mode.
Output lands in `insider_watch_output/` (audit CSV, Slack/Discord logs,
Gmail draft).

To connect a real app instead of mock mode, set the matching environment
variable before running:

| App | Env var | Extra install |
|---|---|---|
| Slack | `INSIDER_WATCH_SLACK_WEBHOOK` (Incoming Webhook URL) | none |
| Discord | `INSIDER_WATCH_DISCORD_WEBHOOK` (channel Webhook URL) | none |
| Google Sheets | `INSIDER_WATCH_GOOGLE_CREDS` + `INSIDER_WATCH_SHEET_ID` | `pip install gspread google-auth` |
| Gmail | `INSIDER_WATCH_GMAIL_TOKEN` (OAuth token path) | `pip install google-api-python-client google-auth-oauthlib` |

Also set `INSIDER_WATCH_CONTACT` to `"Your Name your@email.com"` — SEC asks
every caller of its public feed to self-identify with a real contact in the
User-Agent string.

### Gmail live setup (one-time)

Gmail drafting needs a one-time OAuth authorization since it uses the real
Gmail API rather than a webhook:

1. Create a Google Cloud project → enable the **Gmail API**
2. Configure the OAuth consent screen (External, add yourself as a test
   user) and create an **OAuth client ID** (Application type: Desktop app)
   → download the JSON as `credentials/client_secret.json`
3. `pip install google-api-python-client google-auth-oauthlib`
4. `python scripts/gmail_auth.py` — opens your browser once for you to sign
   in and click Allow, then saves `credentials/token.json`
5. `export INSIDER_WATCH_GMAIL_TOKEN=credentials/token.json`

The script only requests the `gmail.compose` scope — enough to create
drafts, not to read or send mail outright. `credentials/` is gitignored.

### Automated runs (GitHub Actions)

`.github/workflows/insider-cluster-watch.yml` runs `main.py` on a schedule.
GitHub's native `schedule:` trigger is best-effort and can be delayed or
silently skipped for hours on freshly-created workflows, so the reliable
15-minute cadence is driven by an **external cron** (e.g. cron-job.org)
calling the workflow's `workflow_dispatch` endpoint via the GitHub API —
`schedule:` is kept as a free backup. To connect real apps in the
scheduled runs, add the env vars from the table above as repo secrets
under **Settings → Secrets and variables → Actions**; each run's output is
also uploaded as a downloadable artifact from the Actions tab.

## Pipeline

1. **Ingest** (`ingest/edgar.py`) — pulls the live SEC EDGAR Form 4 feed
   (`https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4`),
   fetches and parses each filing's ownership XML: issuer, insider identity
   and role (officer/director/10%-owner), transaction code, shares, price,
   date. Real, live, public filings — no synthetic data anywhere in this
   module.
2. **Filter + cluster** (`engine/cluster.py`) — keeps only open-market
   purchases (transaction code `P`), then for each issuer slides a 7-day
   window and flags it when ≥2 distinct insiders bought within it.
   Severity is `high` when an officer/director is involved AND (≥3 distinct
   insiders OR ≥$250K total), otherwise `medium`.
3. **Reliability audit** (`reliability/audit.py`) — independently
   recomputes clusters from the raw transaction log and diffs against the
   live output before anything escalates.
4. **Escalate** (`connectors/`) — see "External apps used" above.
5. **Report** (`reporting/report.py`) — writes a clean, human-readable HTML
   summary to `insider_watch_output/report.html` after every run (stat
   tiles, a severity-coded cluster table, and the reliability figure) —
   open it in any browser instead of reading terminal output.

## How we tested reliability

**What's measured:** determinism of the clustering logic — same raw
filings in, same flagged clusters out, verified by an independent recompute
before any escalation fires. Since the whole point of this tool is telling
a human about a real pattern, silent classification drift would be the
worst possible failure mode.

**What this does and doesn't prove:**
- Proves: the clustering logic itself is reproducible — no hidden
  randomness or state leakage between runs on the same input.
- Doesn't prove: that SEC EDGAR's live feed is complete or that a filing
  filed late (Form 4s are due within 2 business days but sometimes filed
  later) won't be missed by a single point-in-time run. Running on a
  schedule (e.g. every 15-30 min) closes most of that gap in practice.

**Known limitations:**
- The 7-day cluster window and the $250K/3-insider severity thresholds are
  reasonable starting heuristics, not tuned/backtested values — a v2 would
  calibrate these against historical cluster-buy outcomes.
- Ticker symbols are occasionally blank in raw filings (SEC data quality,
  not a bug here); the tool still keys clusters by CIK, which is always
  present.
- This is a screening tool, not a scoring model — it does not rank clusters
  by predicted return, only by disclosed size/composition.

## Project structure

```
insider_cluster_watch/
  ingest/
    edgar.py          live SEC EDGAR Form 4 ingestion (feed + XML parsing)
  engine/
    cluster.py         open-market-purchase filtering + cluster detection
  reliability/
    audit.py           independent classification recompute + diff
  connectors/
    slack.py, discord.py, sheets.py, gmail.py    mock-mode by default, env-var swap to live
  reporting/
    report.py           human-readable HTML run summary
  scripts/
    gmail_auth.py        one-time local OAuth flow for the Gmail connector
  .github/workflows/
    insider-cluster-watch.yml    scheduled run (workflow_dispatch + backup schedule)
  main.py               orchestrator — the monitoring run
```
