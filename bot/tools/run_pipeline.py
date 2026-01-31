"""All-in-one knowledge pipeline runner.

Runs: Scrape -> Process -> Import in one go.
"""
import asyncio
import os
import sys

# Add bot to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.scraper import scrape_all
from tools.knowledge_processor import process_scraped_file
from tools.import_knowledge import import_knowledge

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


async def run_full_pipeline(dry_run: bool = False, limit: int = None):
    """Run the complete knowledge pipeline."""
    
    print("=" * 60)
    print("ASTRA KNOWLEDGE PIPELINE")
    print("=" * 60)
    
    # Step 1: Scrape Reddit
    print("\n[1/3] SCRAPING REDDIT...")
    print("-" * 40)
    scraped_data = await scrape_all(dry_run=dry_run)
    
    if dry_run:
        print("\n[DRY RUN] Skipping processing and import")
        return
    
    # Find the latest scraped file
    scraped_dir = os.path.join(DATA_DIR, "scraped")
    files = sorted([f for f in os.listdir(scraped_dir) if f.endswith(".json")])
    if not files:
        print("ERROR: No scraped files found!")
        return
    
    latest_scraped = os.path.join(scraped_dir, files[-1])
    
    # Step 2: Process with Gemini
    print("\n[2/3] PROCESSING WITH GEMINI FLASH...")
    print("-" * 40)
    knowledge = await process_scraped_file(latest_scraped, limit=limit)
    
    if not knowledge:
        print("ERROR: No knowledge generated!")
        return
    
    # Step 3: Import to RAG
    print("\n[3/3] IMPORTING TO RAG DATABASE...")
    print("-" * 40)
    processed_file = os.path.join(DATA_DIR, "processed", "knowledge_facts.json")
    await import_knowledge(processed_file)
    
    print("\n" + "=" * 60)
    print("✓ PIPELINE COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    limit = None
    
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])
    
    asyncio.run(run_full_pipeline(dry_run=dry_run, limit=limit))
