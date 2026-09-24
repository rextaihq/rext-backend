QUESTION_PROMPT = {
    "task": "question_generation",
    "rules": {
        "what": "Generate definition-based questions",
        "who": "Generate person-based questions only if subject",
        "why": "Generate cause-based questions if reason exists",
        "when": "Generate time-based questions if date or time exists",
    },
    "constraints": {"no_duplicates": True, "no_yes_no": True},
}


TAGLINE_RULES = {"max_words": 7, "styles": ["benefit-driven", "emotional", "bold", "minimal"]}
