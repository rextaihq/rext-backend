"""
On-Page SEO Scoring Node

This module provides the LangGraph node function for calculating on-page SEO scores.
"""

import logging
from typing import Dict
from src.flow.states.wrext import WREXT
from src.services.seo_scoring_service import OnPageSEOScorer

logger = logging.getLogger(__name__)


def calculate_on_page_seo(state: WREXT) -> Dict:
    """
    Main function to calculate on-page SEO score for generated content.
    
    Args:
        state: WREXT state containing generated content
    
    Returns:
        Updated state with SEO score in the review section
    """
    logger.info("Starting on-page SEO scoring")
    
    content_state = state.get("content", {})
    final_content = content_state.get("final_content", {})
    
    if not final_content:
        logger.warning("No final content found for SEO scoring")
        return {"content": content_state}
    
    try:
        scorer = OnPageSEOScorer()
        seo_results = scorer.calculate_overall_score(final_content)
        
        logger.info(f"On-page SEO score: {seo_results['score']}% ({seo_results['overall_score']}/{seo_results['max_score']})")
        logger.info(f"Status: {seo_results['status_message']}")
        logger.info(f"Optimizations needed: {seo_results['optimizations_needed']}")

        
        # Log top issues for debugging
        if seo_results['all_issues']:
            logger.warning(f"SEO Issues: {seo_results['all_issues'][:5]}")  # Log first 5 issues
        
        return {
            "content": {
                **content_state,
                "review": {
                    "on_page_metrics": seo_results
                }
            }
        }
    
    except Exception as e:
        logger.exception(f"Error calculating on-page SEO score: {str(e)}")
        return {"content": content_state}
