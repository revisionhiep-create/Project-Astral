#!/usr/bin/env python3
"""
Extract user_facts from Project Astral's SQLite database and save to JSON.

This script reads from Project Astral's memory.db and extracts all knowledge
entries where knowledge_type = 'user_fact', then saves them to a JSON file.
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path


def extract_astral_facts():
    """Extract user_facts from Project Astral's database and save to JSON."""

    # Define paths
    db_path = r"c:\Users\revis\OneDrive\Documents\Coding Projects\Project-Astral\db\memory.db"
    output_path = r"c:\Users\revis\OneDrive\Documents\Coding Projects\shared_memory\migrations\astral_facts.json"

    # Verify database exists
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at: {db_path}")
        return

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Connect to database
        print(f"Connecting to database: {db_path}")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()

        # Query for user_facts
        query = """
            SELECT
                id,
                content,
                embedding,
                knowledge_type,
                source,
                metadata,
                created_at
            FROM knowledge
            WHERE knowledge_type = 'user_fact'
            ORDER BY created_at DESC
        """

        print("Executing query to extract user_facts...")
        cursor.execute(query)
        rows = cursor.fetchall()

        # Process rows
        facts = []
        for row in rows:
            fact = {
                'id': row['id'],
                'content': row['content'],
                'embedding': json.loads(row['embedding']) if row['embedding'] else None,
                'knowledge_type': row['knowledge_type'],
                'source': row['source'],
                'metadata': json.loads(row['metadata']) if row['metadata'] else None,
                'created_at': row['created_at']
            }
            facts.append(fact)

        # Close database connection
        conn.close()

        # Save to JSON file
        print(f"Writing {len(facts)} facts to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(facts, f, indent=2, ensure_ascii=False)

        # Print summary
        print("\n" + "="*60)
        print("EXTRACTION COMPLETE")
        print("="*60)
        print(f"Total user_facts extracted: {len(facts)}")
        print(f"Output file: {output_path}")
        print(f"Output file size: {os.path.getsize(output_path):,} bytes")

        # Show sample of first fact if any exist
        if facts:
            print("\nSample (first fact):")
            print(f"  ID: {facts[0]['id']}")
            print(f"  Content: {facts[0]['content'][:100]}..." if len(facts[0]['content']) > 100 else f"  Content: {facts[0]['content']}")
            print(f"  Source: {facts[0]['source']}")
            print(f"  Created: {facts[0]['created_at']}")

        print("="*60)

        return len(facts)

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


if __name__ == "__main__":
    extract_astral_facts()
