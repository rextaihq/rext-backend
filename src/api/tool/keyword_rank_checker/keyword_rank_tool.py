import httpx
from bs4 import BeautifulSoup
from typing import Dict, List
import urllib.parse
import re

async def fetch_serp_results(keyword: str) -> List[str]:
    """
    Fetch SERP results from DuckDuckGo HTML (No API key required).
    """
    url = "https://html.duckduckgo.com/html/"
    params = {'q': keyword}
    # Headers to mimic a real browser to avoid blocking
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://html.duckduckgo.com/'
    }

    async with httpx.AsyncClient() as client:
        # DBG HTML search usually works with POST or GET. Using POST to mimic form submission.
        resp = await client.post(url, data=params, headers=headers)
        if resp.status_code != 200:
            # Fallback to GET if POST fails
            resp = await client.get(url, params=params, headers=headers)

    soup = BeautifulSoup(resp.content, 'html.parser')
    results = []
    
    # Extract links from DuckDuckGo HTML results
    # The class 'result__a' is typically used for the main link in HTML version
    for link in soup.find_all('a', class_='result__a'):
        href = link.get('href')
        if href:
            # DuckDuckGo sometimes wraps URLs in its own redirect format, 
            # but in the HTML version, it's often direct or easy to parse.
            # We also decdoe it just in case.
            if href.startswith('/l/?kh=-1&uddg='):
                href = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
            results.append(href)
            
    return results

async def keyword_rank_checker(
    keyword: str,
    website_url: str
) -> Dict:
    """
    Checks the rank of a website for a given keyword by scraping search results.
    """
    
    # 1. Clean the target website URL to match domains easily (e.g. "example.com")
    parsed_target = urllib.parse.urlparse(website_url)
    target_domain = parsed_target.netloc.replace('www.', '')
    if not target_domain: # Handle case where user types "example.com" without http
        target_domain = website_url.replace('www.', '').split('/')[0]

    # 2. Fetch Results
    serp_urls = await fetch_serp_results(keyword)
    
    # 3. Find Rank
    rank_position = None
    found_url = None

    for index, url in enumerate(serp_urls, start=1):
        try:
            domain = urllib.parse.urlparse(url).netloc.replace('www.', '')
            # Check if target domain is inside the result domain
            if target_domain in domain:
                rank_position = index
                found_url = url
                break
        except Exception:
            continue

    if rank_position:
        status = f"Found at position {rank_position}"
    else:
        status = "Not found in top results"

    return {
        "keyword": keyword,
        "website_url": website_url,
        "rank_position": rank_position,
        "found_url": found_url,
        "status": status
    }