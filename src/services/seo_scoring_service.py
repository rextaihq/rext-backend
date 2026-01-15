"""
On-Page SEO Scoring Service

This module provides SEO scoring functionality to analyze content
and calculate on-page SEO scores based on critical SEO factors.
"""

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class OnPageSEOScorer:
    """Analyzes content against on-page SEO best practices."""
    
    def __init__(self):
        self.max_score = 100
        self.weights = {
            "title_optimization": 15,
            "meta_description": 10,
            "keyword_density": 15,
            "heading_structure": 15,
            "content_length": 10,
            "keyword_in_intro": 10,
            "internal_links": 8,
            "external_links": 7,
            "image_optimization": 5,
            "slug_optimization": 5,
        }
    
    def score_title_optimization(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check if title is SEO-optimized.
        - Contains focus keyword
        - Proper length (50-60 chars)
        - Focus keyword near the beginning
        """
        issues = []
        score = 0
        max_score = self.weights["title_optimization"]
        
        title = content.get("title", "")
        meta_title = content.get("meta_title", "")
        focus_keyword = content.get("focus_keyphrase", "").lower()
        
        if not title:
            issues.append("Missing article title")
            return 0, issues
        
        # Check meta title length (50-60 chars)
        if 50 <= len(meta_title) <= 60:
            score += max_score * 0.3
        elif len(meta_title) < 50:
            issues.append(f"Meta title too short ({len(meta_title)} chars, recommended: 50-60)")
        else:
            issues.append(f"Meta title too long ({len(meta_title)} chars, recommended: 50-60)")
        
        # Check if focus keyword is in title
        if focus_keyword in title.lower():
            score += max_score * 0.4
        else:
            issues.append("Focus keyword not found in title")
        
        # Check if focus keyword is near the beginning of title (first 30 chars)
        if focus_keyword in title.lower()[:30]:
            score += max_score * 0.3
        else:
            issues.append("Focus keyword should be closer to the beginning of the title")
        
        return score, issues
    
    def score_meta_description(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check meta description optimization.
        - Contains focus keyword
        - Proper length (150-160 chars)
        """
        issues = []
        score = 0
        max_score = self.weights["meta_description"]
        
        meta_desc = content.get("meta_description", "")
        focus_keyword = content.get("focus_keyphrase", "").lower()
        
        if not meta_desc:
            issues.append("Missing meta description")
            return 0, issues
        
        # Check length
        if 150 <= len(meta_desc) <= 160:
            score += max_score * 0.5
        elif len(meta_desc) < 150:
            issues.append(f"Meta description too short ({len(meta_desc)} chars, recommended: 150-160)")
        else:
            issues.append(f"Meta description too long ({len(meta_desc)} chars, recommended: 150-160)")
        
        # Check if focus keyword is present
        if focus_keyword in meta_desc.lower():
            score += max_score * 0.5
        else:
            issues.append("Focus keyword not found in meta description")
        
        return score, issues
    
    def score_keyword_density(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check keyword density.
        - Target: 0.5-2.5%
        - Check actual vs target
        """
        issues = []
        score = 0
        max_score = self.weights["keyword_density"]
        
        keyphrase_density = content.get("keyphrase_density", 0)
        
        # Ideal range: 0.5% - 2.5%
        if 0.5 <= keyphrase_density <= 2.5:
            score = max_score
        elif keyphrase_density < 0.5:
            issues.append(f"Keyword density too low ({keyphrase_density}%, recommended: 0.5-2.5%)")
            score = max_score * (keyphrase_density / 0.5) if keyphrase_density > 0 else 0
        else:
            issues.append(f"Keyword density too high ({keyphrase_density}%, recommended: 0.5-2.5%) - risk of keyword stuffing")
            # Penalty for keyword stuffing
            score = max_score * 0.3
        
        return score, issues
    
    def score_heading_structure(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Analyze heading structure in markdown content.
        - Check for H1 (should be 1)
        - Check for H2s (should have multiple)
        - Check keyword usage in headings
        """
        issues = []
        score = 0
        max_score = self.weights["heading_structure"]
        
        body = content.get("body_markdown", "")
        introduction = content.get("introduction", "")
        full_content = introduction + "\n\n" + body
        focus_keyword = content.get("focus_keyphrase", "").lower()
        
        # Count headings
        h1_count = len(re.findall(r'^# [^#]', full_content, re.MULTILINE))
        h2_count = len(re.findall(r'^## [^#]', full_content, re.MULTILINE))
        h3_count = len(re.findall(r'^### [^#]', full_content, re.MULTILINE))
        
        # Check H1 count (should be exactly 1 - the title)
        if h1_count == 1:
            score += max_score * 0.3
        elif h1_count == 0:
            issues.append("No H1 heading found in content")
        else:
            issues.append(f"Multiple H1 headings found ({h1_count}), should be exactly 1")
        
        # Check H2 count (should have at least 4)
        if h2_count >= 4:
            score += max_score * 0.3
        else:
            issues.append(f"Insufficient H2 headings ({h2_count} found, recommended: at least 4)")
            score += max_score * 0.3 * (h2_count / 4)
        
        # Check keyword in headings
        h2_headings = re.findall(r'^## (.+)$', full_content, re.MULTILINE)
        keyword_in_headings = sum(1 for h in h2_headings if focus_keyword in h.lower())
        
        if keyword_in_headings >= 2:
            score += max_score * 0.4
        elif keyword_in_headings == 1:
            score += max_score * 0.2
            issues.append("Focus keyword should appear in at least 2 H2 headings")
        else:
            issues.append("Focus keyword not found in any H2 headings")
        
        return score, issues
    
    def score_content_length(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check if content meets minimum length requirements.
        - Minimum: 1000 words
        - Ideal: 1500-2500 words
        """
        issues = []
        score = 0
        max_score = self.weights["content_length"]
        
        body = content.get("body_markdown", "")
        introduction = content.get("introduction", "")
        full_content = introduction + " " + body
        
        # Remove markdown formatting for word count
        text_only = re.sub(r'[#*`\[\]()]', '', full_content)
        word_count = len(text_only.split())
        
        if word_count >= 1500:
            score = max_score
        elif word_count >= 1000:
            score = max_score * 0.7
            issues.append(f"Content length is adequate ({word_count} words) but could be longer for better SEO")
        else:
            score = max_score * (word_count / 1000) * 0.5
            issues.append(f"Content too short ({word_count} words, recommended: at least 1000)")
        
        return score, issues
    
    def score_keyword_in_intro(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check if focus keyword appears in the first 100 words.
        """
        issues = []
        score = 0
        max_score = self.weights["keyword_in_intro"]
        
        introduction = content.get("introduction", "")
        focus_keyword = content.get("focus_keyphrase", "").lower()
        
        if not introduction:
            issues.append("No introduction found")
            return 0, issues
        
        # Get first 100 words
        words = introduction.split()[:100]
        first_100_words = " ".join(words).lower()
        
        if focus_keyword in first_100_words:
            score = max_score
        else:
            issues.append("Focus keyword not found in the first 100 words of content")
        
        return score, issues
    
    def score_internal_links(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check internal linking.
        - Should have at least 2-3 internal links
        """
        issues = []
        score = 0
        max_score = self.weights["internal_links"]
        
        internal_links = content.get("internal_links", [])
        count = len(internal_links)
        
        if count >= 3:
            score = max_score
        elif count >= 2:
            score = max_score * 0.7
            issues.append(f"Good internal linking ({count} links), consider adding more")
        elif count == 1:
            score = max_score * 0.4
            issues.append(f"Only {count} internal link found, recommended: at least 3")
        else:
            issues.append("No internal links found")
        
        return score, issues
    
    def score_external_links(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check external/outbound linking.
        - Should have at least 2-3 authoritative external links
        """
        issues = []
        score = 0
        max_score = self.weights["external_links"]
        
        outbound_links = content.get("outbound_links", [])
        count = len(outbound_links)
        
        if count >= 2:
            score = max_score
        elif count == 1:
            score = max_score * 0.6
            issues.append(f"Only {count} external link found, recommended: at least 2")
        else:
            issues.append("No external links found - add authoritative sources")
        
        return score, issues
    
    def score_image_optimization(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check image alt text suggestions.
        - Should have at least 1 image alt text suggestion
        - Alt text should contain keywords
        """
        issues = []
        score = 0
        max_score = self.weights["image_optimization"]
        
        images = content.get("images", [])
        focus_keyword = content.get("focus_keyphrase", "").lower()
        
        if not images:
            issues.append("No image alt text suggestions found")
            return 0, issues
        
        # Check if at least one alt text has keyword
        keyword_in_alt = any(focus_keyword in img.get("alt_text", "").lower() for img in images)
        
        if keyword_in_alt:
            score = max_score
        else:
            score = max_score * 0.5
            issues.append("Focus keyword not found in any image alt text suggestion")
        
        return score, issues
    
    def score_slug_optimization(self, content: Dict) -> Tuple[float, List[str]]:
        """
        Check URL slug optimization.
        - Should contain focus keyword
        - Should be URL-friendly
        """
        issues = []
        score = 0
        max_score = self.weights["slug_optimization"]
        
        slug = content.get("slug", "")
        focus_keyword = content.get("focus_keyphrase", "").lower()
        
        if not slug:
            issues.append("No URL slug provided")
            return 0, issues
        
        # Check if slug contains keyword
        if focus_keyword.replace(" ", "-") in slug:
            score = max_score
        else:
            issues.append("Focus keyword not found in URL slug")
            score = max_score * 0.5
        
        return score, issues
    
    def _get_status_message(self, percentage: float) -> str:
        """Get human-readable status message based on score."""
        if percentage >= 95:
            return "Perfect!"
        elif percentage >= 85:
            return "Almost Perfect!"
        elif percentage >= 70:
            return "Good Job!"
        elif percentage >= 50:
            return "Needs Improvement"
        else:
            return "Critical Issues"
    
    def _determine_check_status(self, score: float, max_score: float, issues: list) -> str:
        """Determine if check is pass, warning, or fail."""
        percentage = (score / max_score * 100) if max_score > 0 else 0
        
        if percentage >= 90:
            return "pass"
        elif percentage >= 60:
            return "warning"
        else:
            return "fail"
    
    def _get_check_label(self, category: str) -> str:
        """Get human-readable label for category."""
        labels = {
            "title_optimization": "Focus keyword in title",
            "meta_description": "Meta description length",
            "keyword_density": "Keyword density",
            "heading_structure": "Heading structure (H1, H2)",
            "content_length": "Content length",
            "keyword_in_intro": "Focus keyword in first 100 words",
            "internal_links": "Internal linking",
            "external_links": "External/authoritative links",
            "image_optimization": "Image alt text optimization",
            "slug_optimization": "URL slug optimization",
        }
        return labels.get(category, category)
    
    def calculate_overall_score(self, content: Dict) -> Dict:
        """
        Calculate overall on-page SEO score.
        Returns UI-friendly format with status, checks, and detailed breakdown.
        """
        results = {
            "score": 0,
            "overall_score": 0,
            "max_score": self.max_score,
            "passed": False,
            "status_message": "",
            "optimizations_needed": 0,
            "checks": [],
            "breakdown": {},
            "all_issues": [],
        }
        
        total_score = 0
        
        # Run all scoring functions
        scoring_functions = [
            ("title_optimization", self.score_title_optimization),
            ("meta_description", self.score_meta_description),
            ("keyword_density", self.score_keyword_density),
            ("heading_structure", self.score_heading_structure),
            ("content_length", self.score_content_length),
            ("keyword_in_intro", self.score_keyword_in_intro),
            ("internal_links", self.score_internal_links),
            ("external_links", self.score_external_links),
            ("image_optimization", self.score_image_optimization),
            ("slug_optimization", self.score_slug_optimization),
        ]
        
        for category, func in scoring_functions:
            score, issues = func(content)
            total_score += score
            
            # Store detailed breakdown
            results["breakdown"][category] = {
                "score": round(score, 2),
                "max_score": self.weights[category],
                "issues": issues
            }
            
            # Create check item for UI
            check_status = self._determine_check_status(score, self.weights[category], issues)
            check_message = issues[0] if issues else None
            
            check_item = {
                "category": category,
                "label": self._get_check_label(category),
                "status": check_status,
                "score": round(score, 2),
                "max_score": self.weights[category],
                "message": check_message
            }
            results["checks"].append(check_item)
            
            # Count optimizations needed
            if check_status in ["warning", "fail"]:
                results["optimizations_needed"] += 1
            
            results["all_issues"].extend(issues)
        
        # Calculate final scores
        results["overall_score"] = round(total_score, 2)
        results["score"] = round((total_score / self.max_score) * 100, 1)
        results["passed"] = results["score"] >= 70
        results["status_message"] = self._get_status_message(results["score"])
        
        return results
