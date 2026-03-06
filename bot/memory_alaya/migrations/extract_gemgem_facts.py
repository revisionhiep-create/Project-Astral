#!/usr/bin/env python3
"""
Extract facts from GemGem's ChromaDB database and save to JSON file.

This script reads from GemGem's ChromaDB SQLite database directly,
filters for entries where entry_type='fact', and saves them to a JSON file
in a format compatible with Astral facts.

Note: Uses direct SQLite access to avoid Python 3.14 compatibility issues with ChromaDB.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Any, Optional
import pickle


# Configuration
CHROMADB_PATH = r"c:\Users\revis\OneDrive\Documents\Coding Projects\GemGem-Docker-Live\data\database"
CHROMA_SQLITE = os.path.join(CHROMADB_PATH, "chroma.sqlite3")
COLLECTION_NAME = "google_search_cache"
OUTPUT_FILE = r"c:\Users\revis\OneDrive\Documents\Coding Projects\shared_memory\migrations\gemgem_facts.json"


def connect_to_chromadb_sqlite(db_path: str) -> sqlite3.Connection:
    """
    Connect to ChromaDB's SQLite database.

    Args:
        db_path: Path to the chroma.sqlite3 file

    Returns:
        SQLite connection object
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"ChromaDB SQLite file not found: {db_path}")

    print(f"Connecting to SQLite database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    return conn


def get_collection_id(conn: sqlite3.Connection, collection_name: str) -> Optional[str]:
    """
    Get the collection UUID from the database.

    Args:
        conn: SQLite connection
        collection_name: Name of the collection

    Returns:
        Collection UUID or None if not found
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name FROM collections WHERE name = ?",
        (collection_name,)
    )
    result = cursor.fetchone()

    if result:
        return result['id']

    # List available collections if not found
    print(f"\nCollection '{collection_name}' not found.")
    print("Available collections:")
    cursor.execute("SELECT name FROM collections")
    for row in cursor.fetchall():
        print(f"  - {row['name']}")

    return None


def extract_facts_from_sqlite(conn: sqlite3.Connection, collection_id: str) -> Dict[str, Any]:
    """
    Extract all facts from the ChromaDB SQLite database.

    Args:
        conn: SQLite connection
        collection_id: UUID of the collection

    Returns:
        Dict containing the extracted facts data
    """
    cursor = conn.cursor()

    # Get the metadata segment ID for this collection
    print("Finding metadata segment...")
    cursor.execute("""
        SELECT id FROM segments
        WHERE collection = ? AND type = 'urn:chroma:segment/metadata/sqlite'
    """, (collection_id,))

    segment_result = cursor.fetchone()
    if not segment_result:
        raise ValueError(f"No metadata segment found for collection {collection_id}")

    metadata_segment_id = segment_result['id']
    print(f"Metadata segment ID: {metadata_segment_id}")

    # Get all embeddings for the collection's metadata segment
    print("Querying embeddings table...")
    cursor.execute("""
        SELECT e.id, e.embedding_id, e.segment_id
        FROM embeddings e
        WHERE e.segment_id = ?
        ORDER BY e.id
    """, (metadata_segment_id,))

    all_embeddings = cursor.fetchall()
    total_entries = len(all_embeddings)
    print(f"Total entries in collection: {total_entries}")

    # Filter for facts only
    facts_data = {
        'ids': [],
        'documents': [],
        'embeddings': [],
        'metadatas': []
    }

    entry_types = {}

    for emb_row in all_embeddings:
        embedding_record_id = emb_row['id']
        embedding_id = emb_row['embedding_id']

        # Get metadata for this embedding
        cursor.execute("""
            SELECT key, string_value, int_value, float_value, bool_value
            FROM embedding_metadata
            WHERE id = ?
        """, (embedding_record_id,))

        metadata_rows = cursor.fetchall()

        # Build metadata dictionary
        metadata = {}
        document = None

        for meta_row in metadata_rows:
            key = meta_row['key']

            # Determine which value column to use
            if meta_row['string_value'] is not None:
                value = meta_row['string_value']
            elif meta_row['int_value'] is not None:
                value = meta_row['int_value']
            elif meta_row['float_value'] is not None:
                value = meta_row['float_value']
            elif meta_row['bool_value'] is not None:
                value = bool(meta_row['bool_value'])
            else:
                value = None

            # Special handling for document field
            if key == 'chroma:document':
                document = value
            else:
                metadata[key] = value

        # Track entry types
        entry_type = metadata.get('entry_type', 'None')
        entry_types[entry_type] = entry_types.get(entry_type, 0) + 1

        # Check if this is a fact
        if metadata.get('entry_type') == 'fact':
            facts_data['ids'].append(embedding_id)
            facts_data['documents'].append(document)
            # Note: Embeddings are stored in binary format in separate files
            # For now, we'll set them to None - they can be loaded separately if needed
            facts_data['embeddings'].append(None)
            facts_data['metadatas'].append(metadata)

    fact_count = len(facts_data['ids'])
    print(f"Facts extracted: {fact_count}")

    if fact_count == 0:
        print("\nWarning: No facts found in the collection!")
        print("Entry types found:")
        for et, count in sorted(entry_types.items()):
            print(f"  - {et}: {count}")
    else:
        print(f"\nEntry type distribution:")
        for et, count in sorted(entry_types.items()):
            print(f"  - {et}: {count}")

    return facts_data


def save_to_json(data: Dict[str, Any], output_path: str):
    """
    Save the extracted data to a JSON file.

    Args:
        data: The data to save
        output_path: Path to the output JSON file
    """
    print(f"\nSaving to: {output_path}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Save to JSON file with pretty formatting
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    file_size = os.path.getsize(output_path)
    print(f"Successfully saved {data['total_facts']} facts to JSON")
    print(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")


def print_sample_facts(data: Dict[str, Any], num_samples: int = 3):
    """
    Print sample facts for verification.

    Args:
        data: The extracted data
        num_samples: Number of sample facts to print
    """
    if data['total_facts'] == 0:
        return

    print(f"\n{'='*80}")
    print(f"Sample Facts (showing up to {num_samples}):")
    print('='*80)

    facts = data['facts']
    samples = min(num_samples, len(facts['ids']))

    for i in range(samples):
        print(f"\n[Fact {i+1}]")
        print(f"ID: {facts['ids'][i]}")

        # Safely print document content
        doc = facts['documents'][i]
        if doc:
            doc_preview = str(doc)[:200]
            print(f"Content: {doc_preview}...")
        else:
            print(f"Content: (empty)")

        print(f"Metadata: {json.dumps(facts['metadatas'][i], indent=2)}")

        # Print embedding info
        emb = facts['embeddings'][i]
        if emb:
            emb_len = len(emb) if isinstance(emb, (list, tuple)) else 'unknown'
            print(f"Embedding dimensions: {emb_len}")
        else:
            print(f"Embedding dimensions: None")

        print('-' * 80)


def inspect_database_schema(conn: sqlite3.Connection):
    """
    Inspect and print the database schema for debugging.

    Args:
        conn: SQLite connection
    """
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("Database Schema Inspection")
    print("="*80)

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    print("\nTables:")
    for table in tables:
        table_name = table['name']
        print(f"\n  Table: {table_name}")

        # Get table schema
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()

        for col in columns:
            print(f"    - {col['name']} ({col['type']})")

        # Get row count
        cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
        count = cursor.fetchone()['count']
        print(f"    Rows: {count}")

    print("="*80 + "\n")


def main():
    """Main execution function."""
    print("="*80)
    print("GemGem Facts Extraction Tool (Direct SQLite Access)")
    print("="*80)
    print()

    conn = None
    try:
        # Connect to SQLite database
        conn = connect_to_chromadb_sqlite(CHROMA_SQLITE)

        # Optional: Inspect schema for debugging
        # inspect_database_schema(conn)

        # Get collection ID
        collection_id = get_collection_id(conn, COLLECTION_NAME)
        if not collection_id:
            raise ValueError(f"Collection '{COLLECTION_NAME}' not found in database")

        print(f"Collection ID: {collection_id}")

        # Extract facts
        facts_data = extract_facts_from_sqlite(conn, collection_id)

        # Prepare output data with metadata
        output_data = {
            'source': 'GemGem ChromaDB',
            'collection_name': COLLECTION_NAME,
            'extracted_at': datetime.now().isoformat(),
            'total_facts': len(facts_data['ids']),
            'chromadb_path': CHROMADB_PATH,
            'extraction_method': 'Direct SQLite access',
            'facts': facts_data
        }

        # Save to JSON file
        save_to_json(output_data, OUTPUT_FILE)

        # Print sample facts
        print_sample_facts(output_data, num_samples=3)

        print("\n" + "="*80)
        print("Extraction completed successfully!")
        print(f"Total facts extracted: {output_data['total_facts']}")
        print(f"Output file: {OUTPUT_FILE}")
        print("="*80)

        return output_data['total_facts']

    except Exception as e:
        print(f"\n{'='*80}")
        print(f"ERROR: Extraction failed!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        print('='*80)
        import traceback
        traceback.print_exc()
        raise

    finally:
        if conn:
            conn.close()
            print("\nDatabase connection closed.")


if __name__ == "__main__":
    fact_count = main()
    exit(0 if fact_count >= 0 else 1)
