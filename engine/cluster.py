"""
Cluster-detection engine for Insider Cluster Watch.

Flags a company when multiple DISTINCT insiders make open-market purchases
(SEC transaction code "P") within a short rolling window -- the specific,
well-documented "insider cluster buying" pattern that academic research
ties to outsized forward returns, and that retail investors have no
practical way to monitor themselves since it requires watching every Form 4
filed across the entire market in real time.

This module only classifies public disclosures that have already happened.
It does not recommend or execute any trade, and nothing here is investment
advice.
"""
from __future__ import annotations

import pandas as pd

CLUSTER_WINDOW_DAYS = 7
MIN_DISTINCT_INSIDERS = 2

SEVERITY_HIGH_INSIDERS = 3
SEVERITY_HIGH_DOLLARS = 250_000

CLUSTER_COLUMNS = [
    "issuer_cik", "issuer_name", "ticker", "window_start", "window_end",
    "n_distinct_insiders", "insiders", "total_dollar_value",
    "any_officer_or_director", "severity",
]


def filter_open_market_purchases(transactions: pd.DataFrame) -> pd.DataFrame:
    """Keep only genuine open-market buys with valid share/price data."""
    if transactions.empty:
        return transactions.assign(dollar_value=pd.Series(dtype=float))

    df = transactions.copy()
    df = df[df["transaction_code"] == "P"]
    df = df[(df["shares"] > 0) & (df["price"] > 0)]
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df = df.dropna(subset=["transaction_date"])
    df["dollar_value"] = df["shares"] * df["price"]
    return df.reset_index(drop=True)


def classify_severity(n_insiders: int, total_dollars: float, has_officer_or_director: bool) -> str:
    if not has_officer_or_director:
        return "medium"
    if n_insiders >= SEVERITY_HIGH_INSIDERS or total_dollars >= SEVERITY_HIGH_DOLLARS:
        return "high"
    return "medium"


def detect_clusters(purchases: pd.DataFrame) -> pd.DataFrame:
    """
    For each issuer, slide a CLUSTER_WINDOW_DAYS window anchored at each
    purchase date and flag the issuer if at least MIN_DISTINCT_INSIDERS
    distinct insiders bought within it. One row per flagged issuer (the
    strongest overlapping window wins).
    """
    if purchases.empty:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)

    clusters = []
    for issuer_cik, group in purchases.groupby("issuer_cik"):
        group = group.sort_values("transaction_date")
        for anchor in group["transaction_date"].tolist():
            window_end = anchor + pd.Timedelta(days=CLUSTER_WINDOW_DAYS)
            window = group[(group["transaction_date"] >= anchor) & (group["transaction_date"] <= window_end)]
            distinct_insiders = window["insider_cik"].nunique()
            if distinct_insiders < MIN_DISTINCT_INSIDERS:
                continue
            total_dollars = float(window["dollar_value"].sum())
            any_officer_or_director = bool((window["is_officer"] | window["is_director"]).any())
            clusters.append({
                "issuer_cik": issuer_cik,
                "issuer_name": group["issuer_name"].iloc[0],
                "ticker": group["ticker"].iloc[0],
                "window_start": anchor,
                "window_end": window_end,
                "n_distinct_insiders": distinct_insiders,
                "insiders": sorted(window["insider_name"].unique().tolist()),
                "total_dollar_value": round(total_dollars, 2),
                "any_officer_or_director": any_officer_or_director,
                "severity": classify_severity(distinct_insiders, total_dollars, any_officer_or_director),
            })

    if not clusters:
        return pd.DataFrame(columns=CLUSTER_COLUMNS)

    result = pd.DataFrame(clusters)
    # collapse overlapping windows per issuer down to its single strongest cluster
    result = (
        result.sort_values(["issuer_cik", "total_dollar_value"], ascending=[True, False])
        .drop_duplicates(subset=["issuer_cik"], keep="first")
        .sort_values("total_dollar_value", ascending=False)
        .reset_index(drop=True)
    )
    return result
