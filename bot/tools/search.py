"""SearXNG Search Client - Unlimited free web search."""
import os
import aiohttp
from typing import Optional


SEARXNG_HOST = os.getenv("SEARXNG_HOST", "http://localhost:8080")


async def search(query: str, num_results: int = 5) -> list[dict]:
    """
    Search the web using SearXNG.
    
    Args:
        query: Search query string
        num_results: Number of results to return (default 5)
    
    Returns:
        List of search results with title, url, and content
    """
    params = {
        "q": query,
        "format": "json",
        "language": "en-US"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SEARXNG_HOST}/search", params=params) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
                results = []
                
                for item in data.get("results", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", "")  # Full content for knowledge storage
                    })
                
                return results
    except Exception as e:
        print(f"[Search Error] {e}")
        return []


def format_search_results(results: list[dict]) -> str:
    """Format search results for injection into LLM context."""
    if not results:
        return ""
    
    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(f"- {r['title']}: {r['content']}")
    
    return "\n".join(formatted)


async def search_and_format(query: str, num_results: int = 5) -> str:
    """Search and return formatted results ready for context injection."""
    results = await search(query, num_results)
    return format_search_results(results)
