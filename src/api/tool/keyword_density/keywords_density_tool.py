import re
from typing import Dict, List

def clean_text(text: str) -> List[str]:
    """
    Clean text and return list of lowercase words
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)  # remove punctuation
    words = text.split()
    return words

def keyword_density_checker(
    content: str,
    keywords: List[str]
) -> Dict:
    """
    Calculate keyword density for given content and keywords
    """
    words = clean_text(content)
    total_words = len(words)

    if total_words == 0:
        return {
            "total_words": 0,
            "keywords": []
        }

    results = []

    for keyword in keywords:
        keyword_words = clean_text(keyword)
        keyword_length = len(keyword_words)

        count = 0
        for i in range(len(words) - keyword_length + 1):
            if words[i:i + keyword_length] == keyword_words:
                count += 1

        density = round((count / total_words) * 100, 2)

        results.append({
            "keyword": keyword,
            "count": count,
            "density_percent": density
        })

    return {
        "total_words": total_words,
        "keywords": results
    }
