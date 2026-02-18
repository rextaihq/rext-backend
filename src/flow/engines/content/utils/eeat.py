import re
import logging
from typing import Dict, Any
from src.flow.model.llm_manager import load_model
DEFAULT_MAX_TOKENS = 4096
from src.flow.model.structure.eeat import EEATTrustScore

logger = logging.getLogger(__name__)

def extract_regex_signals(html_content: str) -> Dict[str, Any]:
    """
    Extract low-level trust signals using regular expressions.
    """
    signals = {}
    
    # 1. Technical Trust (HTTPS)
    https_links = len(re.findall(r'href="https://', html_content))
    http_links = len(re.findall(r'href="http://', html_content))
    signals["https_ratio"] = https_links / (https_links + http_links) if (https_links + http_links) > 0 else 1.0
    
    # 2. Citations & References (Outbound Links)
    # Exclude common social media if needed, but here we count all external
    external_links = re.findall(r'href="(https?://[^"]+)"', html_content)
    signals["total_external_links"] = len(external_links)
    
    # Check for authoritative domains (simple list)
    authoritative_domains = [".gov", ".edu", ".org", "wikipedia.org", "reuters.com", "bloomberg.com"]
    auth_links_count = sum(1 for link in external_links if any(domain in link for domain in authoritative_domains))
    signals["authoritative_links_count"] = auth_links_count
    
    # 3. Transparency Signals
    transparency_keywords = ["disclosure", "privacy policy", "contact us", "affiliate", "editorial guidelines"]
    signals["transparency_markers_found"] = [kw for kw in transparency_keywords if re.search(rf"\b{kw}\b", html_content, re.IGNORECASE)]
    
    # 4. Author Presence
    author_patterns = [r"about the author", r"written by", r"author:", r'class="author-name"', r'rel="author"']
    signals["author_info_present"] = any(re.search(pattern, html_content, re.IGNORECASE) for pattern in author_patterns)
    
    # 5. Spam Signals (Basic)
    # Detect repetitive word usage (Keyword Stuffing proxy) or very high link density
    word_count = len(re.findall(r'\w+', html_content))
    signals["link_density"] = len(re.findall(r'<a\b', html_content)) / word_count if word_count > 0 else 0
    
    return signals

async def calculate_eeat_trust_score(html_content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Calculate E-E-A-T score using a hybrid approach of Regex and LLM.
    """
    logger.info("Starting hybrid E-E-A-T evaluation...")
    
    # Phase 1: Regex Extraction
    regex_signals = extract_regex_signals(html_content)
    
    # Phase 2: LLM Qualitative Analysis
    llm = load_model(max_tokens=DEFAULT_MAX_TOKENS).with_structured_output(EEATTrustScore)
    
    # Build prompt
    prompt = f"""
    You are a senior SEO and E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) auditor.
    Evaluate the following content for trust signals based on Google's Quality Rater Guidelines.
    
    Content to Evaluate:
    {html_content[:15000]}  # Truncate if too long
    
    Automated System Signals (Regex-based):
    - HTTPS Ratio: {regex_signals['https_ratio']}
    - Total External Links: {regex_signals['total_external_links']}
    - Authoritative Links found: {regex_signals['authoritative_links_count']}
    - Transparency markers: {', '.join(regex_signals['transparency_markers_found'])}
    - Author info detected: {regex_signals['author_info_present']}
    - Link density: {regex_signals['link_density']:.4f}
    
    Context Metadata:
    {metadata or "No extra metadata available"}
    
    Instructions:
    1. Assess 'Expertise' based on the depth and accuracy of language.
    2. Assess 'Author Credibility' based on how the author is presented.
    3. Assess 'Technical Trust' using the HTTPS ratio and potential security signals.
    4. Assess 'Spam Signals' (100 = No spam, 0 = High spam) based on keyword stuffing and link quality.
    5. Return a complete TrustScore profile.
    """
    
    try:
        result = await llm.ainvoke(prompt)
        trust_data = result.model_dump()
        
        # Log results
        logger.info(f"E-E-A-T Score calculated: {trust_data['score']}")
        return trust_data
        
    except Exception as e:
        logger.exception(f"LLM E-E-A-T evaluation failed: {e}")
        # Fallback to basic regex-based scoring if LLM fails
        return {
            "score": regex_signals['https_ratio'] * 50 + (min(regex_signals['total_external_links'], 5) * 10),
            "expertise": 50,
            "author_credibility": 50 if regex_signals['author_info_present'] else 20,
            "technical_trust": regex_signals['https_ratio'] * 100,
            # ... other fallbacks
        }
