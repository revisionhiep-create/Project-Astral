"""Check recent facts and all knowledge entries by date."""
import sqlite3

conn = sqlite3.connect('/app/data/db/memory.db')
c = conn.cursor()

print("=== MOST RECENT KNOWLEDGE (all types) ===")
c.execute('SELECT created_at, knowledge_type, content FROM knowledge ORDER BY created_at DESC LIMIT 15')
for r in c.fetchall():
    print(f'[{r[0]}] type={r[1]} | {r[2][:120]}')

print("\n=== USER FACTS ONLY ===")
c.execute("SELECT created_at, content FROM knowledge WHERE knowledge_type = 'user_fact' ORDER BY created_at DESC LIMIT 10")
for r in c.fetchall():
    print(f'[{r[0]}] {r[1][:120]}')

print("\n=== KNOWLEDGE COUNTS BY TYPE ===")
c.execute("SELECT knowledge_type, COUNT(*) FROM knowledge GROUP BY knowledge_type")
for r in c.fetchall():
    print(f'  {r[0]}: {r[1]}')

conn.close()
