"""
Google Sheets connector.

Mock mode by default: every "write" is appended to a local CSV so the
pipeline is fully runnable and demoable with zero credentials.

To go live:
  1. pip install gspread google-auth
  2. Set INSIDER_WATCH_GOOGLE_CREDS to a service-account JSON path
  3. Set INSIDER_WATCH_SHEET_ID to the target spreadsheet
  4. SheetsConnector automatically uses the real client (see _get_client)
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path


class SheetsConnector:
    def __init__(self, mock_path: str = "insider_watch_output/sheet_mirror.csv"):
        self.creds_path = os.environ.get("INSIDER_WATCH_GOOGLE_CREDS")
        self.sheet_id = os.environ.get("INSIDER_WATCH_SHEET_ID")
        self.live = bool(self.creds_path and self.sheet_id)
        self.mock_path = Path(mock_path)
        self.mock_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = self._get_client() if self.live else None

    def _get_client(self):
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            creds = Credentials.from_service_account_file(
                self.creds_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            return gspread.authorize(creds).open_by_key(self.sheet_id).sheet1
        except Exception as e:
            print(f"[sheets] live client init failed, falling back to mock: {e}")
            self.live = False
            return None

    def write_signals(self, rows: list[dict]) -> str:
        """rows: list of flagged-cluster dicts (issuer, ticker, insiders, severity, ...)"""
        timestamp = datetime.now(timezone.utc).isoformat()
        if self.live and self._client:
            for row in rows:
                self._client.append_row([timestamp, *row.values()])
            return f"[sheets] wrote {len(rows)} rows to live sheet {self.sheet_id}"

        file_exists = self.mock_path.exists()
        with open(self.mock_path, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists and rows:
                writer.writerow(["timestamp", *rows[0].keys()])
            for row in rows:
                writer.writerow([timestamp, *row.values()])
        return f"[sheets:MOCK] wrote {len(rows)} rows to {self.mock_path}"
