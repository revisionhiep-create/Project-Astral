"""Import processed knowledge into Astra's RAG database."""
import asyncio
import json
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.rag import store_knowledge


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed")


async def import_knowledge(input_file: str = None, batch_size: int = 50):
    """Import processed knowledge facts into RAG."""
    
    if not input_file:
        input_file = os.path.join(DATA_DIR, "knowledge_facts.json")
    
    if not os.path.exists(input_file):
        print(f"File not found: {input_file}")
        return
    
    with open(input_file, "r", encoding="utf-8") as f:
        knowledge = json.load(f)
    
    print(f"Importing {len(knowledge)} knowledge entries...")
    
    imported = 0
    failed = 0
    
    for i, item in enumerate(knowledge):
        try:
            # Store in RAG with category as knowledge_type
            await store_knowledge(
                content=item["facts"],
                knowledge_type=f"reddit_{item.get('category', 'general')}",
                source=f"reddit/r/{item.get('topic', 'unknown')}",
                metadata={
                    "original_title": item.get("original_title", ""),
                    "source_score": item.get("source_score", 0)
                }
            )
            imported += 1
            
        except Exception as e:
            print(f"  Error importing: {e}")
            failed += 1
        
        if (i + 1) % batch_size == 0:
            print(f"  Progress: {i + 1}/{len(knowledge)} ({imported} imported, {failed} failed)")
            await asyncio.sleep(0.1)  # Brief pause
    
    print(f"\n✓ Import complete: {imported} entries imported, {failed} failed")


if __name__ == "__main__":
    # Allow passing a specific file
    input_file = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(import_knowledge(input_file))
