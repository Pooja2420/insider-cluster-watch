"""
Reliability audit for Insider Cluster Watch.

Independently recomputes cluster classification from the raw transaction
log and diffs it against the live pipeline's output before anything is
escalated to Slack/Discord/Sheets/Gmail. A tool whose entire job is
surfacing a disclosure signal to a human must not itself introduce silent
classification drift -- so nothing escalates until the live output and this
independent recompute agree.
"""
from __future__ import annotations

import pandas as pd

from engine.cluster import filter_open_market_purchases, detect_clusters


def audit_clusters(raw_transactions: pd.DataFrame, live_clusters: pd.DataFrame) -> dict:
    recomputed = detect_clusters(filter_open_market_purchases(raw_transactions))

    live_keys = set(live_clusters["issuer_cik"]) if not live_clusters.empty else set()
    recomputed_keys = set(recomputed["issuer_cik"]) if not recomputed.empty else set()

    mismatched = live_keys.symmetric_difference(recomputed_keys)
    n_compared = len(live_keys | recomputed_keys) or 1
    agreement_rate = 1 - (len(mismatched) / n_compared)

    return {
        "n_clusters_compared": n_compared,
        "n_mismatches": len(mismatched),
        "mismatched_issuers": sorted(mismatched),
        "agreement_rate": agreement_rate,
    }
