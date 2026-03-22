#!/usr/bin/env python3
"""
Upload Apollo Postgres backup to Google Drive.

Uses OAuth2 refresh token for personal Google Drive access.
Requires: pip install google-api-python-client google-auth google-auth-oauthlib

Setup (run once locally):
  python3 gdrive_backup.py --setup credentials.json

Usage (daily from cron):
  python3 gdrive_backup.py /path/to/backup.sql.gz

Environment:
  GDRIVE_TOKEN_FILE — path to OAuth token JSON (default: ~/gdrive-token.json)
  GDRIVE_FOLDER_ID — Google Drive folder ID to upload into
"""
import json
import os
import sys

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def setup_token(credentials_file: str, token_file: str = "gdrive-token.json"):
    """One-time OAuth flow to generate refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(token_file, "w") as f:
        f.write(creds.to_json())
    print(f"Token saved to {token_file}")
    print("Copy this file to the prod server as ~/gdrive-token.json")


def upload_to_gdrive(file_path: str) -> str:
    """Upload a file to Google Drive. Returns file ID."""
    token_file = os.environ.get("GDRIVE_TOKEN_FILE", os.path.expanduser("~/gdrive-token.json"))
    folder_id = os.environ.get("GDRIVE_FOLDER_ID", "")

    if not os.path.exists(token_file):
        raise FileNotFoundError(f"Token file not found: {token_file}. Run --setup first.")
    if not folder_id:
        raise ValueError("GDRIVE_FOLDER_ID not set")

    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)

    file_name = os.path.basename(file_path)
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, mimetype="application/gzip", resumable=True)

    result = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return result.get("id")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <backup_file>")
        print(f"       {sys.argv[0]} --setup <credentials.json>")
        sys.exit(1)

    if sys.argv[1] == "--setup":
        creds_file = sys.argv[2] if len(sys.argv) > 2 else "credentials.json"
        setup_token(creds_file)
    else:
        file_path = sys.argv[1]
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            sys.exit(1)
        file_id = upload_to_gdrive(file_path)
        print(f"Uploaded {os.path.basename(file_path)} → {file_id}")
