"""
One-time local OAuth setup for the Gmail connector.

Run this once: it opens your browser, you sign in and click Allow, and it
saves an authorized token to credentials/token.json. After that, set
INSIDER_WATCH_GMAIL_TOKEN=credentials/token.json and GmailConnector will
create real drafts instead of writing mock .eml files.

Only requests the "gmail.compose" scope -- enough to create drafts, not to
read or send mail outright.

Requires: pip install google-api-python-client google-auth-oauthlib
"""
from __future__ import annotations

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
CLIENT_SECRET_PATH = Path(__file__).parent.parent / "credentials" / "client_secret.json"
TOKEN_PATH = Path(__file__).parent.parent / "credentials" / "token.json"

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Saved token to {TOKEN_PATH}")
    print(f'Now run: export INSIDER_WATCH_GMAIL_TOKEN="{TOKEN_PATH}"')
