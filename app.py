"""Streamlit Visual UI for AI Lead Discovery Engine (OpenRouter + Tavily)."""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse
import streamlit as st
from dotenv import load_dotenv

# Ensure Windows terminal handles output smoothly without charmap crashes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from nvidia_client import (
    DEFAULT_MODEL,
    extract_lead_intelligence_with_llm,
    parse_user_query_with_llm,
)

load_dotenv()

# Page Configuration
st.set_page_config(
    page_title="AI Lead Discovery Engine",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for modern dark / vibrant aesthetics
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    }
    .metric-val {
        font-size: 1.5rem;
        font-weight: 700;
        color: #38bdf8;
    }
    .metric-lbl {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .lead-card {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-left: 4px solid #3b82f6;
        border-radius: 10px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        transition: transform 0.2s ease;
    }
    .lead-card:hover {
        border-color: #38bdf8;
    }
    .company-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 0.3rem;
    }
    .dm-badge {
        background: #1e1b4b;
        color: #a5b4fc;
        padding: 0.2rem 0.6rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 0.6rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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


def get_tavily_search_results(query: str, max_results: int, api_key: str) -> list[dict]:
    """Calls Tavily API with extensive directory domain exclusions."""
    from tavily import TavilyClient

    print(f"\n{'='*65}")
    print(f"[STEP 2: TAVILY WEB SEARCH]")
    print(f"{'='*65}")
    print(f"  [Search Query]     : \"{query}\"")
    print(f"  [Max Desired Leads]: {max_results}")

    client = TavilyClient(api_key=api_key)
    # Request extra buffer to guarantee clean direct business candidates
    buffer_max = min(max_results * 3, 20)
    print(f"  [Tavily API] Fetching up to {buffer_max} raw candidates (excluding 25+ directory domains)...")
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=buffer_max,
        exclude_domains=DIRECTORY_DOMAINS[:25],  # Tavily accepts up to ~25 excluded domains
        include_answer=False,
    )
    raw = response.get("results", [])
    print(f"  [Tavily API] Retrieved {len(raw)} raw search results.")

    seen = set()
    cleaned = []
    for item in raw:
        url = item.get("url", "")
        netloc = urlparse(url).netloc.lower().replace("www.", "")

        # Skip known directory, ranking, or aggregator websites
        if any(d in netloc for d in DIRECTORY_DOMAINS):
            print(f"  [Filtered Directory] Skipping aggregator: {netloc}")
            continue

        if netloc and netloc not in seen:
            seen.add(netloc)
            cleaned.append({
                "title": item.get("title", ""),
                "url": url,
                "domain": netloc,
                "content": item.get("content", ""),
            })
            print(f"  [Qualified Candidate #{len(cleaned)}] {netloc} ({url})")
            if len(cleaned) >= max_results:
                break

    print(f"  [Selection Complete] Selected {len(cleaned)} direct candidates for intelligence extraction.")
    print(f"{'-'*65}")
    return cleaned


# ==========================================
# Sidebar: API Keys & Configuration
# ==========================================
with st.sidebar:
    st.header("⚙️ API Configuration")

    nvidia_key = st.text_input(
        "NVIDIA API Key",
        value=os.getenv("NVIDIA_API_KEY", ""),
        type="password",
        help="Get your key at https://build.nvidia.com",
    )

    tavily_key = st.text_input(
        "Tavily API Key",
        value=os.getenv("TAVILY_API_KEY", ""),
        type="password",
        help="Get your key at https://app.tavily.com",
    )

    selected_model = DEFAULT_MODEL
    st.text_input(
        "NVIDIA NIM Model (Fixed)",
        value=selected_model,
        disabled=True,
        help="Configured to use NVIDIA Nemotron 3.5 Super (build.nvidia.com)",
    )

    st.markdown("---")
    st.markdown(
        """
        **Pipeline Flow:**
        1. 🤖 **LLM Query Parsing**: Extracts lead count (default: 2) & builds search query.
        2. 🌐 **Tavily Search**: Retrieves direct company websites.
        3. 🧠 **LLM Intelligence**: Pinpoints true Company Name, Domain & Decision Maker.
        """
    )

# ==========================================
# Main Content
# ==========================================
st.markdown('<div class="main-title">🎯 AI Lead Discovery Engine</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Powered by <b>NVIDIA NIM</b> (Nemotron 3.5) intelligence & <b>Tavily</b> live web search.</div>',
    unsafe_allow_html=True,
)

# Search Input
user_query = st.text_input(
    "Enter what companies you are looking for:",
    value="",
    placeholder="e.g. Find 3 digital agencies in London for agency partnership, or SaaS in Austin hiring devs",
)

# Quick Suggestion Chips
col_chip1, col_chip2, col_chip3 = st.columns(3)
if col_chip1.button("🚀 Digital agencies in London"):
    user_query = "Digital agencies in London"
    st.session_state["user_query_val"] = user_query
if col_chip2.button("💼 3 SaaS in Austin hiring developers"):
    user_query = "3 SaaS in Austin hiring developers"
    st.session_state["user_query_val"] = user_query
if col_chip3.button("🤖 AI automation agencies in New York"):
    user_query = "AI automation agencies in New York"
    st.session_state["user_query_val"] = user_query

if "user_query_val" in st.session_state and not user_query:
    user_query = st.session_state["user_query_val"]

start_search = st.button("🔍 Search & Discover Leads", type="primary", use_container_width=True)

# ==========================================
# Execution Pipeline
# ==========================================
if start_search:
    print(f"\n{'#'*65}")
    print(f"[NEW LEAD SEARCH LAUNCHED]")
    print(f"   Query: \"{user_query}\"")
    print(f"{'#'*65}")

    if not user_query.strip():
        st.warning("Please enter a search query.")
        st.stop()

    if not nvidia_key.strip():
        st.error("Please provide your NVIDIA API Key in the left sidebar or .env file.")
        st.stop()

    if not tavily_key.strip():
        st.error("Please provide your Tavily API Key in the left sidebar.")
        st.stop()

    # Step 1: LLM Query Parsing
    st.markdown("### ⚡ Step 1: LLM Query Parsing")
    with st.spinner("LLM is parsing your request and formulating search parameters..."):
        try:
            parsed_intent = parse_user_query_with_llm(
                user_query=user_query,
                api_key=nvidia_key,
                model=selected_model,
            )
        except Exception as exc:
            st.error(f"Failed to parse query with LLM: {exc}")
            st.stop()

    # Display Parsed Metrics
    target_count = parsed_intent.get("count", 2)
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.markdown(
            f'<div class="metric-card"><div class="metric-val">{target_count}</div><div class="metric-lbl">Lead Count</div></div>',
            unsafe_allow_html=True,
        )
    with col_m2:
        st.markdown(
            f'<div class="metric-card"><div class="metric-val">{parsed_intent.get("target_location", "Global")}</div><div class="metric-lbl">Location</div></div>',
            unsafe_allow_html=True,
        )
    with col_m3:
        st.markdown(
            f'<div class="metric-card"><div class="metric-val">{parsed_intent.get("target_industry", "Target")}</div><div class="metric-lbl">Industry</div></div>',
            unsafe_allow_html=True,
        )
    with col_m4:
        st.markdown(
            f'<div class="metric-card"><div class="metric-val">{selected_model.split("/")[-1]}</div><div class="metric-lbl">Model</div></div>',
            unsafe_allow_html=True,
        )

    with st.expander("👁️ View LLM Extracted Search Query & Reasoning", expanded=True):
        st.write(f"**Tavily Search Query:** `{parsed_intent.get('tavily_query')}`")
        st.info(f"💡 **LLM Reasoning:** {parsed_intent.get('llm_thought')}")

    # Step 2: Tavily Search
    st.markdown("### 🌐 Step 2: Tavily Web Search")
    with st.spinner(f"Running Tavily live search for: '{parsed_intent.get('tavily_query')}'..."):
        try:
            tavily_results = get_tavily_search_results(
                query=parsed_intent.get("tavily_query"),
                max_results=target_count,
                api_key=tavily_key,
            )
        except Exception as exc:
            st.error(f"Tavily search failed: {exc}")
            st.stop()

    if not tavily_results:
        st.warning("No candidate websites found by Tavily for this query.")
        st.stop()

    with st.expander(f"📦 Raw Tavily Results ({len(tavily_results)} candidate websites found)", expanded=False):
        for idx, item in enumerate(tavily_results, start=1):
            st.write(f"**{idx}. [{item['title']}]({item['url']})** (`{item['domain']}`)")
            st.caption(f"{item['content'][:250]}...")
            st.markdown("---")

    # Step 3: LLM Intelligence Extraction
    st.markdown("### 🧠 Step 3: LLM Intelligence Extraction")
    progress_bar = st.progress(0)
    final_leads = []

    for idx, item in enumerate(tavily_results):
        status_text = st.empty()
        status_text.info(f"Analyzing company {idx+1}/{len(tavily_results)}: `{item['domain']}`...")

        try:
            lead_info = extract_lead_intelligence_with_llm(
                tavily_item=item,
                api_key=nvidia_key,
                model=selected_model,
            )
            final_leads.append(lead_info)
        except Exception as exc:
            st.warning(f"Could not extract intelligence for {item['domain']}: {exc}")

        progress_bar.progress((idx + 1) / len(tavily_results))

    status_text.empty()
    progress_bar.empty()

    # Step 4: Final Verified Leads
    st.markdown(f"### 🏆 Verified Leads Discovered ({len(final_leads)})")

    for idx, lead in enumerate(final_leads, start=1):
        with st.container():
            source_citation = ""
            if lead.get("source_url") and lead["source_url"] != lead["website_url"]:
                source_citation = f' <span style="color: #64748b; font-size: 0.85rem; margin-left: 0.8rem;">(Found via: <a href="{lead["source_url"]}" target="_blank" style="color: #94a3b8; text-decoration: underline;">Source Listing</a>)</span>'

            exec_name = lead.get('c_level_name') or lead.get('decision_maker_name') or "Executive Leadership"
            exec_title = lead.get('c_level_title') or lead.get('decision_maker_role') or "C-Level Leadership"

            card_html = (
                f'<div class="lead-card">'
                f'<div class="company-title">#{idx} {lead["company_name"]}</div>'
                f'<div style="margin-bottom: 0.5rem;">'
                f'🌐 <a href="{lead["website_url"]}" target="_blank" style="color: #38bdf8; text-decoration: none; font-size: 1.05rem;"><b>{lead["domain"]}</b></a>'
                f'{source_citation}'
                f'</div>'
                f'<div class="dm-badge">'
                f'👔 C-Level Executive: <b>{exec_name}</b> ({exec_title})'
                f'</div>'
                f'<p style="color: #cbd5e1; font-size: 0.95rem; margin-top: 0.3rem; margin-bottom: 0.2rem;">'
                f'{lead["summary"]}'
                f'</p>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

            col_btn1, col_btn2, _ = st.columns([1.2, 1.8, 1])
            with col_btn1:
                st.link_button(
                    "🌐 Visit Website",
                    lead["website_url"],
                    use_container_width=True,
                )
            with col_btn2:
                st.link_button(
                    "🔍 Find C-Level Executive on LinkedIn",
                    lead["linkedin_search_url"],
                    use_container_width=True,
                )
            st.markdown("<br/>", unsafe_allow_html=True)

    print(f"\n{'='*65}")
    print(f"[PIPELINE COMPLETE] Successfully discovered {len(final_leads)} verified leads!")
    for idx, lead in enumerate(final_leads, start=1):
        print(f"   #{idx} {lead['company_name']} ({lead['domain']}) | {lead.get('c_level_name')} ({lead.get('c_level_title')})")
    print(f"{'='*65}\n")
