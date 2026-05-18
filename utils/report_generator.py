"""
utils/report_generator.py
──────────────────────────
Generates a beautiful, personalised PDF audit report for a prospect.

Pipeline:
  1. Call Claude (Anthropic API) to produce structured JSON report content
     tailored to the company's industry, products, and challenges.
  2. Render the JSON into a polished multi-page PDF with ReportLab.

The PDF is saved to reports/<sanitised_company_name>_<timestamp>.pdf
and the full path is returned.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import anthropic
import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import KeepTogether

logger = logging.getLogger(__name__)

# ── Brand palette ──────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#0D1B2A")
TEAL   = colors.HexColor("#00B4D8")
LIGHT  = colors.HexColor("#F0F4F8")
MUTED  = colors.HexColor("#6B7A8D")
WHITE  = colors.white
ACCENT = colors.HexColor("#FF6B35")

W, H = A4
MARGIN = 2.2 * cm

_REPORT_DIR = Path("reports")
_REPORT_DIR.mkdir(exist_ok=True)


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_pdf_report(lead: Dict[str, Any]) -> str:
    """
    Orchestrate AI content generation + PDF rendering.

    Args:
        lead: Enriched lead dict.

    Returns:
        Absolute path to the saved PDF file.
    """
    logger.info("Generating report for %s", lead.get("company"))

    # 1. Get AI-generated content
    report_data = _generate_ai_content(lead)

    # 2. Render PDF
    filename = _safe_filename(lead.get("company", "report"))
    pdf_path  = str(_REPORT_DIR / filename)
    _render_pdf(lead, report_data, pdf_path)

    logger.info("PDF saved to %s", pdf_path)
    return pdf_path


# ── AI content generation ──────────────────────────────────────────────────────

def _generate_ai_content(lead: Dict[str, Any]) -> Dict:
    """
    Ask Claude to produce a structured JSON audit report for the company.
    Falls back to a sensible template if the API call fails.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — using template fallback")
        return _fallback_content(lead)

    company     = lead.get("company", "your company")
    industry    = lead.get("industry", "technology")
    description = lead.get("description_enriched") or lead.get("description", "")
    tech_stack  = ", ".join(lead.get("tech_stack_hints", [])) or "not detected"
    socials     = lead.get("social_links", {})
    website     = lead.get("website", "")

    prompt = f"""You are a senior business consultant preparing a highly personalised 
AI Readiness & Growth Audit for a prospect company. Generate ONLY valid JSON — 
no markdown fences, no preamble.

Company context:
  Name:        {company}
  Industry:    {industry}
  Website:     {website}
  Description: {description}
  Tech stack:  {tech_stack}
  Socials:     {json.dumps(socials)}

Return a JSON object with EXACTLY this schema:
{{
  "executive_summary": "2-3 paragraph personalised summary addressing their specific context (200-300 words)",
  "company_snapshot": {{
    "what_they_do": "1 crisp sentence",
    "market_position": "brief assessment of their positioning",
    "digital_maturity": "Low / Medium / High with a one-line reason"
  }},
  "opportunity_areas": [
    {{
      "title": "opportunity title",
      "description": "2-3 sentences personalised to their context",
      "impact": "High / Medium / Low",
      "effort": "High / Medium / Low"
    }}
  ],
  "ai_readiness_scores": {{
    "data_infrastructure": 72,
    "process_automation": 58,
    "team_capability":    45,
    "customer_experience": 80,
    "overall": 64
  }},
  "quick_wins": [
    "Specific actionable recommendation 1",
    "Specific actionable recommendation 2",
    "Specific actionable recommendation 3"
  ],
  "recommended_tools": [
    {{
      "name": "tool name",
      "use_case": "how it applies to this company specifically",
      "estimated_roi": "brief ROI statement"
    }}
  ],
  "risks_to_address": [
    {{
      "risk": "risk title",
      "details": "1-2 sentences",
      "severity": "High / Medium / Low"
    }}
  ],
  "next_steps": [
    {{
      "step": "action item",
      "timeline": "e.g. Week 1-2",
      "owner": "e.g. Operations Lead"
    }}
  ],
  "closing_message": "Warm, personalised closing paragraph (50-80 words) that references the company by name and invites them to connect"
}}

Generate 4-5 opportunity areas, 3-5 recommended tools, 2-3 risks, 4 next steps.
All content must be specific to {company} — avoid generic boilerplate.
Return ONLY the JSON object."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        logger.info("AI content generated successfully for %s", company)
        return data
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI JSON: %s\nRaw: %s", exc, raw[:400])
        return _fallback_content(lead)
    except Exception as exc:
        logger.error("Anthropic API call failed: %s", exc, exc_info=True)
        return _fallback_content(lead)


def _fallback_content(lead: Dict) -> Dict:
    """Static template used when the AI call fails."""
    company = lead.get("company", "Your Company")
    return {
        "executive_summary": (
            f"This audit report provides an initial assessment of {company}'s current "
            f"digital footprint and potential growth opportunities. Based on our preliminary "
            f"review, there are several high-impact areas where AI and automation can drive "
            f"meaningful efficiency gains and revenue growth. Our team has identified "
            f"key opportunities tailored to your industry and operational context."
        ),
        "company_snapshot": {
            "what_they_do": lead.get("description", f"{company} operates in the {lead.get('industry','technology')} space."),
            "market_position": "Emerging player with growth potential",
            "digital_maturity": "Medium — solid foundation with clear optimisation opportunities",
        },
        "opportunity_areas": [
            {"title": "Process Automation", "description": "Automating repetitive workflows can free up 30-40% of operational time.", "impact": "High", "effort": "Medium"},
            {"title": "AI-Powered Customer Insights", "description": "Leverage data to personalise customer interactions at scale.", "impact": "High", "effort": "Medium"},
            {"title": "Content & Marketing Automation", "description": "Streamline outreach with AI-assisted content generation.", "impact": "Medium", "effort": "Low"},
        ],
        "ai_readiness_scores": {
            "data_infrastructure": 65,
            "process_automation": 50,
            "team_capability": 55,
            "customer_experience": 70,
            "overall": 60,
        },
        "quick_wins": [
            "Implement a CRM with automated lead scoring",
            "Set up email sequence automation for follow-ups",
            "Deploy an AI chatbot for initial customer queries",
        ],
        "recommended_tools": [
            {"name": "HubSpot CRM", "use_case": "Centralise customer data and automate follow-ups", "estimated_roi": "2-3x productivity gain in sales"},
            {"name": "Zapier", "use_case": "Connect existing tools without custom development", "estimated_roi": "Save 10+ hours/week on manual tasks"},
        ],
        "risks_to_address": [
            {"risk": "Data Silos", "details": "Disconnected data sources limit analytical capability.", "severity": "Medium"},
            {"risk": "Manual Processes", "details": "High reliance on manual steps increases error rates.", "severity": "High"},
        ],
        "next_steps": [
            {"step": "Book a 30-minute discovery call with our team", "timeline": "This week", "owner": "You"},
            {"step": "Audit existing tech stack and integrations", "timeline": "Week 1-2", "owner": "Operations Lead"},
            {"step": "Define top 3 automation priorities", "timeline": "Week 2-3", "owner": "Leadership Team"},
            {"step": "Pilot first automation workflow", "timeline": "Month 1", "owner": "Tech Lead"},
        ],
        "closing_message": (
            f"We're excited about the potential we see in {company} and believe the right "
            f"AI-driven improvements can unlock significant value quickly. We'd love to walk "
            f"you through these findings in detail — reach out to schedule a personalised "
            f"strategy session."
        ),
    }


# ── PDF rendering ──────────────────────────────────────────────────────────────

def _render_pdf(lead: Dict, data: Dict, output_path: str) -> None:
    """Build and save the PDF using ReportLab Platypus."""

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2.8 * cm,
        bottomMargin=2 * cm,
        title=f"AI Readiness Audit — {lead.get('company')}",
        author="SimplifIQ",
        subject="Personalised Audit Report",
    )

    styles = _build_styles()
    story  = []

    # ── Cover section ──────────────────────────────────────────────────────
    story += _cover_section(lead, styles)
    story.append(PageBreak())

    # ── Executive summary ──────────────────────────────────────────────────
    story += _section_header("Executive Summary", styles)
    story.append(Paragraph(data.get("executive_summary", ""), styles["body"]))
    story.append(Spacer(1, 0.5 * cm))

    # ── Company snapshot ──────────────────────────────────────────────────
    snapshot = data.get("company_snapshot", {})
    if snapshot:
        story += _section_header("Company Snapshot", styles)
        snap_rows = [
            ["What They Do", snapshot.get("what_they_do", "—")],
            ["Market Position", snapshot.get("market_position", "—")],
            ["Digital Maturity", snapshot.get("digital_maturity", "—")],
        ]
        if lead.get("tech_stack_hints"):
            snap_rows.append(["Detected Tech Stack", ", ".join(lead["tech_stack_hints"])])
        story.append(_two_col_table(snap_rows, styles))
        story.append(Spacer(1, 0.5 * cm))

    # ── AI Readiness scores ────────────────────────────────────────────────
    scores = data.get("ai_readiness_scores", {})
    if scores:
        story += _section_header("AI Readiness Scorecard", styles)
        story += _scorecard(scores, styles)
        story.append(Spacer(1, 0.5 * cm))

    # ── Opportunity areas ──────────────────────────────────────────────────
    opportunities = data.get("opportunity_areas", [])
    if opportunities:
        story += _section_header("Growth Opportunity Areas", styles)
        for opp in opportunities:
            story += _opportunity_card(opp, styles)
        story.append(Spacer(1, 0.3 * cm))

    story.append(PageBreak())

    # ── Quick wins ─────────────────────────────────────────────────────────
    quick_wins = data.get("quick_wins", [])
    if quick_wins:
        story += _section_header("Quick Wins (30-Day Actions)", styles)
        for i, win in enumerate(quick_wins, 1):
            story.append(Paragraph(f"<b>{i}.</b>  {win}", styles["bullet"]))
        story.append(Spacer(1, 0.5 * cm))

    # ── Recommended tools ──────────────────────────────────────────────────
    tools = data.get("recommended_tools", [])
    if tools:
        story += _section_header("Recommended Tools", styles)
        story.append(_tools_table(tools, styles))
        story.append(Spacer(1, 0.5 * cm))

    # ── Risks ──────────────────────────────────────────────────────────────
    risks = data.get("risks_to_address", [])
    if risks:
        story += _section_header("Risks to Address", styles)
        for risk in risks:
            story += _risk_item(risk, styles)
        story.append(Spacer(1, 0.3 * cm))

    story.append(PageBreak())

    # ── Next steps ────────────────────────────────────────────────────────
    next_steps = data.get("next_steps", [])
    if next_steps:
        story += _section_header("Recommended Next Steps", styles)
        story.append(_next_steps_table(next_steps, styles))
        story.append(Spacer(1, 0.6 * cm))

    # ── Closing ───────────────────────────────────────────────────────────
    story += _section_header("A Note From SimplifIQ", styles)
    story.append(Paragraph(data.get("closing_message", ""), styles["body"]))
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=TEAL))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("SimplifIQ · hello@simplifiq.ai · www.simplifiq.ai", styles["footer"]))

    doc.build(story, onFirstPage=_page_header_footer, onLaterPages=_page_header_footer)


# ── Style helpers ──────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()

    def ps(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "h1": ps("H1", fontName="Helvetica-Bold", fontSize=26, textColor=WHITE,
                  leading=32, alignment=TA_LEFT),
        "h2": ps("H2", fontName="Helvetica-Bold", fontSize=16, textColor=NAVY,
                  leading=20, spaceAfter=4),
        "h3": ps("H3", fontName="Helvetica-Bold", fontSize=12, textColor=TEAL,
                  leading=15, spaceAfter=2),
        "body": ps("Body", fontName="Helvetica", fontSize=10, textColor=NAVY,
                    leading=15, alignment=TA_JUSTIFY),
        "bullet": ps("Bullet", fontName="Helvetica", fontSize=10, textColor=NAVY,
                      leading=14, leftIndent=10, spaceBefore=3, spaceAfter=3),
        "label": ps("Label", fontName="Helvetica-Bold", fontSize=9, textColor=MUTED,
                     leading=12),
        "value": ps("Value", fontName="Helvetica", fontSize=10, textColor=NAVY,
                     leading=13),
        "caption": ps("Caption", fontName="Helvetica-Oblique", fontSize=8,
                       textColor=MUTED, leading=10, alignment=TA_CENTER),
        "footer": ps("Footer", fontName="Helvetica", fontSize=8, textColor=MUTED,
                      alignment=TA_CENTER),
        "score_num": ps("ScoreNum", fontName="Helvetica-Bold", fontSize=20,
                         textColor=TEAL, alignment=TA_CENTER),
        "cover_sub": ps("CoverSub", fontName="Helvetica", fontSize=13,
                          textColor=colors.HexColor("#90E0EF"), leading=18),
        "cover_meta": ps("CoverMeta", fontName="Helvetica", fontSize=10,
                           textColor=colors.HexColor("#CAF0F8"), leading=14),
    }


def _page_header_footer(canvas, doc):
    """Draw the running header/footer on every page except page 1 (handled inline)."""
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        # Top bar
        canvas.setFillColor(NAVY)
        canvas.rect(0, H - 1.2 * cm, W, 1.2 * cm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(MARGIN, H - 0.75 * cm, "SimplifIQ — AI Readiness Audit")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(W - MARGIN, H - 0.75 * cm, f"Page {page}")
    # Bottom stripe
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, W, 0.4 * cm, fill=1, stroke=0)
    canvas.restoreState()


# ── Section builders ───────────────────────────────────────────────────────────

def _cover_section(lead: Dict, styles: dict) -> list:
    items = []
    # Full-width navy background block (simulated via table)
    company = lead.get("company", "Your Company")
    name    = lead.get("name", "")
    role    = lead.get("role", "")
    date_str = datetime.now().strftime("%B %Y")

    cover_content = [
        Spacer(1, 1.5 * cm),
        Paragraph("AI READINESS &amp; GROWTH AUDIT", styles["cover_sub"]),
        Spacer(1, 0.3 * cm),
        Paragraph(company, styles["h1"]),
        Spacer(1, 0.6 * cm),
        HRFlowable(width="60%", thickness=2, color=TEAL, hAlign="LEFT"),
        Spacer(1, 0.6 * cm),
    ]

    if name:
        cover_content.append(Paragraph(f"Prepared for: <b>{name}</b>{' · ' + role if role else ''}", styles["cover_meta"]))
    cover_content.append(Paragraph(f"Report Date: {date_str}", styles["cover_meta"]))
    cover_content.append(Paragraph("Prepared by: SimplifIQ", styles["cover_meta"]))
    cover_content.append(Spacer(1, 2 * cm))

    table_data = [[cover_content]]
    bg_table = Table(table_data, colWidths=[W - 2 * MARGIN])
    bg_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING",  (0, 0), (-1, -1), 30),
        ("RIGHTPADDING", (0, 0), (-1, -1), 30),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 30),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [8, 8, 8, 8]),
    ]))
    items.append(bg_table)

    # Disclaimer
    items.append(Spacer(1, 0.5 * cm))
    items.append(Paragraph(
        "This report has been automatically generated based on publicly available information "
        "and the details you provided. It is intended as a starting point for discussion.",
        styles["caption"],
    ))
    return items


def _section_header(title: str, styles: dict) -> list:
    return [
        Spacer(1, 0.4 * cm),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")),
        Spacer(1, 0.2 * cm),
        Paragraph(title.upper(), styles["h2"]),
        Spacer(1, 0.2 * cm),
    ]


def _two_col_table(rows: list, styles: dict) -> Table:
    usable = W - 2 * MARGIN
    table_data = [
        [Paragraph(row[0], styles["label"]), Paragraph(str(row[1]), styles["value"])]
        for row in rows
    ]
    t = Table(table_data, colWidths=[usable * 0.28, usable * 0.72])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (0, -1), LIGHT),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT]),
    ]))
    return t


def _scorecard(scores: dict, styles: dict) -> list:
    items = []
    usable = W - 2 * MARGIN
    col_w  = usable / 5
    labels = {
        "data_infrastructure": "Data\nInfrastructure",
        "process_automation":  "Process\nAutomation",
        "team_capability":     "Team\nCapability",
        "customer_experience": "Customer\nExperience",
        "overall":             "Overall\nScore",
    }
    header_row  = []
    score_row   = []
    bar_row     = []

    for key, label in labels.items():
        score = scores.get(key, 0)
        color = TEAL if key != "overall" else ACCENT
        header_row.append(Paragraph(f"<b>{label}</b>", ParagraphStyle(
            "sc_label", fontName="Helvetica", fontSize=8, textColor=MUTED,
            alignment=TA_CENTER, leading=10
        )))
        score_row.append(Paragraph(f"<b>{score}</b>", ParagraphStyle(
            "sc_num", fontName="Helvetica-Bold", fontSize=22, textColor=color,
            alignment=TA_CENTER
        )))
        # Bar representation via a mini-table
        filled = max(1, int(score / 10))
        bar_cells = [[""] * filled + [""] * (10 - filled)]
        bar_t = Table(bar_cells, colWidths=[(col_w - 10) / 10] * 10, rowHeights=[6])
        filled_style = [("BACKGROUND", (i, 0), (i, 0), color) for i in range(filled)]
        empty_style  = [("BACKGROUND", (i, 0), (i, 0), colors.HexColor("#E2E8F0")) for i in range(filled, 10)]
        bar_t.setStyle(TableStyle(filled_style + empty_style + [
            ("LEFTPADDING",  (0,0), (-1,-1), 1),
            ("RIGHTPADDING", (0,0), (-1,-1), 1),
            ("TOPPADDING",   (0,0), (-1,-1), 0),
            ("BOTTOMPADDING",(0,0), (-1,-1), 0),
        ]))
        bar_row.append(bar_t)

    card = Table(
        [header_row, score_row, bar_row],
        colWidths=[col_w] * 5,
    )
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",(0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (4, 0), (4, -1), NAVY),
        ("TEXTCOLOR",  (4, 0), (4, 0),  WHITE),
    ]))
    items.append(card)
    return items


def _opportunity_card(opp: dict, styles: dict) -> list:
    impact_colors = {"High": ACCENT, "Medium": TEAL, "Low": MUTED}
    impact = opp.get("impact", "Medium")
    effort = opp.get("effort", "Medium")
    ic     = impact_colors.get(impact, TEAL)

    usable = W - 2 * MARGIN
    inner = [
        [
            Paragraph(f"<b>{opp.get('title','')}</b>", ParagraphStyle(
                "opp_title", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY)),
            Paragraph(
                f"<font color='#{ic.hexval()[2:]}'>●</font>  Impact: <b>{impact}</b>   "
                f"Effort: <b>{effort}</b>",
                ParagraphStyle("opp_badge", fontName="Helvetica", fontSize=9,
                                textColor=MUTED, alignment=TA_RIGHT)
            ),
        ],
        [
            Paragraph(opp.get("description", ""), ParagraphStyle(
                "opp_body", fontName="Helvetica", fontSize=9.5, textColor=NAVY,
                leading=13, colSpan=2)),
            "",
        ],
    ]
    t = Table(inner, colWidths=[usable * 0.65, usable * 0.35])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",(0, 0), (-1, -1), 10),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("SPAN",        (0, 1), (1, 1)),
        ("LINEABOVE",   (0, 0), (-1, 0), 3, ic),
        ("GRID",        (0, 0), (-1, -1), 0, WHITE),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
    ]))
    return [t, Spacer(1, 0.25 * cm)]


def _tools_table(tools: list, styles: dict) -> Table:
    usable = W - 2 * MARGIN
    header = [
        Paragraph("<b>Tool</b>", styles["label"]),
        Paragraph("<b>Use Case</b>", styles["label"]),
        Paragraph("<b>Estimated ROI</b>", styles["label"]),
    ]
    rows = [header]
    for tool in tools:
        rows.append([
            Paragraph(f"<b>{tool.get('name','')}</b>", styles["value"]),
            Paragraph(tool.get("use_case", ""), styles["value"]),
            Paragraph(tool.get("estimated_roi", ""), styles["value"]),
        ])
    t = Table(rows, colWidths=[usable * 0.22, usable * 0.48, usable * 0.30])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",  (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _risk_item(risk: dict, styles: dict) -> list:
    severity_colors = {"High": "#FF4444", "Medium": "#FF9900", "Low": "#22C55E"}
    sc = severity_colors.get(risk.get("severity", "Medium"), "#FF9900")
    usable = W - 2 * MARGIN
    row = [[
        Paragraph(
            f"<font color='{sc}'>▲</font>  <b>{risk.get('risk','')}</b>  "
            f"<font color='{sc}' size='8'>[{risk.get('severity','Medium')}]</font>",
            ParagraphStyle("risk_title", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY)
        ),
        Paragraph(risk.get("details", ""), ParagraphStyle(
            "risk_body", fontName="Helvetica", fontSize=9.5, textColor=NAVY, leading=13))
    ]]
    t = Table(row, colWidths=[usable * 0.30, usable * 0.70])
    t.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW",    (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))
    return [t]


def _next_steps_table(steps: list, styles: dict) -> Table:
    usable = W - 2 * MARGIN
    header = [
        Paragraph("<b>#</b>", styles["label"]),
        Paragraph("<b>Action</b>", styles["label"]),
        Paragraph("<b>Timeline</b>", styles["label"]),
        Paragraph("<b>Owner</b>", styles["label"]),
    ]
    rows = [header]
    for i, step in enumerate(steps, 1):
        rows.append([
            Paragraph(f"<b>{i}</b>", ParagraphStyle(
                "ns_num", fontName="Helvetica-Bold", fontSize=12, textColor=TEAL,
                alignment=TA_CENTER)),
            Paragraph(step.get("step", ""), styles["value"]),
            Paragraph(step.get("timeline", ""), styles["value"]),
            Paragraph(step.get("owner", ""), styles["value"]),
        ])
    t = Table(rows, colWidths=[usable*0.06, usable*0.52, usable*0.22, usable*0.20])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING",  (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",(0, 0), (-1, -1), 8),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",       (0, 0), (0, -1), "CENTER"),
    ]))
    return t


# ── Utilities ──────────────────────────────────────────────────────────────────

def _safe_filename(company: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "_", company.lower().strip())[:40]
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{slug}_{ts}_audit.pdf"
