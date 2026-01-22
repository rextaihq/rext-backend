from typing import Dict, List
from src.flow.states.wrext import WREXT
from src.flow.states.seo_state import SEORESULT


QUESTION_PREFIXES = ("what", "how", "why", "can", "does", "is", "are")


def competitors_gap_node(state: WREXT) -> Dict[str, SEORESULT]:
    print("Competitors Gap...")
    serp = state.get("serp_normalized", {})
    scrape_context = state.get("scrape_context", {}) or {}

    documents = scrape_context.get("documents", [])

    # Collect competitor headings
    all_headings: List[str] = []
    for d in documents:
        all_headings.extend([h.lower().strip() for h in d.get("headings", [])])

    # Topics gap
    related_topics = [t.lower() for t in serp.get("related_topics", [])]

    topic_frequency = {
        topic: sum(1 for h in all_headings if topic in h)
        for topic in related_topics
    }

    missing_topics = [
        topic for topic, freq in topic_frequency.items() if freq == 0
    ]

    weak_topics = [
        topic for topic, freq in topic_frequency.items() if freq == 1
    ]

    # Questions gap
    serp_questions = [q.lower() for q in serp.get("questions", [])]

    heading_questions = [
        h for h in all_headings if h.startswith(QUESTION_PREFIXES)
    ]

    missing_questions = [
        q for q in serp_questions
        if not any(q in h for h in heading_questions)
    ]

    # Recommended sections
    recommended_sections = []

    for t in missing_topics[:5]:
        recommended_sections.append(f"Complete guide on {t}")

    for q in missing_questions[:5]:
        recommended_sections.append(q.capitalize())

    # Output
    # Output
    prev_seo = state.get("seo_result", {})
    return {
        "seo_result": {
            **prev_seo,
            "content_gaps": {
                "missing_topics": missing_topics[:5],
                "missing_questions": missing_questions[:5],
                "weak_coverage_areas": weak_topics[:5],
                "recommended_sections": recommended_sections[:5],
            }
        }
    }
