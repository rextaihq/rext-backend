"""Shared word-count tolerance band.

Previously duplicated with two different ratios: content_generation.py used
0.15 (ceiling only), the old HumanizeMiddleware used 0.12 (TARGET_BUFFER_RATIO,
floor implicitly = target itself). Consolidated here as the single source of
truth for "how far from target_word_count is still acceptable" — used by the
generation prompt, humanize_content, and check_word_count_band so all three
agree on the same band.
"""

DEFAULT_BUFFER_RATIO = 0.12
MIN_BUFFER_WORDS = 30


def compute_word_target_band(
    target_word_count: int,
    ratio: float = DEFAULT_BUFFER_RATIO,
    min_buffer: int = MIN_BUFFER_WORDS,
) -> tuple[int, int]:
    """Return (min_words, max_words) — a percentage-based tolerance band around a target.

    A flat buffer is a large relative overshoot allowance on a short target and
    negligible on a long one, so the buffer scales with the target itself, with
    a floor so very short targets still get a sane minimum band.
    """
    if target_word_count <= 0:
        return 0, 0
    buffer = max(min_buffer, round(target_word_count * ratio))
    return max(0, target_word_count - buffer), target_word_count + buffer
