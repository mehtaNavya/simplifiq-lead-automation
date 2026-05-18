"""
utils/sheets_logger.py
───────────────────────
BONUS: Appends each submitted lead's data to a Google Sheet.

Auth: Service account JSON key (path set via GOOGLE_SERVICE_ACCOUNT_FILE env var)
      OR Application Default Credentials (gcloud auth, Cloud Run, etc.)

The sheet must be shared with the service account email.
Set GOOGLE_SHEETS_ID to the spreadsheet ID in .env.

Sheet columns (auto-created if sheet is blank):
  Timestamp | Name | Email | Company | Website | Industry | Role |
  Enrichment Status | PDF Status | Email Status
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_HEADER = [
    "Timestamp", "Name", "Email", "Company", "Website",
    "Industry", "Role", "Enrichment", "PDF", "Email Status",
]


def log_to_sheets(lead: Dict[str, Any], pipeline_status: Dict[str, str]) -> None:
    """
    Append one row of lead + pipeline metadata to the configured Google Sheet.

    Args:
        lead:            Enriched lead dict.
        pipeline_status: Dict with keys 'enrichment', 'pdf', 'email'.
    """
    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        logger.debug("GOOGLE_SHEETS_ID not set — skipping Sheets logging")
        return

    service = _get_sheets_service()
    sheet_name = os.getenv("GOOGLE_SHEETS_TAB", "Leads")

    # Ensure header row exists
    _ensure_header(service, sheets_id, sheet_name)

    row = [
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        lead.get("name", ""),
        lead.get("email", ""),
        lead.get("company", ""),
        lead.get("website", ""),
        lead.get("industry", ""),
        lead.get("role", ""),
        pipeline_status.get("enrichment", ""),
        pipeline_status.get("pdf", ""),
        pipeline_status.get("email", ""),
    ]

    body = {"values": [row]}
    service.spreadsheets().values().append(
        spreadsheetId=sheets_id,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()

    logger.info("Lead logged to Google Sheet (ID: %s)", sheets_id)


def _ensure_header(service, sheets_id: str, sheet_name: str) -> None:
    """Write column headers if A1 is empty."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheets_id,
            range=f"{sheet_name}!A1:A1",
        ).execute()
        values = result.get("values", [])
        if not values:
            service.spreadsheets().values().update(
                spreadsheetId=sheets_id,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [_HEADER]},
            ).execute()
            logger.info("Header row written to sheet '%s'", sheet_name)
    except Exception as exc:
        logger.warning("Could not check/write header: %s", exc)


def _get_sheets_service():
    """Build and return an authorised Google Sheets API service object."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        if sa_file and os.path.exists(sa_file):
            creds = service_account.Credentials.from_service_account_file(
                sa_file, scopes=_SCOPES
            )
        else:
            # Fall back to Application Default Credentials
            import google.auth
            creds, _ = google.auth.default(scopes=_SCOPES)

        return build("sheets", "v4", credentials=creds, cache_discovery=False)
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. "
            "Run: pip install google-api-python-client google-auth"
        )
