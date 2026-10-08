"""Shared word-count tolerance band.

Previously duplicated with two different ratios: content_generation.py used
0.15 (ceiling only), the old HumanizeMiddleware used 0.12 (TARGET_BUFFER_RATIO,
floor implicitly = target itself). Consolidated here as the single source of
truth for "how far from target_word_count is still acceptable" — used by the
generation prompt, humanize_content, and check_word_count_band so all three
agree on the same band.
"""

from typing import NamedTuple

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


class SectionLengths(NamedTuple):
    """What the writer is told about the parts' lengths, all inside the band the whole is
    checked against."""

    total_min: int
    total_max: int
    intro_words: int
    body_min: int
    body_max: int
    # What one H2 section averages when the body is inside its range.
    average_low: int
    average_high: int
    section_min: int
    subsection_min: int


def plan_section_lengths(target_word_count: int, sections: int) -> SectionLengths:
    """The parts' lengths for an article of ``sections`` H2 sections.

    The floors used to come from the target alone (a tenth of it per H2 section), whatever
    the number of sections: eleven sections at a 1,500-word target were each told "150 words
    at least", 1,650 before the introduction, where the check accepts 1,680 with it. The
    writer met the floors and failed the total (rext-control#787). Here a floor is never more
    than three quarters of what a section averages inside the band, so every section at its
    floor still leaves the article under the band, with room to vary.
    """
    total_min, total_max = compute_word_target_band(target_word_count)
    intro_words = min(200, max(60, round(target_word_count * 0.12)))
    body_min = max(0, total_min - intro_words)
    body_max = max(0, total_max - intro_words)
    sections = max(1, sections)
    # Rounded inward, so either end of the average keeps the body inside its range.
    average_low, average_high = -(-body_min // sections), body_max // sections
    section_min = min(max(80, round(target_word_count * 0.10)), round(average_low * 0.75))
    subsection_min = min(max(40, round(target_word_count * 0.04)), section_min // 2)
    return SectionLengths(
        total_min,
        total_max,
        intro_words,
        body_min,
        body_max,
        average_low,
        average_high,
        max(0, section_min),
        max(0, subsection_min),
    )
