# from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.context_modifier import context_modifier

# class ContextModifierService:
#     def apply(self, rext_data, intent) -> float:
#         return context_modifier(
#             competitors=rext_data["competitors"],
#             serp_normalized=rext_data["serp_normalized"],
#             keyword_intent=intent,
#         )


from ...utils.domains import classify_domain_type

class ContextModifierService:
    def apply(self, rext_data, intent):
        modifier = 0.0
        domains = rext_data["serp_normalized"]["domains"]

        ugc = sum(1 for d in domains if classify_domain_type(d) == "ugc")
        if ugc >= len(domains) * 0.3:
            modifier -= 4

        brands = {"brand", "publisher", "gov", "edu"}
        brand_count = sum(1 for d in domains if classify_domain_type(d) in brands)

        if brand_count >= len(domains) * 0.8:
            modifier += 10
        elif brand_count >= len(domains) * 0.5:
            modifier += 4

        return max(min(modifier, 5), -5)
