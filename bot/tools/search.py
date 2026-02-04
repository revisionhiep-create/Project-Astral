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
                
                for item in data.get("results", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", "")
                    })
                
                return results
    except Exception as e:
        print(f"[Search Error] {e}")
        return []


def format_search_results(results: list[dict]) -> str:
    """Format search results for injection into LLM context with sources."""
    if not results:
        return ""
    
    formatted = []
    for i, r in enumerate(results, 1):
        # Include URL so model can reference sources
        formatted.append(f"{i}. [{r['title']}]({r['url']})\n   {r['content']}")
    
    return "\n\n".join(formatted)


async def search_and_format(query: str, num_results: int = 5, time_range: str = None) -> str:
    """Search and return formatted results ready for context injection."""
    results = await search(query, num_results, time_range)
    return format_search_results(results)
