"""A keyword in another script, or with accents, is matched in its titles (G69b, #594).

Matching kept only a-z and 0-9, so a Chinese, Arabic or Cyrillic keyword flattened to nothing and
an accented one lost its accented letters: no title could contain it, every title was dropped as
missing the keyphrase, and the run ended at the title step. Text is now NFC-normalized and
lowercased, the letters, marks and digits of every script are kept, and a keyword in a script
written without spaces is matched as a run of characters.
"""

import unicodedata
from unittest.mock import AsyncMock

import pytest

from src.flow.engines.content.generation import topic_generation as tg
from src.flow.engines.content.generation.seo_title_rules import (
    contains_keyphrase,
    keyphrase_fits_a_title,
    normalize_title,
    title_is_valid,
    title_max_chars,
)
from src.flow.model.structure.topics import SEOTopic, SEOTopics


def _nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


@pytest.mark.parametrize(
    ("title", "keyphrase", "expected"),
    [
        # Latin, as before: whole words, case and punctuation ignored.
        ("Best SEO-Agency Picks for 2026", "seo agency", True),
        ("An SEO agencyx review", "seo agency", False),
        # Accents are part of the phrase, typed precomposed or as separate marks.
        ("Recette de crème brûlée facile", "crème brûlée", True),
        ("Recette de crème brûlée facile", _nfd("crème brûlée"), True),
        (_nfd("Recette de crème brûlée facile"), "crème brûlée", True),
        ("Recette de creme brulee facile", "crème brûlée", False),
        # Cyrillic, any case.
        ("ЛУЧШИЕ программы для небольших команд", "лучшие программы", True),
        # Arabic: whole words, not part of one.
        ("أفضل برامج إدارة المشاريع للفرق الصغيرة", "برامج إدارة المشاريع", True),
        ("أفضل برامجنا لهذا العام", "برامج", False),
        # Devanagari keeps its vowel signs.
        ("हिन्दी में सबसे अच्छा सॉफ्टवेयर", "हिन्दी", True),
        # Chinese has no spaces between words: the phrase as a run of characters.
        ("2026年最佳项目管理软件推荐", "项目管理软件", True),
        ("2026年最佳项目管理推荐", "项目管理软件", False),
        # Japanese, kana and kanji, and halfwidth kana.
        ("小規模チーム向けのプロジェクト管理ツール比較", "プロジェクト管理ツール", True),
        ("ﾌﾟﾛｼﾞｪｸﾄﾂｰﾙ比較", "ﾌﾟﾛｼﾞｪｸﾄﾂｰﾙ", True),
        # A mixed phrase keeps the boundary at its Latin edge.
        ("AIツール比較", "AIツール", True),
        ("XAIツール比較", "AIツール", False),
        ("项目管理 software 推荐", "项目管理 software", True),
        ("项目管理 softwarex", "项目管理 software", False),
        # A Latin word written against Chinese characters, with no space, is still a word.
        ("最佳seo工具推荐", "seo", True),
        # Lowercase, not casefold: ß and ss are different words.
        ("Maße und Gewichte", "Masse", False),
        ("MASSE UND GEWICHTE", "masse", True),
        # Turkish: a capital dotted İ is an i; the dotless ı is a letter of its own.
        ("İstanbul'da En İyi SEO Ajansları", "istanbul", True),
        ("ISTANBUL İÇİN SEO REHBERİ", "İstanbul", True),
        ("ıstanbul için seo", "istanbul", False),
        # CJK ideographs beyond the first plane (Extension B on) are unspaced too.
        ("𠀀𠀁𠀂", "𠀁", True),
        ("2026年𠮷野家の店舗", "𠮷野家", True),
    ],
)
def test_a_keyphrase_in_any_script_is_matched(title, keyphrase, expected):
    assert contains_keyphrase(title, keyphrase) is expected


def test_an_empty_or_punctuation_only_keyphrase_matches_nothing():
    assert not contains_keyphrase("Anything at all", "")
    assert not contains_keyphrase("Anything at all", " -- ")


def test_a_keyphrase_is_measured_in_characters_however_it_was_typed():
    keyphrase = "café crème brûlée recipes for beginners at home"
    assert len(_nfd(keyphrase)) > len(keyphrase)
    assert title_max_chars(_nfd(keyphrase)) == title_max_chars(keyphrase) == 67
    assert len(normalize_title(_nfd(keyphrase))) == len(keyphrase)


def test_a_keyword_in_another_script_fits_a_title():
    assert keyphrase_fits_a_title("项目管理软件")
    assert keyphrase_fits_a_title("برامج إدارة المشاريع")
    assert title_max_chars("项目管理软件") == 59


def test_a_title_in_another_script_can_be_valid():
    title = "أفضل برامج إدارة المشاريع للفرق الصغيرة: دليل شامل للاختيار"  # 59
    assert len(title) == 59
    assert title_is_valid(title, "برامج إدارة المشاريع")


@pytest.mark.asyncio
async def test_an_arabic_keywords_titles_reach_the_picker():
    """The bug: every title was dropped as missing the keyphrase, and the run ended."""
    keyphrase = "برامج إدارة المشاريع"
    written = SEOTopics(
        topics=[
            SEOTopic(
                title="أفضل برامج إدارة المشاريع للفرق الصغيرة: دليل شامل للاختيار",  # 59
                recommended=True,
            ),
            SEOTopic(title="دليل برامج إدارة المشاريع للفرق الصغيرة والشركات الناشئة"),  # 56
        ]
    )
    model = AsyncMock()
    model.ainvoke.side_effect = [written]

    result = await tg._generate_and_validate_topics(
        model=model, messages=[], query=keyphrase, keyphrase=keyphrase
    )

    assert result is not None
    assert [topic.title for topic in result.topics] == [t.title for t in written.topics]
