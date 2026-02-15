import sqlite3
import json
import time
import google.generativeai as genai
import os
import sys

# Add project root to path to allow imports if needed, though we use direct sqlite/genai here
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env vars if .env exists
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))
except ImportError:
    pass

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("Error: GEMINI_API_KEY not found in environment.")
    print("Please run with: env GEMINI_API_KEY=... python bot/scripts/cleanup_rag.py")
    sys.exit(1)

genai.configure(api_key=API_KEY)

MODEL = "models/gemini-embedding-001"
# Path relative to where script is run, usually from root
DB_PATH = os.getenv("RAG_DATABASE", "bot/data/db/memory.db")

# If running from inside bot/scripts, adjust path? 
# Best to assume script is run from project root: python bot/scripts/cleanup_rag.py
if not os.path.exists(DB_PATH):
    # Try absolute path if dev environment
    possible_path = r"c:\Users\revis\OneDrive\Documents\Coding Projects\Project-Astral\db\memory.db"
    if os.path.exists(possible_path):
        DB_PATH = possible_path
    else:
        # Fallback to default container path if we are in container
        DB_PATH = "/app/data/db/memory.db"

print(f"Using database: {DB_PATH}")

def get_embedding(text):
    try:
        result = genai.embed_content(
            model=MODEL,
            content=text[:2000],
            task_type="retrieval_document"
        )
        return result["embedding"]
    except Exception as e:
        print(f"  Error embedding: {e}")
        return None

def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. DELETE DRAWING FACTS
    print("\n[1/5] Deleting drawing facts...")
    c.execute("SELECT COUNT(*) FROM knowledge WHERE knowledge_type = 'drawing'")
    count = c.fetchone()[0]
    print(f"Found {count} drawing facts.")
    
    if count > 0:
        c.execute("DELETE FROM knowledge WHERE knowledge_type = 'drawing'")
        conn.commit()
        print(f"Deleted {count} rows.")
    else:
        print("No drawing facts found.")

    # 2. RE-EMBED KNOWLEDGE
    print("\n[2/5] Re-embedding Knowledge table...")
    c.execute("SELECT id, content FROM knowledge")
    rows = c.fetchall()
    print(f"Processing {len(rows)} entries...")
    
    for kid, content in rows:
        emb = get_embedding(content)
        if emb:
            c.execute("UPDATE knowledge SET embedding = ? WHERE id = ?", (json.dumps(emb), kid))
            sys.stdout.write(".")
            sys.stdout.flush()
        time.sleep(0.1)
    conn.commit()
    print(" Done.")

    # 3. RE-EMBED CONVERSATIONS
    print("\n[3/5] Re-embedding Conversations table...")
    try:
        c.execute("SELECT id, user_message, gemgem_response, username FROM conversations")
        rows = c.fetchall()
        print(f"Processing {len(rows)} entries...")
        
        for cid, user_msg, resp, username in rows:
             # Re-create content summary for embedding
            content = f"Chat - {username or 'User'}: {user_msg} | Astra: {resp}"
            emb = get_embedding(content)
            if emb:
                c.execute("UPDATE conversations SET embedding = ? WHERE id = ?", (json.dumps(emb), cid))
                sys.stdout.write(".")
                sys.stdout.flush()
            time.sleep(0.1)
        conn.commit()
        print(" Done.")
    except Exception as e:
        print(f"Skipping conversations (maybe table doesn't exist): {e}")

    # 4. RE-EMBED SEARCH KNOWLEDGE
    print("\n[4/5] Re-embedding Search Knowledge table...")
    try:
        c.execute("SELECT id, query FROM search_knowledge")
        rows = c.fetchall()
        print(f"Processing {len(rows)} entries...")
        
        for sid, query in rows:
            content = f"Search about: {query}"
            emb = get_embedding(content)
            if emb:
                c.execute("UPDATE search_knowledge SET embedding = ? WHERE id = ?", (json.dumps(emb), sid))
                sys.stdout.write(".")
                sys.stdout.flush()
            time.sleep(0.1)
        conn.commit()
        print(" Done.")
    except Exception as e:
        print(f"Skipping search_knowledge: {e}")

    # 5. RE-EMBED IMAGE KNOWLEDGE
    print("\n[5/5] Re-embedding Image Knowledge table...")
    try:
        c.execute("SELECT id, gemini_description, user_context FROM image_knowledge")
        rows = c.fetchall()
        print(f"Processing {len(rows)} entries...")
        
        for iid, desc, ctx in rows:
            content = f"Image analysis: {desc}"
            if ctx:
                content = f"User asked about image: {ctx}\nImage shows: {desc}"
            
            emb = get_embedding(content)
            if emb:
                c.execute("UPDATE image_knowledge SET embedding = ? WHERE id = ?", (json.dumps(emb), iid))
                sys.stdout.write(".")
                sys.stdout.flush()
            time.sleep(0.1)
        conn.commit()
        print(" Done.")
    except Exception as e:
        print(f"Skipping image_knowledge: {e}")

    # Vacuum to reclaim space
    print("\nVacuuming database...")
    c.execute("VACUUM")
    conn.close()
    print("Database cleanup complete!")

if __name__ == "__main__":
    main()
