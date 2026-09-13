"""
Gmail connector.

By design this DRAFTS the digest email rather than auto-sending it -- a
human reviews and decides whether to send, since this tool's whole purpose
is surfacing a signal for a person to act on, not acting autonomously.

Mock mode by default: writes the draft to a local .eml-style file.

To go live:
  1. pip install google-api-python-client google-auth-oauthlib
  2. Complete the OAuth flow, store the token per Google's Gmail API quickstart
  3. Set INSIDER_WATCH_GMAIL_TOKEN to the token path
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


class GmailConnector:
    def __init__(self, mock_path: str = "insider_watch_output/drafts"):
        self.token_path = os.environ.get("INSIDER_WATCH_GMAIL_TOKEN")
        self.live = bool(self.token_path)
        self.mock_dir = Path(mock_path)
        self.mock_dir.mkdir(parents=True, exist_ok=True)

    def draft_digest(self, subject: str, body: str, to: str) -> str:
        if self.live:
            try:
                return self._create_live_draft(subject, body, to)
            except Exception as e:
                print(f"[gmail] live draft failed, falling back to mock: {e}")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        path = self.mock_dir / f"digest_{timestamp}.eml"
        with open(path, "w") as f:
            f.write(f"To: {to}\nSubject: {subject}\n\n{body}\n")
        return f"[gmail:MOCK] draft saved to {path} (not sent — awaiting human review)"

    def _create_live_draft(self, subject: str, body: str, to: str) -> str:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        import base64
        from email.mime.text import MIMEText

        creds = Credentials.from_authorized_user_file(self.token_path)
        service = build("gmail", "v1", credentials=creds)
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        return "[gmail] draft created in live account (not sent)"
