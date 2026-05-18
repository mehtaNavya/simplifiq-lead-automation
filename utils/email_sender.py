"""
utils/email_sender.py
──────────────────────
Sends the generated PDF report to the prospect via email.

Supports two back-ends (checked in order):
  1. SendGrid (SENDGRID_API_KEY env var)
  2. SMTP     (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS env vars)

The email is HTML with a personal greeting and the PDF attached.
"""

import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def send_report_email(lead: Dict[str, Any], pdf_path: str) -> None:
    """
    Send the audit report PDF to the lead.

    Args:
        lead:     Enriched lead dict (must have 'email', 'name', 'company').
        pdf_path: Absolute path to the generated PDF.

    Raises:
        RuntimeError: If no sending back-end is configured.
        Exception:    Propagated from the underlying transport on failure.
    """
    to_email = lead["email"]
    to_name  = lead.get("name", "there")
    company  = lead.get("company", "your company")

    subject  = f"Your AI Readiness Audit — {company} | SimplifIQ"
    html_body = _build_html(to_name, company)
    text_body = _build_plain(to_name, company)

    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    if sendgrid_key:
        _send_via_sendgrid(sendgrid_key, to_email, subject, html_body, text_body, pdf_path)
    else:
        _send_via_smtp(to_email, subject, html_body, text_body, pdf_path)

    logger.info("Email dispatched to %s for company '%s'", to_email, company)


# ── SendGrid ───────────────────────────────────────────────────────────────────

def _send_via_sendgrid(
    api_key: str,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    pdf_path: str,
) -> None:
    """Send via SendGrid Mail Send API v3 (no SDK required)."""
    import base64
    import json

    import requests

    pdf_data = Path(pdf_path).read_bytes()
    pdf_b64  = base64.b64encode(pdf_data).decode()
    filename = Path(pdf_path).name

    from_email = os.getenv("FROM_EMAIL", "hello@simplifiq.ai")
    from_name  = os.getenv("FROM_NAME", "SimplifIQ")

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": from_name},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text_body},
            {"type": "text/html",  "value": html_body},
        ],
        "attachments": [
            {
                "content":     pdf_b64,
                "type":        "application/pdf",
                "filename":    filename,
                "disposition": "attachment",
            }
        ],
    }

    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        data=json.dumps(payload),
        timeout=20,
    )
    resp.raise_for_status()
    logger.info("SendGrid accepted email (status %d)", resp.status_code)


# ── SMTP ───────────────────────────────────────────────────────────────────────

def _send_via_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    pdf_path: str,
) -> None:
    """Send via SMTP — works with Gmail (app password), Mailgun SMTP, etc."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    from_email = os.getenv("FROM_EMAIL", smtp_user or "hello@simplifiq.ai")
    from_name  = os.getenv("FROM_NAME", "SimplifIQ")

    if not smtp_host or not smtp_user or not smtp_pass:
        raise RuntimeError(
            "No email back-end configured. Set either SENDGRID_API_KEY or "
            "SMTP_HOST + SMTP_USER + SMTP_PASS in your .env file."
        )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"{from_name} <{from_email}>"
    msg["To"]      = to_email

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html",  "utf-8"))
    msg.attach(alt)

    # Attach PDF
    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "pdf")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=Path(pdf_path).name)
    msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())

    logger.info("SMTP email sent via %s:%d", smtp_host, smtp_port)


# ── Email templates ────────────────────────────────────────────────────────────

def _build_html(name: str, company: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Your AI Readiness Audit</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 16px;">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);">

        <!-- Header -->
        <tr>
          <td style="background:#0d1b2a;padding:32px 40px;">
            <p style="margin:0;font-size:11px;letter-spacing:3px;color:#00b4d8;text-transform:uppercase;font-weight:700;">SimplifIQ</p>
            <h1 style="margin:12px 0 0;font-size:26px;color:#ffffff;font-weight:700;line-height:1.3;">
              Your AI Readiness Audit<br>is Ready, {name.split()[0]}
            </h1>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:36px 40px;">
            <p style="margin:0 0 16px;font-size:15px;color:#0d1b2a;line-height:1.7;">
              Hi {name.split()[0]},
            </p>
            <p style="margin:0 0 16px;font-size:15px;color:#0d1b2a;line-height:1.7;">
              Thank you for your interest in SimplifIQ. We've prepared a personalised 
              <strong>AI Readiness &amp; Growth Audit</strong> for <strong>{company}</strong> 
              based on your submission and our initial research.
            </p>
            <p style="margin:0 0 24px;font-size:15px;color:#0d1b2a;line-height:1.7;">
              Inside the attached report you'll find:
            </p>
            <ul style="margin:0 0 24px;padding-left:20px;font-size:15px;color:#0d1b2a;line-height:2;">
              <li>An AI Readiness Scorecard across 4 dimensions</li>
              <li>Tailored growth opportunity areas for {company}</li>
              <li>Quick wins you can action in the next 30 days</li>
              <li>Recommended tools &amp; their potential ROI</li>
              <li>A prioritised roadmap with clear next steps</li>
            </ul>
            <p style="margin:0 0 32px;font-size:15px;color:#0d1b2a;line-height:1.7;">
              We'd love to walk you through the findings in a brief 20-minute call — 
              just reply to this email to schedule.
            </p>
            <a href="mailto:hello@simplifiq.ai?subject=Audit%20Call%20—%20{company}"
               style="display:inline-block;background:#00b4d8;color:#ffffff;font-weight:700;
                      font-size:14px;padding:14px 28px;border-radius:6px;text-decoration:none;">
              Book a Discovery Call →
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f0f4f8;padding:20px 40px;border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:12px;color:#6b7a8d;line-height:1.6;">
              SimplifIQ · hello@simplifiq.ai · www.simplifiq.ai<br>
              You're receiving this because you submitted a lead form on our website.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_plain(name: str, company: str) -> str:
    first = name.split()[0]
    return f"""Hi {first},

Thank you for your interest in SimplifIQ.

We've prepared a personalised AI Readiness & Growth Audit for {company}.
Please find the report attached to this email.

The report includes:
- AI Readiness Scorecard
- Tailored growth opportunities
- 30-day quick wins
- Recommended tools & ROI estimates
- Prioritised next steps

Reply to this email to schedule a 20-minute walkthrough call.

Best regards,
The SimplifIQ Team
hello@simplifiq.ai | www.simplifiq.ai
"""
