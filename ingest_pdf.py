"""
ingest_pdf.py - Ingests college PDF documents (prospectuses, handbooks, syllabi, circulars)
into the offline knowledge.json database for SIT Humanoid Robot.

Usage:
    python ingest_pdf.py <path_to_pdf>
    python ingest_pdf.py --all  (processes all PDFs in data/documents/)
"""

import argparse
import glob
import json
import os
import re
from typing import Dict, List
import pypdf

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(ROOT, "data", "documents")
KNOWLEDGE_PATH = os.path.join(ROOT, "knowledge.json")


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts all text from a PDF file."""
    reader = pypdf.PdfReader(pdf_path)
    full_text = []
    print(f"Reading '{pdf_path}' ({len(reader.pages)} pages)...")
    for idx, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            full_text.append(text)
    return "\n\n".join(full_text)


def chunk_text_into_sections(raw_text: str, source_name: str) -> List[Dict]:
    """
    Splits PDF text into clean, structured knowledge chunks based on
    headings, numbered points, or paragraph boundaries.
    """
    lines = raw_text.splitlines()
    sections = []
    current_title = f"{source_name} Overview"
    current_body = []

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue

        # Detect potential headings (e.g., "1. ADMISSION PROCEDURE", "HOSTEL RULES", "DEPARTMENT OF CSE")
        is_heading = (
            (cleaned.isupper() and 4 < len(cleaned) < 60)
            or re.match(r"^(\d+\.|\bSECTION\b|\bCHAPTER\b)\s+[A-Z]", cleaned)
            or (len(cleaned) < 50 and cleaned.endswith(":"))
        )

        if is_heading and current_body:
            body_text = " ".join(current_body).strip()
            if len(body_text) > 60:
                sections.append({
                    "title": current_title,
                    "text": body_text
                })
            current_title = cleaned.rstrip(":")
            current_body = []
        else:
            current_body.append(cleaned)

    if current_body:
        body_text = " ".join(current_body).strip()
        if len(body_text) > 60:
            sections.append({
                "title": current_title,
                "text": body_text
            })

    return sections


def generate_keywords(title: str, text: str) -> List[str]:
    """Extracts natural keywords and potential student questions from title and text."""
    clean_title = re.sub(r"[^\w\s]", " ", title.lower()).strip()
    words = clean_title.split()
    keywords = [clean_title]

    # Add individual significant words from title
    for w in words:
        if len(w) > 3 and w not in ["about", "overview", "rules", "section"]:
            keywords.append(w)

    # Add natural phrasing variations
    keywords.append(f"what is {clean_title}")
    keywords.append(f"tell me about {clean_title}")
    keywords.append(f"{clean_title} details")

    # Add unique and sorted list
    return list(dict.fromkeys(keywords))


def ingest_file(pdf_path: str):
    """Parses a single PDF and updates knowledge.json."""
    if not os.path.isfile(pdf_path):
        print(f"Error: File not found at {pdf_path}")
        return

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    raw_text = extract_text_from_pdf(pdf_path)
    if not raw_text.strip():
        print(f"Warning: No extractable text found in {pdf_path}")
        return

    sections = chunk_text_into_sections(raw_text, base_name)
    print(f"Extracted {len(sections)} sections from {base_name}.")

    # Load existing knowledge
    if os.path.exists(KNOWLEDGE_PATH):
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            knowledge = json.load(f)
    else:
        knowledge = []

    existing_ids = {item["id"] for item in knowledge}
    added_count = 0

    for idx, sec in enumerate(sections):
        safe_id = f"pdf_{base_name.lower()}_{idx+1}"
        if safe_id in existing_ids:
            continue

        keywords = generate_keywords(sec["title"], sec["text"])
        entry = {
            "id": safe_id,
            "title": f"{base_name}: {sec['title']}",
            "category": "pdf_document",
            "keywords": keywords,
            "answer": sec["text"][:350]  # Concise summary for robot speech
        }
        knowledge.append(entry)
        added_count += 1

    with open(KNOWLEDGE_PATH, "w", encoding="utf-8") as f:
        json.dump(knowledge, f, indent=2, ensure_ascii=False)

    print(f"Successfully ingested {added_count} new entries from '{pdf_path}' into knowledge.json!")


def main():
    parser = argparse.ArgumentParser(description="Ingest PDF documents into SIT knowledge base")
    parser.add_argument("pdf_path", nargs="?", help="Path to PDF file")
    parser.add_argument("--all", action="store_true", help="Ingest all PDFs from data/documents/")
    args = parser.parse_args()

    if args.all:
        pdf_files = glob.glob(os.path.join(DOCS_DIR, "*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in {DOCS_DIR}. Please place your PDF documents there.")
            return
        for pdf in pdf_files:
            ingest_file(pdf)
    elif args.pdf_path:
        ingest_file(args.pdf_path)
    else:
        print("Usage: python ingest_pdf.py <path_to_pdf> or python ingest_pdf.py --all")


if __name__ == "__main__":
    main()
