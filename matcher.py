"""
matcher.py - High-Precision Multi-Tier Hybrid Matcher for SIT Humanoid Robot.

Combines:
1. Phonetic and acoustic normalization (normalizer.py)
2. Exact phrase and n-gram substring matching with length weighting
3. Stopword-aware token matching
4. RapidFuzz token_set_ratio & token_sort_ratio for flexible sentence structures
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz
from normalizer import normalize_query

ROOT = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_PATH = os.path.join(ROOT, "knowledge.json")
SITE_CORPUS_PATH = os.path.join(ROOT, "data", "sit_website_pages.json")
DEPARTMENT_DATA_PATH = os.path.join(ROOT, "data", "sit_departments.json")

# Stopwords that shouldn't grant high match scores when matched alone
COMMON_STOPWORDS = {
    "what", "is", "where", "how", "who", "which", "are", "tell", "me", "about",
    "can", "you", "the", "in", "at", "to", "for", "of", "and", "a", "an",
    "sit", "college", "institute", "tumkur", "tumakuru", "karnataka", "details",
    "information", "please", "sir", "madam", "give", "know", "there", "do", "we"
}

# When a question names a specific campus topic, rank a matching topic record
# ahead of a broad institute overview that happens to share an exact entity name.
SPECIALIZED_QUERY_TERMS = {
    "principal", "dean", "faculty", "professor", "hod", "placement", "admission",
    "fee", "hostel", "scholarship", "library", "department", "laboratory", "lab",
    "club", "transport", "bus", "canteen", "ranking", "award", "sports", "exam",
    "calendar", "attendance", "scholarship", "internship", "recruiter",
}


class KnowledgeMatcher:
    def __init__(self, knowledge_path: str = KNOWLEDGE_PATH):
        self.knowledge_path = knowledge_path
        self.knowledge: List[Dict] = []
        self.website_pages: List[Dict] = []
        self.departments: List[Dict] = []
        self._knowledge_mtime = None
        self.reload()

    def reload(self):
        """Loads or reloads the knowledge database."""
        if os.path.exists(self.knowledge_path):
            with open(self.knowledge_path, "r", encoding="utf-8") as f:
                self.knowledge = json.load(f)
            self._knowledge_mtime = os.path.getmtime(self.knowledge_path)
        else:
            self.knowledge = []
            self._knowledge_mtime = None
        if os.path.exists(SITE_CORPUS_PATH):
            try:
                with open(SITE_CORPUS_PATH, "r", encoding="utf-8") as f:
                    corpus = json.load(f)
                self.website_pages = corpus.get("pages", [])
                for page in self.website_pages:
                    page["_body_terms"] = self._content_terms(page.get("text", ""))
                    page["_title_terms"] = self._content_terms(page.get("title", ""))
            except (OSError, json.JSONDecodeError):
                self.website_pages = []
        else:
            self.website_pages = []
        if os.path.exists(DEPARTMENT_DATA_PATH):
            try:
                with open(DEPARTMENT_DATA_PATH, "r", encoding="utf-8") as f:
                    self.departments = json.load(f).get("records", [])
            except (OSError, json.JSONDecodeError):
                self.departments = []
        else:
            self.departments = []

    def _department_answer(self, query_norm: str) -> Optional[Dict]:
        """Answer a department-specific detail question from its SIT page."""
        # Resolve the most specific department name/alias first (e.g. CSE AI/ML
        # before CSE), and require a category so this doesn't replace the FAQ.
        department = None
        matched_alias = ""
        for record in self.departments:
            for alias in sorted([record["name"], *record.get("aliases", [])], key=len, reverse=True):
                alias_norm = normalize_query(alias)
                if alias_norm and re.search(r"\b" + re.escape(alias_norm) + r"\b", query_norm):
                    if len(alias_norm) > len(matched_alias):
                        department, matched_alias = record, alias_norm
        if not department:
            return None

        intents = [
            ("faculty", ("faculty", "professor", "hod", "head of department", "teachers", "staff")),
            ("labs", ("lab", "labs", "laboratory", "laboratories")),
            ("placements", ("placement", "placements", "placed", "internship", "internships", "salary", "package")),
            ("awards", ("award", "awards", "achievement", "achievements", "recognition", "medal")),
            ("facilities", ("facility", "facilities", "infrastructure", "equipment", "classroom", "library")),
            ("research", ("research", "projects", "patents", "publications")),
        ]
        field = next((key for key, words in intents if any(re.search(r"\b" + re.escape(w) + r"\b", query_norm) for w in words)), None)
        if not field:
            return None
        detail = re.sub(r"\s+", " ", department.get(field, "")).strip()
        if detail:
            # Keep the first useful part of long page sections; robots should
            # answer in a conversational-sized turn and offer a follow-up.
            detail = detail[:520].rsplit(" ", 1)[0].rstrip(" ,;:")
            answer = f"Here’s a quick look at {department['name']}: {detail}. Would you like to hear about its courses or student projects next?"
        elif field == "placements":
            answer = (f"I don’t have a verified, department-specific placement figure for {department['name']} right now. "
                      "SIT publishes placement updates centrally, and results can vary by course and graduating batch. Want me to share the latest overall figures instead?")
        else:
            labels = {"faculty": "faculty", "labs": "laboratories", "awards": "awards or achievements",
                      "facilities": "facilities", "research": "research details"}
            answer = f"I don’t see {labels[field]} in the department information I have for {department['name']}. I can still help with its courses or give you a quick overview."
        return {"matched": True, "confidence": 96.0, "topic_id": f"department_{field}",
                "title": f"{department['name']} {field}", "answer": answer,
                "suggestions": [], "normalized_query": query_norm, "source": department.get("source", department.get("url"))}

    @staticmethod
    def _content_terms(text: str) -> set:
        """Returns meaningful normalized terms for corpus retrieval."""
        normalized = normalize_query(text)
        return {word for word in normalized.split()
                if len(word) >= 3 and word not in COMMON_STOPWORDS}

    def _search_website_corpus(self, query_norm: str) -> Optional[Dict]:
        """Finds a relevant official site page and extracts a short answer."""
        query_terms = self._content_terms(query_norm)
        if not query_terms or not self.website_pages:
            return None

        best_score = 0.0
        best_page = None
        best_overlap = set()
        for page in self.website_pages:
            title = page.get("title", "")
            body_terms = page.get("_body_terms") or self._content_terms(page.get("text", ""))
            title_terms = page.get("_title_terms") or self._content_terms(title)
            overlap = query_terms & body_terms
            if not overlap:
                continue
            body_coverage = len(overlap) / len(query_terms)
            title_coverage = len(query_terms & title_terms) / len(query_terms)
            # Weight page titles heavily so a department or service page wins
            # over generic pages that happen to mention the same terms.
            score = 35.0 + 40.0 * body_coverage + 25.0 * title_coverage
            if score > best_score:
                best_score, best_page, best_overlap = score, page, overlap

        if best_page is None or best_score < 62.0:
            return None

        text = best_page.get("text", "")
        sentences = re.split(r"(?<=[.!?])\s+", text)
        ranked_sentences = []
        for position, sentence in enumerate(sentences):
            sentence_terms = self._content_terms(sentence)
            hits = len(best_overlap & sentence_terms)
            if hits and len(sentence.strip()) >= 35:
                ranked_sentences.append((hits, position, sentence.strip()))
        ranked_sentences.sort(key=lambda row: (-row[0], row[1]))
        selected = []
        for _, _, sentence in ranked_sentences:
            if sentence not in selected:
                selected.append(sentence)
            if len(selected) == 2:
                break
        excerpt = " ".join(selected) or text[:300]
        excerpt = re.sub(r"\s+", " ", excerpt).strip()
        if len(excerpt) > 440:
            excerpt = excerpt[:437].rsplit(" ", 1)[0] + "..."

        title = best_page.get("title") or "SIT website"
        return {
            "matched": True,
            "confidence": round(best_score, 1),
            "topic_id": "site_page",
            "title": title,
            "answer": f"Here’s the helpful short version: {excerpt} If you’d like to check the official details or dig a little deeper, I can point you to the {title} page on the SIT website.",
            "suggestions": [],
            "normalized_query": query_norm,
            "source": best_page.get("url", "https://sit.ac.in/"),
        }

    def score_item(self, query_norm: str, query_raw: str, item: Dict) -> float:
        """
        Computes a confidence score (0 to 100) for a given knowledge item
        against the normalized query.
        """
        best_score = 0.0
        query_words = set(query_norm.split())
        query_content_words = query_words - COMMON_STOPWORDS

        # Check all keywords and variants for this topic
        for raw_key in item.get("keywords", []):
            key_norm = normalize_query(raw_key)
            if not key_norm:
                continue

            key_tokens = key_norm.split()
            key_len = len(key_tokens)
            key_content_words = set(key_tokens) - COMMON_STOPWORDS

            # 1. Exact full query match
            if key_norm == query_norm:
                return 100.0

            # 2. Multi-word phrase containment (word-bounded)
            if key_len >= 2:
                if re.search(r"\b" + re.escape(key_norm) + r"\b", query_norm):
                    # Substantial bonus for multi-word exact matches (e.g. "boys hostel", "management quota")
                    score = 90.0 + min(10.0, key_len * 2.5)
                    best_score = max(best_score, score)

            elif key_len == 1 and key_tokens[0] not in COMMON_STOPWORDS:
                if key_norm in query_words:
                    # Single specific keyword (e.g. "dinesh", "halcyon", "birla", "hostel", "placement")
                    score = 75.0
                    best_score = max(best_score, score)

            # 3. Fuzzy matching with RapidFuzz
            # Token Set Ratio: handles word order and irrelevant filler words
            ts_ratio = fuzz.token_set_ratio(query_norm, key_norm)
            if ts_ratio >= 90:
                best_score = max(best_score, float(ts_ratio) * 0.95)
            elif ts_ratio >= 80 and len(key_content_words) >= 1:
                # Only trust medium fuzzy match if there is a non-stopword involved
                if query_content_words.intersection(key_content_words):
                    best_score = max(best_score, float(ts_ratio) * 0.88)

            # 4. Partial Ratio for longer key phrases
            if key_len >= 2:
                p_ratio = fuzz.partial_ratio(query_norm, key_norm)
                if p_ratio >= 88 and query_content_words.intersection(key_content_words):
                    best_score = max(best_score, float(p_ratio) * 0.90)

        return round(min(100.0, best_score), 1)

    def search(self, raw_query: str) -> Dict:
        """
        Searches the knowledge base with the student's question.
        Returns match dict with answer and confidence.
        """
        try:
            current_mtime = os.path.getmtime(self.knowledge_path)
        except OSError:
            current_mtime = None
        if current_mtime != self._knowledge_mtime:
            self.reload()
        query_norm = normalize_query(raw_query)
        if not query_norm:
            return {
                "matched": False,
                "confidence": 0.0,
                "topic_id": "",
                "title": "",
                "answer": "I did not hear any question. Please ask me about SIT.",
                "suggestions": ["Principal", "Departments", "Placements", "Hostel", "Admissions"],
                "normalized_query": ""
            }

        # These short social exchanges should stay warm and predictable rather
        # than being sent to the general similarity matcher or an online model.
        from robo_brain_core import get_settings
        conversation = get_settings().get("conversation", {})
        social_query = " ".join(query_norm.lower().split())
        if any(phrase in social_query.split() for phrase in ("thank", "thanks", "thx")) or social_query in ("dhanyavad", "dhanyavada", "thank u"):
            return {"matched": True, "confidence": 100.0, "topic_id": "thank_reply", "title": "You’re welcome",
                    "answer": conversation.get("thank_reply", "You’re very welcome!"), "suggestions": [], "normalized_query": query_norm}

        department_result = self._department_answer(query_norm)

        scored_results: List[Tuple[float, Dict]] = []
        for item in self.knowledge:
            score = self.score_item(query_norm, raw_query, item)
            scored_results.append((score, item))

        query_intents = set(query_norm.split()) & SPECIALIZED_QUERY_TERMS

        def matches_specialized_intent(item: Dict) -> bool:
            if not query_intents:
                return False
            item_text = normalize_query(" ".join([
                str(item.get("title", "")),
                " ".join(str(term) for term in item.get("keywords", [])),
            ]))
            return bool(query_intents & set(item_text.split()))

        # Resolve equal fuzzy/exact scores by the question's named intent first.
        # Example: "principal of Siddaganga Institute of Technology" also exactly
        # contains the broad "Siddaganga Institute of Technology" keyword.
        scored_results.sort(
            key=lambda x: (matches_specialized_intent(x[1]), x[0], x[1].get("updated_at", "")),
            reverse=True,
        )

        best_score, best_item = scored_results[0] if scored_results else (0.0, None)
        # A human-authored correction in the dashboard overrides the scraped
        # department profile when it answers the same kind of question.
        if department_result and not (best_item and best_item.get("updated_at") and best_score >= 60.0):
            return department_result
        site_result = self._search_website_corpus(query_norm)
        # Prefer the reviewed, conversational FAQ whenever it has a solid
        # match. Use the larger website corpus for questions the FAQ misses.
        if site_result and (not best_item or best_score < 60.0):
            return site_result

        # High confidence match (>= 60.0)
        if best_item and best_score >= 60.0:
            return {
                "matched": True,
                "confidence": best_score,
                "topic_id": best_item.get("id", ""),
                "title": best_item.get("title", ""),
                "answer": best_item["answer"],
                "suggestions": [r[1]["title"] for r in scored_results[1:4] if r[0] > 40],
                "normalized_query": query_norm
            }

        # Moderate confidence (40.0 - 59.9)
        if best_item and best_score >= 40.0:
            top_suggestions = [r[1]["title"] for r in scored_results[:3]]
            return {
                "matched": True,
                "confidence": best_score,
                "topic_id": best_item.get("id", ""),
                "title": best_item.get("title", ""),
                "answer": best_item["answer"],
                "suggestions": top_suggestions,
                "normalized_query": query_norm
            }

        # Low confidence (< 40.0) -> Fallback with suggestions
        top_suggestions = [r[1]["title"] for r in scored_results[:3]]
        fallback_msg = (
            "I’m not quite sure I understood that. Could you ask it another way? "
            "I can help with SIT courses, admissions, hostels, placements, clubs, and campus services."
        )
        fallback_msg = conversation.get("no_match_reply", fallback_msg)
        return {
            "matched": False,
            "confidence": best_score,
            "topic_id": "",
            "title": "Uncertain",
            "answer": fallback_msg,
            "suggestions": top_suggestions,
            "normalized_query": query_norm
        }


# Singleton instance
matcher = KnowledgeMatcher()

if __name__ == "__main__":
    test_queries = [
        "who is the principle of safety college",
        "where is bella auditor young",
        "highest package in cse placement",
        "tell me about boy hostal mess",
        "when is hall sean cultural fest",
        "k cet cutoff rank for aiml",
        "how to reach sit from tumkur railway station",
        "who founded siddaganga mutt",
        "can i get direct management quota seat",
        "what is the minimum attendance percentage required"
    ]
    print("Testing Updated Knowledge Matcher with Voice Transcriptions:")
    print("=" * 65)
    for q in test_queries:
        res = matcher.search(q)
        print(f"User Query : '{q}'")
        print(f"Normalized : '{res['normalized_query']}'")
        print(f"Matched    : {res['title']} (Confidence: {res['confidence']}%)")
        print(f"Answer     : {res['answer'][:110]}...")
        print("-" * 65)
