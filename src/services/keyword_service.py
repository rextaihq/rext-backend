from typing import Dict, Any, List, Tuple
from src.flow.states.rext import REXT
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.util import ngrams
# from nltk.stem import PorterStemmer
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
import nltk
import re
import math
import random

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
        # self.stemmer = PorterStemmer()
    
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
        query: str,
        intent_matched_titles: List[str] | None = None,
        intent_matched_domains: List[str] | None = None,
    ) -> List[str]:
        """
        Extract text corpus from SERP data.
        Each document represents a different source for TF-IDF calculation.

        When intent_matched_* are set, titles/snippets come only from competitors
        whose intent matches the keyword (from competitor.py LLM).
        """
        documents = []
        domain_filter = set(intent_matched_domains or [])

        if intent_matched_titles:
            titles = " ".join(intent_matched_titles)
        else:
            titles = " ".join(
                result.get("title", "")
                for result in (normalize_results or [])
            )
        if titles.strip():
            documents.append(titles)

        snippet_rows = normalize_results or []
        if domain_filter:
            snippet_rows = [
                r for r in snippet_rows if r.get("domain") in domain_filter
            ]

        snippets = " ".join((result.get("snippet") or "") for result in snippet_rows)
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
            import logging
            logging.getLogger(__name__).warning(f"TF-IDF calculation error: {e}")
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
        serp_normalized: Dict[str, Any] = None,
        top_n: int = 50,
        intent_matched_titles: List[str] | None = None,
        intent_matched_domains: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract and rank keywords using N-grams + TF-IDF.

        Args:
            serp_normalized: SERP normalized results dictionary
            top_n: Number of top keywords to return
            intent_matched_titles: Titles from competitors matching keyword intent
            intent_matched_domains: Domains of those competitors (snippet filter)

        Returns:
            List of keyword dictionaries with scores and metadata
        """
        query = serp_normalized.get("query", "")
        related_topics = serp_normalized.get("related_topics", [])
        questions = serp_normalized.get("questions", [])
        normalize_results = serp_normalized.get("normalize_results", [])

        documents = self._extract_corpus_from_serp(
            normalize_results,
            related_topics,
            questions,
            query,
            intent_matched_titles=intent_matched_titles,
            intent_matched_domains=intent_matched_domains,
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
    
    def keyword_recommendation(
        self,
        serp_normalized: Dict[str, Any],
        extracted_keywords: List[Dict[str, Any]] = None,
        seo_opportunity: Dict[str, Any] = None,
        competitors_gap: Dict[str, Any] = None,
        keyword_difficulty: Dict[str, Any] = None,
        top_n: int = 10
    ) -> Dict[str, Any]:
        """
        Generate Google autocomplete-style keyword recommendations.
        
        Utilizes ALL SEO signals:
        - Keyword Difficulty: Prioritize easier keywords
        - SEO Opportunity: Boost high-opportunity topics
        - Competitor Gaps: Surface missing topics/questions
        - Extracted Keywords: TF-IDF ranked keywords
        
        Args:
            serp_normalized: SERP data containing query, normalize_results, related_topics
            extracted_keywords: Pre-extracted keywords with TF-IDF scores
            seo_opportunity: Opportunity analysis from seo_opportunity_node
            competitors_gap: Gap analysis from competitors_gap_node
            keyword_difficulty: Difficulty analysis from keyword_difficulty_node
            top_n: Number of recommendations to generate
            
        Returns:
            Dict containing ranked keyword recommendations with composite scores
        """
        query = serp_normalized.get("query", "")
        normalize_results = serp_normalized.get("normalize_results", [])
        related_topics = serp_normalized.get("related_topics", [])
        questions = serp_normalized.get("questions", [])
        
        if not query:
            return {"error": "No query provided", "recommendations": []}
        
        query_lower = query.lower().strip()
        query_words = set(query_lower.split())
        query_word_count = len(query.split())
        
        # Extract SEO signals
        difficulty_score = keyword_difficulty.get("difficulty_score", 50) if keyword_difficulty else 50
        difficulty_level = keyword_difficulty.get("difficulty_level", "medium") if keyword_difficulty else "medium"
        
        opportunity = seo_opportunity or {}
        opportunity_score = opportunity.get("opportunity_score", 50)
        opportunity_level = opportunity.get("opportunity_level", "medium")
        
        gaps = competitors_gap or {}
        missing_topics = gaps.get("missing_topics", [])
        missing_questions = gaps.get("missing_questions", [])
        weak_areas = gaps.get("weak_coverage_areas", [])
        
        # Candidate pool with source tracking
        candidates = []
        seen_keywords = {query_lower}
        
        # ==================================
        # PRIORITY 1: Missing Topics (Gap Analysis)
        # These are topics competitors cover but we could do better
        # ==================================
        for topic in missing_topics[:5]:
            topic_clean = topic.strip() if isinstance(topic, str) else str(topic)
            topic_lower = topic_clean.lower()
            
            if topic_lower in seen_keywords or not topic_clean:
                continue
            
            seen_keywords.add(topic_lower)
            candidates.append({
                "keyword": topic_clean,
                "source": "gap_topic",
                "base_score": 95,  # High priority - competitors are missing this
                "opportunity_boost": 20,  # High opportunity
                "difficulty_modifier": 0,
                "relevance_boost": 10 if any(w in topic_lower for w in query_words) else 0
            })
        
        # ==================================
        # PRIORITY 2: Missing Questions (PAA Gaps)
        # Questions that appear in SERP but competitors don't answer
        # ==================================
        for question in missing_questions[:5]:
            q_text = question.strip() if isinstance(question, str) else str(question)
            q_lower = q_text.lower()
            
            if q_lower in seen_keywords or not q_text:
                continue
            
            # Create keyword version of question
            q_clean = self._clean_text(q_text)
            question_prefixes = {"what", "how", "why", "when", "where", "who", "which", "is", "are", "do", "does", "can"}
            filtered = [w for w in q_clean.split() if w not in question_prefixes]
            keyword = " ".join(filtered[:query_word_count + 3])
            
            if keyword.lower() in seen_keywords or len(keyword) < 4:
                continue
            
            seen_keywords.add(keyword.lower())
            candidates.append({
                "keyword": keyword,
                "source": "gap_question",
                "base_score": 90,
                "opportunity_boost": 15,
                "difficulty_modifier": 0,
                "relevance_boost": 15 if any(w in keyword.lower() for w in query_words) else 5
            })
        
        # ==================================
        # PRIORITY 3: Weak Coverage Areas
        # Topics with minimal competitor coverage (opportunity!)
        # ==================================
        for topic in weak_areas[:5]:
            topic_clean = topic.strip() if isinstance(topic, str) else str(topic)
            topic_lower = topic_clean.lower()
            
            if topic_lower in seen_keywords or not topic_clean:
                continue
            
            seen_keywords.add(topic_lower)
            candidates.append({
                "keyword": topic_clean,
                "source": "weak_coverage",
                "base_score": 85,
                "opportunity_boost": 25,  # Very high opportunity (weak competition)
                "difficulty_modifier": -10,  # Likely easier to rank
                "relevance_boost": 10 if any(w in topic_lower for w in query_words) else 0
            })
        
        # ==================================
        # PRIORITY 4: Related Topics (Google suggestions)
        # These are from "People also search" - reliable signals
        # ==================================
        for topic in related_topics:
            topic_text = topic if isinstance(topic, str) else topic.get("topic", "")
            if not topic_text:
                continue
            
            topic_clean = topic_text.strip()
            topic_lower = topic_clean.lower()
            
            if topic_lower in seen_keywords:
                continue
            
            topic_word_count = len(topic_clean.split())
            if topic_word_count > query_word_count + 3:
                continue
            
            seen_keywords.add(topic_lower)
            candidates.append({
                "keyword": topic_clean,
                "source": "related_topic",
                "base_score": 80,
                "opportunity_boost": 5,
                "difficulty_modifier": 0,
                "relevance_boost": 15 if any(w in topic_lower for w in query_words) else 0
            })
        
        # ==================================
        # PRIORITY 5: PAA Questions (high intent)
        # Questions from SERP - good for long-tail
        # ==================================
        for question in questions:
            q_text = question if isinstance(question, str) else question.get("question", "")
            if not q_text:
                continue
            
            q_clean = self._clean_text(q_text)
            question_prefixes = {"what", "how", "why", "when", "where", "who", "which", "is", "are", "do", "does", "can"}
            filtered = [w for w in q_clean.split() if w not in question_prefixes]
            keyword = " ".join(filtered[:query_word_count + 2])
            keyword_lower = keyword.lower()
            
            if keyword_lower in seen_keywords or len(keyword) < 4:
                continue
            
            seen_keywords.add(keyword_lower)
            candidates.append({
                "keyword": keyword,
                "source": "paa_question",
                "base_score": 75,
                "opportunity_boost": 10,
                "difficulty_modifier": 0,
                "relevance_boost": 10 if any(w in keyword_lower for w in query_words) else 0
            })
        
        # ==================================
        # PRIORITY 6: Extracted Keywords (TF-IDF)
        # High-frequency keywords from competitor content
        # ==================================
        if extracted_keywords:
            for kw_data in extracted_keywords[:20]:  # Top 20 TF-IDF keywords
                keyword = kw_data.get("keyword", "")
                keyword_lower = keyword.lower()
                
                if keyword_lower in seen_keywords:
                    continue
                
                keyword_word_count = len(keyword.split())
                if keyword_word_count > query_word_count + 2:
                    continue
                
                tfidf_score = kw_data.get("score", 0)
                kw_words = set(keyword_lower.split())
                
                # Only include if relevant to query or high TF-IDF
                if not kw_words.intersection(query_words) and tfidf_score < 50:
                    continue
                
                seen_keywords.add(keyword_lower)
                candidates.append({
                    "keyword": keyword,
                    "source": "tfidf",
                    "base_score": min(70, tfidf_score * 0.7),
                    "opportunity_boost": 0,
                    "difficulty_modifier": 0,
                    "relevance_boost": 20 if kw_words.intersection(query_words) else 0
                })
        
        # ==================================
        # CALCULATE FINAL COMPOSITE SCORES
        # ==================================
        recommendations = []
        
        # Apply global modifiers based on SEO signals
        difficulty_bonus = {
            "easy": 15,
            "medium": 5,
            "hard": -5,
            "very_hard": -15
        }.get(difficulty_level, 0)
        
        opportunity_bonus = {
            "high": 15,
            "medium": 5,
            "low": -5
        }.get(opportunity_level, 0)
        
        for candidate in candidates:
            # Calculate composite score
            composite_score = (
                candidate["base_score"]
                + candidate["opportunity_boost"]
                + candidate["difficulty_modifier"]
                + candidate["relevance_boost"]
                + difficulty_bonus  # Global difficulty context
                + opportunity_bonus  # Global opportunity context
            )
            
            # Clamp to 0-100
            composite_score = max(0, min(100, composite_score))
            
            recommendations.append({
                "keyword": candidate["keyword"],
                "score": round(composite_score, 1),
                "source": candidate["source"],
                "word_count": len(candidate["keyword"].split()),
                "opportunity": self._get_opportunity_label(composite_score),
                "difficulty": difficulty_level  # All inherit from main query for now
            })
        
        # Sort by composite score descending
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        
        # Assign ranks
        for i, rec in enumerate(recommendations[:top_n], 1):
            rec["rank"] = i
        
        return {
            "original_title": query,
            "recommendations": recommendations[:top_n],
            "patterns_found": {
                "gap_topics": len([c for c in candidates if c["source"] == "gap_topic"]),
                "gap_questions": len([c for c in candidates if c["source"] == "gap_question"]),
                "weak_areas": len([c for c in candidates if c["source"] == "weak_coverage"]),
                "related_topics": len([c for c in candidates if c["source"] == "related_topic"]),
                "paa_questions": len([c for c in candidates if c["source"] == "paa_question"]),
                "tfidf_keywords": len([c for c in candidates if c["source"] == "tfidf"])
            },
            "seo_context": {
                "query_difficulty": difficulty_level,
                "query_difficulty_score": difficulty_score,
                "opportunity_level": opportunity_level,
                "opportunity_score": opportunity_score,
                "content_gaps_detected": len(missing_topics) + len(missing_questions) + len(weak_areas)
            },
            "top_keywords_used": [r["keyword"] for r in recommendations[:5]],
            "total_competitors_analyzed": len(normalize_results)
        }
    
    def _get_opportunity_label(self, score: float) -> str:
        """Convert composite score to opportunity label."""
        if score >= 85:
            return "excellent"
        elif score >= 70:
            return "high"
        elif score >= 50:
            return "medium"
        else:
            return "low"
