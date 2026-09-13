"""
Slack connector -- mock mode by default (appends to a local log file so the
pipeline is fully runnable and demoable with zero credentials). Set
INSIDER_WATCH_SLACK_WEBHOOK (an Incoming Webhook URL) to post for real --
no bot token or OAuth needed.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests


class SlackConnector:
    def __init__(self, mock_path: str):
        self.webhook_url = os.environ.get("INSIDER_WATCH_SLACK_WEBHOOK")
        self.mock_path = mock_path
        if not self.webhook_url:
            os.makedirs(os.path.dirname(mock_path), exist_ok=True)

    def post_summary(self, text: str) -> str:
        if self.webhook_url:
            resp = requests.post(self.webhook_url, json={"text": text}, timeout=10)
            resp.raise_for_status()
            return f"[slack:live] posted (status {resp.status_code})"
        with open(self.mock_path, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {text}\n\n")
        return f"[slack:mock] appended to {self.mock_path}"
