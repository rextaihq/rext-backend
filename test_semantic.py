import re
import math
from typing import List, Dict, Any

class WordPressPublisher:
    def _get_word_stems(self, text: str) -> List[str]:
        words = re.findall(r'\b[a-z0-9]+\b', text.lower())
        stems = []
        stop_words = {"the", "and", "for", "with", "about", "how", "what", "why", "are", "is", "this", "that", "in", "on", "at", "to", "of", "a", "an"}
        for w in words:
            if w in stop_words:
                continue
            if len(w) <= 3:
                stems.append(w)
                continue
            for suffix in ['ing', 'ers', 'er', 'es', 's', 'ed', 'ly', 'tion', 'ies']:
                if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                    w = w[:-len(suffix)]
                    if suffix == 'ies':
                        w += 'y'
                    break
            stems.append(w)
        return stems

    def _select_relevant_categories(self, content_text: str, existing_categories: List[Dict[str, Any]], max_categories: int = 2) -> List[int]:
        content_lower = content_text.lower()
        content_stems_list = self._get_word_stems(content_text)
        content_stems_set = set(content_stems_list)
        matches = []
        for category in existing_categories:
            cat_name = str(category.get("name", "")).strip()
            if not cat_name or cat_name.lower() == "uncategorized":
                continue
            cat_name_lower = cat_name.lower()
            cat_stems_set = set(self._get_word_stems(cat_name))
            if not cat_stems_set:
                continue
            score = 0
            if re.search(r'\b' + re.escape(cat_name_lower) + r'\b', content_lower):
                score += 100
            overlap = len(cat_stems_set.intersection(content_stems_set))
            if overlap > 0:
                score += (overlap / len(cat_stems_set)) * 50
            for stem in cat_stems_set:
                count = content_stems_list.count(stem)
                if count > 0:
                    score += math.log(count + 1) * 5
            if score > 0:
                matches.append({
                    "id": category["id"],
                    "name": cat_name,
                    "score": score,
                    "cat_stems": list(cat_stems_set),
                    "overlap": overlap
                })
        
        for m in matches:
            print(f"Considered: {m['name']} | Score: {m['score']:.1f} | Stems: {m['cat_stems']} | Overlap: {m['overlap']}")
            
        if not matches:
            return []
        matches.sort(key=lambda x: x["score"], reverse=True)
        top_score = matches[0]["score"]
        threshold = top_score * 0.3
        valid_matches = [m for m in matches if m["score"] >= threshold]
        top_matches = valid_matches[:max_categories]
        selected_ids = [m["id"] for m in top_matches]
        selected_names = [f"{m['name']} ({m['id']}, score: {m['score']:.1f})" for m in top_matches]
        print(f"Selected categories: {', '.join(selected_names)}")
        return selected_ids

if __name__ == "__main__":
    wp = WordPressPublisher()
    article = "Best AI Content Writing Tools for Bloggers in 2026"
    print(f"Article Stems: {wp._get_word_stems(article)}")
    categories = [
        {"id": 12, "name": "AI"},
        {"id": 14, "name": "SEO"},
        {"id": 18, "name": "Technology"},
        {"id": 20, "name": "Marketing"},
        {"id": 25, "name": "Blogging Tools"},
    ]
    wp._select_relevant_categories(article, categories)
