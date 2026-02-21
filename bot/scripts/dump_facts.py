import sqlite3
import os

db_path = r'c:\Users\revis\OneDrive\Documents\Coding Projects\Project-Astral\db\memory.db'
output_path = r'c:\Users\revis\OneDrive\Documents\Coding Projects\stored_facts.md'

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

markdown_content = "# Stored Facts & Knowledge Log\n\n"
markdown_content += "This log shows the 50 most recent entries in the knowledge database.\n\n"

# Recent User Facts
markdown_content += "## 📝 Recent User Facts\n\n"
c.execute("SELECT created_at, content FROM knowledge WHERE knowledge_type = 'user_fact' ORDER BY created_at DESC LIMIT 20")
rows = c.fetchall()
if rows:
    markdown_content += "| Timestamp | Fact Content |\n|---|---|\n"
    for r in rows:
        # Clean newlines in content for table/list format
        content = r[1].replace('\n', ' ')
        markdown_content += f"| {r[0]} | {content} |\n"
else:
    markdown_content += "*No user facts found.*\n"

markdown_content += "\n## 📚 All Recent Knowledge Entries\n\n"
c.execute("SELECT created_at, knowledge_type, content FROM knowledge ORDER BY created_at DESC LIMIT 50")
rows = c.fetchall()

if rows:
    markdown_content += "| Timestamp | Type | Content |\n|---|---|---|\n"
    for r in rows:
        content = r[2].replace('\n', ' ')
        markdown_content += f"| {r[0]} | {r[1]} | {content[:150]}... |\n" # Truncate long content
else:
    markdown_content += "*No entries found.*\n"

conn.close()

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(markdown_content)

print(f"Successfully wrote facts to {output_path}")
