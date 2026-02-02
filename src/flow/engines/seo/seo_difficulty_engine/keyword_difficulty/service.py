from .evaluator import CompetitorEvaluator
from .intent_resolver import IntentResolver
from .context_builder import build_competitor_context
from .aggregator import median
from ..weights import INTENT_WEIGHTS
from .components.link import LinkDifficulty
from .components.serp import SERPDifficulty
from .components.content import ContentDifficulty
from .modifiers.serp_context import ContextModifierService
from src.flow.engines.seo.seo_difficulty_engine.utils.math import clamp

class KeywordDifficultyService:
    def __init__(self):
        self.intent_resolver = IntentResolver()
        self.context_modifier = ContextModifierService()
        self.components = [
            LinkDifficulty(),
            SERPDifficulty(),
            ContentDifficulty(),
        ]

    def calculate(self, rext_data: dict) -> dict:
        keyword = rext_data["serp_normalized"]["query"]
        intent = self.intent_resolver.resolve(rext_data)
        weights = INTENT_WEIGHTS.get(intent, INTENT_WEIGHTS["informational"])

        evaluator = CompetitorEvaluator(self.components, weights)
        scores = []

        for comp in rext_data["competitors"]:
            ctx = build_competitor_context(keyword, intent, comp, rext_data)
            scores.append(evaluator.evaluate(ctx))

        base_kd = median(scores) * 100
        base_kd += self.context_modifier.apply(rext_data, intent)

        return {
            "seo_result": {
                "keyword_difficulty": {
                    "keyword": keyword,
                    "kd": round(clamp(base_kd, 0, 100), 2),
                }
            }
        }
