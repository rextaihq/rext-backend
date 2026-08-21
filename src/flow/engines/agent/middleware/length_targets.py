"""
Single source of truth for word-count targets derived from a content type's
``target_word_count``.

Previously three different call sites each computed their own, disagreeing
range from the same ``target_word_count``:
  - ``content_generation.py``'s human message: ``target_word_count`` to
    ``target_word_count + max(50, round(target_word_count * 0.15))``
  - ``persona_middleware.py``'s system prompt: body 1500-1725, but a
    *separate* combined-total floor of ``target_word_count + 200``
  - ``humanize_middleware.py``'s own rewrite-prompt calc: ``target_word_count``
    to ``target_word_count + max(30, round(target_word_count * 0.12))``

Because the agent was told to aim for one range while HumanizeMiddleware
independently believed a different (lower) range was correct, the length
instruction it computed post-generation was frequently already wrong before
the rewrite even started. All three now import this instead of maintaining
their own copy.
"""


def compute_length_targets(target_word_count: int) -> dict[str, int]:
    """Return the body/total min/max and per-section floors for a given
    target word count. ``total_*`` covers ``introduction + body_markdown``
    combined (introduction has its own separate ~200-word floor)."""
    body_min = target_word_count
    body_buffer = max(200, int(target_word_count * 0.15))
    body_max = body_min + body_buffer
    total_min = target_word_count + 200
    total_max = total_min + body_buffer
    return {
        "body_min": body_min,
        "body_max": body_max,
        "total_min": total_min,
        "total_max": total_max,
        "section_min": max(300, int(target_word_count * 0.12)),
        "subsection_min": max(120, int(target_word_count * 0.05)),
    }
