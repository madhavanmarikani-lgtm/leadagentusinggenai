"""Lead Discovery Service integrating NVIDIA NIM and Tavily with SQLite persistence."""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv

# Ensure Windows terminal line-buffers logs so prints appear immediately
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    except Exception:
        pass

from apollo_client import (
    enrich_lead_full_apollo,
    is_apollo_configured,
)
from database import save_company_and_people, get_company_by_id
from nvidia_client import (
    DEFAULT_MODEL,
    call_nvidia_json,
    extract_lead_intelligence_with_llm,
)

load_dotenv()

GREETINGS_OR_VAGUE = {
    "hi", "hello", "hey", "hola", "namaste", "test", "help", "who are you",
    "what can you do", "good morning", "good evening", "good afternoon",
    "yo", "sup", "how are you", "start", "find leads", "leads", "search",
    "hi there", "hello there"
}


def validate_search_prompt_intent(prompt: str) -> Tuple[bool, str]:
    """
    Checks if a user's prompt is merely a greeting or lacking B2B search criteria.
    Returns (is_greeting, guidance_message).
    """
    p_clean = re.sub(r"[^\w\s]", "", (prompt or "").lower()).strip()
    words = p_clean.split()

    if not p_clean or p_clean in GREETINGS_OR_VAGUE or len(p_clean) <= 3:
        return True, "Hello! Please describe the target companies or decision-makers you are looking for (e.g., 'Find 5 automobile companies in Australia' or 'B2B SaaS founders in India')."

    business_signals = {
        "company", "companies", "firm", "firms", "agency", "agencies", "startup", "startups",
        "saas", "software", "tech", "india", "us", "uk", "australia", "canada", "germany",
        "hiring", "engineer", "engineers", "ceo", "founder", "cto", "developer", "marketing",
        "logistics", "export", "b2b", "hospital", "transport", "retail", "fintech", "ai",
        "automobile", "automotive", "manufacturing", "business", "service", "services"
    }
    if len(words) <= 2 and not any(w in business_signals for w in words):
        return True, f"'{prompt}' is too brief. Please specify your target industry, geography, or roles (e.g., '{prompt} companies in India hiring developers')."

    return False, ""

DIRECTORY_DOMAINS = [
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "clutch.co", "goodfirms.co", "yelp.com", "glassdoor.com", "indeed.com",
    "medium.com", "reddit.com", "wikipedia.org", "revenuebase.ai",
    "zoominfo.com", "apollo.io", "pitchbook.com", "gregslist.com",
    "connectively.us", "builtin.com", "builtinaustin.com", "builtinla.com",
    "builtinnyc.com", "builtinchicago.com", "builtinseattle.com",
    "builtincolorado.com", "builtinboston.com", "builtinsf.com",
    "crunchbase.com", "g2.com", "capterra.com", "softwareadvice.com",
    "trustradius.com", "themanifest.com", "sortlist.com",
    "topinteractiveagencies.com", "upwork.com", "fiverr.com", "github.com",
    "youtube.com", "quora.com", "pinterest.com", "bloomberg.com",
    "forbes.com", "techcrunch.com", "businessinsider.com", "inc.com",
    "designrush.com", "agencyreviews.io", "trustpilot.com",
]


def formulate_search_query_from_criteria(criteria: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """
    Uses NVIDIA NIM to synthesize criteria from the dashboard filters into a high-intent Tavily query.
    """
    geos = ", ".join(criteria.get("geographies", ["United States", "United Kingdom"]))
    industries = ", ".join(criteria.get("industries", ["SaaS", "IT Services"]))
    services = ", ".join(criteria.get("services", ["AI Development", "Web & Mobile Development"]))
    signals = ", ".join(criteria.get("signals", ["Developer Hiring", "AI Initiatives"]))
    titles = ", ".join(criteria.get("titles", ["CEO", "Founder", "CTO"]))
    count = int(criteria.get("count", 10))

    system_prompt = (
        "You are an expert B2B lead generation query builder. "
        "Formulate an ultra-clean, concise search query for Tavily web search (UNDER 10 WORDS total). "
        "Target companies with active intent and leadership pages. "
        "Output strict JSON only. Start immediately with '{'."
    )

    prompt = f"""
Dashboard Criteria:
- Target Geography: {geos}
- Target Industries: {industries}
- Services / Needs: {services}
- Buying Signals: {signals}
- Target Job Titles: {titles}
- Desired Companies Count: {count}

Synthesize a search query for web search that will directly surface company websites (e.g. 'digital agency London AI development CEO Founder -jobs').
Keep negative keywords to max 2 (-jobs -directory).

Return ONLY this JSON structure:
{{
  "tavily_query": "...",
  "primary_industry": "...",
  "primary_country": "...",
  "strategy_thought": "..."
}}
"""
    return call_nvidia_json(prompt, system_prompt, api_key)


def formulate_search_query_from_prompt(user_prompt: str, count: int, api_key: str) -> Dict[str, Any]:
    """
    Parses a natural language AI prompt into structured search parameters,
    extracts count dynamically, and synthesizes a high-intent Tavily query.
    """
    system_prompt = (
        "You are an expert B2B lead intelligence search strategist. "
        "A user is describing the companies and decision-makers they want to find. "
        "Analyze the user's natural language prompt, extract target geography, industry, executive roles, "
        "and desired company count, and formulate a laser-focused search query for web search (UNDER 10 WORDS total). "
        "Output strict JSON only. Start immediately with '{'."
    )

    prompt = f"""
User's Search Prompt:
"{user_prompt}"

Tasks:
1. Extract target geography (e.g., India, United States, UK). If India or Indian cities/states are mentioned, set primary_country to "India" and country_code to "IN".
2. Extract target industry (e.g., Seafood & Aquaculture, Logistics, SaaS).
3. Extract desired decision-maker titles (e.g. CEO, Founder, Managing Director).
4. Extract desired company count if mentioned in the prompt (e.g. 'find 2...', 'find 5...', '10 companies'). If not specified, default to 5.
5. Formulate an ultra-clean, concise search query for web search (UNDER 10 WORDS total, e.g. 'seafood transport India CEO Founder -jobs'). Keep negative keywords to max 2 (-jobs -directory).

Return ONLY this JSON structure:
{{
  "tavily_query": "...",
  "primary_industry": "...",
  "primary_country": "...",
  "country_code": "...",
  "extracted_count": 5,
  "titles": ["CEO", "Founder"],
  "strategy_thought": "..."
}}
"""
    return call_nvidia_json(prompt, system_prompt, api_key)



def is_generic_or_missing_leadership(name: Optional[str], company_name: str = "") -> bool:
    """
    Evaluates whether an extracted decision-maker name is generic, missing,
    or placeholder text, indicating that targeted Pass 2 enrichment should be triggered.
    """
    if not name:
        return True
    clean = re.sub(r"[^\w\s]", " ", str(name)).strip().lower()
    if not clean:
        return True

    generic_terms = {
        "not listed", "not listed in snippet", "executive team", "executive leadership",
        "leadership team", "management team", "management", "c-suite", "c level",
        "unknown", "unspecified", "n/a", "null", "none", "team", "founder", "ceo",
        "cto", "coo", "director", "president", "contact us", "about us", "staff",
        "employees", "corporate", "administration", "leadership", "executive"
    }

    if clean in generic_terms:
        return True

    # If any generic phrase is in the string
    if any(phrase in clean for phrase in [
        "not listed", "executive team", "leadership team", "management team",
        "not specified", "unknown", "c-level", "in snippet", "team /"
    ]):
        return True

    # If the name is basically the company name itself
    if company_name:
        clean_company = re.sub(r"[^\w\s]", " ", str(company_name)).strip().lower()
        if clean_company and (clean == clean_company or clean_company in clean or clean in clean_company):
            return True

    # A valid human name almost always consists of at least 2 words (First + Last)
    words = [w for w in clean.split() if len(w) > 1]
    if len(words) < 2:
        return True

    # Check if the words are solely corporate job titles rather than a person's name
    titles_set = {
        "chief", "executive", "officer", "ceo", "founder", "cto", "coo",
        "managing", "director", "president", "vice", "head", "lead", "owner"
    }
    if all(w in titles_set for w in words):
        return True

    return False


def enrich_decision_maker_via_tavily(
    company_name: str,
    domain: str,
    country: str,
    tavily_key: str,
    nvidia_key: str,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Pass 2: Targeted Tavily Leadership Search.
    Fires when Pass 1 did not surface an individual person's name for the company.
    Queries the live web specifically for the company's C-level leadership & LinkedIn profiles,
    then parses the snippets via NVIDIA NIM LLM.
    """
    from tavily import TavilyClient

    clean_company = re.sub(r"[^\w\s]", " ", company_name).strip()
    leadership_query = f'"{clean_company}" (CEO OR Founder OR "Co-Founder" OR "Managing Director" OR President OR CTO OR Director)'
    print(f"     [Pass 2: Targeted Leadership Search] Query: \"{leadership_query}\"", flush=True)

    try:
        client = TavilyClient(api_key=tavily_key)
        search_res = client.search(
            query=leadership_query,
            search_depth="basic",
            max_results=3,
            include_answer=False,
        )
        results = search_res.get("results", [])
        if not results:
            print(f"     [Pass 2 Notice] No leadership search results returned for {clean_company}.", flush=True)
            return {}

        snippets = []
        for r in results:
            snippets.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:350],
            })

        system_prompt = (
            "You are an expert executive intelligence analyst. "
            f"Identify the top C-level decision-maker (CEO, Founder, Managing Director, CTO, President) for '{company_name}'. "
            "Extract their real human full name, exact title, and personal LinkedIn profile URL if present. "
            "If no individual person's name is found in the snippets, set name to 'Executive Leadership'. "
            "Output MUST be strict JSON only. Start immediately with '{'."
        )

        prompt = f"""Target Company: {company_name} (Domain: {domain}, Country: {country})

Search Results:
{json.dumps(snippets, indent=2)}

Tasks:
1. Extract the actual full name of the primary human leader / founder / CEO of {company_name}.
2. Extract their exact title (e.g. 'Founder & CEO', 'Managing Director', 'Chief Executive Officer').
3. Extract their personal LinkedIn profile URL if present in the results (e.g. 'https://linkedin.com/in/...').
4. If no individual person is named in the snippets, return name as 'Executive Leadership'.

Return ONLY this JSON structure:
{{
  "name": "...",
  "title": "...",
  "linkedin_url": "https://linkedin.com/in/..." or null,
  "confidence": "high" or "medium" or "low"
}}
"""
        extracted = call_nvidia_json(prompt, system_prompt, nvidia_key, model=model)
        person_name = str(extracted.get("name", "")).strip()

        if is_generic_or_missing_leadership(person_name, company_name=clean_company):
            return {}

        linkedin_url = extracted.get("linkedin_url")
        if linkedin_url and not ("linkedin.com/in/" in str(linkedin_url).lower()):
            linkedin_url = None

        return {
            "name": person_name,
            "title": extracted.get("title") or "Managing Director / CEO",
            "linkedin_url": linkedin_url,
        }

    except Exception as exc:
        print(f"     [Pass 2 Error] Failed leadership enrichment for {company_name}: {exc}", flush=True)
        return {}


def run_lead_discovery(criteria: Dict[str, Any], nvidia_key: str, tavily_key: str) -> List[Dict[str, Any]]:
    """
    Executes end-to-end lead discovery:
    1. Synthesizes search query via AI Engine (from structured filters or natural language prompt)
    2. Searches live web
    3. Extracts verified company & leadership intelligence
    4. Automatically saves every qualified lead into SQLite
    """
    from tavily import TavilyClient

    mode = criteria.get("mode", "manual")
    count = int(criteria.get("count", 10))

    # Step 1: Formulate query based on active mode
    if mode == "prompt" and criteria.get("prompt"):
        user_prompt = criteria.get("prompt", "").strip()
        print(f"\n{'='*65}", flush=True)
        print(f"[DISCOVERY ENGINE STARTED] Mode: AI PROMPT", flush=True)
        print(f"  [Processing Natural Language Prompt]: \"{user_prompt}\"", flush=True)
        query_info = formulate_search_query_from_prompt(user_prompt, count, nvidia_key)
        geos = query_info.get("primary_country") or "India"
        if query_info.get("extracted_count"):
            try:
                count = max(1, min(20, int(query_info.get("extracted_count"))))
            except (ValueError, TypeError):
                count = 5
        else:
            count = 5
        print(f"  [AI Inferred Target Count]: {count} companies", flush=True)
        print(f"{'='*65}", flush=True)
    else:
        print(f"\n{'='*65}", flush=True)
        print(f"[DISCOVERY ENGINE STARTED] Mode: STRUCTURED FILTERS | Target Count: {count}", flush=True)
        print(f"{'='*65}", flush=True)
        query_info = formulate_search_query_from_criteria(criteria, nvidia_key)
        geos = ", ".join(criteria.get("geographies", ["United States", "United Kingdom"]))

    tavily_query = query_info.get("tavily_query") or "SaaS AI development CEO Founder leadership -jobs"
    print(f"  [Synthesized Search Query]: \"{tavily_query}\"", flush=True)
    print(f"  [Resolved Target Geography]: \"{geos}\"", flush=True)

    # Step 2: Tavily Search
    client = TavilyClient(api_key=tavily_key)
    buffer_max = min(max(count * 2, 8), 20)
    print(f"  [Web Search] Fetching up to {buffer_max} candidates...", flush=True)
    search_response = client.search(
        query=tavily_query,
        search_depth="advanced",
        max_results=buffer_max,
        exclude_domains=DIRECTORY_DOMAINS[:25],
        include_answer=False,
    )

    raw_results = search_response.get("results", [])
    print(f"  [Tavily Search] Retrieved {len(raw_results)} results.", flush=True)

    candidates = []
    seen = set()
    blog_paths = ("/blog/", "/blogs/", "/article/", "/articles/", "/news/", "/guide/", "/guides/", "/top-", "/best-", "/resources/")

    for item in raw_results:
        url = item.get("url", "")
        netloc = urlparse(url).netloc.lower().replace("www.", "")

        if any(d in netloc for d in DIRECTORY_DOMAINS):
            continue

        # If Tavily returned a blog/article URL, use the root domain homepage for company extraction
        target_url = url
        if any(bp in url.lower() for bp in blog_paths):
            target_url = f"https://{netloc}"

        if netloc and netloc not in seen:
            seen.add(netloc)
            candidates.append({
                "title": item.get("title", ""),
                "url": target_url,
                "domain": netloc,
                "content": item.get("content", ""),
            })
            if len(candidates) >= count:
                break

    print(f"  [Candidates Filtered] {len(candidates)} direct company sites queued for LLM analysis.", flush=True)

    # Step 3: Intelligence extraction and SQLite saving
    discovered_leads = []
    for idx, candidate in enumerate(candidates, start=1):
        print(f"\n  [Analyzing {idx}/{len(candidates)}] -> {candidate['domain']}", flush=True)
        try:
            # Pass 1: Extract company intelligence from candidate site
            intel = extract_lead_intelligence_with_llm(
                tavily_item=candidate,
                api_key=nvidia_key,
                model=DEFAULT_MODEL,
                target_geography=geos,
            )

            # Assign company type and key need from criteria if not extracted
            if not intel.get("company_type") or intel.get("company_type") == "Digital Business":
                intel["company_type"] = criteria.get("company_types", ["Digital Agency"])[0] if criteria.get("company_types") else "Software Company"

            # Step 2b: Apollo.io Enterprise Enrichment (Active when APOLLO_API_KEY is configured)
            if is_apollo_configured():
                print(f"     [Apollo API] Querying organization & executive intelligence for {intel.get('domain')}...", flush=True)
                try:
                    apollo_data = enrich_lead_full_apollo(
                        domain=intel.get("domain", candidate["domain"]),
                        company_name=intel.get("company_name", ""),
                    )
                    org_info = apollo_data.get("organization") or {}
                    apollo_people = apollo_data.get("people") or []

                    if org_info:
                        if org_info.get("company_name"):
                            intel["company_name"] = org_info["company_name"]
                        if org_info.get("employee_count"):
                            intel["employee_count"] = org_info["employee_count"]
                        if org_info.get("annual_revenue"):
                            intel["annual_revenue"] = org_info["annual_revenue"]
                        if org_info.get("technologies"):
                            intel["technologies"] = org_info["technologies"]
                        if org_info.get("company_linkedin_url"):
                            intel["company_linkedin_url"] = org_info["company_linkedin_url"]
                        if org_info.get("primary_phone"):
                            intel["primary_phone"] = org_info["primary_phone"]
                        if org_info.get("city"):
                            intel["city"] = org_info["city"]
                        if org_info.get("state"):
                            intel["state"] = org_info["state"]
                        intel["apollo_org_id"] = org_info.get("apollo_org_id")
                        intel["apollo_enrichment_status"] = "enriched"

                    if apollo_people:
                        top_person = apollo_people[0]
                        intel["c_level_name"] = top_person["name"]
                        intel["c_level_title"] = top_person.get("title", "Chief Executive Officer")
                        intel["decision_maker_name"] = top_person["name"]
                        intel["decision_maker_role"] = intel["c_level_title"]
                        intel["email"] = top_person.get("email", "")
                        intel["email_status"] = top_person.get("email_status", "verified" if top_person.get("email") else "unverified")
                        intel["phone"] = top_person.get("phone", "")
                        intel["linkedin_url"] = top_person.get("linkedin_url", "")
                        intel["apollo_person_id"] = top_person.get("apollo_person_id")
                        intel["apollo_headline"] = top_person.get("apollo_headline")
                        intel["apollo_enrichment_status"] = "enriched"
                        print(f"     [Apollo Success] Verified Leader: {top_person['name']} ({intel['c_level_title']}) | Email: {intel['email'] or 'pending'}", flush=True)
                except Exception as apollo_err:
                    print(f"     [Apollo Warning] Apollo enrichment error: {apollo_err}", flush=True)

            # Pass 2: Two-Pass Decision-Maker Cascade
            # If Pass 1 and Apollo did not find an individual person's name, run a targeted Tavily search for C-suite leaders
            c_name = intel.get("c_level_name", "")
            comp_name = intel.get("company_name", candidate["domain"])
            if is_generic_or_missing_leadership(c_name, company_name=comp_name):
                print(f"     [Pass 1 Result] Decision-maker was generic ('{c_name}'). Triggering Pass 2 Targeted Leadership Search...", flush=True)
                enriched_dm = enrich_decision_maker_via_tavily(
                    company_name=comp_name,
                    domain=intel.get("domain", candidate["domain"]),
                    country=intel.get("country", geos),
                    tavily_key=tavily_key,
                    nvidia_key=nvidia_key,
                )
                if enriched_dm and enriched_dm.get("name"):
                    intel["c_level_name"] = enriched_dm["name"]
                    intel["c_level_title"] = enriched_dm.get("title") or "C-Level Leadership"
                    intel["decision_maker_name"] = enriched_dm["name"]
                    intel["decision_maker_role"] = intel["c_level_title"]
                    if enriched_dm.get("linkedin_url"):
                        intel["linkedin_url"] = enriched_dm["linkedin_url"]
                    print(f"     [Pass 2 SUCCESS] Enriched Decision-Maker: {enriched_dm['name']} ({intel['c_level_title']})", flush=True)
                    if enriched_dm.get("linkedin_url"):
                        print(f"     [Pass 2 SUCCESS] Direct LinkedIn Profile: {enriched_dm['linkedin_url']}", flush=True)
                else:
                    print(f"     [Pass 2 Notice] No named individual identified in Pass 2. Keeping Executive Leadership.", flush=True)
            else:
                print(f"     [Leadership Verified] Decision-maker identified: {c_name} ({intel.get('c_level_title')}) - Skipping Pass 2", flush=True)

            # Save directly into SQLite database
            company_id = save_company_and_people(intel)
            saved_lead = get_company_by_id(company_id)

            if saved_lead:
                discovered_leads.append(saved_lead)
            else:
                discovered_leads.append(intel)

        except Exception as exc:
            print(f"  [Warning] Failed extraction on {candidate['domain']}: {exc}", flush=True)

    print(f"\n{'='*65}", flush=True)
    print(f"[DISCOVERY ENGINE COMPLETE] {len(discovered_leads)} leads stored in SQLite!", flush=True)
    print(f"{'='*65}\n", flush=True)

    return discovered_leads

