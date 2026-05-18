# SimplifIQ — Automated Lead Intake & AI Audit Report System

> A fully automated pipeline that captures prospect data, enriches it from public sources, generates a personalised AI-powered PDF audit report, and emails it to the lead — all without human intervention.

---

## Architecture Overview

```
Lead Form (Browser)
      │ POST /submit-lead
      ▼
┌─────────────────────────────────────────────────────────┐
│                    Flask Backend                         │
│                                                         │
│  1. Validate         → validators.py                   │
│  2. Enrich           → enrichment.py                   │
│     ├─ Scrape website (meta, tech stack, socials)      │
│     ├─ DuckDuckGo Instant Answer API                   │
│     └─ Wikipedia REST API                              │
│  3. Generate PDF     → report_generator.py             │
│     ├─ Claude API  → structured JSON report content    │
│     └─ ReportLab   → polished multi-page PDF           │
│  4. Send email       → email_sender.py                 │
│     ├─ SendGrid (preferred)                            │
│     └─ SMTP fallback                                   │
│  5. [BONUS] Log      → sheets_logger.py               │
│  6. [BONUS] Archive  → drive_archiver.py              │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+ / Flask 3 |
| AI Report Generation | Anthropic Claude (claude-sonnet-4-20250514) |
| PDF Rendering | ReportLab 4 |
| Data Enrichment | BeautifulSoup4, DuckDuckGo API, Wikipedia API |
| Email | SendGrid API v3 / SMTP |
| Bonus — Sheets | Google Sheets API v4 |
| Bonus — Drive | Google Drive API v3 |
| Frontend | Vanilla HTML/CSS/JS (served by Flask) |

---

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/your-username/simplifiq-lead-automation.git
cd simplifiq-lead-automation

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys (see Configuration section below)
```

### 3. Run

```bash
python app.py
# → http://localhost:5000
```

---

## Configuration

Edit `.env` — minimum required keys for full functionality:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ Yes | Powers the AI report generation |
| `SENDGRID_API_KEY` | One of these | SendGrid email delivery |
| `SMTP_HOST` + `SMTP_USER` + `SMTP_PASS` | One of these | SMTP email delivery |
| `FROM_EMAIL` | ✅ Yes | Sender email address |
| `GOOGLE_SHEETS_ID` | Optional (bonus) | Enable Google Sheets logging |
| `GOOGLE_DRIVE_FOLDER_ID` | Optional (bonus) | Enable Drive PDF archiving |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | If using Google APIs | Path to service account JSON |

### Email setup options

**Option A — SendGrid (recommended)**
1. Create account at [sendgrid.com](https://sendgrid.com) (free tier: 100 emails/day)
2. Create an API key with "Mail Send" permission
3. Set `SENDGRID_API_KEY=SG.xxxxx` in `.env`
4. Verify your sender email in SendGrid dashboard

**Option B — Gmail SMTP**
1. Enable 2-Step Verification on your Google account
2. Generate an App Password: Account → Security → App Passwords
3. Set in `.env`:
   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your@gmail.com
   SMTP_PASS=xxxx xxxx xxxx xxxx    # 16-char app password
   ```

### Google APIs setup (bonus features)

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable **Google Sheets API** and **Google Drive API**
3. Create a **Service Account** and download the JSON key
4. Save key as `service_account.json` in project root
5. Share your Google Sheet / Drive folder with the service account email
6. Set `GOOGLE_SHEETS_ID` and/or `GOOGLE_DRIVE_FOLDER_ID` in `.env`

---

## API Reference

### `POST /submit-lead`

**Request body (JSON):**
```json
{
  "name":        "Jane Smith",         // required
  "email":       "jane@acme.com",      // required
  "company":     "Acme Corp",          // required
  "website":     "https://acme.com",   // optional
  "industry":    "SaaS / Software",    // optional
  "role":        "Head of Operations", // optional
  "description": "We build B2B..."     // optional
}
```

**Success response (200):**
```json
{
  "success": true,
  "message": "Your personalised audit report has been sent to jane@acme.com.",
  "pipeline": {
    "enrichment": "success",
    "pdf":        "success",
    "email":      "success",
    "sheets":     "success",
    "drive":      "success"
  }
}
```

**Validation error (400):**
```json
{
  "success": false,
  "errors": ["Full name is required.", "Email address format is invalid."]
}
```

### `GET /health`
Returns `{"status": "ok"}` — useful for uptime monitoring.

---

## PDF Report Structure

The generated PDF includes:

1. **Cover Page** — company name, date, prepared-for details
2. **Executive Summary** — AI-written, 200–300 words personalised to the company
3. **Company Snapshot** — what they do, market position, digital maturity
4. **AI Readiness Scorecard** — 5 dimensions with visual bar indicators (0–100)
5. **Growth Opportunity Areas** — 4–5 tailored opportunities with impact/effort ratings
6. **Quick Wins** — 3 actions actionable in 30 days
7. **Recommended Tools** — table with use-case and estimated ROI
8. **Risks to Address** — severity-coded risk items
9. **Next Steps** — prioritised roadmap with timeline and owner
10. **Closing Note** — personalised call-to-action

---

## Design Decisions & Tradeoffs

| Decision | Reasoning |
|---|---|
| No external scraping proxy | Uses direct HTTP requests with a polite user-agent; respects robots.txt implicitly via timeouts and rate limits |
| Graceful enrichment failure | Enrichment errors are non-fatal — the pipeline continues with whatever data is available |
| Claude JSON output | Structured JSON prompt gives deterministic parsing; fallback template handles JSON parse failures |
| ReportLab over WeasyPrint | No OS-level dependencies (Chrome/Chromium), faster, and fully portable |
| SendGrid + SMTP dual support | Flexibility for different deployment environments without changing code |
| Synchronous pipeline | Simpler for a prototype; in production, replace with Celery + Redis for async processing |

---

## Project Structure

```
simplifiq/
├── app.py                    # Flask app, route handlers
├── requirements.txt
├── .env.example              # Environment variable template
├── README.md
├── templates/
│   └── index.html            # Lead intake form
├── utils/
│   ├── __init__.py
│   ├── validators.py         # Form validation
│   ├── enrichment.py         # Company data enrichment
│   ├── report_generator.py   # AI + PDF generation
│   ├── email_sender.py       # SendGrid / SMTP email
│   ├── sheets_logger.py      # Bonus: Google Sheets
│   └── drive_archiver.py     # Bonus: Google Drive
├── reports/                  # Generated PDFs (gitignored)
└── logs/                     # App logs (gitignored)
```

---

## Limitations & Production Notes

- **Rate limits**: DuckDuckGo and Wikipedia APIs are rate-limited. Under high load, some enrichment calls may be skipped.
- **Website scraping**: Some sites block scrapers via Cloudflare or JavaScript rendering. The system falls back gracefully.
- **Async processing**: For production, wrap the pipeline in a Celery task and return a job ID immediately, then poll for status.
- **PDF storage**: Currently written to local disk. In production, upload to S3/GCS.
- **Security**: Add CSRF protection and rate limiting (e.g., Flask-Limiter) before exposing publicly.

---

## License

MIT — see LICENSE file.
