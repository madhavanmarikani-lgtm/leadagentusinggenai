"""Apollo.io API Integration Client for B2B Company & Decision-Maker Enrichment."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

APOLLO_API_URL = "https://api.apollo.io/v1"


def get_apollo_api_key(provided_key: Optional[str] = None) -> str:
    """Retrieves the active Apollo API key from parameters, env, or empty string."""
    if provided_key and provided_key.strip():
        return provided_key.strip()
    return os.getenv("APOLLO_API_KEY", "").strip()


def is_apollo_configured(api_key: Optional[str] = None) -> bool:
    """Returns True if a valid Apollo API key is present."""
    key = get_apollo_api_key(api_key)
    return bool(key and len(key) > 8 and not key.startswith("your_"))


def clean_domain_for_apollo(url_or_domain: str) -> str:
    """Extracts a clean, canonical domain name suitable for Apollo API queries."""
    if not url_or_domain:
        return ""
    clean = url_or_domain.strip().lower()
    if clean.startswith("http://") or clean.startswith("https://"):
        parsed = urlparse(clean)
        clean = parsed.netloc
    clean = re.sub(r"^www\.", "", clean)
    clean = clean.split("/")[0].split("?")[0].strip()
    return clean


def enrich_organization_apollo(
    domain: str,
    company_name: str = "",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Enriches organization details via Apollo.io Organization Enrichment API (/v1/organizations/enrich).
    Returns verified company data including exact employee count, revenue, headquarters, and tech stack.
    """
    key = get_apollo_api_key(api_key)
    if not key:
        return {"status": "skipped", "reason": "APOLLO_API_KEY missing"}

    clean_dom = clean_domain_for_apollo(domain)
    if not clean_dom or "." not in clean_dom:
        return {"status": "error", "reason": f"Invalid domain: {domain}"}

    url = f"{APOLLO_API_URL}/organizations/enrich"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "x-api-key": key,
    }
    payload = {"domain": clean_dom}

    print(f"  [Apollo Org Enrichment] Querying domain: {clean_dom}...", flush=True)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=12)
        if response.status_code == 200:
            data = response.json()
            org = data.get("organization") or {}
            if not org:
                print(f"  [Apollo Org Enrichment] No organization profile found for {clean_dom}.", flush=True)
                return {"status": "not_found", "domain": clean_dom}

            # Parse technologies
            tech_raw = org.get("current_technologies") or []
            tech_names = [t.get("name") for t in tech_raw if isinstance(t, dict) and t.get("name")]
            if not tech_names and isinstance(tech_raw, list):
                tech_names = [str(t) for t in tech_raw if isinstance(t, str)]

            # Revenue printing
            annual_rev = org.get("annual_revenue_printed")
            if not annual_rev and org.get("annual_revenue"):
                rev_num = org.get("annual_revenue")
                annual_rev = f"${rev_num:,.0f}" if isinstance(rev_num, (int, float)) else str(rev_num)

            result = {
                "status": "success",
                "apollo_org_id": org.get("id"),
                "company_name": org.get("name") or company_name,
                "website_url": org.get("website_url") or f"https://www.{clean_dom}",
                "domain": clean_dom,
                "country": org.get("country") or "",
                "state": org.get("state") or "",
                "city": org.get("city") or "",
                "employee_count": str(org.get("estimated_num_employees") or ""),
                "annual_revenue": annual_rev or "",
                "industry": org.get("industry") or "",
                "company_linkedin_url": org.get("linkedin_url") or "",
                "primary_phone": org.get("phone") or org.get("primary_phone", {}).get("sanitized_number") if isinstance(org.get("primary_phone"), dict) else (org.get("primary_phone") or ""),
                "technologies": tech_names[:15],
                "short_description": org.get("short_description") or "",
            }
            print(f"  [Apollo Org Enrichment OK] {result['company_name']} | Headcount: {result['employee_count']} | Revenue: {result['annual_revenue']}", flush=True)
            return result

        elif response.status_code in (401, 403):
            print(f"  [Apollo Org Warning] Authentication error ({response.status_code}): Invalid or unpermitted Apollo API key.", flush=True)
            return {"status": "auth_error", "code": response.status_code}
        else:
            print(f"  [Apollo Org Warning] Apollo returned status {response.status_code}: {response.text[:150]}", flush=True)
            return {"status": "api_error", "code": response.status_code}

    except Exception as exc:
        print(f"  [Apollo Org Error] Exception during enrichment for {clean_dom}: {exc}", flush=True)
        return {"status": "error", "message": str(exc)}


def search_decision_makers_apollo(
    domain: str,
    company_name: str = "",
    org_id: Optional[str] = None,
    api_key: Optional[str] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """
    Searches and extracts verified C-level executives & decision-makers for a company
    using Apollo's People Search API (/v1/mixed_people/search).
    Returns real human names, verified emails, phone numbers, and direct LinkedIn profile URLs.
    """
    key = get_apollo_api_key(api_key)
    if not key:
        return []

    clean_dom = clean_domain_for_apollo(domain)
    if not clean_dom and not org_id:
        return []

    url = f"{APOLLO_API_URL}/mixed_people/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "x-api-key": key,
    }

    target_titles = [
        "CEO",
        "Founder",
        "Co-Founder",
        "Managing Director",
        "Chief Executive Officer",
        "President",
        "CTO",
        "Chief Technology Officer",
        "COO",
        "Owner",
        "Partner",
    ]

    payload: Dict[str, Any] = {
        "person_titles": target_titles,
        "person_seniorities": ["owner", "founder", "c_suite", "partner"],
        "page": 1,
        "per_page": limit,
    }

    if clean_dom:
        payload["q_organization_domains"] = clean_dom
    if org_id:
        payload["organization_ids"] = [org_id]

    print(f"  [Apollo People Search] Searching C-suite executives for domain: {clean_dom}...", flush=True)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=12)
        if response.status_code == 200:
            data = response.json()
            raw_people = data.get("people") or []
            print(f"  [Apollo People Search] Found {len(raw_people)} matching decision-maker profiles.", flush=True)

            people = []
            for p in raw_people:
                name = p.get("name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                if not name:
                    continue

                # Phone number resolution
                phone = p.get("sanitized_phone")
                if not phone and p.get("phone_numbers"):
                    p_nums = p.get("phone_numbers", [])
                    if p_nums and isinstance(p_nums[0], dict):
                        phone = p_nums[0].get("sanitized_number") or p_nums[0].get("raw_number")

                title = p.get("title") or "Executive Leader"
                email = p.get("email") or ""
                email_status = p.get("email_status") or ("verified" if email else "unavailable")
                linkedin = p.get("linkedin_url") or ""

                people.append({
                    "apollo_person_id": p.get("id"),
                    "name": name,
                    "title": title,
                    "seniority": "C-Suite" if any(r in title.lower() for r in ["ceo", "cto", "coo", "founder", "managing director", "president", "owner"]) else "Executive",
                    "email": email,
                    "email_status": email_status,
                    "phone": phone or "",
                    "linkedin_url": linkedin,
                    "city": p.get("city") or "",
                    "state": p.get("state") or "",
                    "country": p.get("country") or "",
                    "apollo_headline": p.get("headline") or title,
                    "apollo_enrichment_status": "enriched" if email else "partial",
                })
                print(f"     [Apollo DM] {name} | {title} | Email: {email or 'Locked/Pending'} | Phone: {phone or 'N/A'}", flush=True)

            return people

        elif response.status_code in (401, 403):
            print(f"  [Apollo People Warning] Auth error ({response.status_code}): Invalid Apollo API key.", flush=True)
            return []
        else:
            print(f"  [Apollo People Warning] Apollo returned status {response.status_code}: {response.text[:150]}", flush=True)
            return []

    except Exception as exc:
        print(f"  [Apollo People Error] Exception during people search for {clean_dom}: {exc}", flush=True)
        return []


def enrich_lead_full_apollo(
    domain: str,
    company_name: str = "",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Combined helper: Enriches both organization attributes and verified decision-makers.
    """
    key = get_apollo_api_key(api_key)
    if not key:
        return {"status": "skipped", "reason": "APOLLO_API_KEY missing"}

    org_res = enrich_organization_apollo(domain, company_name=company_name, api_key=key)
    org_id = org_res.get("apollo_org_id") if org_res.get("status") == "success" else None

    people_res = search_decision_makers_apollo(domain, company_name=company_name, org_id=org_id, api_key=key)

    return {
        "status": "success" if (org_res.get("status") == "success" or people_res) else "failed",
        "organization": org_res if org_res.get("status") == "success" else {},
        "people": people_res,
    }
