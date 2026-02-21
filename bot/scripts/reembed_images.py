"""Re-embed image_knowledge entries that have wrong-dimension embeddings (768 -> 3072)."""
import sqlite3
import json
import asyncio
import os
import sys

# Add bot dir to path so we can import embeddings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))
from memory.embeddings import get_embedding

DB_PATH = os.getenv("RAG_DATABASE", "/app/data/db/memory.db")
TARGET_DIM = 3072  # gemini-embedding-001 output dimension


async def reembed_images():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT id, gemini_description, user_context, embedding FROM image_knowledge WHERE embedding IS NOT NULL")
    rows = c.fetchall()
    
    fixed = 0
    skipped = 0
    failed = 0
    
    for row in rows:
        entry_id, description, user_context, emb_json = row
        emb = json.loads(emb_json)
        
        if len(emb) == TARGET_DIM:
            skipped += 1
            print(f"  ✓ {entry_id[:30]} already {TARGET_DIM}-dim, skipping")
            continue
        
        print(f"  ⚠ {entry_id[:30]} has {len(emb)}-dim, re-embedding...")
        
        # Rebuild the content string the same way store_image_knowledge does
        content = f"Image analysis: {description}"
        if user_context:
            content = f"User asked about image: {user_context}\nImage shows: {description}"
        
        new_emb = await get_embedding(content)
        if not new_emb:
            print(f"  ✗ Failed to get new embedding for {entry_id[:30]}")
            failed += 1
            continue
        
        c.execute("UPDATE image_knowledge SET embedding = ? WHERE id = ?", (json.dumps(new_emb), entry_id))
        fixed += 1
        print(f"  ✓ Fixed {entry_id[:30]} -> {len(new_emb)}-dim")
    
    conn.commit()
    conn.close()
    print(f"\nDone: {fixed} fixed, {skipped} already OK, {failed} failed (total: {len(rows)})")


if __name__ == "__main__":
    asyncio.run(reembed_images())
