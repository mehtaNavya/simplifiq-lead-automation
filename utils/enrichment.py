"""
utils/enrichment.py
────────────────────
Enriches a lead's company data from publicly available sources.

Strategy (in priority order):
  1. Scrape the company's own website (meta tags, About page text)
  2. Query the Clearbit Logo API for a logo URL (free, no key needed)
  3. Wikipedia summary via REST API
  4. DuckDuckGo Instant Answer API (no key needed)
  5. Graceful fallback — return whatever partial data was gathered

All network calls have timeouts; failures are swallowed so the pipeline
continues even with incomplete enrichment.
"""

import logging
import re
import time
from typing import Any, Dict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SimplifIQ-Bot/1.0; "
        "+https://simplifiq.ai/bot)"
    )
}
_TIMEOUT = 10  # seconds per request


def enrich_company(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gather public intelligence about the prospect's company.

    Args:
        lead: Dict containing at minimum 'company' and optionally 'website'.

    Returns:
        Dict of extra fields merged into the lead record:
            logo_url, tagline, description_enriched, employee_count_est,
            founding_year, hq_location, social_links, key_products,
            tech_stack_hints, news_snippets
    """
    company  = lead.get("company", "")
    website  = lead.get("website", "")
    industry = lead.get("industry", "")

    enriched: Dict[str, Any] = {
        "logo_url":            "",
        "tagline":             "",
        "description_enriched": lead.get("description", ""),
        "employee_count_est":  "",
        "founding_year":       "",
        "hq_location":         "",
        "social_links":        {},
        "key_products":        [],
        "tech_stack_hints":    [],
        "news_snippets":       [],
    }

    # ── 1. Scrape company website ──────────────────────────────────────────
    if website:
        _scrape_website(website, enriched)

    # ── 2. Logo via Clearbit (free, no key) ───────────────────────────────
    if not enriched["logo_url"]:
        domain = _extract_domain(website) if website else _guess_domain(company)
        if domain:
            enriched["logo_url"] = f"https://logo.clearbit.com/{domain}"

    # ── 3. DuckDuckGo Instant Answer API ──────────────────────────────────
    _ddg_enrich(company, enriched)

    # ── 4. Wikipedia summary ──────────────────────────────────────────────
    if not enriched.get("description_enriched") or len(enriched["description_enriched"]) < 80:
        _wikipedia_enrich(company, enriched)

    logger.debug("Enrichment result for '%s': %s", company, enriched)
    return enriched


# ── Internal helpers ──────────────────────────────────────────────────────────

def _scrape_website(url: str, enriched: Dict) -> None:
    """Parse the homepage for meta tags, social links, and text signals."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Meta description / OG
        for tag in ["og:description", "description", "twitter:description"]:
            meta = soup.find("meta", attrs={"name": tag}) or \
                   soup.find("meta", attrs={"property": tag})
            if meta and meta.get("content"):
                enriched["description_enriched"] = meta["content"].strip()
                break

        # OG site name / tagline
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            enriched["tagline"] = og_title["content"].strip()

        # Favicon / logo
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            enriched["logo_url"] = og_image["content"].strip()

        # Social links
        social_patterns = {
            "linkedin":  r"linkedin\.com/company",
            "twitter":   r"twitter\.com/|x\.com/",
            "github":    r"github\.com/",
            "instagram": r"instagram\.com/",
            "facebook":  r"facebook\.com/",
        }
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            for platform, pattern in social_patterns.items():
                if re.search(pattern, href, re.I):
                    enriched["social_links"][platform] = href

        # Detect tech stack hints from script/link sources
        tech_signals = {
            "React":       r"react",
            "Next.js":     r"next\.js|_next/",
            "Vue":         r"vue\.js",
            "Angular":     r"angular",
            "Shopify":     r"shopify",
            "WordPress":   r"wp-content|wordpress",
            "HubSpot":     r"hubspot",
            "Salesforce":  r"salesforce",
            "Intercom":    r"intercom",
            "Stripe":      r"stripe\.com",
            "Segment":     r"segment\.com",
            "Google Analytics": r"gtag|analytics\.js|ga\(",
        }
        page_src = resp.text
        for tech, pattern in tech_signals.items():
            if re.search(pattern, page_src, re.I) and tech not in enriched["tech_stack_hints"]:
                enriched["tech_stack_hints"].append(tech)

    except Exception as exc:
        logger.warning("Website scrape failed for %s: %s", url, exc)


def _ddg_enrich(company: str, enriched: Dict) -> None:
    """Query DuckDuckGo Instant Answer API (free, no auth needed)."""
    try:
        params = {"q": company, "format": "json", "no_redirect": "1", "no_html": "1"}
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params=params,
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        abstract = data.get("AbstractText", "")
        if abstract and len(abstract) > 50:
            if not enriched.get("description_enriched") or len(enriched["description_enriched"]) < 80:
                enriched["description_enriched"] = abstract

        # Related topics can give product/service clues
        for topic in data.get("RelatedTopics", [])[:3]:
            text = topic.get("Text", "")
            if text and len(text) > 20:
                enriched["news_snippets"].append(text[:200])

    except Exception as exc:
        logger.warning("DuckDuckGo enrichment failed for '%s': %s", company, exc)


def _wikipedia_enrich(company: str, enriched: Dict) -> None:
    """Try Wikipedia REST API for a company summary."""
    try:
        slug = company.replace(" ", "_")
        resp = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            extract = data.get("extract", "")
            if extract and len(extract) > 60:
                enriched["description_enriched"] = extract[:800]
            thumbnail = data.get("thumbnail", {}).get("source", "")
            if thumbnail and not enriched.get("logo_url"):
                enriched["logo_url"] = thumbnail
    except Exception as exc:
        logger.warning("Wikipedia enrichment failed for '%s': %s", company, exc)


def _extract_domain(url: str) -> str:
    """Return bare domain from a URL, e.g. 'https://www.acme.com/about' → 'acme.com'."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lstrip("www.")
        return domain
    except Exception:
        return ""


def _guess_domain(company: str) -> str:
    """Naive guess: 'Acme Corp' → 'acmecorp.com'."""
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug}.com" if slug else ""
