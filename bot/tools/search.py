"""SearXNG Search Client - Unlimited free web search."""
import os
import aiohttp
from typing import Optional


SEARXNG_HOST = os.getenv("SEARXNG_HOST", "http://localhost:8080")

# Browser-like User-Agent to avoid being blocked by search engines
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


async def search(query: str, num_results: int = 5, time_range: str = None) -> list[dict]:
    """
    Search the web using SearXNG.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default 5)
        time_range: Optional time filter - 'day', 'week', 'month', 'year', or None (all time)
    
    Returns:
        List of search results with title, url, and content
    """
    params = {
        "q": query,
        "format": "json",
        "language": "en-US",
    }
    # Only add time_range if specified (None = all time for historical/evergreen queries)
    if time_range:
        params["time_range"] = time_range
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SEARXNG_HOST}/search", params=params, headers=HEADERS) as resp:
                if resp.status != 200:
                    print(f"[Search] Error {resp.status}")
                    return []
                
                data = await resp.json()
                results = []
                
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", "")
                    })
                
                # Rerank by content quality (longer snippets = more useful info)
                results = sorted(results, key=lambda x: len(x.get('content', '')), reverse=True)
                
                return results[:num_results]
    except Exception as e:
        print(f"[Search Error] {e}")
        return []


def format_search_results(results: list[dict]) -> str:
    """Format search results with numbered citations for LLM grounding."""
    if not results:
        return ""
    
    import re
    
    def _sanitize(text: str) -> str:
        """Strip markdown formatting that confuses the model."""
        if not text:
            return ""
        # Remove **bold** and *italic* markdown
        text = re.sub(r'\*\*([^*]*)\*\*', r'\1', text)  # **text** -> text
        text = re.sub(r'\*([^*]*)\*', r'\1', text)      # *text* -> text
        # Remove empty ** that sometimes appear
        text = re.sub(r'\*\*', '', text)
        return text.strip()
    
    # Header instructs model to use citations
    formatted = ["SEARCH RESULTS - Cite with [1], [2] etc when using these facts:\n"]
    for i, r in enumerate(results, 1):
        title = _sanitize(r['title'])
        content = _sanitize(r['content'])
        # Numbered citation format
        formatted.append(f"[{i}] {title}\n    URL: {r['url']}\n    {content}")
    
    return "\n\n".join(formatted)


async def search_and_format(query: str, num_results: int = 5, time_range: str = None) -> str:
    """Search and return formatted results ready for context injection."""
    results = await search(query, num_results, time_range)
    return format_search_results(results)
