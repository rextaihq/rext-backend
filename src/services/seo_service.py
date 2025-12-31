from typing import Dict, Any, List, Tuple
from src.flow.states.wrext import WREXT
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.util import ngrams
from nltk.stem import PorterStemmer
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
import nltk
import re
import math

# Download required NLTK data
nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)


class KeywordExtractor:
    """
    NLTK N-grams + TF-IDF Keyword Extractor
    
    This approach mirrors how early Ahrefs & SEMrush worked:
    1. Extract text corpus from SERP data (titles, snippets, questions, topics)
    2. Tokenize and clean the text
    3. Generate n-grams (1-gram, 2-gram, 3-gram)
    4. Calculate TF-IDF scores for each n-gram
    5. Rank keywords by combined TF-IDF score
    """
    
    def __init__(self):
        self.stop_words = set(stopwords.words('english'))
        self.stemmer = PorterStemmer()
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for processing."""
        if not text:
            return ""
        # Convert to lowercase
        text = text.lower()
        # Remove URLs
        text = re.sub(r'https?://\S+|www\.\S+', '', text)
        # Remove special characters but keep spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text and remove stopwords."""
        tokens = word_tokenize(text)
        # Filter: only alphabetic, length > 2, not stopword
        filtered = [
            token for token in tokens 
            if token.isalpha() 
            and len(token) > 2 
            and token not in self.stop_words
        ]
        return filtered
    
    def _generate_ngrams(self, tokens: List[str], n: int) -> List[str]:
        """Generate n-grams from token list."""
        if len(tokens) < n:
            return []
        n_grams = list(ngrams(tokens, n))
        return [' '.join(gram) for gram in n_grams]
    
    def _extract_corpus_from_serp(
        self, 
        normalize_results: List[Dict[str, Any]],
        related_topics: List[str],
        questions: List[str],
        query: str
    ) -> List[str]:
        """
        Extract text corpus from SERP data.
        Each document represents a different source for TF-IDF calculation.
        """
        documents = []
        
        # Document 1: All titles (high weight - titles are keyword-rich)
        titles = ' '.join([
            result.get('title', '') 
            for result in (normalize_results or [])
        ])
        if titles.strip():
            documents.append(titles)
        
        # Document 2: All snippets (medium weight - context and variations)
        snippets = ' '.join([
            result.get('snippet', '') 
            for result in (normalize_results or [])
        ])
        if snippets.strip():
            documents.append(snippets)
        
        # Document 3: Related topics (high weight - semantic expansion)
        topics_text = ' '.join(related_topics or [])
        if topics_text.strip():
            documents.append(topics_text)
        
        # Document 4: Questions (PAA - high intent signals)
        questions_text = ' '.join(questions or [])
        if questions_text.strip():
            documents.append(questions_text)
        
        # Document 5: Original query (anchor document)
        if query:
            documents.append(query)
        
        return documents
    
    def _build_vocabulary(
        self, 
        cleaned_docs: List[str], 
        ngram_range: Tuple[int, int] = (1, 3)
    ) -> List[str]:
        """
        Build vocabulary from cleaned documents using NLTK tokenization.
        
        This is the classic approach used by early SEO tools:
        1. Tokenize each document
        2. Remove stopwords using NLTK
        3. Generate n-grams (unigrams, bigrams, trigrams)
        4. Return unique vocabulary terms
        
        Args:
            cleaned_docs: List of cleaned text documents
            ngram_range: Tuple of (min_n, max_n) for n-gram generation
            
        Returns:
            List of unique vocabulary terms (n-grams)
        """
        vocabulary = set()
        min_n, max_n = ngram_range
        
        for doc in cleaned_docs:
            # Tokenize and filter using NLTK stopwords
            tokens = self._tokenize(doc)
            
            if not tokens:
                continue
            
            # Generate n-grams for each n in range
            for n in range(min_n, max_n + 1):
                if len(tokens) >= n:
                    doc_ngrams = self._generate_ngrams(tokens, n)
                    vocabulary.update(doc_ngrams)
        
        return list(vocabulary)
    
    def _calculate_tfidf_scores(
        self, 
        documents: List[str],
        ngram_range: Tuple[int, int] = (1, 3)
    ) -> Dict[str, float]:
        """
        Calculate TF-IDF scores for n-grams across documents.
        
        Uses NLTK-built vocabulary to ensure stopwords are properly filtered.
        
        Returns a dictionary of {keyword: tfidf_score}
        """
        if not documents:
            return {}
        
        # Clean all documents
        cleaned_docs = [self._clean_text(doc) for doc in documents]
        
        # Filter out empty documents
        cleaned_docs = [doc for doc in cleaned_docs if doc.strip()]
        
        if not cleaned_docs:
            return {}
        
        # Build vocabulary using NLTK tokenization and stopword filtering
        vocabulary = self._build_vocabulary(cleaned_docs, ngram_range)
        
        if not vocabulary:
            return {}
        
        try:
            # Initialize TF-IDF Vectorizer with pre-built vocabulary
            # If only one document, max_df must be 1.0
            max_df = 1.0 if len(cleaned_docs) == 1 else 0.95
            
            vectorizer = TfidfVectorizer(
                ngram_range=ngram_range,
                vocabulary=vocabulary,  # Use NLTK-filtered vocabulary
                min_df=1,
                max_df=max_df,
                lowercase=True,
                token_pattern=r'(?u)\b[a-zA-Z][a-zA-Z]+\b',  # Only alphabetic tokens
            )            
            # Fit and transform documents
            tfidf_matrix = vectorizer.fit_transform(cleaned_docs)
            feature_names = vectorizer.get_feature_names_out()
            
            # Calculate average TF-IDF score across all documents for each term
            keyword_scores = {}
            threshold = 0.001 if len(cleaned_docs) == 1 else 0.01
            for idx, term in enumerate(feature_names):
                # Average score across all documents
                avg_score = tfidf_matrix[:, idx].mean()
                # Skip very low scores
                if avg_score > threshold:
                    keyword_scores[term] = float(avg_score)
            
            return keyword_scores
            
        except Exception as e:
            print(f"TF-IDF calculation error: {e}")
            return {}
    
    def _boost_keyword_scores(
        self,
        keyword_scores: Dict[str, float],
        query: str,
        related_topics: List[str]
    ) -> Dict[str, float]:
        """
        Apply SEO-specific boosts to keyword scores.
        
        Boost factors:
        - Query terms: 1.5x (most relevant)
        - Related topics: 1.3x (semantic relevance)
        - Multi-word phrases: 1.2x (long-tail value)
        """
        boosted_scores = {}
        query_terms = set(self._tokenize(self._clean_text(query or "")))
        topic_terms = set()
        
        for topic in (related_topics or []):
            topic_terms.update(self._tokenize(self._clean_text(topic)))
        
        for keyword, score in keyword_scores.items():
            boost = 1.0
            keyword_tokens = set(keyword.split())
            
            # Boost if keyword contains query terms
            if keyword_tokens.intersection(query_terms):
                boost *= 1.5
            
            # Boost if keyword relates to topics
            if keyword_tokens.intersection(topic_terms):
                boost *= 1.3
            
            # Boost multi-word phrases (long-tail keywords)
            word_count = len(keyword.split())
            if word_count == 2:
                boost *= 1.2
            elif word_count == 3:
                boost *= 1.15
            
            boosted_scores[keyword] = score * boost
        
        return boosted_scores
    
    def extract_keywords(
        self,
        normalize_results: List[Dict[str, Any]] = None,
        related_topics: List[str] = None,
        questions: List[str] = None,
        query: str = None,
        top_n: int = 50,
        text: str = None
    ) -> List[Dict[str, Any]]:
        """
        Extract and rank keywords using N-grams + TF-IDF.
        
        Args:
            normalize_results: SERP organic results
            related_topics: Related search topics
            questions: People Also Ask questions
            query: Original search query
            top_n: Number of top keywords to return
            text: Optional single document text to extract from
            
        Returns:
            List of keyword dictionaries with scores and metadata
        """
        if text:
            documents = [text]
        else:
            # Extract corpus from SERP data
            documents = self._extract_corpus_from_serp(
                normalize_results or [], 
                related_topics or [], 
                questions or [], 
                query or ""
            )
        
        if not documents:
            return []
        
        # Calculate TF-IDF scores for 1-grams, 2-grams, and 3-grams
        keyword_scores = self._calculate_tfidf_scores(
            documents, 
            ngram_range=(1, 3)
        )
        
        if not keyword_scores:
            return []
        
        # Apply SEO-specific boosts
        boosted_scores = self._boost_keyword_scores(
            keyword_scores, 
            query, 
            related_topics
        )
        
        # Sort by score descending
        sorted_keywords = sorted(
            boosted_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:top_n]
        
        # Normalize scores to 0-100 scale
        max_score = sorted_keywords[0][1] if sorted_keywords else 1.0
        
        # Build result with metadata
        results = []
        for rank, (keyword, score) in enumerate(sorted_keywords, 1):
            word_count = len(keyword.split())
            normalized_score = round((score / max_score) * 100, 2)
            
            results.append({
                "keyword": keyword,
                "score": normalized_score,
                "raw_tfidf": round(score, 4),
                "rank": rank,
                "word_count": word_count,
                "in_query": keyword in (query or "").lower(),
                "in_topics": any(
                    keyword in (topic or "").lower() 
                    for topic in (related_topics or [])
                )
            })
        
        return results
    
    def title_recommendation(
        self,
        user_title: str,
        normalize_results: List[Dict[str, Any]],
        related_topics: List[str] = None,
        extracted_keywords: List[Dict[str, Any]] = None,
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        Generate optimized title recommendations based on user title and SERP analysis.
        
        Analyzes competitor titles to extract patterns and suggests high-relevance
        titles optimized for SEO.
        
        Args:
            user_title: The user's original title/topic
            normalize_results: SERP organic results with competitor titles
            related_topics: Related search topics for keyword enrichment
            extracted_keywords: Pre-extracted keywords with scores
            top_n: Number of title recommendations to generate
            
        Returns:
            Dict containing title recommendations and analysis
        """
        if not user_title:
            return {"error": "No title provided", "recommendations": []}
        
        # Extract competitor titles
        competitor_titles = [
            r.get("title", "") for r in (normalize_results or [])
            if r.get("title")
        ]
        
        # Analyze title patterns
        patterns = self._analyze_title_patterns(competitor_titles)
        
        # Extract high-value keywords from user title and SERP data
        user_keywords = self._tokenize(self._clean_text(user_title))
        
        # Get top keywords from extracted_keywords if available
        top_keywords = []
        if extracted_keywords:
            top_keywords = [
                kw["keyword"] for kw in extracted_keywords[:10]
                if kw.get("type") in ["body", "long-tail"]
            ]
        
        # Generate title recommendations
        recommendations = self._generate_title_recommendations(
            user_title=user_title,
            user_keywords=user_keywords,
            patterns=patterns,
            top_keywords=top_keywords,
            related_topics=related_topics or [],
            top_n=top_n
        )
        
        # Score each recommendation
        scored_recommendations = self._score_titles(
            recommendations,
            user_keywords,
            patterns
        )
        
        return {
            "original_title": user_title,
            "recommendations": scored_recommendations,
            "patterns_found": patterns,
            "top_keywords_used": top_keywords[:5],
            "total_competitors_analyzed": len(competitor_titles)
        }
    
    def _analyze_title_patterns(self, titles: List[str]) -> Dict[str, Any]:
        """
        Analyze competitor titles to extract common patterns.
        
        Extracts:
        - Average word count
        - Common power words
        - Number usage patterns
        - Year/date patterns
        - Title structures (listicle, how-to, question)
        """
        if not titles:
            return {
                "avg_word_count": 8,
                "power_words": [],
                "uses_numbers": False,
                "uses_year": False,
                "dominant_structure": "standard"
            }
        
        # Power words commonly used in high-CTR titles
        power_words = {
            "best", "top", "ultimate", "complete", "guide", "essential",
            "proven", "powerful", "effective", "simple", "easy", "quick",
            "free", "new", "secret", "amazing", "incredible", "definitive"
        }
        
        word_counts = []
        found_power_words = Counter()
        number_count = 0
        year_count = 0
        structure_counts = {"listicle": 0, "how_to": 0, "question": 0, "standard": 0}
        
        current_year = "2024"  # Can be dynamic
        
        for title in titles:
            clean_title = title.lower()
            words = clean_title.split()
            word_counts.append(len(words))
            
            # Check for power words
            for word in words:
                if word in power_words:
                    found_power_words[word] += 1
            
            # Check for numbers (listicle pattern)
            if re.search(r'\b\d+\b', clean_title):
                number_count += 1
                if re.match(r'^\d+', clean_title):
                    structure_counts["listicle"] += 1
            
            # Check for year
            if re.search(r'\b20\d{2}\b', clean_title):
                year_count += 1
            
            # Check for how-to
            if clean_title.startswith("how to") or "how to" in clean_title:
                structure_counts["how_to"] += 1
            
            # Check for question
            if any(clean_title.startswith(q) for q in ["what", "why", "when", "where", "which", "who"]):
                structure_counts["question"] += 1
        
        # Determine dominant structure
        for struct, count in structure_counts.items():
            if struct != "standard" and count == 0:
                structure_counts["standard"] += 1
        
        dominant_structure = max(structure_counts, key=structure_counts.get)
        
        return {
            "avg_word_count": round(sum(word_counts) / len(word_counts)) if word_counts else 8,
            "power_words": [w for w, c in found_power_words.most_common(5)],
            "uses_numbers": number_count > len(titles) * 0.3,
            "uses_year": year_count > len(titles) * 0.2,
            "dominant_structure": dominant_structure,
            "structure_distribution": structure_counts
        }
    
    def _generate_title_recommendations(
        self,
        user_title: str,
        user_keywords: List[str],
        patterns: Dict[str, Any],
        top_keywords: List[str],
        related_topics: List[str],
        top_n: int
    ) -> List[str]:
        """
        Generate title recommendations based on patterns and keywords.
        """
        recommendations = []
        
        # Extract core topic from user title
        core_topic = user_title.strip()
        if len(user_keywords) >= 2:
            core_topic = ' '.join(user_keywords[:3]).title()
        
        # Get power words to use
        power_words = patterns.get("power_words", ["Best", "Complete", "Ultimate"])
        if not power_words:
            power_words = ["Best", "Complete", "Ultimate", "Essential", "Top"]
        
        # Template-based generation
        templates = []
        
        # 1. Listicle format (if pattern shows numbers work)
        if patterns.get("uses_numbers", False) or patterns.get("dominant_structure") == "listicle":
            templates.append(f"10 {power_words[0].title()} {core_topic} Tips for 2024")
            templates.append(f"7 {core_topic} Strategies That Actually Work")
        
        # 2. How-to format
        templates.append(f"How to Master {core_topic}: A Complete Guide")
        templates.append(f"How to {core_topic} Like a Pro in 2024")
        
        # 3. Ultimate/Complete guide
        templates.append(f"The Ultimate Guide to {core_topic}")
        templates.append(f"{core_topic}: Everything You Need to Know")
        
        # 4. Question format
        templates.append(f"What is {core_topic}? A Beginner's Guide")
        
        # 5. With year (if pattern shows it works)
        if patterns.get("uses_year", False):
            templates.append(f"{core_topic} in 2024: Complete Guide")
            templates.append(f"Best {core_topic} Guide [2024 Updated]")
        
        # 6. Power word enhanced
        if power_words:
            templates.append(f"The {power_words[0].title()} {core_topic} Tutorial for Beginners")
        
        # 7. Include related topics if available
        if related_topics and len(related_topics) > 0:
            related = related_topics[0].split()[-1] if related_topics[0] else ""
            if related:
                templates.append(f"{core_topic} and {related.title()}: Complete Guide")
        
        # 8. Include top keywords
        if top_keywords:
            kw = top_keywords[0].title() if top_keywords else ""
            if kw and kw.lower() not in core_topic.lower():
                templates.append(f"{core_topic}: {kw} Explained")
        
        # Remove duplicates and select top_n
        seen = set()
        for template in templates:
            if template not in seen:
                recommendations.append(template)
                seen.add(template)
            if len(recommendations) >= top_n + 2:
                break
        
        return recommendations[:top_n + 2]  # Return a few extra for scoring
    
    def _score_titles(
        self,
        titles: List[str],
        user_keywords: List[str],
        patterns: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Score each title recommendation based on SEO factors.
        
        Scoring factors:
        - Keyword presence (from user title)
        - Word count (optimal 50-60 chars / 6-10 words)
        - Power word presence
        - Number presence
        - Structure match with competitors
        """
        scored = []
        
        for title in titles:
            score = 50  # Base score
            reasons = []
            
            clean_title = title.lower()
            words = clean_title.split()
            char_count = len(title)
            
            # 1. Keyword presence (+20 max)
            keyword_matches = sum(1 for kw in user_keywords if kw.lower() in clean_title)
            keyword_score = min(keyword_matches * 5, 20)
            score += keyword_score
            if keyword_matches > 0:
                reasons.append(f"{keyword_matches} keywords matched")
            
            # 2. Optimal length (+15 max)
            # Optimal: 50-60 chars, 6-10 words
            if 50 <= char_count <= 60:
                score += 15
                reasons.append("Optimal character length")
            elif 40 <= char_count <= 70:
                score += 10
            elif char_count > 70:
                score -= 10
                reasons.append("Title too long")
            
            if 6 <= len(words) <= 10:
                score += 5
            
            # 3. Power word presence (+10)
            power_words = {"best", "top", "ultimate", "complete", "guide", "essential", 
                          "proven", "powerful", "effective", "simple", "easy", "quick"}
            if any(pw in clean_title for pw in power_words):
                score += 10
                reasons.append("Contains power word")
            
            # 4. Number presence (+5 if pattern supports)
            if re.search(r'\b\d+\b', clean_title):
                if patterns.get("uses_numbers"):
                    score += 10
                    reasons.append("Number format matches competitors")
                else:
                    score += 3
            
            # 5. Year presence (+5 if pattern supports) 
            if re.search(r'\b20\d{2}\b', clean_title):
                if patterns.get("uses_year"):
                    score += 10
                    reasons.append("Year format matches competitors")
                else:
                    score += 3
            
            # Cap score at 100
            score = min(score, 100)
            
            scored.append({
                "title": title,
                "score": score,
                "char_count": char_count,
                "word_count": len(words),
                "reasons": reasons
            })
        
        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        
        # Add rank
        for i, item in enumerate(scored, 1):
            item["rank"] = i
        
        return scored


if __name__ == "__main__":
    import json
    
    # Mock SERP data for testing
    mock_normalize_results = [
        {
            "position": 1,
            "title": "Python Tutorial - W3Schools",
            "url": "https://www.w3schools.com/python/",
            "snippet": "Learn Python programming with our complete tutorial guide for beginners.",
            "domain": "w3schools.com",
            "has_sitelinks": True
        },
        {
            "position": 2,
            "title": "The Python Tutorial — Python 3.12 Documentation",
            "url": "https://docs.python.org/3/tutorial/",
            "snippet": "This tutorial introduces the reader informally to the basic concepts and features of the Python language.",
            "domain": "docs.python.org",
            "has_sitelinks": False
        },
        {
            "position": 3,
            "title": "Learn Python - Free Interactive Python Tutorial",
            "url": "https://www.learnpython.org/",
            "snippet": "Welcome to the LearnPython.org interactive Python tutorial.",
            "domain": "learnpython.org",
            "has_sitelinks": False
        },
        {
            "position": 4,
            "title": "Python Tutorial for Beginners [2024] - Complete Guide",
            "url": "https://realpython.com/python-tutorial/",
            "snippet": "In this step-by-step Python tutorial, you'll learn how to get started with Python.",
            "domain": "realpython.com",
            "has_sitelinks": True
        },
        {
            "position": 5,
            "title": "10 Best Python Tutorials for Beginners in 2024",
            "url": "https://example.com/best-python-tutorials/",
            "snippet": "Looking for the best Python tutorials? Here are 10 top-rated courses and guides.",
            "domain": "example.com",
            "has_sitelinks": False
        }
    ]
    
    mock_related_topics = [
        "python tutorial for beginners",
        "python programming language",
        "learn python online free",
        "python basics"
    ]
    
    mock_questions = [
        "How do I start learning Python?",
        "What is Python used for?",
        "Is Python easy to learn?"
    ]
    
    print("=" * 60)
    print("🧪 TESTING SEO SERVICE")
    print("=" * 60)
    
    # Initialize the extractor
    extractor = KeywordExtractor()
    
    # Test 1: Extract Keywords
    print("\n📌 TEST 1: Keyword Extraction")
    print("-" * 40)
    
    keywords = extractor.extract_keywords(
        normalize_results=mock_normalize_results,
        related_topics=mock_related_topics,
        questions=mock_questions,
        query="python tutorial",
        top_n=10
    )
    
    print(f"✅ Extracted {len(keywords)} keywords")
    print("\nTop 5 Keywords:")
    for kw in keywords[:5]:
        print(f"  - {kw['keyword']} (score: {kw['score']}, type: {kw['type']})")
    
    # Test 2: Title Recommendation
    print("\n📌 TEST 2: Title Recommendation")
    print("-" * 40)
    
    title_result = extractor.title_recommendation(
        user_title="python tutorial",
        normalize_results=mock_normalize_results,
        related_topics=mock_related_topics,
        extracted_keywords=keywords,
        top_n=5
    )
    
    print(f"✅ Generated {len(title_result['recommendations'])} title recommendations")
    print(f"📊 Competitors analyzed: {title_result['total_competitors_analyzed']}")
    print(f"🔍 Patterns found: {json.dumps(title_result['patterns_found'], indent=2)}")
    
    print("\n🏆 Top Title Recommendations:")
    for rec in title_result['recommendations'][:5]:
        print(f"  #{rec['rank']} (score: {rec['score']})")
        print(f"     Title: {rec['title']}")
        print(f"     Chars: {rec['char_count']}, Words: {rec['word_count']}")
        if rec['reasons']:
            print(f"     Reasons: {', '.join(rec['reasons'])}")
        print()
    
    print("=" * 60)
    print("✅ ALL TESTS COMPLETED!")
    print("=" * 60)