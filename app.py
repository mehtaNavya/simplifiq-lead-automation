"""
SimplifIQ Lead Automation System
=================================
Main Flask application that orchestrates the entire lead intake workflow:
1. Receive & validate lead form submission
2. Enrich company data from public sources
3. Generate a personalized AI-powered PDF audit report
4. Send the report to the prospect via email
5. (Bonus) Log lead to Google Sheets + archive PDF to Google Drive
"""

import os
import logging
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv

from utils.enrichment import enrich_company
from utils.report_generator import generate_pdf_report
from utils.email_sender import send_report_email
from utils.sheets_logger import log_to_sheets
from utils.drive_archiver import archive_to_drive
from utils.validators import validate_lead_form

# ── Setup ──────────────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Ensure output directories exist
os.makedirs("reports", exist_ok=True)
os.makedirs("logs", exist_ok=True)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the lead intake form."""
    return render_template("index.html")


@app.route("/health")
def health():
    """Simple health-check endpoint."""
    return jsonify({"status": "ok", "service": "SimplifIQ Lead Automation"})


@app.route("/submit-lead", methods=["POST"])
def submit_lead():
    """
    Core endpoint — receives form data and triggers the full automation pipeline.

    Expects JSON body:
        {
            "name":        "Jane Smith",
            "email":       "jane@acme.com",
            "company":     "Acme Corp",
            "website":     "https://acme.com",          # optional
            "industry":    "SaaS",                       # optional
            "role":        "Head of Sales",              # optional
            "description": "We sell B2B analytics..."   # optional
        }

    Returns JSON with pipeline status and any errors encountered.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    logger.info("Lead received: %s <%s>", data.get("company"), data.get("email"))

    # ── 1. Validate ─────────────────────────────────────────────────────────
    errors = validate_lead_form(data)
    if errors:
        logger.warning("Validation failed: %s", errors)
        return jsonify({"success": False, "errors": errors}), 400

    lead = {
        "name":        data.get("name", "").strip(),
        "email":       data.get("email", "").strip().lower(),
        "company":     data.get("company", "").strip(),
        "website":     data.get("website", "").strip(),
        "industry":    data.get("industry", "").strip(),
        "role":        data.get("role", "").strip(),
        "description": data.get("description", "").strip(),
    }

    pipeline_status = {
        "enrichment":  "pending",
        "pdf":         "pending",
        "email":       "pending",
        "sheets":      "skipped",
        "drive":       "skipped",
    }

    # ── 2. Enrich company data ───────────────────────────────────────────────
    try:
        enriched = enrich_company(lead)
        lead.update(enriched)
        pipeline_status["enrichment"] = "success"
        logger.info("Enrichment complete for %s", lead["company"])
    except Exception as exc:
        logger.error("Enrichment failed: %s", exc, exc_info=True)
        pipeline_status["enrichment"] = f"failed: {exc}"
        # Non-fatal — continue with whatever data we have

    # ── 3. Generate PDF report ───────────────────────────────────────────────
    pdf_path = None
    try:
        pdf_path = generate_pdf_report(lead)
        pipeline_status["pdf"] = "success"
        logger.info("PDF generated: %s", pdf_path)
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc, exc_info=True)
        pipeline_status["pdf"] = f"failed: {exc}"
        return jsonify({
            "success": False,
            "message": "Report generation failed — no email sent.",
            "pipeline": pipeline_status,
        }), 500

    # ── 4. Send email ────────────────────────────────────────────────────────
    try:
        send_report_email(lead, pdf_path)
        pipeline_status["email"] = "success"
        logger.info("Email sent to %s", lead["email"])
    except Exception as exc:
        logger.error("Email delivery failed: %s", exc, exc_info=True)
        pipeline_status["email"] = f"failed: {exc}"
        # Non-fatal — report was still generated

    # ── 5. (Bonus) Google Sheets logging ────────────────────────────────────
    sheets_enabled = os.getenv("GOOGLE_SHEETS_ID")
    if sheets_enabled:
        try:
            log_to_sheets(lead, pipeline_status)
            pipeline_status["sheets"] = "success"
        except Exception as exc:
            logger.warning("Sheets logging failed: %s", exc)
            pipeline_status["sheets"] = f"failed: {exc}"

    # ── 6. (Bonus) Google Drive archiving ────────────────────────────────────
    drive_enabled = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    if drive_enabled and pdf_path:
        try:
            archive_to_drive(pdf_path, lead["company"])
            pipeline_status["drive"] = "success"
        except Exception as exc:
            logger.warning("Drive archiving failed: %s", exc)
            pipeline_status["drive"] = f"failed: {exc}"

    logger.info("Pipeline complete for %s: %s", lead["company"], pipeline_status)
    return jsonify({
        "success": True,
        "message": f"Your personalised audit report has been sent to {lead['email']}.",
        "pipeline": pipeline_status,
    })


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting SimplifIQ on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
