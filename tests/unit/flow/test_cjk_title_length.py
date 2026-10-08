"""A title in Chinese, Japanese, Korean or Thai has a length range that suits its script (G69c,
#610).

The title rules counted code points, 50 to 59, which suits Latin text: a natural Chinese or
Japanese title is 20 to 30 characters, so every one was padded with an English qualifier. Titles
are now measured by width (a wide character counts two, a mark or an invisible format character
none, so Latin text measures as before), each script family has its own range, and a short title
is padded in its own language, never in English.
"""

import pytest

from src.flow.engines.content.generation.seo_title_rules import (
    _local_language,
    keyphrase_fits_a_title,
    keyphrase_title,
    repair_title,
    title_is_valid,
    title_range,
    title_width,
)
from src.flow.engines.content.generation.topic_generation import _build_system_prompt


def test_width_is_length_for_latin_and_double_for_wide_characters():
    assert title_width("SEO Agencies for Small Businesses") == len(
        "SEO Agencies for Small Businesses"
    )
    assert title_width("Crème brûlée, café") == len("Crème brûlée, café")
    assert title_width("项目管理软件") == 12
    assert title_width("プロジェクト") == 12
    assert title_width("หิน") == 2  # a Thai vowel mark takes no width
    assert title_width("co­operate") == 9  # nor a soft hyphen


@pytest.mark.parametrize(
    ("title", "keyphrase"),
    [
        ("2026年最佳项目管理软件推荐：小团队如何选择合适的工具", "项目管理软件"),  # 26 characters
        ("小規模チーム向けプロジェクト管理ツールの選び方と比較", "プロジェクト管理ツール"),
        ("소규모 팀을 위한 프로젝트 관리 도구 추천", "프로젝트 관리 도구"),
        ("โปรแกรมจัดการโครงการที่ดีที่สุดสำหรับทีมขนาดเล็ก", "โปรแกรมจัดการโครงการ"),
    ],
)
def test_a_natural_title_in_its_script_is_valid_as_written(title, keyphrase):
    assert title_is_valid(title, keyphrase)
    assert repair_title(title, keyphrase) == title


@pytest.mark.parametrize(
    ("title", "keyphrase", "expected"),
    [
        ("项目管理软件推荐", "项目管理软件", "项目管理软件推荐：基本概念、常见用途与选择方法"),
        ("專案管理軟體推薦與選擇", "專案管理軟體", "專案管理軟體推薦與選擇：定義、用途與選擇要點"),
        (
            "プロジェクト管理ツール比較",
            "プロジェクト管理ツール",
            "プロジェクト管理ツール比較の基本：意味・使い方・選び方",
        ),
        (
            "프로젝트 관리 도구 추천",
            "프로젝트 관리 도구",
            "프로젝트 관리 도구 추천 | 의미, 활용법, 선택 기준",
        ),
    ],
)
def test_a_short_title_is_padded_in_its_own_language(title, keyphrase, expected):
    """Simplified or Traditional Chinese by the characters the title uses."""
    repaired = repair_title(title, keyphrase)
    assert repaired == expected
    assert title_is_valid(repaired, keyphrase)


@pytest.mark.parametrize(
    "keyphrase",
    ["项目管理软件", "茶叶", "專案管理軟體", "プロジェクト管理ツール", "프로젝트 관리 도구"],
)
def test_the_keyphrase_fallback_adds_no_english(keyphrase):
    title = keyphrase_title(keyphrase)
    assert title is not None
    assert title_is_valid(title, keyphrase)
    assert not any("a" <= char.lower() <= "z" for char in title)


@pytest.mark.parametrize("keyphrase", ["人工智能", "人工知能", "茶", "文化"])
def test_a_short_han_keyphrase_still_gets_a_last_resort_title(keyphrase):
    """Han characters alone don't say Chinese or Japanese. The neutral qualifiers lift even one
    character to the minimum, in characters all three writings share, so a run whose generated
    titles all failed still has a title, with no English in it."""
    title = keyphrase_title(keyphrase)

    assert title is not None
    assert title.startswith(keyphrase)
    assert title_is_valid(title, keyphrase), title
    assert not any(char.isascii() and char.isalpha() for char in title), title
    assert repair_title(keyphrase, keyphrase) == title


def test_the_neutral_han_qualifiers_cover_every_short_width():
    """From one Han character up to the widest keyphrase a title holds, some qualifier lands in
    the range: no gap where the padding overshoots or falls short."""
    for count in range(1, 21):
        keyphrase = "茶" * count
        title = keyphrase_title(keyphrase)
        assert title is not None and title_is_valid(title, keyphrase), (count, title)


def test_a_mixed_title_follows_the_script_most_of_it_is_in():
    # "seo" in a Chinese title: the Chinese range, and Chinese padding.
    repaired = repair_title("最佳seo工具推荐", "seo")
    assert repaired == "最佳seo工具推荐：基本概念、常见用途与选择方法"
    # A little kana in an English title: the Latin range.
    title = "How to Make Onigiri (おにぎり) at Home for Beginners Today"
    assert title_range(title, "onigiri") == (50, 59)
    assert title_is_valid(title, "onigiri")


def test_a_long_keyphrase_has_room_up_to_its_scripts_ceiling():
    assert title_range("", "项目管理软件") == (40, 60)
    assert title_range("", "项" * 25) == (40, 64)  # 50 wide, plus 20, capped at 64
    assert keyphrase_fits_a_title("项" * 32)  # 64 wide
    assert not keyphrase_fits_a_title("项" * 33)
    assert title_range("", "seo agencies") == (50, 59)  # Latin as before


def _prompt(keyphrase: str) -> str:
    return _build_system_prompt(
        keyphrase=keyphrase,
        current_year=2026,
        selected_intent="informational",
        selected_content_type="guide",
    )


def test_the_prompt_states_the_range_in_the_characters_a_writer_counts():
    chinese = _prompt("项目管理软件")
    assert "BETWEEN 20 AND 30 CHARACTERS" in chinese
    assert "Count each Chinese, Japanese or Korean character" in chinese
    thai = _prompt("โปรแกรมจัดการโครงการ")
    assert "BETWEEN 38 AND 55 CHARACTERS" in thai
    assert "BETWEEN 50 AND 59 CHARACTERS" in _prompt("seo agencies")


@pytest.mark.parametrize(
    ("title", "language"),
    [
        ("東京観光", "ja"),  # Japanese kanji forms, no kana
        ("プロジェクト管理ツール", "ja"),
        ("项目管理软件", "zh-Hans"),
        ("專案管理軟體推薦與選擇", "zh-Hant"),
        ("人工知能", "han"),  # nothing tells Chinese from Japanese: neutral qualifiers
        ("프로젝트 관리 도구", "ko"),
    ],
)
def test_a_han_title_is_padded_in_its_language_only_when_the_characters_show_it(title, language):
    assert _local_language(title) == language


def test_the_prompt_counts_full_width_punctuation_and_names_the_other_scripts_ranges():
    assert "each full-width punctuation mark" in _prompt("项目管理软件")
    # A Latin keyword may still get a Chinese title ("最佳seo工具推荐").
    assert "20-30 of those characters" in _prompt("seo")


def test_the_regenerate_note_keeps_the_counting_guidance():
    import inspect

    from src.flow.engines.content.generation import topic_generation

    source = inspect.getsource(topic_generation.generate_topics)
    assert "low, high, how = title_length_terms(keyphrase)" in source
    assert "characters ({how})" in source
