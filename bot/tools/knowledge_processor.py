"""Knowledge Processor - Uses Gemini Flash to rephrase Reddit posts into clean facts."""
import asyncio
import json
import os
import aiohttp
from typing import Optional


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "scraped")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")

REPHRASE_PROMPT = """Convert this Reddit post into 1-3 factual knowledge statements. 
Remove opinions, usernames, and fluff. Keep only useful facts.
If there are no clear facts, respond with "SKIP".
Write in a neutral, encyclopedic tone. Keep it brief.

Post:
{content}

Facts:"""


async def rephrase_post(session: aiohttp.ClientSession, post: dict) -> Optional[dict]:
    """Rephrase a single post into knowledge facts using Gemini Flash."""
    try:
        payload = {
            "contents": [{"parts": [{"text": REPHRASE_PROMPT.format(content=post["content"])}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 256}
        }
        
        async with session.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as resp:
            if resp.status != 200:
                return None
            
            data = await resp.json()
            facts = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        if "SKIP" in facts.upper() or len(facts) < 20:
            return None
        
        return {
            "topic": post.get("subreddit", "unknown"),
            "original_title": post.get("title", ""),
            "facts": facts,
            "source_score": post.get("score", 0),
            "category": post.get("category", "general")
        }
        
    except Exception as e:
        print(f"  Error rephrasing: {e}")
        return None


async def process_scraped_file(input_file: str, limit: Optional[int] = None) -> list[dict]:
    """Process all posts from a scraped JSON file."""
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    all_knowledge = []
    
    async with aiohttp.ClientSession() as session:
        for category, posts in data.items():
            print(f"\n=== Processing {category.upper()} ({len(posts)} posts) ===")
            
            if limit:
                posts = posts[:limit]
            
            for i, post in enumerate(posts):
                post["category"] = category
                result = await rephrase_post(session, post)
                
                if result:
                    all_knowledge.append(result)
                
                if (i + 1) % 10 == 0:
                    print(f"  Processed {i + 1}/{len(posts)} ({len(all_knowledge)} facts)")
                
                # Small delay for API rate limiting
                await asyncio.sleep(0.2)
    
    # Save processed knowledge
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, "knowledge_facts.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_knowledge, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved {len(all_knowledge)} knowledge entries to {output_file}")
    return all_knowledge


async def main():
    """Find latest scraped file and process it."""
    import sys
    
    # Find most recent scraped file
    if not os.path.exists(DATA_DIR):
        print(f"No scraped data found in {DATA_DIR}")
        return
    
    files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".json")])
    if not files:
        print("No JSON files found to process")
        return
    
    latest = os.path.join(DATA_DIR, files[-1])
    print(f"Processing: {latest}")
    
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    
    await process_scraped_file(latest, limit=limit)


if __name__ == "__main__":
    asyncio.run(main())
