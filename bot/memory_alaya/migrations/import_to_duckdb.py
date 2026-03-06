"""Import unified facts into DuckDB with FTS indexing.

Reads unified_facts.json and imports all facts into the Memory Alaya DuckDB backend.
"""

import json
import sys
import os
import asyncio

# Add parent directory to path to import shared_memory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from shared_memory.memory_alaya import MemoryAlaya


async def import_facts():
    """Import unified facts into DuckDB."""
    print("=" * 60)
    print("IMPORTING FACTS TO DUCKDB")
    print("=" * 60)

    # Load unified facts
    facts_path = "c:/Users/revis/OneDrive/Documents/Coding Projects/shared_memory/migrations/unified_facts.json"
    try:
        with open(facts_path, 'r', encoding='utf-8') as f:
            facts = json.load(f)
        print(f"[OK] Loaded {len(facts)} unified facts")
    except Exception as e:
        print(f"[ERROR] Error loading facts: {e}")
        return

    # Initialize Memory Alaya with DuckDB backend
    db_path = "c:/Users/revis/OneDrive/Documents/Coding Projects/shared_memory/memory.duckdb"
    print(f"\n[SETUP] Initializing Memory Alaya (DuckDB backend)...")
    print(f"   Database: {db_path}")

    memory = MemoryAlaya(backend="duckdb", database_path=db_path)

    # Import facts
    print(f"\n[IMPORT] Importing {len(facts)} facts...")
    success_count = 0
    error_count = 0

    for i, fact in enumerate(facts):
        if i % 100 == 0:
            print(f"   Progress: {i}/{len(facts)} imported")

        try:
            # Extract fields
            fact_id = fact.get("id")
            content = fact.get("content")
            embedding = fact.get("embedding")
            knowledge_type = fact.get("knowledge_type", "user_fact")
            source = fact.get("source")
            metadata = fact.get("metadata", {})

            # Parse embedding if string
            if isinstance(embedding, str):
                embedding = json.loads(embedding)

            # Extract user_id, guild_id from metadata if available
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            user_id = metadata.get("user_id")
            guild_id = metadata.get("guild_id")
            channel_id = metadata.get("channel_id")

            # Skip facts without embeddings
            if not embedding:
                error_count += 1
                continue

            # Store in Memory Alaya
            result = await memory.backend.insert(
                id=fact_id,
                content=content,
                embedding=embedding,
                knowledge_type=knowledge_type,
                source=source,
                metadata=metadata,
                user_id=user_id,
                guild_id=guild_id,
                channel_id=channel_id
            )

            if not result:
                error_count += 1
                continue

            success_count += 1

        except Exception as e:
            error_count += 1
            if error_count <= 5:  # Only print first 5 errors
                print(f"   [WARN] Error importing fact {i}: {e}")

    print(f"\n[OK] Import complete:")
    print(f"   - Successfully imported: {success_count}")
    print(f"   - Errors: {error_count}")

    # Get stats
    stats = await memory.get_stats()
    print(f"\n[STATS] Database Statistics:")
    print(f"   Backend: {stats['backend']}")
    print(f"   Database: {stats['database_path']}")
    print(f"   Total entries: {stats['total_entries']}")
    print(f"   By type:")
    for fact_type, count in stats['by_type'].items():
        print(f"      - {fact_type}: {count}")

    # Close connection
    memory.close()

    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(import_facts())
