"""
utils/validators.py
────────────────────
Input validation for the lead intake form.
Returns a list of human-readable error strings (empty = valid).
"""

import re
from typing import Any, Dict, List

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE   = re.compile(r"^https?://[^\s]+$")


def validate_lead_form(data: Dict[str, Any]) -> List[str]:
    """
    Validate required fields and basic format checks.

    Args:
        data: Raw dict from request body / form.

    Returns:
        List of error messages. Empty list means the form is valid.
    """
    errors: List[str] = []

    # ── Required fields ────────────────────────────────────────────────────
    required = {
        "name":    "Full name",
        "email":   "Email address",
        "company": "Company name",
    }
    for field, label in required.items():
        value = (data.get(field) or "").strip()
        if not value:
            errors.append(f"{label} is required.")

    # ── Email format ───────────────────────────────────────────────────────
    email = (data.get("email") or "").strip()
    if email and not _EMAIL_RE.match(email):
        errors.append("Email address format is invalid.")

    # ── Optional URL format ────────────────────────────────────────────────
    website = (data.get("website") or "").strip()
    if website and not _URL_RE.match(website):
        errors.append("Website URL must start with http:// or https://")

    # ── Length guards ──────────────────────────────────────────────────────
    name = (data.get("name") or "").strip()
    if name and len(name) > 120:
        errors.append("Name must be 120 characters or fewer.")

    company = (data.get("company") or "").strip()
    if company and len(company) > 200:
        errors.append("Company name must be 200 characters or fewer.")

    description = (data.get("description") or "").strip()
    if description and len(description) > 2000:
        errors.append("Description must be 2 000 characters or fewer.")

    return errors
