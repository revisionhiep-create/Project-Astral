"""Deduplicate facts from Project Astral and GemGem using cosine similarity.

Merges facts from both bots, removes duplicates based on cosine similarity > 0.90,
and outputs a unified fact list.
"""

import json
import numpy as np
from typing import List, Dict, Any
from collections import defaultdict


def load_facts(file_path: str) -> List[Dict[str, Any]]:
    """Load facts from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle different formats
        if isinstance(data, list):
            # Astral format: direct list
            print(f"[OK] Loaded {len(data)} facts from {file_path}")
            return data
        elif isinstance(data, dict) and 'facts' in data:
            # GemGem format: wrapped in metadata
            facts_data = data['facts']
            ids = facts_data.get('ids', [])
            documents = facts_data.get('documents', [])
            embeddings = facts_data.get('embeddings', [])
            metadatas = facts_data.get('metadatas', [])

            # Convert to unified format
            facts = []
            for i in range(len(ids)):
                fact = {
                    'id': ids[i],
                    'content': documents[i] if i < len(documents) else '',
                    'embedding': embeddings[i] if i < len(embeddings) and embeddings[i] else None,
                    'knowledge_type': 'user_fact',
                    'source': 'GemGem',
                    'metadata': metadatas[i] if i < len(metadatas) else {}
                }
                facts.append(fact)

            print(f"[OK] Loaded {len(facts)} facts from {file_path}")
            return facts
        else:
            print(f"[ERROR] Unknown format in {file_path}")
            return []
    except Exception as e:
        print(f"[ERROR] Error loading {file_path}: {e}")
        return []


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def deduplicate_facts(
    facts: List[Dict[str, Any]],
    similarity_threshold: float = 0.90
) -> List[Dict[str, Any]]:
    """Remove duplicate facts based on embedding similarity.

    Args:
        facts: List of fact dictionaries
        similarity_threshold: Similarity threshold for duplicates (default 0.90)

    Returns:
        Deduplicated list of facts
    """
    if not facts:
        return []

    print(f"\n[DEDUP] Deduplicating {len(facts)} facts (threshold: {similarity_threshold})...")

    unique_facts = []
    duplicate_count = 0
    skipped_no_embedding = 0

    for i, fact in enumerate(facts):
        if i % 100 == 0:
            print(f"   Progress: {i}/{len(facts)} processed, {duplicate_count} duplicates found")

        # Skip facts without embeddings
        embedding = fact.get("embedding")
        if not embedding or embedding is None:
            skipped_no_embedding += 1
            continue

        # Parse embedding if it's a string
        if isinstance(embedding, str):
            try:
                embedding = json.loads(embedding)
            except:
                skipped_no_embedding += 1
                continue

        # Check against existing unique facts
        is_duplicate = False
        for unique_fact in unique_facts:
            unique_embedding = unique_fact.get("embedding")
            if not unique_embedding:
                continue

            # Parse if string
            if isinstance(unique_embedding, str):
                try:
                    unique_embedding = json.loads(unique_embedding)
                except:
                    continue

            # Calculate similarity
            try:
                similarity = cosine_similarity(embedding, unique_embedding)

                if similarity >= similarity_threshold:
                    is_duplicate = True
                    duplicate_count += 1

                    # Prefer fact with more metadata or newer timestamp
                    fact_meta_count = len(fact.get("metadata", {}))
                    unique_meta_count = len(unique_fact.get("metadata", {}))

                    if fact_meta_count > unique_meta_count:
                        # Replace with better fact
                        unique_facts.remove(unique_fact)
                        unique_facts.append(fact)
                    break
            except Exception as e:
                print(f"[WARN] Error computing similarity: {e}")
                continue

        if not is_duplicate:
            unique_facts.append(fact)

    print(f"\n[OK] Deduplication complete:")
    print(f"   - Original facts: {len(facts)}")
    print(f"   - Unique facts: {len(unique_facts)}")
    print(f"   - Duplicates removed: {duplicate_count}")
    print(f"   - Skipped (no embedding): {skipped_no_embedding}")

    return unique_facts


def analyze_facts(facts: List[Dict[str, Any]], source_name: str):
    """Print analysis of facts."""
    print(f"\n[STATS] Analysis for {source_name}:")
    print(f"   Total facts: {len(facts)}")

    # Count by knowledge_type
    types = defaultdict(int)
    for fact in facts:
        fact_type = fact.get("knowledge_type", "unknown")
        types[fact_type] += 1

    print(f"   By type:")
    for fact_type, count in sorted(types.items(), key=lambda x: x[1], reverse=True):
        print(f"      - {fact_type}: {count}")

    # Count by source
    sources = defaultdict(int)
    for fact in facts:
        source = fact.get("source", "unknown")
        if source and source.startswith("conversation_"):
            user = source.replace("conversation_", "")
            sources[user] += 1
        elif source:
            sources[source] += 1

    print(f"   Top sources:")
    for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"      - {source}: {count}")


def main():
    """Main execution."""
    print("=" * 60)
    print("FACT DEDUPLICATION")
    print("=" * 60)

    # Load facts from both sources
    astral_facts = load_facts(
        "c:/Users/revis/OneDrive/Documents/Coding Projects/shared_memory/migrations/astral_facts.json"
    )
    gemgem_facts = load_facts(
        "c:/Users/revis/OneDrive/Documents/Coding Projects/shared_memory/migrations/gemgem_facts.json"
    )

    # Analyze input facts
    analyze_facts(astral_facts, "Project Astral")
    analyze_facts(gemgem_facts, "GemGem")

    # Combine facts
    all_facts = astral_facts + gemgem_facts
    print(f"\n[MERGE] Combined total: {len(all_facts)} facts")

    # Deduplicate
    unique_facts = deduplicate_facts(all_facts, similarity_threshold=0.90)

    # Analyze output
    analyze_facts(unique_facts, "Unified (After Deduplication)")

    # Save unified facts
    output_path = "c:/Users/revis/OneDrive/Documents/Coding Projects/shared_memory/migrations/unified_facts.json"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(unique_facts, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Unified facts saved to: {output_path}")
        print(f"   File size: {len(json.dumps(unique_facts))} bytes")
    except Exception as e:
        print(f"[ERROR] Error saving unified facts: {e}")

    print("\n" + "=" * 60)
    print("DEDUPLICATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
