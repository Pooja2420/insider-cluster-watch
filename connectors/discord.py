"""
Discord connector -- mock mode by default (appends to a local log file).
Set INSIDER_WATCH_DISCORD_WEBHOOK (a channel Webhook URL) to post for real
-- no bot token or OAuth needed.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

DISCORD_CONTENT_LIMIT = 2000  # Discord webhook payload hard limit


class DiscordConnector:
    def __init__(self, mock_path: str):
        self.webhook_url = os.environ.get("INSIDER_WATCH_DISCORD_WEBHOOK")
        self.mock_path = mock_path
        if not self.webhook_url:
            os.makedirs(os.path.dirname(mock_path), exist_ok=True)

    def post_summary(self, text: str) -> str:
        content = text if len(text) <= DISCORD_CONTENT_LIMIT else text[: DISCORD_CONTENT_LIMIT - 3] + "..."
        if self.webhook_url:
            resp = requests.post(self.webhook_url, json={"content": content}, timeout=10)
            resp.raise_for_status()
            return f"[discord:live] posted (status {resp.status_code})"
        with open(self.mock_path, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {content}\n\n")
        return f"[discord:mock] appended to {self.mock_path}"
