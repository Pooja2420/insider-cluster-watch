"""
Data layer for Insider Cluster Watch.

Pulls LIVE insider-transaction disclosures (SEC Form 4) directly from SEC
EDGAR's public, free, real-time filings feed. Every transaction this module
returns is a real, publicly-filed disclosure -- there is no synthetic or
mocked data anywhere in this module.

SEC EDGAR asks every caller to identify itself with a real User-Agent
string. Set INSIDER_WATCH_CONTACT to "Your Name your@email.com" before
running; it falls back to a generic placeholder otherwise (fine for local
testing, but SEC may rate-limit or block anonymous-looking traffic).
"""
from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict

import pandas as pd
import requests

FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom&count={count}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _user_agent() -> str:
    # os.environ.get's default only applies when the key is absent -- an
    # empty string (e.g. an unset GitHub Actions repo variable still gets
    # passed through as "") would otherwise slip past it and get this
    # request rejected by SEC with a 403.
    return os.environ.get("INSIDER_WATCH_CONTACT") or "InsiderClusterWatch hackathon-demo@example.com"


def _get(url: str, session: requests.Session) -> requests.Response:
    resp = session.get(url, headers={"User-Agent": _user_agent()}, timeout=15)
    resp.raise_for_status()
    return resp


@dataclass
class Transaction:
    issuer_cik: str
    issuer_name: str
    ticker: str
    insider_name: str
    insider_cik: str
    is_officer: bool
    is_director: bool
    is_ten_pct_owner: bool
    officer_title: str
    transaction_date: str
    transaction_code: str
    shares: float
    price: float
    source_filing_url: str


def fetch_recent_filing_index_urls(session: requests.Session, count: int = 100) -> list[str]:
    """Return the -index.htm URLs for the most recent Form 4 filings, newest first."""
    import xml.etree.ElementTree as ET

    resp = _get(FEED_URL.format(count=count), session)
    root = ET.fromstring(resp.content)
    urls = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        link_el = entry.find(f"{ATOM_NS}link")
        if link_el is not None and link_el.get("href"):
            urls.append(link_el.get("href"))
    return urls


def _find_ownership_xml_url(index_url: str, session: requests.Session) -> str | None:
    resp = _get(index_url, session)
    base = index_url.rsplit("/", 1)[0]
    candidates = sorted(set(re.findall(r'href="([^"]+\.xml)"', resp.text)))
    for c in candidates:
        if "index" not in c.lower():
            return c if c.startswith("http") else f"{base}/{c.rsplit('/', 1)[-1]}"
    return None


def _bool(el) -> bool:
    return el is not None and (el.text or "").strip().lower() == "true"


def parse_ownership_xml(xml_bytes: bytes, source_filing_url: str) -> list[Transaction]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)
    issuer = root.find("issuer")
    if issuer is None:
        return []
    issuer_cik = (issuer.findtext("issuerCik") or "").strip()
    issuer_name = (issuer.findtext("issuerName") or "").strip()
    ticker = (issuer.findtext("issuerTradingSymbol") or "").strip()

    transactions: list[Transaction] = []
    for owner in root.findall("reportingOwner"):
        owner_id = owner.find("reportingOwnerId")
        if owner_id is None:
            continue
        insider_name = (owner_id.findtext("rptOwnerName") or "").strip()
        insider_cik = (owner_id.findtext("rptOwnerCik") or "").strip()
        rel = owner.find("reportingOwnerRelationship")
        is_officer = _bool(rel.find("isOfficer")) if rel is not None else False
        is_director = _bool(rel.find("isDirector")) if rel is not None else False
        is_ten_pct = _bool(rel.find("isTenPercentOwner")) if rel is not None else False
        officer_title = (rel.findtext("officerTitle") or "").strip() if rel is not None else ""

        for table_name in ("nonDerivativeTable", "derivativeTable"):
            table = root.find(table_name)
            if table is None:
                continue
            tx_tag = table_name[:-5] + "Transaction"
            for tx in table.findall(tx_tag):
                code = (tx.findtext("transactionCoding/transactionCode") or "").strip()
                shares_str = tx.findtext("transactionAmounts/transactionShares/value")
                price_str = tx.findtext("transactionAmounts/transactionPricePerShare/value")
                date_str = (tx.findtext("transactionDate/value") or "").strip()
                if shares_str is None or price_str is None or not date_str:
                    continue
                try:
                    shares = float(shares_str)
                    price = float(price_str)
                except ValueError:
                    continue
                transactions.append(Transaction(
                    issuer_cik=issuer_cik,
                    issuer_name=issuer_name,
                    ticker=ticker,
                    insider_name=insider_name,
                    insider_cik=insider_cik,
                    is_officer=is_officer,
                    is_director=is_director,
                    is_ten_pct_owner=is_ten_pct,
                    officer_title=officer_title,
                    transaction_date=date_str,
                    transaction_code=code,
                    shares=shares,
                    price=price,
                    source_filing_url=source_filing_url,
                ))
    return transactions


def _fetch_one_filing(index_url: str, session: requests.Session) -> list[Transaction]:
    xml_url = _find_ownership_xml_url(index_url, session)
    if not xml_url:
        return []
    try:
        xml_resp = _get(xml_url, session)
    except requests.RequestException:
        return []
    return parse_ownership_xml(xml_resp.content, source_filing_url=xml_url)


def fetch_recent_transactions(max_filings: int = 60, max_workers: int = 5) -> pd.DataFrame:
    """
    Pull the most recent Form 4 filings from SEC EDGAR's live feed and
    return one row per reported transaction. Real, live, public data --
    the source-of-truth swap point if EDGAR's format ever changes.
    """
    columns = [
        "issuer_cik", "issuer_name", "ticker", "insider_name", "insider_cik",
        "is_officer", "is_director", "is_ten_pct_owner", "officer_title",
        "transaction_date", "transaction_code", "shares", "price", "source_filing_url",
    ]

    session = requests.Session()
    index_urls = fetch_recent_filing_index_urls(session, count=max_filings)

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one_filing, url, session): url for url in index_urls}
        for future in as_completed(futures):
            for tx in future.result():
                rows.append(asdict(tx))

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns]
