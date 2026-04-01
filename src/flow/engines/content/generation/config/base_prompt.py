# src/prompts/base_prompt.py

BASE_PROMPT = """
You are an expert content strategist.

Generate a structured outline.

CONTENT TYPE: {content_type}
TOPIC: {topic}
PATTERN: {pattern}

STRUCTURE:
{structure}

STYLE:
{style}

FORMAT RULES:
{format_rules}

SERP RELATED TOPICS:
{related_topics}

PEOPLE ALSO ASK:
{questions}

PREVIOUS REJECTION REASON:
{rejected_reason}

PREVIOUS OUTLINE SECTIONS:
{previous_outline}

STRICT RULES:
- Follow structure exactly
- Each section must match its purpose
- Do NOT default to generic blog format
- Keep content aligned with intent

Return valid JSON only.
"""
