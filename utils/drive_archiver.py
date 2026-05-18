"""
utils/drive_archiver.py
────────────────────────
BONUS: Saves a copy of the generated PDF to a Google Drive folder.

Auth: Same service-account credentials as sheets_logger.py
Set GOOGLE_DRIVE_FOLDER_ID to the target Drive folder ID in .env.
The service account must have Editor access to that folder.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]


def archive_to_drive(pdf_path: str, company_name: str) -> Optional[str]:
    """
    Upload the PDF to the configured Google Drive folder.

    Args:
        pdf_path:     Local path to the PDF file.
        company_name: Used to build a readable filename in Drive.

    Returns:
        The Drive file ID of the uploaded file, or None on failure.
    """
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        logger.debug("GOOGLE_DRIVE_FOLDER_ID not set — skipping Drive archiving")
        return None

    service = _get_drive_service()
    filename = Path(pdf_path).name

    try:
        from googleapiclient.http import MediaFileUpload

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
            "mimeType": "application/pdf",
        }
        media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
        ).execute()

        file_id   = file.get("id")
        view_link = file.get("webViewLink")
        logger.info(
            "PDF archived to Drive: %s (ID: %s, Link: %s)",
            filename, file_id, view_link
        )
        return file_id

    except Exception as exc:
        logger.error("Drive upload failed: %s", exc, exc_info=True)
        raise


def _get_drive_service():
    """Build and return an authorised Google Drive API service object."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        if sa_file and os.path.exists(sa_file):
            creds = service_account.Credentials.from_service_account_file(
                sa_file, scopes=_SCOPES
            )
        else:
            import google.auth
            creds, _ = google.auth.default(scopes=_SCOPES)

        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. "
            "Run: pip install google-api-python-client google-auth"
        )
