"""
Human-readable HTML report for Insider Cluster Watch.

The terminal output is useful for logs, but hard to read at a glance on
camera or for a non-technical reviewer. This renders the same run's
results as a clean, static HTML page written to
insider_watch_output/report.html -- open it in any browser.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

import pandas as pd

DISCLAIMER = "Public-disclosure signal only. Not investment advice. No trades are placed by this tool."

SEVERITY_COLORS = {
    "high": "#c0392b",
    "medium": "#b8860b",
}

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Insider Cluster Watch — Run Report</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0f1216; color: #e6e6e6; margin: 0; padding: 32px; }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .subtitle {{ color: #9aa4af; margin-bottom: 24px; font-size: 14px; }}
  .stats {{ display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
  .stat {{ background: #1b2028; border: 1px solid #2a303a; border-radius: 10px; padding: 14px 18px; min-width: 140px; }}
  .stat .value {{ font-size: 26px; font-weight: 700; }}
  .stat .label {{ font-size: 12px; color: #9aa4af; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #2a303a; font-size: 14px; }}
  th {{ color: #9aa4af; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
  .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; color: white; }}
  .empty {{ color: #9aa4af; padding: 24px; text-align: center; background: #1b2028; border-radius: 10px; border: 1px solid #2a303a; }}
  .reliability {{ background: #16321f; border: 1px solid #234a2c; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px; font-size: 14px; }}
  .disclaimer {{ font-size: 12px; color: #9aa4af; border-top: 1px solid #2a303a; padding-top: 16px; margin-top: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Insider Cluster Watch</h1>
  <div class="subtitle">Live run · {timestamp}</div>

  <div class="stats">
    <div class="stat"><div class="value">{n_total}</div><div class="label">Transactions scanned</div></div>
    <div class="stat"><div class="value">{n_purchases}</div><div class="label">Open-market purchases</div></div>
    <div class="stat"><div class="value">{n_clusters}</div><div class="label">Clusters flagged</div></div>
    <div class="stat"><div class="value">{agreement:.0%}</div><div class="label">Reliability agreement</div></div>
  </div>

  <div class="reliability">
    Reliability audit: independent recompute of every cluster from the raw filing
    log agreed with the live output on {n_compared} issuer(s), {n_mismatches} mismatch(es).
  </div>

  {clusters_html}

  <div class="disclaimer">{disclaimer}</div>
</div>
</body>
</html>
"""

_EMPTY_HTML = '<div class="empty">No insider clusters detected this cycle.</div>'


def _clusters_table_html(clusters: pd.DataFrame) -> str:
    if clusters.empty:
        return _EMPTY_HTML

    rows = []
    for row in clusters.itertuples():
        color = SEVERITY_COLORS.get(row.severity, "#555")
        insiders = ", ".join(row.insiders) if isinstance(row.insiders, list) else str(row.insiders)
        rows.append(f"""
        <tr>
          <td><strong>{html.escape(str(row.ticker) or "—")}</strong></td>
          <td>{html.escape(str(row.issuer_name))}</td>
          <td>{row.n_distinct_insiders}</td>
          <td>{html.escape(insiders)}</td>
          <td>${row.total_dollar_value:,.0f}</td>
          <td>{html.escape(str(row.window_start.date()))} → {html.escape(str(row.window_end.date()))}</td>
          <td><span class="badge" style="background:{color}">{html.escape(row.severity.upper())}</span></td>
        </tr>""")

    return f"""
    <table>
      <thead>
        <tr>
          <th>Ticker</th><th>Company</th><th>Insiders</th><th>Who</th>
          <th>Total $</th><th>Window</th><th>Severity</th>
        </tr>
      </thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    """


def write_html_report(
    path: str,
    raw_transactions: pd.DataFrame,
    purchases: pd.DataFrame,
    clusters: pd.DataFrame,
    audit: dict,
) -> str:
    html_content = _PAGE_TEMPLATE.format(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        n_total=len(raw_transactions),
        n_purchases=len(purchases),
        n_clusters=len(clusters),
        agreement=audit["agreement_rate"],
        n_compared=audit["n_clusters_compared"],
        n_mismatches=audit["n_mismatches"],
        clusters_html=_clusters_table_html(clusters),
        disclaimer=DISCLAIMER,
    )
    with open(path, "w") as f:
        f.write(html_content)
    return path
