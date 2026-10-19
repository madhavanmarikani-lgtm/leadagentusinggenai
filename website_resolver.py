import os
import re
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv('d:/Lead Agent/.env')
from tavily import TavilyClient

EXCLUDED_BASE_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "wikipedia.org", "crunchbase.com", "zoominfo.com", "pitchbook.com",
    "glassdoor.com", "indeed.com", "rocketreach.co", "apollo.io", "dnb.com",
    "bloomberg.com", "forbes.com", "owler.com", "yelp.com", "yellowpages.com",
    "bbb.org", "clutch.co", "g2.com", "capterra.com", "trustpilot.com",
    "sortlist.com", "themanifest.com", "hubspot.com", "wellfound.com", "angel.co",
    "ycombinator.com", "a16z.com", "tiktok.com", "pinterest.com", "medium.com",
    "datanyze.com", "prospeo.io", "doctorfynd.com", "theknot.com", "youtube.com"
}

LISTICLE_PATTERNS = [
    "/blog/", "/blogs/", "/news/", "/companies/", "/portfolio/",
    "/directory/", "/tag/", "/category/", "/article/", "/author/"
]

def clean_domain_info(url_str: str) -> Optional[Dict[str, Any]]:
    """Parses URL, returns cleaned root hostname and origin."""
    try:
        u = urlparse(url_str.strip())
        if not u.netloc and not u.path:
            return None
        hostname = (u.hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        if not hostname or "." not in hostname:
            return None
        
        # Check exclusion blacklist
        for bad in EXCLUDED_BASE_DOMAINS:
            if hostname == bad or hostname.endswith("." + bad):
                return None
                
        is_root = u.path in ["", "/", "/index.html", "/home", "/en", "/us"]
        scheme = u.scheme if u.scheme in ["http", "https"] else "https"
        return {
            "hostname": hostname,
            "origin": f"{scheme}://www.{hostname}",
            "path": u.path,
            "is_root": is_root
        }
    except Exception:
        return None

def extract_embedded_urls_from_snippet(text: str) -> List[str]:
    """Finds URLs embedded in directory / profile snippets like Rocketreach/Zoominfo."""
    found = []
    # Pattern 1: Website | http://domain.com
    m1 = re.findall(r'(?:website|site|url)\s*[:\|]\s*(https?://[^\s\|<>"\']+)', text, re.I)
    found.extend(m1)
    
    # Pattern 2: General URLs in snippet
    m2 = re.findall(r'https?://[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}(?:/[^\s\|<>"\']*)?', text)
    for u in m2:
        u_clean = u.rstrip('/.,;)')
        found.append(u_clean)
    return found

def score_and_rank_candidates(
    candidates_data: List[Dict[str, Any]],
    target_company: str,
    target_country: str = "",
    target_industry: str = ""
) -> Optional[Dict[str, Any]]:
    """Runs the multi-factor scoring algorithm across discovered domain groups."""
    target_slug = re.sub(r"[^a-z0-9]", "", target_company.lower())
    clean_target_name = re.sub(r"(?i)\b(inc|llc|ltd|corp|corporation|technologies|group|co|labs|sa|de|cv)\b\.?", "", target_company).strip().lower()
    clean_target_slug = re.sub(r"[^a-z0-9]", "", clean_target_name) or target_slug

    candidate_groups: Dict[str, Dict[str, Any]] = {}

    for item in candidates_data:
        url_str = item.get("url", "")
        info = clean_domain_info(url_str)
        if not info:
            continue
        
        domain = info["hostname"]
        # Skip if path has listicle pattern
        if any(pat in info["path"].lower() for pat in LISTICLE_PATTERNS):
            continue

        if domain not in candidate_groups:
            candidate_groups[domain] = {
                "domain": domain,
                "website_url": info["origin"],
                "has_clean_root": False,
                "titles": [],
                "content": "",
                "highest_tavily_score": 0.0,
                "hit_count": 0,
                "is_embedded_site": item.get("is_embedded", False)
            }
        
        grp = candidate_groups[domain]
        grp["hit_count"] += 1
        if info["is_root"]:
            grp["has_clean_root"] = True
        if item.get("title"):
            grp["titles"].append(item["title"])
        if item.get("content"):
            grp["content"] += " " + item["content"]
        score_val = float(item.get("score") or 0.0)
        if score_val > grp["highest_tavily_score"]:
            grp["highest_tavily_score"] = score_val

    if not candidate_groups:
        return None

    scored_list = []
    for domain, grp in candidate_groups.items():
        domain_stem = domain.split(".")[0].replace("-", "")
        score = 0.0

        # Factor 1: Stem match (Weight: 35)
        if domain_stem == target_slug or domain_stem == clean_target_slug:
            score += 35.0
        elif target_slug in domain_stem or clean_target_slug in domain_stem:
            score += 30.0
        elif domain_stem in target_slug or domain_stem in clean_target_slug:
            score += 25.0
        else:
            score += 5.0

        # Factor 2: Clean root homepage (Weight: 25)
        if grp["has_clean_root"] or grp["is_embedded_site"]:
            score += 25.0
        else:
            score += 10.0

        # Factor 3: Title & brand affinity (Weight: 20)
        title_text = " ".join(grp["titles"]).lower()
        if target_company.lower() in title_text or clean_target_name in title_text:
            score += 20.0
        elif any(w in title_text for w in target_company.lower().split() if len(w) > 3):
            score += 12.0
        else:
            score += 5.0

        # Factor 4: Frequency / embedded site bonus (Weight: 15)
        if grp["is_embedded_site"]:
            score += 15.0
        else:
            score += min(15.0, grp["hit_count"] * 5.0)

        # Context Bonus: Country / Industry (up to 10)
        combined_text = (title_text + " " + grp["content"]).lower()
        if target_country and target_country.lower() in combined_text:
            score += 5.0
        if target_industry:
            for w in target_industry.lower().split():
                if len(w) > 3 and w in combined_text:
                    score += 3.0
                    break

        total_score = min(100.0, score)
        grp["total_score"] = total_score
        scored_list.append(grp)

    # Sort descending
    scored_list.sort(key=lambda x: x["total_score"], reverse=True)
    winner = scored_list[0]
    return {
        "website_url": winner["website_url"],
        "domain": winner["domain"],
        "confidence": round(winner["total_score"] / 100.0, 2),
        "all_candidates": scored_list
    }

def resolve_company_website(
    company_name: str,
    ceo_name: str = "",
    country: str = "",
    industry: str = ""
) -> Dict[str, Any]:
    """
    Resolves the exact company website using Tavily search with query:
    'Get the website of {company_name} and the decision maker is {ceo_name}'
    """
    clean_company = (company_name or "").strip()
    clean_ceo = (ceo_name or "").strip()
    
    # Fallback slug if Tavily unavailable or fails
    fallback_slug = re.sub(r"(?i)\b(inc|llc|ltd|corp|corporation|technologies|group|co|labs|sa|de|cv)\b\.?", "", clean_company).strip()
    fallback_slug = re.sub(r"[^a-zA-Z0-9]", "", fallback_slug.lower()) or "company"
    default_fallback = {
        "website_url": f"https://www.{fallback_slug}.com",
        "domain": f"{fallback_slug}.com",
        "confidence": 0.50,
        "source": "fallback_slug"
    }

    if not clean_company:
        return default_fallback

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return default_fallback

    try:
        client = TavilyClient(api_key=tavily_key)
        
        # Primary user-specified query format
        if clean_ceo and clean_ceo.lower() not in ["executive", "unknown", "executive leadership", "c-level"]:
            primary_query = f"Get the website of {clean_company} and the decision maker is {clean_ceo}"
        else:
            primary_query = f"Get the website of {clean_company}"

        exclude_list = [
            "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
            "wikipedia.org", "youtube.com"
        ]

        res = client.search(
            query=primary_query,
            max_results=8,
            exclude_domains=exclude_list
        )
        raw_results = res.get("results", []) or []

        # Collect raw results and also extract embedded websites from directory snippets
        items_to_score = []
        for r in raw_results:
            items_to_score.append({
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
                "is_embedded": False
            })
            # Check snippet for embedded official website (e.g. RocketReach / ZoomInfo "Website | http://www.artisoftlabs.com/")
            snippet = r.get("content", "")
            embedded = extract_embedded_urls_from_snippet(snippet)
            for emb_url in embedded:
                items_to_score.append({
                    "url": emb_url,
                    "title": r.get("title", ""),
                    "content": snippet,
                    "score": 0.95,
                    "is_embedded": True
                })

        winner = score_and_rank_candidates(items_to_score, clean_company, country, industry)
        
        # If confidence is low (< 0.60) and we searched with CEO name, try secondary direct query
        if (not winner or winner["confidence"] < 0.60) and clean_ceo:
            sec_query = f"Get the website of {clean_company}"
            sec_res = client.search(
                query=sec_query,
                max_results=8,
                exclude_domains=exclude_list
            )
            sec_raw = sec_res.get("results", []) or []
            for r in sec_raw:
                items_to_score.append({
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.0),
                    "is_embedded": False
                })
                for emb_url in extract_embedded_urls_from_snippet(r.get("content", "")):
                    items_to_score.append({
                        "url": emb_url,
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "score": 0.95,
                        "is_embedded": True
                    })
            winner = score_and_rank_candidates(items_to_score, clean_company, country, industry)

        if winner and winner["confidence"] >= 0.50:
            return {
                "website_url": winner["website_url"],
                "domain": winner["domain"],
                "confidence": winner["confidence"],
                "source": "tavily_resolver"
            }
        
        return default_fallback
    except Exception as exc:
        print(f"[Website Resolver Error] {clean_company}: {exc}")
        return default_fallback

if __name__ == "__main__":
    test_cases = [
        ("Artisoft", "Jesús Álvaro Tovar Durán", "United States", "Software Development"),
        ("Oceanpick", "Irfan Thassim", "Sri Lanka", "Aquaculture"),
    ]
    for c_name, ceo, country, ind in test_cases:
        res = resolve_company_website(c_name, ceo, country, ind)
        print(f"Company: {c_name} | CEO: {ceo}")
        print(f"  -> Website: {res['website_url']} | Domain: {res['domain']} | Confidence: {res['confidence']}")
