"""Flask Server for LeadGen AI Dashboard powered by NVIDIA NIM, Tavily, and SQLite."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

# Safe stream wrapper to prevent OSError [Errno 22] on Windows when running in background/redirected pipes
class SafeStream:
    def __init__(self, stream):
        self._stream = stream

    def write(self, data):
        try:
            return self._stream.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            return self._stream.flush()
        except Exception:
            pass

    def reconfigure(self, **kwargs):
        try:
            return self._stream.reconfigure(**kwargs)
        except Exception:
            pass

    def __getattr__(self, attr):
        return getattr(self._stream, attr)

if sys.stdout is not None:
    sys.stdout = SafeStream(sys.stdout)
if sys.stderr is not None:
    sys.stderr = SafeStream(sys.stderr)


from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from config import (
    COMPANY_SIZE_MAX,
    COMPANY_SIZE_MIN,
    DECISION_MAKER_TITLES,
    ICP_CATEGORIES,
    TARGET_INDUSTRIES,
    TARGET_REGIONS,
)
from apollo_client import enrich_lead_full_apollo, is_apollo_configured
from coresignal_client import (
    execute_coresignal_agentic_search,
    is_coresignal_configured,
)
from database import (
    apply_apollo_enrichment_to_company,
    delete_company,
    export_leads_csv,
    get_all_companies,
    get_company_by_id,
    get_stats,
    init_db,
    save_company_and_people,
    update_company_status,
)
from discovery_service import run_lead_discovery, validate_search_prompt_intent
from website_resolver import resolve_company_website

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Verify SQLite schema on startup
init_db()


@app.errorhandler(500)
@app.errorhandler(Exception)
def handle_app_exception(e):
    """Guarantees API endpoints always return JSON even on unhandled errors."""
    return jsonify({"success": False, "error": str(e)}), 500


@app.route("/")
@app.route("/dashboard")
def index():
    """Renders the Consolidated AI Lead Intelligence Dashboard."""
    stats = get_stats()
    leads = get_all_companies(limit=250)
    default_prompt = "Find 5 US based Software Development Companies whose employee count is 20 to 100 with their CEO , Founder name"
    return render_template(
        "dashboard.html",
        stats=stats,
        leads=leads,
        default_prompt=default_prompt,
    )


@app.route("/leads")
def extracted_leads_view():
    """Renders the dedicated extracted leads repository."""
    stats = get_stats()
    leads = get_all_companies(limit=500)
    return render_template(
        "extracted_leads.html",
        stats=stats,
        leads=leads,
    )


@app.route("/api/discover", methods=["POST"])
def api_discover():
    """Runs AI Discovery Engine from frontend criteria or prompt and saves to SQLite."""
    data: Dict[str, Any] = request.get_json() or {}
    mode = data.get("mode", "manual")
    print(f"\n[SERVER] >>> POST /api/discover - Mode: {mode.upper()} | Requested Count: {data.get('count', 10)}", flush=True)

    if mode == "prompt":
        prompt_text = str(data.get("prompt", "")).strip()
        print(f"[SERVER]     Prompt: \"{prompt_text}\"", flush=True)

        # Intercept greetings, conversational phrases, or vague prompts
        is_greeting, guidance_msg = validate_search_prompt_intent(prompt_text)
        if is_greeting:
            print(f"[SERVER]     [Prompt Intent] Conversational input detected. Returning guidance.", flush=True)
            return jsonify({
                "success": False,
                "is_guidance": True,
                "message": guidance_msg
            }), 200
    else:
        print(f"[SERVER]     Geographies: {data.get('geographies')}", flush=True)
        print(f"[SERVER]     Industries: {data.get('industries')}", flush=True)

    nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip() or data.get("nvidia_api_key", "").strip()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip() or data.get("tavily_api_key", "").strip()

    if not nvidia_key:
        print("[SERVER] [Error] AI Engine API key is missing.", flush=True)
        return jsonify({"success": False, "error": "AI Engine API key is missing in .env or request."}), 400

    if not tavily_key:
        print("[SERVER] [Error] Search Agent API key is missing.", flush=True)
        return jsonify({"success": False, "error": "Search Agent API key is missing in .env or request."}), 400

    try:
        leads = run_lead_discovery(data, nvidia_key=nvidia_key, tavily_key=tavily_key)
        stats = get_stats()
        print(f"[SERVER] <<< 200 OK /api/discover - Returned {len(leads)} qualified leads. Total in DB: {stats.get('total_companies')}\n", flush=True)
        return jsonify({
            "success": True,
            "leads": leads,
            "count": len(leads),
            "stats": stats,
        })
    except Exception as exc:
        print(f"[SERVER] [Error in /api/discover]: {exc}", flush=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/leads", methods=["GET"])
def api_get_leads():
    """Returns stored leads with optional search, industry, and status filtering."""
    search = request.args.get("search")
    industry = request.args.get("industry")
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))

    print(f"[SERVER] >>> GET /api/leads - Search: '{search}', Industry: '{industry}', Status: '{status}'", flush=True)
    leads = get_all_companies(search=search, industry=industry, status=status, limit=limit)
    print(f"[SERVER] <<< 200 OK /api/leads - Returning {len(leads)} leads", flush=True)
    return jsonify({"success": True, "leads": leads, "count": len(leads)})


@app.route("/api/leads/<int:company_id>", methods=["GET"])
@app.route("/api/companies/<int:company_id>", methods=["GET"])
def api_get_lead_details(company_id: int):
    """Returns detailed information of a specific lead and associated people."""
    print(f"[SERVER] >>> GET /api/leads/{company_id}", flush=True)
    lead = get_company_by_id(company_id)
    if not lead:
        print(f"[SERVER] [Error] Lead ID {company_id} not found.", flush=True)
        return jsonify({"success": False, "error": "Lead not found."}), 404
    print(f"[SERVER] <<< 200 OK /api/leads/{company_id} - Company: {lead.get('company_name')}", flush=True)
    return jsonify({"success": True, "lead": lead})


@app.route("/api/leads/<int:company_id>/status", methods=["PATCH"])
@app.route("/api/companies/<int:company_id>/status", methods=["PATCH"])
def api_update_status(company_id: int):
    """Updates lead qualification status."""
    data = request.get_json() or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"success": False, "error": "New status is required."}), 400

    print(f"[SERVER] >>> PATCH /api/leads/{company_id}/status -> '{new_status}'", flush=True)
    success = update_company_status(company_id, new_status)
    return jsonify({"success": success})


@app.route("/api/leads/<int:company_id>", methods=["DELETE"])
@app.route("/api/companies/<int:company_id>", methods=["DELETE"])
def api_delete_lead(company_id: int):
    """Deletes a company and its people from SQLite."""
    print(f"[SERVER] >>> DELETE /api/leads/{company_id}", flush=True)
    success = delete_company(company_id)
    print(f"[SERVER] <<< Lead ID {company_id} deleted: {success}", flush=True)
    return jsonify({"success": success})


@app.route("/api/export", methods=["GET"])
def api_export_csv():
    """Exports all stored leads as a downloadable CSV file."""
    print("[SERVER] >>> GET /api/export - Generating CSV export...", flush=True)
    csv_data = export_leads_csv()
    print(f"[SERVER] <<< CSV generated successfully ({len(csv_data)} bytes)", flush=True)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leadgen_ai_extracted_leads.csv"},
    )


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Returns current database metrics."""
    return jsonify({"success": True, "stats": get_stats()})


@app.route("/api/enrich/apollo/<int:company_id>", methods=["POST"])
@app.route("/api/leads/<int:company_id>/enrich-apollo", methods=["POST"])
def api_apollo_enrich(company_id: int):
    """
    Live Apollo.io enrichment endpoint:
    Enriches company headcount, revenue, tech stack, and decision-maker verified emails & phones.
    """
    lead = get_company_by_id(company_id)
    if not lead:
        return jsonify({"success": False, "error": "Company not found"}), 404

    data = request.get_json(silent=True) or {}
    api_key = (data.get("apollo_api_key") or os.getenv("APOLLO_API_KEY", "")).strip()

    if not is_apollo_configured(api_key):
        return jsonify({
            "success": False,
            "requires_key": True,
            "error": "APOLLO_API_KEY is not configured yet. Please add your Apollo API key to .env or enter it in the dashboard."
        }), 400

    print(f"\n[SERVER] >>> POST /api/enrich/apollo/{company_id} - Domain: {lead['domain']}", flush=True)

    try:
        apollo_result = enrich_lead_full_apollo(
            domain=lead["domain"],
            company_name=lead["company_name"],
            api_key=api_key,
        )

        if apollo_result.get("status") == "success":
            apply_apollo_enrichment_to_company(company_id, apollo_result)
            updated_lead = get_company_by_id(company_id)
            print(f"[SERVER] <<< 200 OK /api/enrich/apollo/{company_id} - Successfully enriched with Apollo data!\n", flush=True)
            return jsonify({
                "success": True,
                "message": f"Successfully enriched {lead['company_name']} with Apollo intelligence!",
                "lead": updated_lead,
                "apollo_data": apollo_result,
            })
        else:
            print(f"[SERVER] [Apollo Notice] No additional Apollo profile found for {lead['domain']}.", flush=True)
            return jsonify({
                "success": False,
                "message": f"Apollo could not find verified profiles for domain: {lead['domain']}. Domain might be unindexed.",
                "lead": lead,
            }), 404

    except Exception as exc:
        print(f"[SERVER] [Error in Apollo Enrichment]: {exc}", flush=True)
        return jsonify({"success": False, "error": str(exc)}), 500

@app.route("/coresignal")
def coresignal_view():
    """Renders the consolidated Executive Search console."""
    stats = get_stats()
    leads = get_all_companies(limit=250)
    default_prompt = "Find 5 US based Software Development Companies whose employee count is 20 to 100 with their CEO , Founder name"
    return render_template(
        "dashboard.html",
        stats=stats,
        leads=leads,
        default_prompt=default_prompt,
    )


@app.route("/website-extractor")
def website_extractor_view():
    """Renders the Tavily Website Extractor Interactive Testbench."""
    stats = get_stats()
    return render_template("website_extractor.html", stats=stats)


@app.route("/api/coresignal/search", methods=["POST"])
def api_coresignal_search():
    """Executes Coresignal Agentic Fast Search API."""
    data: Dict[str, Any] = request.get_json() or {}
    prompt = data.get("prompt", "").strip()
    threshold = float(data.get("threshold", 0.97))
    entity = data.get("entity", "employee")
    return_data = data.get("return_data", True)
    api_key = (data.get("api_key") or "").strip()

    limit_val = data.get("limit")
    limit = int(limit_val) if (limit_val is not None and str(limit_val).isdigit()) else None

    exclude_saved = bool(data.get("exclude_saved", True))
    offset = int(data.get("offset", 0))

    if not prompt:
        return jsonify({"success": False, "error": "Search prompt cannot be empty."}), 400

    try:
        res = execute_coresignal_agentic_search(
            prompt=prompt,
            threshold=threshold,
            entity=entity,
            return_data=return_data,
            api_key=api_key,
            limit=limit,
            exclude_saved=exclude_saved,
            offset=offset,
        )
        return jsonify(res)
    except Exception as exc:
        print(f"[SERVER] [Coresignal Error]: {exc}", flush=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/resolve-website", methods=["POST"])
def api_resolve_website():
    """Resolves canonical company website using Tavily multi-factor intelligence."""
    data: Dict[str, Any] = request.get_json() or {}
    company_name = (data.get("company_name") or "").strip()
    ceo_name = (data.get("ceo_name") or "").strip()
    country = (data.get("country") or "").strip()
    industry = (data.get("industry") or "").strip()

    if not company_name:
        return jsonify({"success": False, "error": "Company name is required."}), 400

    try:
        res = resolve_company_website(
            company_name=company_name,
            ceo_name=ceo_name,
            country=country,
            industry=industry,
        )
        return jsonify({"success": True, **res})
    except Exception as exc:
        print(f"[SERVER] [Website Resolver Error]: {exc}", flush=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@app.route("/api/coresignal/save-leads", methods=["POST"])
def api_coresignal_save_leads():
    """Converts and saves Coresignal search results into SQLite database with verified websites concurrently."""
    import re
    from concurrent.futures import ThreadPoolExecutor

    data: Dict[str, Any] = request.get_json() or {}
    items = data.get("leads", [])
    if not items:
        return jsonify({"success": False, "error": "No lead items provided to save."}), 400

    country_map = {
        "US": "United States",
        "GB": "United Kingdom",
        "UK": "United Kingdom",
        "CA": "Canada",
        "AU": "Australia",
        "DE": "Germany",
        "FR": "France",
        "IN": "India",
        "LK": "Sri Lanka",
        "SG": "Singapore",
        "IE": "Ireland",
        "NL": "Netherlands",
        "CH": "Switzerland",
        "SE": "Sweden",
        "AE": "United Arab Emirates",
    }

    def _prepare_lead(item: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves official website using Tavily concurrently and prepares lead dict."""
        try:
            full_name = item.get("full_name") or "Executive Leadership"
            title = item.get("active_experience_title") or "Executive"
            company_name = item.get("company_name") or "Unnamed Company"
            linkedin_url = item.get("linkedin_url") or ""

            exp_list = item.get("experience") or []
            exp = exp_list[0] if exp_list else {}

            raw_ind = exp.get("company_industry")
            if not raw_ind and exp.get("company_categories_and_keywords"):
                cats = exp.get("company_categories_and_keywords")
                if isinstance(cats, list) and len(cats) > 0:
                    raw_ind = str(cats[0]).strip().title()
            if not raw_ind and item.get("company_industry"):
                raw_ind = str(item.get("company_industry")).strip().title()
            industry = (raw_ind or "General Business").strip()

            employees_count = exp.get("company_employees_count")
            country_iso = (exp.get("company_hq_country_iso2") or "US").strip().upper()
            country = country_map.get(country_iso, country_iso)

            clean_name = re.sub(r"(?i)\b(inc|llc|ltd|corp|corporation|technologies|intelligence|group|co|labs|sa|de|cv)\b\.?", "", company_name).strip()
            clean_slug = re.sub(r"[^a-zA-Z0-9]", "", clean_name.lower()) or "company"

            # Check if website is already verified
            if item.get("website_url") and item.get("domain") and not str(item.get("website_url")).endswith("company.com"):
                domain = item["domain"]
                website_url = item["website_url"]
                confidence = 0.95
            else:
                resolved = resolve_company_website(
                    company_name=company_name,
                    ceo_name=full_name,
                    country=country,
                    industry=industry
                )
                domain = resolved.get("domain") or exp.get("company_domain") or f"{clean_slug}.com"
                website_url = resolved.get("website_url") or exp.get("company_website") or f"https://www.{domain}"
                confidence = resolved.get("confidence", 0.85)

            company_type = industry if any(w in industry.lower() for w in ["agency", "company", "firm", "service", "tech"]) else f"{industry} Company"

            lead_dict = {
                "company_name": company_name,
                "domain": domain,
                "website_url": website_url,
                "country": country,
                "country_code": country_iso,
                "industry": industry,
                "company_type": company_type,
                "key_need": f"Verified leadership: {industry} organization led by {full_name} ({title})",
                "summary": f"{company_name} is a verified {industry} firm (~{employees_count or '20-100'} employees), led by {full_name}.",
                "employee_count": employees_count,
                "c_level_name": full_name,
                "c_level_title": title,
                "decision_maker_name": full_name,
                "decision_maker_role": title,
                "linkedin_url": linkedin_url,
                "source_url": linkedin_url or "https://leadgen.ai",
            }

            return {
                "success": True,
                "lead_dict": lead_dict,
                "saved_lead": {
                    "company_name": company_name,
                    "domain": domain,
                    "website_url": website_url,
                    "confidence": confidence,
                }
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"{item.get('company_name', 'Unknown')}: {str(exc)}",
                "saved_lead": {
                    "company_name": item.get("company_name", "Unknown"),
                    "domain": item.get("domain") or "company.com",
                    "website_url": item.get("website_url") or "",
                    "confidence": 0.5,
                }
            }

    # Parallel website resolution via ThreadPoolExecutor (fast batch resolution)
    max_workers = min(max(len(items), 1), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        prepared_results = list(executor.map(_prepare_lead, items))

    saved_count = 0
    saved_leads = []
    errors = []

    # Sequential SQLite database commit in main thread (thread-safe, 0 risk of database lock)
    for res in prepared_results:
        if res.get("success") and res.get("lead_dict"):
            try:
                save_company_and_people(res["lead_dict"])
                saved_count += 1
                saved_leads.append(res["saved_lead"])
            except Exception as exc:
                errors.append(f"{res.get('saved_lead', {}).get('company_name', 'Unknown')}: {str(exc)}")
        else:
            if res.get("error"):
                errors.append(res["error"])
            saved_leads.append(res.get("saved_lead", {}))

    stats = get_stats()
    return jsonify({
        "success": True,
        "saved_count": saved_count,
        "saved_leads": saved_leads,
        "total_requested": len(items),
        "stats": stats,
        "errors": errors,
    })



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'='*65}", flush=True)
    print(f"🚀 [LEADGEN AI FLASK SERVER LAUNCHED]", flush=True)
    print(f"   Dashboard URL: http://localhost:{port}", flush=True)
    print(f"   Provider: NVIDIA NIM (nemotron-3.5-super-vl-120b-a12b)", flush=True)
    print(f"   Search: Live Web Intelligence Engine", flush=True)
    print(f"   Database: SQLite (leads.db)", flush=True)
    print(f"{'='*65}\n", flush=True)
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

