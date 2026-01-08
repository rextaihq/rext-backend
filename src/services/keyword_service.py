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
        serp_normalized: Dict[str, Any] = None,
        top_n: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Extract and rank keywords using N-grams + TF-IDF.
        
        Args:
            serp_normalized: SERP normalized results dictionary
            top_n: Number of top keywords to return
            
        Returns:
            List of keyword dictionaries with scores and metadata
        """
        # Extract data from serp_normalized dictionary
        query = serp_normalized.get("query", "")
        related_topics = serp_normalized.get("related_topics", [])
        questions = serp_normalized.get("questions", [])
        normalize_results = serp_normalized.get("normalize_results", [])

        # Extract corpus from SERP data
        documents = self._extract_corpus_from_serp(
                normalize_results,
                related_topics,
                questions,
                query
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
        top_n: int = 5
    ) -> Dict[str, Any]:
        """
        Generate Google autocomplete-style keyword recommendations.
        
        Uses related topics, questions, and high-value keywords from SERP data
        to suggest better keyword variations.
        
        Args:
            serp_normalized: SERP data containing query, normalize_results, related_topics
            extracted_keywords: Pre-extracted keywords with scores
            top_n: Number of recommendations to generate
            
        Returns:
            Dict containing keyword recommendations
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
        
        recommendations = []
        seen_keywords = {query_lower}
        
        # Priority 1: Related topics (best quality suggestions)
        for i, topic in enumerate(related_topics):
            topic_text = topic if isinstance(topic, str) else topic.get("topic", "")
            if topic_text:
                topic_clean = topic_text.strip()
                topic_lower = topic_clean.lower()
                
                # Skip if same as query or already seen
                if topic_lower in seen_keywords:
                    continue
                
                # Check word count (max query + 2 words)
                topic_word_count = len(topic_clean.split())
                if topic_word_count <= query_word_count + 2:
                    seen_keywords.add(topic_lower)
                    recommendations.append({
                        "keyword": topic_clean,
                        "score": round(100 - (len(recommendations) * 5), 1),
                        "rank": len(recommendations) + 1,
                        "word_count": topic_word_count,
                        "source": "related_topic"
                    })
                
                if len(recommendations) >= top_n:
                    break
        
        # Priority 2: Questions (good for long-tail keywords)
        if len(recommendations) < top_n:
            for question in questions:
                q_text = question if isinstance(question, str) else question.get("question", "")
                if q_text:
                    # Extract short version of question (remove question words)
                    q_clean = self._clean_text(q_text)
                    q_words = q_clean.split()
                    
                    # Remove question words and keep relevant part
                    question_words = {"what", "how", "why", "when", "where", "who", "which", "is", "are", "do", "does", "can"}
                    filtered_words = [w for w in q_words if w.lower() not in question_words]
                    
                    if filtered_words:
                        keyword = " ".join(filtered_words[:query_word_count + 2])
                        keyword_lower = keyword.lower()
                        
                        if keyword_lower not in seen_keywords and len(keyword) > 3:
                            seen_keywords.add(keyword_lower)
                            recommendations.append({
                                "keyword": keyword,
                                "score": round(80 - (len(recommendations) * 5), 1),
                                "rank": len(recommendations) + 1,
                                "word_count": len(keyword.split()),
                                "source": "question"
                            })
                
                if len(recommendations) >= top_n:
                    break
        
        # Priority 3: Extracted keywords with good TF-IDF scores
        if len(recommendations) < top_n and extracted_keywords:
            for kw_data in extracted_keywords:
                keyword = kw_data["keyword"]
                keyword_lower = keyword.lower()
                keyword_word_count = len(keyword.split())
                
                # Skip if already seen or too long
                if keyword_lower in seen_keywords:
                    continue
                if keyword_word_count > query_word_count + 2:
                    continue
                
                # Check if shares words with query (relevance check)
                kw_words = set(keyword_lower.split())
                if kw_words.intersection(query_words) or kw_data["score"] > 50:
                    seen_keywords.add(keyword_lower)
                    recommendations.append({
                        "keyword": keyword,
                        "score": kw_data["score"],
                        "rank": len(recommendations) + 1,
                        "word_count": keyword_word_count,
                        "source": "tfidf"
                    })
                
                if len(recommendations) >= top_n:
                    break
        
        return {
            "original_title": query,
            "recommendations": recommendations[:top_n],
            "patterns_found": {"sources_used": len(recommendations)},
            "top_keywords_used": [r["keyword"] for r in recommendations[:5]],
            "total_competitors_analyzed": len(normalize_results)
        }
