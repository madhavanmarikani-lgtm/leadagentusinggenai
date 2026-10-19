"""NVIDIA NIM Client for LLM-powered Query Parsing and Lead Intelligence Extraction."""

from __future__ import annotations

import json
import os
import re
from urllib.parse import quote, urlparse

import sys
import time
from openai import OpenAI

# Ensure Windows terminal handles output smoothly without charmap crashes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
FALLBACK_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"


def extract_brand_name_from_domain(domain: str, title: str = "") -> str:
    """Extracts a clean, human-readable company brand name from domain and title."""
    if title:
        parts = re.split(r"\s+[|\-–—:]\s+", title)
        for part in reversed(parts):
            p = part.strip()
            p_lower = p.lower()
            if 2 <= len(p) <= 35 and not any(w in p_lower for w in [
                "how to", "best", "top ", "list", "guide", "blog", "home", "2024", "2025", "2026",
                "email list", "contact information", "pricing", "login", "reviews"
            ]):
                return p

    root = domain.lower().replace("www.", "").split(".")[0]
    root = re.sub(r"^(the|get|use|try|join|my|weare)", "", root)
    if not root:
        root = domain.split(".")[0]
    return root.title()


def is_valid_domain(d: str) -> bool:
    """Verifies that a string represents a valid, legitimate domain name."""
    if not d or not isinstance(d, str):
        return False
    d = d.strip().lower()
    if " " in d or "/" in d or ":" in d or "@" in d or "\\" in d:
        return False
    if any(w in d for w in ["snippet", "listed", "unknown", "none", "not available", "n/a", "null", "http"]):
        return False
    return bool(re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$", d))


def call_nvidia_json(prompt: str, system_prompt: str, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Sends a prompt to NVIDIA NIM API and guarantees a parsed JSON dict response."""
    if not api_key:
        raise ValueError("NVIDIA API key is missing. Please provide it in .env (NVIDIA_API_KEY) or the sidebar.")

    client = OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=api_key.strip(),
    )

    target_model = model or DEFAULT_MODEL
    print(f"  [NVIDIA NIM] Sending request to {target_model}...", flush=True)
    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2500,
        )

        elapsed = time.time() - start_time
        print(f"  [NVIDIA NIM] Response received in {elapsed:.2f}s", flush=True)

        if not response.choices:
            if target_model != FALLBACK_MODEL:
                print(f"  [NVIDIA NIM Warning] Empty choices from {target_model}. Retrying with {FALLBACK_MODEL}...", flush=True)
                return call_nvidia_json(prompt, system_prompt, api_key, model=FALLBACK_MODEL)
            raise RuntimeError(f"NVIDIA API returned empty choices: {response}")

        msg = response.choices[0].message
        content = msg.content or ""
        if not content and hasattr(msg, "reasoning_content"):
            content = getattr(msg, "reasoning_content", "") or ""

    except Exception as exc:
        err_str = str(exc)
        if any(code in err_str for code in ["500", "502", "503", "504", "429", "overloaded", "404"]) and target_model != FALLBACK_MODEL:
            print(f"  [NVIDIA NIM Warning] Model {target_model} failed ({exc}). Retrying with {FALLBACK_MODEL}...", flush=True)
            return call_nvidia_json(prompt, system_prompt, api_key, model=FALLBACK_MODEL)
        raise RuntimeError(f"NVIDIA API call failed: {exc}")

    # Clean reasoning tags if any
    cleaned_content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

    # Extract JSON block if wrapped in markdown code blocks
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned_content)
    if match:
        cleaned_content = match.group(1).strip()

    try:
        parsed_json = json.loads(cleaned_content)
        return parsed_json
    except json.JSONDecodeError:
        # Fallback regex extraction of first json object
        obj_match = re.search(r"(\{[\s\S]*\})", cleaned_content)
        if obj_match:
            try:
                parsed_json = json.loads(obj_match.group(1))
                return parsed_json
            except Exception:
                pass

        if target_model != FALLBACK_MODEL:
            print(f"  [NVIDIA NIM Warning] Non-JSON output from {target_model}. Retrying with {FALLBACK_MODEL}...")
            return call_nvidia_json(prompt, system_prompt, api_key, model=FALLBACK_MODEL)

        raise ValueError(f"LLM returned non-JSON response:\n{content}")


# Alias for backward compatibility
call_openrouter_json = call_nvidia_json


def parse_user_query_with_llm(user_query: str, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """
    Uses NVIDIA NIM LLM to extract the desired count (default 2) and formulate an
    optimized Tavily search query targeting C-Level executives (CEO, CTO, Founder).
    """
    print(f"\n{'='*65}")
    print(f"[STEP 1: LLM QUERY PARSING] (NVIDIA NIM)")
    print(f"{'='*65}")
    print(f"  [User Query]       : \"{user_query}\"")
    print(f"  [Model]            : {model}")

    system_prompt = (
        "You are a strict JSON-only API for B2B Lead Generation. "
        "Analyze the user's search request and extract key search parameters. "
        "Formulate search queries that surface company leadership (CEO, CTO, Founders, C-Suite). "
        "Keep search queries short and concise (under 10 words). "
        "Output MUST be strict JSON only, with no markdown, reasoning, or conversational text. "
        "Start response immediately with '{'."
    )

    prompt = f"""
Analyze this user query: "{user_query}"

Extract the following information:
1. "count": Integer number of leads requested by the user. If the user didn't specify a number, the DEFAULT IS 2.
2. "tavily_query": A clean search query for Tavily API (UNDER 10 WORDS total, e.g. 'digital agency London CEO Founder leadership -jobs'). Target pages mentioning C-level executives (CEO, CTO, Founder). NEVER use more than 3 negative keywords.
3. "target_industry": The industry or service identified (e.g. "Digital Agency", "SaaS", "E-Commerce").
4. "target_location": The country, city, or region targeted (e.g. "London, UK", "Austin, Texas", "US/UK").
5. "llm_thought": A short 1-sentence explanation of what you extracted.

CRITICAL: Start response with '{{' immediately. Return ONLY this JSON structure:
{{
  "count": 2,
  "tavily_query": "...",
  "target_industry": "...",
  "target_location": "...",
  "llm_thought": "..."
}}
"""
    result = call_nvidia_json(prompt, system_prompt, api_key, model)

    print(f"  [Extracted Count]  : {result.get('count', 2)}")
    print(f"  [Tavily Query]     : \"{result.get('tavily_query')}\"")
    print(f"  [Target Location]  : {result.get('target_location', 'Global')}")
    print(f"  [Target Industry]  : {result.get('target_industry', 'General')}")
    print(f"  [LLM Reasoning]    : {result.get('llm_thought', '')}")
    print(f"{'-'*65}")

    return result


def extract_lead_intelligence_with_llm(
    tavily_item: dict,
    api_key: str,
    model: str = DEFAULT_MODEL,
    target_geography: str = "",
) -> dict:
    """
    Uses AI LLM to read a Tavily search result and extract:
    - Real Company Name (stripping all SEO fluff)
    - Clean Domain & Verified Company URL (preventing directory mismatches)
    - Accurate Country & Country Code (India, UK, US, etc.)
    - C-Level Executive (CEO, Founder, CTO, COO, Managing Director)
    - Targeted LinkedIn search link
    """
    url = tavily_item.get("url", "")
    title = tavily_item.get("title", "")
    snippet = tavily_item.get("content", "")
    source_netloc = urlparse(url).netloc.lower().replace("www.", "")

    print(f"\n  ---------------------------------------------------------------")
    print(f"  [STEP 3: ANALYZING CANDIDATE] -> {source_netloc}")
    print(f"     Title: {title[:75]}...")
    print(f"     URL  : {url}")

    geo_hint = f" The target search geography is {target_geography}." if target_geography else ""

    system_prompt = (
        "You are a strict JSON-only API specializing in B2B company intelligence and executive leadership identification. "
        "Extract the actual business brand name, its clean domain, country, industry, company type, key business need/opportunity, and C-Level Executive. "
        f"{geo_hint} Output MUST be strict JSON only. NEVER output commentary, analysis, thinking, or markdown. "
        "Start your response immediately with '{'."
    )

    prompt = f"""URL: {url}
Page Title: {title}
Content Snippet: {snippet}

Extract:
1. "company_name": The TRUE, concise business/brand name. NEVER use generic SEO phrases like "Austin SaaS Companies - Gregslist" or "Contact Us". If title is "uStudio - Austin SaaS Companies", company name is "uStudio".
2. "domain": The clean official company root domain (e.g. "aquaconnect.com", "ustudio.com"). If snippet is from an aggregator, directory, event/forum, or news article, identify the ACTUAL company's official domain, NOT the host website.
3. "country": The country where company is based (e.g. "India", "UK", "US", "Canada", "Germany", "Australia"). Check city mentions or TLD (.in, .co.in = India; .co.uk = UK; .ca = Canada; .de = Germany). If target geography is "{target_geography}", verify if company operates in {target_geography}.
4. "industry": Concise industry (e.g. "Aquaculture / AgriTech", "Seafood Export", "SaaS", "Digital Agency", "Software Company", "E-Commerce").
5. "company_type": Type of company (e.g. "Exporters", "Digital Agency", "Software Company", "B2B SaaS", "Enterprise").
6. "key_need": A clear summary of the company's business focus, services, or expansion opportunity.
7. "c_level_name": The full name of the internal C-Level Executive (CEO, Founder, Co-Founder, CTO, COO, Managing Director) who OWNS or RUNS this company. CRITICAL: NEVER extract names from customer reviews, client testimonials, case studies, or partner quotes (e.g. 'Jane Doe, CEO at ClientCorp said...'). If the person is a client or testimonial, return "Executive Team / Not listed in snippet".
8. "c_level_title": The exact C-level title (e.g. "Chief Executive Officer (CEO)", "Founder & CEO", "Managing Director", "CTO", "COO").
9. "summary": A brief 1-sentence summary of what this company does.

CRITICAL: Start your output with '{{' immediately. Return ONLY this JSON structure:
{{
  "company_name": "...",
  "domain": "...",
  "country": "...",
  "industry": "...",
  "company_type": "...",
  "key_need": "...",
  "c_level_name": "...",
  "c_level_title": "...",
  "summary": "..."
}}
"""
    try:
        result = call_nvidia_json(prompt, system_prompt, api_key, model)
    except Exception as exc:
        print(f"  [Extraction Warning] LLM failed for {url}: {exc}. Using domain brand extractor...", flush=True)
        brand_name = extract_brand_name_from_domain(source_netloc, title)
        result = {
            "company_name": brand_name,
            "domain": source_netloc,
            "country": target_geography if target_geography else ("India" if any(k in url.lower() for k in [".in", ".co.in"]) else "United States"),
            "industry": "Technology",
            "company_type": "Digital Business",
            "key_need": f"Commercial development and enterprise services for {brand_name}",
            "c_level_name": "Executive Team / Not listed in snippet",
            "c_level_title": "C-Level Leadership",
            "summary": snippet[:200].strip() if snippet else f"{brand_name} operations and customer services.",
        }

    raw_company = str(result.get("company_name", "")).strip()
    # Check if raw_company is an article headline, listicle, or search fluff
    is_bad_name = (
        not raw_company
        or len(raw_company) > 38
        or any(w in raw_company.lower() for w in [
            "how to", "top ", "best ", "email list", "contact information", "database",
            "directory", "guide to", "companies hiring", "find b2b", "lead generation",
            "pricing", "login", "free trial", "reviews"
        ])
    )
    if is_bad_name:
        company_name = extract_brand_name_from_domain(source_netloc, title)
    else:
        company_name = raw_company

    raw_domain = result.get("domain") or source_netloc


    # Normalize clean domain (strip protocols, paths, www)
    clean_domain = re.sub(r"^https?://", "", str(raw_domain).strip()).rstrip("/").replace("www.", "")
    clean_domain = clean_domain.split("/")[0].split("?")[0].strip().lower()

    # Fallback to source netloc if extracted domain is invalid or placeholder text
    if not is_valid_domain(clean_domain):
        clean_domain = source_netloc

    # Align website_url with the actual company domain to prevent URL mismatches
    if clean_domain and clean_domain in source_netloc:
        website_url = url
    elif is_valid_domain(clean_domain):
        website_url = f"https://www.{clean_domain}"
    else:
        website_url = url

    # Dynamic Country Resolution
    raw_country = str(result.get("country", "")).strip()
    full_text = f"{url} {title} {snippet} {raw_country} {target_geography}".lower()

    if any(k in full_text for k in [".lk/", ".lk?", "sri lanka", "colombo", "ceylon", "kandy", "galle"]) or "sri lanka" in raw_country.lower():
        country = "Sri Lanka"
        country_code = "LK"
    elif any(k in full_text for k in [".co.in", ".in/", ".in?", "india", "chennai", "mumbai", "delhi", "bengaluru", "bangalore", "hyderabad", "pune", "kolkata", "visakhapatnam", "vizag", "ahmedabad", "kerala", "gujarat", "andhra"]) or "india" in raw_country.lower():
        country = "India"
        country_code = "IN"
    elif any(k in full_text for k in [".co.uk", ".uk/", ".uk?", "united kingdom", "london", "manchester", "birmingham", "edinburgh", "england", "scotland"]) or "uk" in raw_country.lower():
        country = "United Kingdom"
        country_code = "GB"
    elif any(k in full_text for k in [".de/", ".de?", "germany", "berlin", "munich", "frankfurt"]) or "germany" in raw_country.lower():
        country = "Germany"
        country_code = "DE"
    elif any(k in full_text for k in [".ca/", ".ca?", "canada", "toronto", "vancouver", "montreal"]) or "canada" in raw_country.lower():
        country = "Canada"
        country_code = "CA"
    elif any(k in full_text for k in [".au/", ".au?", "australia", "sydney", "melbourne"]) or "australia" in raw_country.lower():
        country = "Australia"
        country_code = "AU"
    elif target_geography and "sri lanka" in target_geography.lower():
        country = "Sri Lanka"
        country_code = "LK"
    elif target_geography and "india" in target_geography.lower():
        country = "India"
        country_code = "IN"
    elif target_geography and ("uk" in target_geography.lower() or "united kingdom" in target_geography.lower()):
        country = "United Kingdom"
        country_code = "GB"
    elif target_geography and "canada" in target_geography.lower():
        country = "Canada"
        country_code = "CA"
    elif target_geography and "germany" in target_geography.lower():
        country = "Germany"
        country_code = "DE"
    elif target_geography and "australia" in target_geography.lower():
        country = "Australia"
        country_code = "AU"
    elif target_geography and ("united states" in target_geography.lower() or "usa" in target_geography.lower() or "us" in target_geography.lower()):
        country = "United States"
        country_code = "US"
    elif raw_country and raw_country.lower() not in ["not specified", "unknown", "n/a", "null", "none", "not available", "unspecified"]:
        country = raw_country
        c_low = country.lower()
        if "sri lanka" in c_low:
            country_code = "LK"
        elif "india" in c_low:
            country_code = "IN"
        elif "united kingdom" in c_low or c_low == "uk":
            country_code = "GB"
        elif "united states" in c_low or c_low in ["us", "usa"]:
            country_code = "US"
        else:
            country_code = "GL"
    else:
        country = "Global / Unspecified"
        country_code = "GL"

    result["country"] = country
    result["country_code"] = country_code


    # Generate targeted LinkedIn search query for C-Level executives
    c_level_roles = '("CEO" OR "Chief Executive Officer" OR "Founder" OR "Co-Founder" OR "CTO" OR "Chief Technology Officer" OR "COO" OR "Managing Director")'
    clean_search_name = re.sub(r"[^\w\s]", " ", company_name).strip()
    query_str = f'site:linkedin.com/in "{clean_search_name}" {c_level_roles}'
    linkedin_url = f"https://www.google.com/search?q={quote(query_str)}"

    result["company_name"] = company_name
    result["domain"] = clean_domain
    result["website_url"] = website_url
    result["source_url"] = url
    result["linkedin_search_url"] = linkedin_url

    # Fallback compatibility
    if "decision_maker_name" not in result:
        result["decision_maker_name"] = result.get("c_level_name", "Executive Team")
    if "decision_maker_role" not in result:
        result["decision_maker_role"] = result.get("c_level_title", "C-Level Leadership")

    print(f"     [OK] Extracted Company : {company_name}", flush=True)
    print(f"     [OK] Verified Domain   : {clean_domain}", flush=True)
    print(f"     [OK] Company URL       : {website_url}", flush=True)
    print(f"     [OK] Country           : {country} ({country_code})", flush=True)
    print(f"     [OK] C-Level Executive : {result.get('c_level_name')} ({result.get('c_level_title')})", flush=True)
    print(f"     [OK] Summary           : {result.get('summary')[:80]}...", flush=True)
    print(f"  ---------------------------------------------------------------", flush=True)

    return result

