"""Crawl public pages linked from sit.ac.in into a local source corpus.

The query bot uses reviewed answers in knowledge.json. This crawler keeps a
broader offline reference corpus without replacing those answers with noisy
navigation text. It follows public HTML links on sit.ac.in only and skips
portals, downloads, search results, and personal contact details.

Usage: python scrape_sit.py
"""

import json
import os
import re
import ssl
import time
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
import certifi

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(ROOT, "data", "sit_website_pages.json")
START_URL = "https://sit.ac.in/"
MAX_PAGES = 180
MAX_DEPTH = 3
REQUEST_DELAY_SECONDS = 0.15
BLOCKED_PREFIXES = (
    "/wp-admin", "/wp-login", "/feed", "/tag/", "/author/", "/category/",
    "/page/", "/search/", "/cart", "/checkout", "/my-account",
)
BLOCKED_HOSTS = {
    "moodle.sit.ac.in", "sims.sit.ac.in", "erp.sit.ac.in", "icl.sit.ac.in",
}
PERSONAL_DATA_PATH_HINTS = (
    "/students/", "/student-placed", "/students-placed", "/placed-students",
    "/testimonials", "/placement-gallery",
)
NON_HTML_SUFFIXES = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".mp4", ".mp3",
)


def canonical_page_url(raw_url: str, base_url: str) -> str:
    url = urldefrag(urljoin(base_url, raw_url))[0]
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or host not in {"sit.ac.in", "www.sit.ac.in"}:
        return ""
    if host in BLOCKED_HOSTS or parts.query:
        return ""
    path = parts.path or "/"
    lowered = path.lower()
    if lowered.endswith(NON_HTML_SUFFIXES) or lowered.startswith(BLOCKED_PREFIXES):
        return ""
    if any(hint in lowered for hint in PERSONAL_DATA_PATH_HINTS):
        return ""
    # Normalize host, scheme, trailing slash, and common duplicate home URLs.
    path = re.sub(r"/{2,}", "/", path)
    if path != "/":
        path = path.rstrip("/") + "/"
    return "https://sit.ac.in" + path


def clean_page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "button", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.find(id="content") or soup.body
    if not main:
        return ""
    text = " ".join(main.stripped_strings)
    text = re.sub(r"\s+", " ", text).strip()
    # Keep useful institutional content while excluding direct contact details
    # and student USNs that can appear in profiles, testimonials, or galleries.
    text = re.sub(r"(?i)\b[\w.+-]+@[\w.-]+\.ac\.in\b", "[email omitted]", text)
    text = re.sub(r"(?<!\d)(?:\+?91[\s-]?)?(?:\d[\s-]?){10}(?!\d)", "[phone omitted]", text)
    text = re.sub(r"\b\d[A-Z]{2}\d{2}[A-Z]{2}\d{3}\b", "[student ID omitted]", text)
    return text[:18000]


def fetch_page(url: str):
    request = Request(url, headers={"User-Agent": "SIT-Humanoid-knowledge-crawler/1.0"})
    context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, context=context, timeout=15) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return None, []
        html = response.read(2_000_000)
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    links = []
    for anchor in soup.find_all("a", href=True):
        target = canonical_page_url(anchor["href"], url)
        if target:
            links.append(target)
    return {
        "url": url,
        "title": re.sub(r"\s+", " ", title).strip(),
        "text": clean_page_text(soup),
    }, links


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    queue = deque([(START_URL, 0)])
    seen = set()
    pages = []
    errors = []
    while queue and len(seen) < MAX_PAGES:
        url, depth = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            record, links = fetch_page(url)
            if record and record["text"]:
                pages.append(record)
                print(f"[{len(pages):03d}] {record['title'] or url}")
            if depth < MAX_DEPTH:
                for link in links:
                    if link not in seen:
                        queue.append((link, depth + 1))
        except Exception as exc:
            errors.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[WARN] {url}: {type(exc).__name__}: {exc}")
        time.sleep(REQUEST_DELAY_SECONDS)

    corpus = {
        "source": "https://sit.ac.in/",
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "page_count": len(pages),
        "pages": pages,
        "errors": errors,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as output:
        json.dump(corpus, output, indent=2, ensure_ascii=False)
    print(f"Saved {len(pages)} pages to {OUTPUT_PATH}; {len(errors)} fetch errors.")


if __name__ == "__main__":
    main()
