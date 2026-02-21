"""Re-embed all existing knowledge entries with the new gemini-embedding-001 model."""
import sqlite3
import json
import time
import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "models/gemini-embedding-001"
DB_PATH = os.getenv("RAG_DATABASE", "/app/data/db/memory.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Get all knowledge entries
c.execute("SELECT id, content FROM knowledge")
rows = c.fetchall()
print(f"Found {len(rows)} knowledge entries to re-embed")

success = 0
failed = 0

for kid, content in rows:
    try:
        result = genai.embed_content(
            model=MODEL,
            content=content[:2000],  # Truncate very long content
            task_type="retrieval_document"
        )
        embedding = result["embedding"]
        c.execute("UPDATE knowledge SET embedding = ? WHERE id = ?", 
                  (json.dumps(embedding), kid))
        success += 1
        if success % 10 == 0:
            print(f"  Re-embedded {success}/{len(rows)}...")
            conn.commit()
        # Rate limit: free tier is ~1500 RPM
        time.sleep(0.1)
    except Exception as e:
        print(f"  Failed to embed id={kid}: {e}")
        failed += 1
        time.sleep(1)

conn.commit()
conn.close()
print(f"\nDone! Success: {success}, Failed: {failed}")
