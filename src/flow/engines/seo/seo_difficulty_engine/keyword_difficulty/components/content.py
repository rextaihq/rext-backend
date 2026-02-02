# from .base import DifficultyComponent
# from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.content_difficulty import content_strength

# class ContentDifficulty(DifficultyComponent):
#     name = "content"

#     def score(self, ctx):
#         if not ctx.scrape_doc or not ctx.serp_entry:
#             return 0.0

#         return content_strength(
#             keyword_intent=ctx.intent,
#             competitor=ctx.competitor,
#             normalized_result=ctx.serp_entry,
#             scrape_data=ctx.scrape_doc,
#         )

from .base import DifficultyComponent
from ...utils.math import clamp
from ...utils.freshness import normalize_freshness

def intent_match(intent, distribution):
    total = sum(distribution.values()) or 1
    return distribution.get(intent, 0) / total

def normalize_word_count(wc):
    return clamp(min(wc / 2000, 1.0))

def normalize_structure(h2, h3):
    return clamp((h2 * 0.6 + h3 * 0.4) / 10)

class ContentDifficulty(DifficultyComponent):
    name = "content"

    def score(self, ctx):
        if not ctx.scrape_doc:
            return 0.0

        documents = ctx.scrape_doc.get("documents", [])
        if not documents:
            return 0.0

        wc = sum(d["content_length"] for d in documents) / len(documents)
        wc_score = normalize_word_count(wc)

        struct_scores = []
        for doc in documents:
            h2 = sum(1 for h in doc.get("headings", []) if h.startswith("##"))
            h3 = sum(1 for h in doc.get("headings", []) if h.startswith("###"))
            struct_scores.append(normalize_structure(h2, h3))

        structure = sum(struct_scores) / len(struct_scores)
        freshness = normalize_freshness(ctx.serp_entry.get("date"))
        intent_score = intent_match(ctx.intent, ctx.competitor.get("intent_distribution", {}))

        return clamp(
            0.3 * ((wc_score + structure) / 2) +
            0.3 * freshness +
            0.4 * intent_score
        )
