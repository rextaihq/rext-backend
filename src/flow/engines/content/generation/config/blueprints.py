# src/config/blueprints.py

BLUEPRINTS = {
    "educational": {
        "structure": [
            "introduction",
            "core_explanation",
            "step_by_step",
            "tips",
            "faq",
            "conclusion"
        ],
        "style": "educational",
        "format_rules": {
            "step_by_step": "numbered",
        }
    },

    "list": {
        "structure": [
            "introduction",
            "list_items",
            "faq"
        ],
        "style": "concise",
        "format_rules": {
            "list_items": "bullet"
        }
    },

    "comparison": {
        "structure": [
            "introduction",
            "comparison_table",
            "feature_comparison",
            "pros_cons",
            "verdict",
            "faq"
        ],
        "style": "analytical",
    },

    "conversion": {
        "structure": [
            "hero",
            "problem",
            "solution",
            "benefits",
            "social_proof",
            "faq",
            "cta"
        ],
        "style": "persuasive",
    },

    "proof": {
        "structure": [
            "introduction",
            "background",
            "problem",
            "solution",
            "results",
            "takeaways"
        ],
        "style": "storytelling",
    },

    "navigational": {
        "structure": [
            "hero",
            "features",
            "details",
            "faq",
            "cta"
        ],
        "style": "product_focused",
    }
}