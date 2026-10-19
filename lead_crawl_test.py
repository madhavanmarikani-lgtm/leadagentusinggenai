"""Small, polite crawler prototype for inspecting one public website.

Example:
    python lead_crawl_test.py --url https://example.com --query "AI development"

This does not search the web for URLs. Supply a public starting URL; the
prototype follows a few links on that same site and prints matching snippets.
"""

from __future__ import annotations

import argparse
import time
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


USER_AGENT = "ICPLeadResearchPrototype/0.1 (polite public-page crawler)"
MAX_PAGES = 5
REQUEST_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 12


def normalized_url(url: str) -> str:
    """Drop fragments and normalize a URL for crawling/deduplication."""
    return urldefrag(url.strip())[0]


def read_robots(origin: str) -> RobotFileParser:
    robots_url = urljoin(origin, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
        else:
            # Missing robots.txt means there are no published disallow rules.
            parser.parse([])
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not check robots.txt at {robots_url}: {exc}") from exc
    return parser


def crawl(start_url: str, query: str, page_limit: int = MAX_PAGES) -> list[dict[str, str]]:
    start_url = normalized_url(start_url)
    parsed_start = urlparse(start_url)
    if parsed_start.scheme not in {"http", "https"} or not parsed_start.netloc:
        raise ValueError("Starting URL must be a full public http(s) URL.")

    origin = f"{parsed_start.scheme}://{parsed_start.netloc}"
    robots = read_robots(origin)
    terms = [term.casefold() for term in query.split() if len(term) > 2]
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    queue = deque([start_url])
    visited: set[str] = set()
    matches: list[dict[str, str]] = []

    while queue and len(visited) < page_limit:
        url = queue.popleft()
        if url in visited or urlparse(url).netloc != parsed_start.netloc:
            continue
        if not robots.can_fetch(USER_AGENT, url):
            print(f"Skipping disallowed by robots.txt: {url}")
            visited.add(url)
            continue

        if visited:
            time.sleep(REQUEST_DELAY_SECONDS)
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS)
            visited.add(url)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Could not fetch {url}: {exc}")
            continue

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        page_text = " ".join(soup.stripped_strings)
        if not page_text:
            continue

        folded_text = page_text.casefold()
        score = sum(folded_text.count(term) for term in terms)
        if score:
            title = soup.title.get_text(" ", strip=True) if soup.title else "(no page title)"
            matches.append({"url": url, "title": title, "text": page_text, "score": str(score)})

        for link in soup.select("a[href]"):
            next_url = normalized_url(urljoin(url, link.get("href", "")))
            parsed_next = urlparse(next_url)
            if (
                parsed_next.scheme in {"http", "https"}
                and parsed_next.netloc == parsed_start.netloc
                and next_url not in visited
            ):
                queue.append(next_url)

    return sorted(matches, key=lambda item: int(item["score"]), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl a few public pages on one site for query terms.")
    parser.add_argument("--url", required=True, help="Public starting page, e.g. https://example.com")
    parser.add_argument("--query", required=True, help="Words describing the lead or buying signal to look for")
    parser.add_argument("--pages", type=int, default=MAX_PAGES, help=f"Maximum pages to visit (default: {MAX_PAGES})")
    args = parser.parse_args()
    if args.pages < 1 or args.pages > 20:
        parser.error("--pages must be between 1 and 20")

    try:
        matches = crawl(args.url, args.query, args.pages)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    print(f"\nVisited up to {args.pages} page(s). Matching pages: {len(matches)}")
    if not matches:
        print("No matching text found. The site may require JavaScript or block automated access.")
        return 0

    for number, result in enumerate(matches, start=1):
        snippet = " ".join(result["text"].split())
        print(f"\n{number}. {result['title']} (term matches: {result['score']})")
        print(f"Source: {result['url']}")
        print(f"Snippet: {snippet[:700]}{'…' if len(snippet) > 700 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
