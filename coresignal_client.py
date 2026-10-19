"""Coresignal Agentic Search API Client for Natural Language B2B Lead Intelligence."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

CORESIGNAL_API_URL = "https://api.coresignal.com/cdapi/v2/agentic_search/fast"


def is_coresignal_configured(api_key: Optional[str] = None) -> bool:
    """Checks if a valid Coresignal API key is provided or present in environment."""
    key = (api_key or os.getenv("CORESIGNAL_API_KEY", "")).strip()
    return bool(key and len(key) > 5)


def _safe_print(*args, **kwargs):
    """Safely prints without throwing OSError on Windows when streams are disconnected."""
    try:
        print(*args, **kwargs)
    except Exception:
        pass


import re
import sqlite3


def get_existing_db_identifiers() -> Dict[str, set]:
    """
    Fetches sets of existing company names, domains, person names, and linkedin URLs
    from SQLite database (leads.db) to enable deduplication and prevent repeat leads.
    """
    db_path = os.path.join(os.path.dirname(__file__), "leads.db")
    companies, domains, people, linkedins = set(), set(), set(), set()

    if not os.path.exists(db_path):
        return {"companies": companies, "domains": domains, "people": people, "linkedins": linkedins}

    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT LOWER(TRIM(company_name)), LOWER(TRIM(domain)) FROM companies WHERE company_name IS NOT NULL")
        for row in c.fetchall():
            if row[0]:
                companies.add(row[0])
            if row[1]:
                domains.add(row[1])

        c.execute("SELECT LOWER(TRIM(name)), LOWER(TRIM(linkedin_url)) FROM people WHERE name IS NOT NULL")
        for row in c.fetchall():
            if row[0]:
                people.add(row[0])
            if row[1] and "linkedin.com" in row[1]:
                clean_url = row[1].rstrip("/")
                linkedins.add(clean_url)
        conn.close()
    except Exception as e:
        print(f"[CORESIGNAL DEDUP WARNING] Could not read existing DB leads: {e}", flush=True)

    return {"companies": companies, "domains": domains, "people": people, "linkedins": linkedins}


def is_lead_already_in_db(item: Dict[str, Any], db_identifiers: Dict[str, set]) -> bool:
    """Checks whether a candidate or their company is already saved in SQLite."""
    company_name = (item.get("company_name") or "").strip().lower()
    full_name = (item.get("full_name") or "").strip().lower()
    raw_linkedin = (item.get("linkedin_url") or "").strip().lower().rstrip("/")

    # Match by full person name or direct LinkedIn profile
    if full_name and full_name in db_identifiers["people"]:
        return True
    if raw_linkedin and raw_linkedin in db_identifiers["linkedins"]:
        return True

    # Match by company name
    if company_name and company_name in db_identifiers["companies"]:
        return True

    # Match by normalized company domain slug
    clean_name = re.sub(r"(?i)\b(inc|llc|ltd|corp|corporation|technologies|intelligence|group|co)\b\.?", "", company_name).strip()
    clean_slug = re.sub(r"[^a-zA-Z0-9]", "", clean_name.lower())
    domain = f"{clean_slug}.com"
    if domain in db_identifiers["domains"]:
        return True

    return False


def extract_requested_count(prompt: str) -> Optional[int]:
    """
    Extracts explicit count requested by the user in the prompt (e.g. 'Find 2...', 'Top 5...').
    Avoids matching employee headcount numbers such as '20 to 100'.
    """
    patterns = [
        r"(?i)\b(?:find|get|fetch|show|extract|return|give me|top)\s+(\d{1,2})\b",
        r"(?i)\b(\d{1,2})\s+(?:us|uk|united states|united kingdom|companies|agencies|startups|firms|leads|records|decision|executives|ceos|founders)\b",
    ]
    for pat in patterns:
        m = re.search(pat, prompt)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 100:
                return val
    return None


def execute_coresignal_agentic_search(
    prompt: str,
    threshold: float = 0.97,
    entity: str = "employee",
    return_data: bool = True,
    api_key: Optional[str] = None,
    limit: Optional[int] = None,
    exclude_saved: bool = True,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Executes a live POST request to Coresignal Agentic Search Fast API.
    Endpoint: https://api.coresignal.com/cdapi/v2/agentic_search/fast
    Header: 'apikey: <key>'
    """
    # Ensure environment is freshly checked
    load_dotenv()
    effective_key = (api_key or os.getenv("CORESIGNAL_API_KEY", "")).strip()

    payload = {
        "prompt": prompt.strip(),
        "return_data": bool(return_data),
        "threshold": float(threshold),
        "entity": entity,
    }

    _safe_print(f"\n{'='*65}")
    _safe_print(f"[CORESIGNAL API] >>> POST {CORESIGNAL_API_URL}")
    _safe_print(f"[CORESIGNAL API]     Prompt: \"{payload['prompt']}\"")
    _safe_print(f"[CORESIGNAL API]     Entity: {entity} | Threshold: {threshold} | Return Data: {return_data}")

    if not effective_key:
        _safe_print("[CORESIGNAL API] [Error] CORESIGNAL_API_KEY is not configured.")
        _safe_print(f"{'='*65}\n")
        return {
            "success": False,
            "error": "CORESIGNAL_API_KEY is missing. Please add CORESIGNAL_API_KEY to your .env file or enter it in API Parameters.",
        }

    masked_key = f"{effective_key[:4]}...{effective_key[-4:]}" if len(effective_key) > 8 else "***"
    _safe_print(f"[CORESIGNAL API]     Using API Key: {masked_key}")

    headers = {
        "apikey": effective_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            CORESIGNAL_API_URL,
            headers=headers,
            json=payload,
            timeout=45,
        )

        _safe_print(f"[CORESIGNAL API] <<< HTTP Response Code: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            items = result.get("data", [])
            query = result.get("query", {})
            total_raw_count = len(items)

            # Deduplication against local SQLite database
            db_identifiers = get_existing_db_identifiers() if exclude_saved else {"companies": set(), "domains": set(), "people": set(), "linkedins": set()}
            
            fresh_items = []
            existing_items = []
            for it in items:
                in_db = is_lead_already_in_db(it, db_identifiers)
                it["is_saved_in_db"] = in_db
                if in_db:
                    existing_items.append(it)
                else:
                    fresh_items.append(it)

            # Determine candidate pool (prefer fresh unseen leads if exclude_saved is active)
            candidate_pool = fresh_items if (exclude_saved and fresh_items) else items

            # Determine target count: explicit limit parameter takes priority, else auto-detect from prompt
            target_limit = limit if (limit is not None and limit > 0) else extract_requested_count(prompt)

            start_idx = max(0, offset)
            end_idx = start_idx + target_limit if target_limit else len(candidate_pool)
            sliced_leads = candidate_pool[start_idx:end_idx] if start_idx < len(candidate_pool) else []

            has_more_unique = (start_idx + len(sliced_leads) < len(candidate_pool))
            remaining_unique = max(0, len(candidate_pool) - (start_idx + len(sliced_leads)))

            _safe_print(
                f"[CORESIGNAL API DEDUP] Total: {total_raw_count} | Fresh/Unique: {len(fresh_items)} | "
                f"Skipped in DB: {len(existing_items)} | Offset: {start_idx} | Returning: {len(sliced_leads)}"
            )

            if sliced_leads:
                top_lead = sliced_leads[0]
                exp_list = top_lead.get("experience") or []
                emp_count = exp_list[0].get("company_employees_count") if exp_list else "N/A"
                _safe_print(f"[CORESIGNAL API SAMPLE] Lead #1: {top_lead.get('full_name')} | Title: {top_lead.get('active_experience_title')} | Company: {top_lead.get('company_name')} (~{emp_count} emp)")
            _safe_print(f"{'='*65}\n")

            return {
                "success": True,
                "entity": result.get("entity", entity),
                "query": query,
                "data": sliced_leads,
                "count": len(sliced_leads),
                "total_candidates": total_raw_count,
                "unique_fresh_count": len(fresh_items),
                "skipped_existing_count": len(existing_items),
                "requested_limit": target_limit,
                "offset": start_idx,
                "has_more_unique": has_more_unique,
                "remaining_unique": remaining_unique,
            }
        else:
            error_body = response.text
            _safe_print(f"[CORESIGNAL API ERROR {response.status_code}]: {error_body}")
            _safe_print(f"{'='*65}\n")
            return {
                "success": False,
                "error": f"Coresignal API Error (HTTP {response.status_code}): {error_body}",
                "status_code": response.status_code,
            }

    except requests.exceptions.RequestException as req_err:
        _safe_print(f"[CORESIGNAL API EXCEPTION]: {req_err}")
        _safe_print(f"{'='*65}\n")
        return {
            "success": False,
            "error": f"Network error contacting Coresignal API: {str(req_err)}",
        }
