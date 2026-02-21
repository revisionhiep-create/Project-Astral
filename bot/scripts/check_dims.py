import sqlite3, json, collections

conn = sqlite3.connect('/app/data/db/memory.db')
c = conn.cursor()

# List tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"Tables: {tables}")

# Check knowledge table dimensions
dims = collections.Counter()
c.execute("SELECT id, embedding FROM knowledge WHERE embedding IS NOT NULL")
for row in c.fetchall():
    emb = json.loads(row[1])
    dims[len(emb)] += 1
print(f"\nknowledge table - embedding dims: {dict(dims)}")

# Check conversations
dims = collections.Counter()
c.execute("SELECT id, embedding FROM conversations WHERE embedding IS NOT NULL")
for row in c.fetchall():
    emb = json.loads(row[1])
    dims[len(emb)] += 1
print(f"conversations table - embedding dims: {dict(dims)}")

# Check image_knowledge
dims = collections.Counter()
c.execute("SELECT id, embedding FROM image_knowledge WHERE embedding IS NOT NULL")
for row in c.fetchall():
    emb = json.loads(row[1])
    dims[len(emb)] += 1
print(f"image_knowledge table - embedding dims: {dict(dims)}")

# Check search_knowledge
dims = collections.Counter()
c.execute("SELECT id, embedding FROM search_knowledge WHERE embedding IS NOT NULL")
for row in c.fetchall():
    emb = json.loads(row[1])
    dims[len(emb)] += 1
print(f"search_knowledge table - embedding dims: {dict(dims)}")

conn.close()
