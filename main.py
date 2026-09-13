"""
Insider Cluster Watch -- detects clustered insider open-market buying from
LIVE, public SEC Form 4 filings and escalates flagged clusters to a human
across Slack, Discord, Sheets, and Gmail.

The problem: insider buying is 100% public and free (SEC EDGAR), but the
specific pattern that matters -- multiple distinct insiders at the same
company buying in the same short window -- is buried across thousands of
filings a day. Institutions pay for terminals that watch this in real
time; retail investors have no practical way to notice it themselves. This
tool watches the live feed and surfaces that pattern the moment it appears.

This tool surfaces a PUBLIC DISCLOSURE SIGNAL faster than it would
otherwise be noticed. It is not investment advice, does not recommend any
trade, and never executes one.

Pipeline:
  1. Ingest live Form 4 filings from SEC EDGAR (ingest/edgar.py)
  2. Filter to open-market purchases, detect insider clusters
     (engine/cluster.py)
  3. Reliability audit: independently recompute clusters, diff vs. live
     output before escalating (reliability/audit.py)
  4. Escalate: Slack + Discord real-time alerts, full audit log to Sheets,
     Gmail digest DRAFT (never auto-sent) for high-severity clusters
     (connectors/*)

Run: python main.py
"""
from __future__ import annotations

import json
import os
import webbrowser
from datetime import datetime, timezone

from ingest.edgar import fetch_recent_transactions
from engine.cluster import filter_open_market_purchases, detect_clusters
from reliability.audit import audit_clusters
from connectors.slack import SlackConnector
from connectors.discord import DiscordConnector
from connectors.sheets import SheetsConnector
from connectors.gmail import GmailConnector
from reporting.report import write_html_report

DISCLAIMER = "Public-disclosure signal only. Not investment advice. No trades are placed by this tool."
DIGEST_RECIPIENT = "pooja.vb2000@gmail.com"


def utcnow():
    return datetime.now(timezone.utc)


def run_monitoring_cycle(max_filings: int = 60):
    print("=== Insider Cluster Watch monitoring run ===\n")

    print(f"Fetching up to {max_filings} recent LIVE Form 4 filings from SEC EDGAR...")
    raw_transactions = fetch_recent_transactions(max_filings=max_filings)
    print(f"Parsed {len(raw_transactions)} transaction rows from live filings.\n")

    purchases = filter_open_market_purchases(raw_transactions)
    clusters = detect_clusters(purchases)

    print(f"Open-market purchases: {len(purchases)} -> clusters flagged: {len(clusters)}\n")
    if not clusters.empty:
        print(clusters[["ticker", "issuer_name", "n_distinct_insiders", "total_dollar_value", "severity"]]
              .to_string(index=False))

    audit = audit_clusters(raw_transactions, clusters)
    print(f"\nReliability audit: {audit['agreement_rate']:.1%} agreement over "
          f"{audit['n_clusters_compared']} cluster-issuer(s) ({audit['n_mismatches']} mismatches)")

    sheets = SheetsConnector(mock_path="insider_watch_output/sheet_mirror.csv")
    slack = SlackConnector(mock_path="insider_watch_output/slack_mirror.log")
    discord = DiscordConnector(mock_path="insider_watch_output/discord_mirror.log")
    gmail = GmailConnector(mock_path="insider_watch_output/drafts")

    print("\n=== Connector actions ===")
    if not clusters.empty:
        sheet_rows = clusters.astype(str).to_dict("records")
        print(sheets.write_signals(sheet_rows))
    else:
        print("[sheets] no clusters this cycle — nothing to log")

    if not clusters.empty:
        lines = [
            f"*{row.ticker or row.issuer_name}* ({row.issuer_name}): {row.n_distinct_insiders} insiders bought "
            f"${row.total_dollar_value:,.0f} between {row.window_start.date()} and {row.window_end.date()} "
            f"[{row.severity}]"
            for row in clusters.itertuples()
        ]
        summary = (
            f"*Insider Cluster Watch — {utcnow().date()}*\n"
            f"{len(clusters)} cluster(s) flagged from {len(purchases)} open-market purchases "
            f"(out of {len(raw_transactions)} total transactions scanned).\n"
            f"Reliability: {audit['agreement_rate']:.1%} agreement.\n"
            + "\n".join(lines)
            + f"\n\n_{DISCLAIMER}_"
        )
    else:
        summary = (
            f"*Insider Cluster Watch — {utcnow().date()}*\n"
            f"No insider clusters detected this cycle "
            f"({len(purchases)} open-market purchases scanned).\n_{DISCLAIMER}_"
        )

    print(slack.post_summary(summary))
    print(discord.post_summary(summary))

    high_sev = clusters[clusters["severity"] == "high"] if not clusters.empty else clusters
    if not high_sev.empty:
        memo_body = (
            f"Insider Cluster Watch Digest — {utcnow().date()}\n\n"
            f"{len(high_sev)} high-severity cluster(s) detected.\n\n"
            + json.dumps(high_sev.astype(str).to_dict("records"), indent=2)
            + f"\n\n{DISCLAIMER}"
        )
        print(gmail.draft_digest(
            subject=f"[Insider Cluster Watch] {len(high_sev)} high-severity cluster(s) — {utcnow().date()}",
            body=memo_body,
            to=DIGEST_RECIPIENT,
        ))
    else:
        print("[gmail] no high-severity clusters — no digest drafted")

    report_path = write_html_report(
        path="insider_watch_output/report.html",
        raw_transactions=raw_transactions,
        purchases=purchases,
        clusters=clusters,
        audit=audit,
    )
    print(f"\n[report] human-readable summary written to {report_path}")

    # Auto-open for local/demo runs only -- skip in CI (no display, would
    # just hang or error) and let INSIDER_WATCH_NO_BROWSER opt out locally too.
    if "GITHUB_ACTIONS" not in os.environ and "INSIDER_WATCH_NO_BROWSER" not in os.environ:
        try:
            webbrowser.open(f"file://{os.path.abspath(report_path)}")
        except Exception as e:
            print(f"[report] could not auto-open browser: {e}")


if __name__ == "__main__":
    run_monitoring_cycle()
