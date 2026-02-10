"""Extract all facts from Astral's RAG database."""
import sqlite3
import json
import os

for db_path in ['/app/data/db/memory.db', '/app/data/memory.db']:
    print(f'=== DB: {db_path} ===')
    if not os.path.exists(db_path):
        print('  Not found')
        continue
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        print(f'Tables: {tables}')
        
        if 'knowledge' in tables:
            c.execute('SELECT content, knowledge_type, source, created_at FROM knowledge ORDER BY created_at DESC')
            rows = c.fetchall()
            print(f'Knowledge entries: {len(rows)}')
            for row in rows:
                content, ktype, source, created = row
                print('---FACT---')
                print(f'TYPE: {ktype}')
                print(f'SOURCE: {source}')
                print(f'DATE: {created}')
                print(f'CONTENT: {content[:500]}')
        conn.close()
    except Exception as e:
        print(f'Error: {e}')
