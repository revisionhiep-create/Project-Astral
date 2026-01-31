"""Reddit Knowledge Scraper - Uses public JSON endpoints (no API key needed)."""
import asyncio
import aiohttp
import json
import re
import os
from datetime import datetime
from typing import Optional


# Configuration
SUBREDDITS = {
    "vtuber": ["VirtualYoutubers", "Hololive", "Nijisanji"],
    "tech": ["technology", "LocalLLaMA", "programming"],
    "gaming": ["Games", "pcgaming", "indiegaming"]
}

POSTS_PER_SUBREDDIT = 350  # ~1000 per category, 3000 total
MIN_UPVOTES = 50
MIN_LENGTH = 100
MAX_LENGTH = 2000
REQUEST_DELAY = 3  # seconds between requests (respectful)

# Output path
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "scraped")


def clean_text(text: str) -> str:
    """Remove Reddit-specific formatting and usernames."""
    if not text:
        return ""
    # Remove usernames
    text = re.sub(r'/?u/\w+', '', text)
    # Remove subreddit mentions
    text = re.sub(r'/?r/\w+', '', text)
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
    text = re.sub(r'~~([^~]+)~~', r'\1', text)  # Strikethrough
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def fetch_subreddit_posts(
    session: aiohttp.ClientSession,
    subreddit: str,
    limit: int = 100,
    time_filter: str = "year"
) -> list[dict]:
    """Fetch top posts from a subreddit using public JSON endpoint."""
    posts = []
    after = None
    
    while len(posts) < limit:
        url = f"https://www.reddit.com/r/{subreddit}/top.json"
        params = {
            "t": time_filter,
            "limit": min(100, limit - len(posts)),
            "raw_json": 1
        }
        if after:
            params["after"] = after
        
        headers = {
            "User-Agent": "AstraKnowledgeScraper/1.0 (educational project)"
        }
        
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 429:
                    print(f"  Rate limited, waiting 60s...")
                    await asyncio.sleep(60)
                    continue
                    
                if resp.status != 200:
                    print(f"  Error {resp.status} for r/{subreddit}")
                    break
                
                data = await resp.json()
                children = data.get("data", {}).get("children", [])
                
                if not children:
                    break
                
                for child in children:
                    post = child.get("data", {})
                    
                    # Quality filters
                    score = post.get("score", 0)
                    selftext = post.get("selftext", "")
                    title = post.get("title", "")
                    
                    # Skip low quality
                    if score < MIN_UPVOTES:
                        continue
                    if post.get("removed_by_category"):
                        continue
                    if selftext in ["[removed]", "[deleted]", ""]:
                        # Use title for link posts
                        content = title
                    else:
                        content = f"{title}\n\n{selftext}"
                    
                    content = clean_text(content)
                    
                    if len(content) < MIN_LENGTH or len(content) > MAX_LENGTH:
                        continue
                    
                    posts.append({
                        "subreddit": subreddit,
                        "title": clean_text(title),
                        "content": content,
                        "score": score,
                        "created_utc": post.get("created_utc"),
                        "num_comments": post.get("num_comments", 0),
                        "id": post.get("id")
                    })
                
                # Pagination
                after = data.get("data", {}).get("after")
                if not after:
                    break
                
                print(f"  r/{subreddit}: {len(posts)} posts collected...")
                await asyncio.sleep(REQUEST_DELAY)
                
        except Exception as e:
            print(f"  Error fetching r/{subreddit}: {e}")
            break
    
    return posts[:limit]


async def scrape_all(dry_run: bool = False) -> dict:
    """Scrape all configured subreddits."""
    all_posts = {"vtuber": [], "tech": [], "gaming": []}
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    async with aiohttp.ClientSession() as session:
        for category, subreddits in SUBREDDITS.items():
            print(f"\n=== Scraping {category.upper()} ===")
            category_posts = []
            
            posts_per_sub = POSTS_PER_SUBREDDIT // len(subreddits) + 50  # Buffer
            
            for subreddit in subreddits:
                print(f"Fetching r/{subreddit}...")
                
                if dry_run:
                    print(f"  [DRY RUN] Would fetch {posts_per_sub} posts")
                    continue
                
                posts = await fetch_subreddit_posts(
                    session, 
                    subreddit, 
                    limit=posts_per_sub
                )
                category_posts.extend(posts)
                print(f"  Got {len(posts)} quality posts from r/{subreddit}")
                
                await asyncio.sleep(REQUEST_DELAY)
            
            all_posts[category] = category_posts[:POSTS_PER_SUBREDDIT]
    
    # Save to JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"reddit_scrape_{timestamp}.json")
    
    if not dry_run:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_posts, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Saved to {output_file}")
    
    # Summary
    total = sum(len(posts) for posts in all_posts.values())
    print(f"\n=== SUMMARY ===")
    for cat, posts in all_posts.items():
        print(f"  {cat}: {len(posts)} posts")
    print(f"  TOTAL: {total} posts")
    
    return all_posts


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    asyncio.run(scrape_all(dry_run=dry_run))
