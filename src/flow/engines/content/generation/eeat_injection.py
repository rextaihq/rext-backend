def get_eeat_persona(persona_id: str = "eeat_persona_001") -> dict:
    """
    Returns EEAT persona details for content generation flows.
    """

    personas = {
        "eeat_persona_001": {
            "id": "eeat_persona_001",
            "name": "Arsalan Khan",
            "role": "Technical SEO & AI Content Systems Consultant",
            "years_experience": 7,
            "focus_areas": [
                "technical SEO",
                "programmatic SEO",
                "AI-assisted content pipelines",
                "large-scale content audits"
            ],
            "worked_with": [
                "B2B SaaS websites",
                "content-heavy blogs (100k+ pages)",
                "marketing agencies",
                "early-stage startups"
            ],
            "writing_style": "practical, experience-driven, no-fluff",
            "eeat": {
                "experience": {
                    "hands_on": True,
                    "language_patterns": [
                        "In practice",
                        "From real-world projects",
                        "When working with real sites"
                    ]
                },
                "expertise": {
                    "explains_tradeoffs": True,
                    "avoids_generic_advice": True,
                    "decision_driven": True
                },
                "authoritativeness": {
                    "tone": "confident",
                    "no_self_promotion": True,
                    "consistent_terminology": True
                },
                "trustworthiness": {
                    "states_limitations": True,
                    "no_exaggerated_claims": True,
                    "fact_check_required": True
                }
            }
        }
    }

    if persona_id not in personas:
        raise ValueError(f"Persona '{persona_id}' not found")

    return personas[persona_id]