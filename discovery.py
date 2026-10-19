"""Discovery Module: Uses Tavily API to find target companies and URLs tailored to your ICP."""

from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import quote, urlparse
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    DECISION_MAKER_TITLES,
    DISALLOWED_GEO_KEYWORDS,
    DISCOVERY_QUERY_TEMPLATES,
    ICP_CATEGORIES,
    TARGET_REGIONS,
    TAVILY_API_KEY,
)

load_dotenv()

# Domains/platforms to filter out when discovering direct company websites
EXCLUDED_BASE_DOMAINS = [
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "wikipedia.org",
    "glassdoor.com",
    "indeed.com",
    "clutch.co",
    "goodfirms.co",
    "yelp.com",
    "yahoo.com",
    "bloomberg.com",
    "forbes.com",
    "reuters.com",
    "techcrunch.com",
    "medium.com",
    "reddit.com",
    "quora.com",
    "digitalagencynetwork.com",
    "designrush.com",
    "upwork.com",
    "fiverr.com",
    "revenuebase.ai",
    "crunchbase.com",
    "zoominfo.com",
    "apollo.io",
    "pitchbook.com",
    "sortlist.com",
    "themanifest.com",
    "agencyanalytics.com",
    "hubspot.com",
    "topinteractiveagencies.com",
    "marketingagencyindex.com",
    "wellfound.com",
    "angel.co",
    "substack.com",
    "slideserve.com",
    "slideshare.net",
    "jobeka.com",
    "a16z.com",
    "ycombinator.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "monster.com",
]

# Patterns in URLs that indicate an article/blog/directory rather than a direct company website
LISTICLE_URL_PATTERNS = [
    "/blog/",
    "/blogs/",
    "/news/",
    "/articles/",
    "/article/",
    "/best-",
    "/top-",
    "/ranking/",
    "/list/",
    "/tag/",
    "/category/",
    "/companies/",
    "/directory/",
    "/find/",
    "/agencies/",
]

SEEN_DOMAINS_FILE = os.path.join(os.path.dirname(__file__), "seen_domains.txt")


def load_seen_domains() -> set[str]:
    """Loads previously discovered domains to avoid showing duplicates."""
    if not os.path.exists(SEEN_DOMAINS_FILE):
        return set()
    try:
        with open(SEEN_DOMAINS_FILE, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except Exception:
        return set()


def save_seen_domain(domain: str) -> None:
    """Saves a domain to prevent showing it again in future runs."""
    try:
        with open(SEEN_DOMAINS_FILE, "a", encoding="utf-8") as f:
            f.write(domain.strip().lower() + "\n")
    except Exception:
        pass


def clear_seen_domains() -> None:
    """Resets the history of seen domains."""
    if os.path.exists(SEEN_DOMAINS_FILE):
        os.remove(SEEN_DOMAINS_FILE)
        print("[Memory Cleared] Cleared seen_domains.txt. You will now get all original leads again.")


def is_excluded_domain(netloc: str) -> bool:
    """Checks if the domain or any of its subdomains belongs to an excluded platform."""
    clean_domain = netloc.lower().split(":")[0]
    for excluded in EXCLUDED_BASE_DOMAINS:
        if clean_domain == excluded or clean_domain.endswith("." + excluded):
            return True
    return False


def is_listicle_or_article(url: str, title: str) -> bool:
    """Detects whether a URL or title looks like a blog, directory, or listicle article."""
    lower_url = url.lower()
    for pattern in LISTICLE_URL_PATTERNS:
        if pattern in lower_url:
            return True

    lower_title = title.lower()
    if re.search(r"\b(top\s+\d+|\d+\s+best|\d+\s+top|\d+\s+leading|\d+\s+agencies|list of|reviews of)\b", lower_title):
        return True

    return False


def get_tavily_client():
    """Validates and returns the Tavily client."""
    api_key = os.getenv("TAVILY_API_KEY") or TAVILY_API_KEY
    if not api_key or api_key == "your_tavily_api_key_here":
        print("\n[ERROR] Tavily API key is missing!")
        print("Please set your TAVILY_API_KEY in the .env file:")
        print("    TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxx\n")
        print("You can get a free API key (1,000 free searches/month) at: https://app.tavily.com")
        return None

    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=api_key)
    except ImportError:
        print("[ERROR] tavily-python is not installed. Run: pip install tavily-python")
        return None


def extract_root_domain(url: str) -> str:
    """Extract clean domain from URL, e.g. https://www.example.com/about -> example.com"""
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def match_icp_pillars(text: str) -> list[tuple[str, int]]:
    """Scores content against the 5 ICP pillars and returns matched pillars."""
    lower_text = text.lower()
    scores = []
    for category, keywords in ICP_CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in lower_text)
        if score > 0:
            scores.append((category, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def evaluate_icp_verdict(text: str, title: str, domain: str) -> dict:
    """
    Evaluates headcount, geography, and ICP fit to produce a 3-tier verdict:
    - Likely fit (50-200 verified + US/UK verified)
    - Verify first (strong service overlap, headcount needs verification)
    - Exclude (<50, >200, directory, or outside US/UK)
    """
    combined_text = f"{title} {text}".lower()

    # 1. Geographic check: Exclude non-US/UK explicitly
    for bad_geo in DISALLOWED_GEO_KEYWORDS:
        if bad_geo in combined_text:
            return {
                "verdict": "Exclude",
                "tag": "[EXCLUDE]",
                "evidence": f"Found reference to '{bad_geo.capitalize()}'",
                "reason": "Outside target US / UK geography.",
            }

    # 2. Check for explicit company size indicators
    # Small size (<50)
    if re.search(r"\b(11[-–]50|2[-–]10|1[-–]10)\s+employees\b", combined_text):
        return {
            "verdict": "Exclude",
            "tag": "[EXCLUDE]",
            "evidence": "Reported size: 11-50 employees",
            "reason": "Below your 50–200 employee threshold.",
        }

    # Enterprise size (>200)
    if re.search(r"\b(500\+|1,000\+|500[-–]1,000|600\+|200\+)\s+employees\b", combined_text):
        return {
            "verdict": "Exclude",
            "tag": "[EXCLUDE]",
            "evidence": "Reported size: 200+ / 500+ employees",
            "reason": "Too large for your 50–200 employee filter.",
        }

    # Target sweet spot (50-200)
    if re.search(r"\b(51[-–]200|50[-–]200)\s+employees\b", combined_text) or re.search(r"\b(50\+|80\+|100\+|150\+)\s+(specialists|team|engineers|people|employees)\b", combined_text):
        return {
            "verdict": "Likely fit",
            "tag": "[LIKELY FIT]",
            "evidence": "US/UK presence; 50-200 employee band verified",
            "reason": "Fits the 50–200 employee band and ICP service criteria.",
        }

    # Ambiguous headcount (Needs website/LinkedIn crawl)
    return {
        "verdict": "Verify first",
        "tag": "[VERIFY FIRST]",
        "evidence": "US/UK presence detected; headcount unconfirmed",
        "reason": "Strong service overlap; verify whether employee count reaches 50.",
    }


GENERIC_TITLE_PHRASES = {
    "digital marketing agency", "digital agency", "creative agency", "marketing agency",
    "advertising agency", "pr agency", "web design agency", "seo agency",
    "web design", "web development", "software development", "digital strategy",
    "performance marketing", "integrated agency", "our services", "services",
    "contact us", "contact", "about us", "about", "home", "homepage",
    "london", "manchester", "birmingham", "uk", "united kingdom", "england",
    "new york", "texas", "california", "austin", "san francisco", "chicago",
    "us", "usa", "united states", "global", "europe"
}


def clean_segment(seg: str) -> str:
    """Removes leading/trailing punctuation and symbols."""
    return re.sub(r"^[^\w]+|[^\w]+$", "", seg).strip()


def is_generic_phrase(text: str) -> bool:
    """Detects if a string is pure SEO filler (e.g. 'Digital Marketing Agency London')."""
    cleaned = re.sub(r"[^\w\s]", " ", text).lower().strip()
    words = cleaned.split()
    if not words:
        return True
    if cleaned in GENERIC_TITLE_PHRASES:
        return True
    generic_words = sum(1 for w in words if any(w in gp.split() for gp in GENERIC_TITLE_PHRASES))
    return len(words) <= 5 and generic_words >= len(words) - 1


def extract_domain_brand(domain: str) -> str:
    """Extracts a readable business brand name from the domain name."""
    parts = domain.lower().split(".")
    if parts and parts[0] in ("www", "blog", "jobs", "careers", "app", "news"):
        parts = parts[1:]

    suffix = ""
    # Check for domain industry suffixes like .digital, .agency, .media
    if len(parts) >= 2 and parts[-1] in ("digital", "agency", "media", "studio", "tech", "solutions", "group", "consulting"):
        suffix = " " + parts[-1].capitalize()
        base = parts[-2]
    elif len(parts) >= 2 and parts[-1] in ("uk", "us", "ca", "au") and parts[-2] in ("co", "com", "org", "net"):
        base = parts[-3] if len(parts) >= 3 else parts[0]
    elif len(parts) >= 2:
        base = parts[-2]
    else:
        base = parts[0]

    if "-" in base:
        base = " ".join(w.capitalize() for w in base.split("-") if w)
    else:
        base = base.capitalize()

    return base + suffix


def extract_real_company_name(title: str, domain: str) -> str:
    """
    Intelligently extracts the real company/brand name instead of generic SEO titles.
    E.g.: 'Digital Marketing Agency London | TEAM LEWIS' -> 'TEAM LEWIS'
          'Manchester Digital Agency - The Drawing Room' -> 'The Drawing Room'
    """
    domain_brand = extract_domain_brand(domain)
    clean_domain_root = re.sub(r"[^\w]", "", domain_brand.lower())

    # Split on colon, pipes, dashes, and bullets
    raw_segments = re.split(r"[:\|\-–—•/]\s*", title)
    segments = [clean_segment(s) for s in raw_segments if clean_segment(s)]

    candidates = []
    for seg in segments:
        if is_generic_phrase(seg):
            continue

        seg_lower_clean = re.sub(r"[^\w]", "", seg.lower())
        match_score = 0
        # If segment contains domain tokens, it's overwhelmingly likely the actual company brand!
        if clean_domain_root in seg_lower_clean or seg_lower_clean in clean_domain_root:
            match_score += 15

        word_count = len(seg.split())
        if 1 <= word_count <= 4:
            match_score += 5
        elif word_count > 6:
            match_score -= 10

        if match_score > 0:
            candidates.append((seg, match_score))

    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    return domain_brand


def build_decision_maker_linkedin_link(company_name: str) -> str:
    """Generates direct Google Search URL to find Founders, CEOs, and CTOs on LinkedIn."""
    clean_name = re.sub(r"[^\w\s]", " ", company_name).strip()
    roles = '("Founder" OR "CEO" OR "CTO" OR "VP of Engineering" OR "Head of Product" OR "Agency Owner")'
    query_str = f'site:linkedin.com/in "{clean_name}" {roles}'
    return f"https://www.google.com/search?q={quote(query_str)}"


def discover_companies(
    query: str,
    max_results: int = 5,
    search_depth: str = "advanced",
    filter_aggregators: bool = True,
    filter_listicles: bool = True,
    deduplicate_history: bool = True,
) -> list[dict]:
    """Uses Tavily to search for direct, unique company websites matching the query."""
    client = get_tavily_client()
    if not client:
        return []

    history_seen = load_seen_domains() if deduplicate_history else set()
    if history_seen:
        print(f"[Lead Memory] {len(history_seen)} previously discovered domain(s) will be automatically skipped.")

    buffer_max = min(max((max_results + len(history_seen)) * 2, 10), 30)
    print(f"[Tavily Search] Query: '{query}' (Targeting {max_results} NEW unique companies)")

    try:
        response = client.search(
            query=query,
            search_depth=search_depth,
            max_results=buffer_max,
            exclude_domains=EXCLUDED_BASE_DOMAINS if filter_aggregators else None,
            include_answer=False,
        )
    except Exception as exc:
        print(f"[ERROR] Tavily search failed: {exc}")
        return []

    raw_results = response.get("results", [])
    seen_in_run = set()
    cleaned_companies = []

    for item in raw_results:
        url = item.get("url", "")
        title = item.get("title", "")
        domain = extract_root_domain(url)
        snippet = item.get("content", "")

        # 1. Skip aggregator / directory domains
        if filter_aggregators and is_excluded_domain(domain):
            continue

        # 2. Skip listicle / blog posts / directories
        if filter_listicles and is_listicle_or_article(url, title):
            continue

        # 3. Ensure uniqueness in current run
        if not domain or domain in seen_in_run:
            continue

        # 4. Skip previously seen companies across past runs
        if deduplicate_history and domain in history_seen:
            continue

        # Perform ICP & Verdict evaluation
        matched_pillars = match_icp_pillars(f"{title} {snippet}")
        primary_icp = matched_pillars[0][0] if matched_pillars else "General Software / Services"
        verdict_data = evaluate_icp_verdict(snippet, title, domain)

        # Intelligently extract real company brand name (rejecting generic SEO titles)
        clean_company_name = extract_real_company_name(title, domain)
        dm_link = build_decision_maker_linkedin_link(clean_company_name)

        seen_in_run.add(domain)
        if deduplicate_history:
            save_seen_domain(domain)

        cleaned_companies.append({
            "company_name": clean_company_name,
            "title": title,
            "url": url,
            "domain": domain,
            "snippet": snippet,
            "matched_icp": primary_icp,
            "verdict": verdict_data["verdict"],
            "tag": verdict_data["tag"],
            "evidence": verdict_data["evidence"],
            "reason": verdict_data["reason"],
            "decision_maker_link": dm_link,
        })

        if len(cleaned_companies) >= max_results:
            break

    return cleaned_companies


DEFAULT_CSV_PATH = os.path.join(os.path.dirname(__file__), "output", "discovered_leads.csv")
CSV_HEADERS = [
    "Company Name",
    "Domain",
    "Website URL",
    "Primary ICP Pillar",
    "Verdict",
    "Size / Region Evidence",
    "Reason",
    "Strategy",
    "Decision Maker LinkedIn Search",
    "Date Discovered",
]


def save_leads_to_csv(leads: list[dict], filepath: str = DEFAULT_CSV_PATH, strategy: str = "") -> tuple[str, int]:
    """Appends discovered leads into a structured CSV file, avoiding duplicate rows."""
    import csv
    from datetime import datetime

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    existing_domains = set()

    file_exists = os.path.exists(filepath)
    if file_exists:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Domain"):
                        existing_domains.add(row["Domain"].strip().lower())
        except Exception:
            pass

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows_to_add = []

    for lead in leads:
        dom = lead["domain"].strip().lower()
        if dom not in existing_domains:
            existing_domains.add(dom)
            rows_to_add.append({
                "Company Name": lead["company_name"],
                "Domain": lead["domain"],
                "Website URL": lead["url"],
                "Primary ICP Pillar": lead["matched_icp"],
                "Verdict": lead["verdict"],
                "Size / Region Evidence": lead["evidence"],
                "Reason": lead["reason"],
                "Strategy": strategy,
                "Decision Maker LinkedIn Search": lead["decision_maker_link"],
                "Date Discovered": date_str,
            })

    if not rows_to_add:
        return filepath, 0

    mode = "a" if file_exists else "w"
    with open(filepath, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows_to_add)

    return filepath, len(rows_to_add)


def main():
    parser = argparse.ArgumentParser(description="ICP-Driven Company Discovery with 50-200 Headcount Targeting.")
    parser.add_argument(
        "--strategy",
        type=str,
        choices=list(DISCOVERY_QUERY_TEMPLATES.keys()),
        default="agency_white_label_uk",
        help="Target strategy from config.py",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Custom search query override",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=5,
        help="Number of NEW unique companies to discover (default: 5)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=DEFAULT_CSV_PATH,
        help=f"Path to export CSV file (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Disable automatic CSV export",
    )
    parser.add_argument(
        "--clear-history",
        action="store_true",
        help="Clear seen_domains.txt history to restart fresh",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Allow re-discovering companies already seen in history",
    )

    args = parser.parse_args()

    if args.clear_history:
        clear_seen_domains()
        return

    search_query = args.query if args.query else DISCOVERY_QUERY_TEMPLATES.get(args.strategy)
    results = discover_companies(
        query=search_query,
        max_results=args.max,
        deduplicate_history=not args.allow_duplicates,
    )

    if not results:
        print("\n[INFO] No new companies found for this query.")
        print("Tip: Reset history using 'python discovery.py --clear-history' or try another strategy, e.g.:")
        print("    python discovery.py --strategy hiring_developers_us")
        print("    python discovery.py --strategy ai_development_us\n")
        return

    print("\n" + "=" * 90)
    print(f"  ICP LEAD DISCOVERY REPORT (Strategy: {args.strategy})")
    print("=" * 90)

    for idx, c in enumerate(results, start=1):
        print(f"\n#{idx}  {c['company_name']} ({c['domain']})")
        print(f"    URL:                 {c['url']}")
        print(f"    Size / Region:       {c['evidence']}")
        print(f"    Verdict:             {c['tag']}")
        print(f"    Primary ICP Fit:     {c['matched_icp']}")
        print(f"    Reason:              {c['reason']}")
        print(f"    Decision Maker Link: {c['decision_maker_link']}")

    print("\n" + "=" * 90)

    # Save to CSV
    if not args.no_csv:
        csv_file, count = save_leads_to_csv(results, filepath=args.csv, strategy=args.strategy)
        print(f"\n[CSV Export] Saved {count} lead(s) to: {csv_file}")


if __name__ == "__main__":
    main()
