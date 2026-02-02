class IntentResolver:
    def resolve(self, rext_data: dict) -> str:
        return (
            rext_data.get("seo_result", {})
            .get("intent", {})
            .get("primary_intent", "informational")
        )
