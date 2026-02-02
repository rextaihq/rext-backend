# from .base import DifficultyComponent
# from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.serp_score import competitor_serp_kd

# class SERPDifficulty(DifficultyComponent):
#     name = "serp"

#     def score(self, ctx):
#         return competitor_serp_kd(
#             serp_normalized=ctx.serp_normalized,
#             comp=ctx.competitor,
#             competitors=ctx.competitors,
#         )


from .base import DifficultyComponent
from ...utils.math import clamp
from ...utils.freshness import normalize_freshness

class SERPDifficulty(DifficultyComponent):
    name = "serp"

    def score(self, ctx):
        score = 0

        if ctx.competitor.get("featured_snippet"):
            score += 5

        paa_present = (
            ctx.serp_normalized.get("features", {}).get("people_also_ask")
            or ctx.serp_normalized.get("questions")
        )
        if paa_present:
            score += 3

        if ctx.competitor.get("has_sitelinks"):
            score += 4

        freshness = normalize_freshness(ctx.serp_entry.get("date"))
        if freshness >= 0.85:
            score += 2

        domains = [c["domain"] for c in ctx.competitors]
        repeat = domains.count(ctx.competitor["domain"])
        serp_lock = 0.15 if repeat >= 3 else 0.07 if repeat == 2 else 0

        brand_boost = 0.10 if ctx.competitor.get("is_brand") else 0.0

        return clamp(score / 14 + serp_lock + brand_boost)
