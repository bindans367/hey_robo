"""Build the offline department reference from SIT's crawled official pages."""
import json
import os
import re
import ssl
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
import certifi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "data", "sit_website_pages.json")
OUTPUT = os.path.join(ROOT, "data", "sit_departments.json")

DEPARTMENTS = [
    ("Architecture", ["architecture", "b arch", "barch"], "https://sit.ac.in/architecture/"),
    ("Artificial Intelligence and Data Science", ["ai ds", "aids", "artificial intelligence and data science"], "https://sit.ac.in/artificial-intelligence-and-data-science/"),
    ("Biotechnology", ["biotechnology", "biotech"], "https://sit.ac.in/biotechnology/"),
    ("Chemical Engineering", ["chemical engineering", "chemical"], "https://sit.ac.in/chemical-engineering-2/"),
    ("Chemistry", ["chemistry"], "https://sit.ac.in/chemistry/"),
    ("Civil Engineering", ["civil engineering", "civil"], "https://sit.ac.in/civil-engineering/"),
    ("Computer Science and Engineering", ["computer science and engineering", "computer science", "cse"], "https://sit.ac.in/computer-science/"),
    ("CSE Artificial Intelligence and Machine Learning", ["cse ai ml", "cse aiml", "artificial intelligence and machine learning", "aiml"], "https://sit.ac.in/cse-artificial-intelligence-machine-learning/"),
    ("Electrical and Electronics Engineering", ["electrical and electronics engineering", "electrical electronics", "eee"], "https://sit.ac.in/electrical-and-electronics-engineering/"),
    ("Electronics and Communication Engineering", ["electronics and communication engineering", "electronics communication", "ece"], "https://sit.ac.in/electronics-and-communication-engineering/"),
    ("Electronics and Instrumentation Engineering", ["electronics and instrumentation engineering", "electronics instrumentation", "eie"], "https://sit.ac.in/electronics-and-instrumental-engineering/"),
    ("Electronics and Telecommunication Engineering", ["electronics and telecommunication engineering", "electronics telecommunication", "ete"], "https://sit.ac.in/electronics-and-telecommunication-engineering/"),
    ("Industrial Engineering and Management", ["industrial engineering and management", "industrial engineering", "iem"], "https://sit.ac.in/industrial-engineering-and-management/"),
    ("Information Science and Engineering", ["information science and engineering", "information science", "ise"], "https://sit.ac.in/information-science-and-engineering/"),
    ("Mathematics", ["mathematics", "maths", "math"], "https://sit.ac.in/mathematics/"),
    ("Mechanical Engineering", ["mechanical engineering", "mechanical", "mech"], "https://sit.ac.in/mechanical-engineering/"),
    ("Master of Business Administration", ["master of business administration", "mba"], "https://sit.ac.in/master-of-business-administration/"),
    ("Master of Computer Applications", ["master of computer applications", "master of computer application", "mca"], "https://sit.ac.in/master-of-computer-application/"),
    ("Physics", ["physics"], "https://sit.ac.in/physics/"),
]

HEADINGS = [
    "Overview", "Program Details", "Programme Details", "Vision & Mission", "Infrastructure & Facilities",
    "Laboratories", "Faculty", "Faculty Achievements", "Achievements & Recognition",
    "Student Achievements", "Internship & Placements", "Placements", "Placement", "Research",
    "Department Activities", "Academic Programs", "Awards", "Student Activities", "Alumni Success",
]

FIELDS = {
    "overview": ["Overview"],
    "faculty": ["Faculty"],
    "labs": ["Infrastructure & Facilities", "Laboratories"],
    "facilities": ["Infrastructure & Facilities", "Laboratories"],
    "placements": ["Internship & Placements", "Placements", "Placement"],
    "awards": ["Achievements & Recognition", "Student Achievements", "Faculty Achievements", "Awards"],
    "research": ["Research"],
}

def clean(value):
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"(?i)\b[\w.+-]+@[\w.-]+\.ac\.in\b", "", value)
    value = re.sub(r"(?<!\d)(?:\+?91[\s-]?)?(?:\d[\s-]?){10}(?!\d)", "", value)
    value = re.sub(r"\b\d[A-Z]{2}\d{2}[A-Z]{2}\d{3}\b", "", value)
    return value.strip(" :-|;,.")

def section(text, labels):
    # Pages in the source corpus are flattened to readable text. Extract the
    # requested section until the next recognized section heading.
    starts = []
    for label in labels:
        for m in re.finditer(r"(?<![\w])" + re.escape(label) + r"(?![\w])", text, re.I):
            starts.append((m.start(), m.end()))
    if not starts:
        return ""
    choices = []
    for start, end in starts:
        # The crawl begins with a table of contents. Ignore those menu hits
        # when the page has a substantive occurrence later in the text.
        if start < 1000 and any(s >= 1000 for s, _ in starts):
            continue
        stop = len(text)
        for heading in HEADINGS:
            for m in re.finditer(r"(?<![\w])" + re.escape(heading) + r"(?![\w])", text[end:], re.I):
                pos = end + m.start()
                if pos > start + 35:
                    stop = min(stop, pos)
        candidate = clean(text[end:stop])
        if len(candidate) > 90:
            choices.append((len(candidate), candidate))
    if not choices:
        return ""
    return max(choices, key=lambda row: row[0])[1][:5000]

def live_sections(url):
    """Read real SIT section containers, preserving the page's heading structure."""
    try:
        request = Request(url, headers={"User-Agent": "SIT-Humanoid-knowledge-builder/1.0"})
        with urlopen(request, context=ssl.create_default_context(cafile=certifi.where()), timeout=20) as response:
            soup = BeautifulSoup(response.read(2_000_000), "html.parser")
    except Exception:
        return {}
    found = {}
    for key, labels in FIELDS.items():
        if key == "facilities":
            continue
        for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
            title = clean(heading.get_text(" ", strip=True)).lower()
            if not any(title == label.lower() for label in labels):
                continue
            container = heading
            # SIT's Elementor pages put each section in an e-con-dept block.
            for _ in range(3):
                if container.parent:
                    container = container.parent
            content = clean(container.get_text(" ", strip=True))
            content = re.sub(r"^" + re.escape(clean(heading.get_text(" ", strip=True))) + r"\s*", "", content, flags=re.I)
            if len(content) > len(found.get(key, "")):
                found[key] = content[:5000]
    for key in FIELDS:
        found.setdefault(key, "")
    found["facilities"] = found.get("labs", "")
    return found

def main():
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    pages = corpus.get("pages", [])
    by_url = {p.get("url", "").rstrip("/").lower(): p for p in pages}
    records = []
    for name, aliases, url in DEPARTMENTS:
        page = by_url.get(url.rstrip("/").lower())
        if not page or "Top Best engineering college in Bangalore | SIT" in page.get("title", ""):
            # A few directory URLs now resolve to a generic landing page. Use
            # the older detailed SIT page when the crawl has one.
            search_terms = [name.lower().replace(" and ", " ").replace("&", " ")]
            search_terms += [a.lower() for a in aliases]
            candidates = [p for p in pages if any(term in (p.get("title", "") + " " + p.get("url", "")).lower() for term in search_terms)]
            candidates = [p for p in candidates if len(p.get("text", "")) > 9000 and "Top Best engineering college in Bangalore | SIT" not in p.get("title", "")]
            page = candidates[0] if candidates else None
        text = page.get("text", "") if page else ""
        source = page.get("url", url) if page else url
        fields = live_sections(source) if source != url else {}
        if not fields:
            fields = {key: section(text, labels) for key, labels in FIELDS.items()}
            fields["facilities"] = fields["labs"]
        # Don't index flattened site navigation or the home page as department facts.
        if page and "Top Best engineering college in Bangalore | SIT" in page.get("title", ""):
            fields = {key: "" for key in fields}
            source = url
        for key in FIELDS:
            fields.setdefault(key, "")
        records.append({"name": name, "aliases": aliases, "url": url, "source": source,
                        "verified_at": "2026-10-21", "verified_from_crawl": bool(page and text), **fields})
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"source": "https://sit.ac.in/department/", "records": records}, f, ensure_ascii=False, indent=2)
    available = sum(bool(x["overview"] or x["labs"] or x["faculty"]) for x in records)
    print(f"Saved {len(records)} departments; {available} have detailed source-page content.")

if __name__ == "__main__":
    main()
