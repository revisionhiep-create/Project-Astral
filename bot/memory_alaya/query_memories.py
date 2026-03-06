#!/usr/bin/env python3
"""
Query and inspect the Memory Alaya system.

This script provides utilities to:
- Query/recall facts from the unified memory database
- View all stored facts
- Get statistics
- Test the hybrid search + reranking system

Works with both Project Astral and GemGem's shared memory.
"""

import asyncio
import sys
import os
from typing import List, Optional

# Import Memory Alaya
from memory_alaya import MemoryAlaya


class MemoryQuery:
    """Interactive query tool for Memory Alaya."""

    def __init__(self, db_path: str = None):
        """Initialize with DuckDB backend.

        Args:
            db_path: Path to memory.duckdb file (defaults to ./memory.duckdb)
        """
        if not db_path:
            db_path = os.path.join(os.path.dirname(__file__), "memory.duckdb")

        self.db_path = db_path
        self.memory = MemoryAlaya(
            backend="duckdb",
            database_path=db_path
        )

        # Initialize Gemini for embeddings
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        self.gemini_client = genai.Client(api_key=api_key)

        print(f"[OK] Connected to Memory Alaya at {db_path}")

    async def get_stats(self) -> dict:
        """Get database statistics."""
        stats = await self.memory.get_stats()
        return stats

    async def list_all_facts(self, limit: int = 100) -> List[dict]:
        """List all facts in the database.

        Args:
            limit: Maximum number of facts to return

        Returns:
            List of fact dictionaries
        """
        from backends.duckdb_backend import DuckDBBackend
        backend = self.memory.backend

        if isinstance(backend, DuckDBBackend):
            result = backend.conn.execute(
                f"SELECT id, content, knowledge_type, source, created_at, metadata FROM knowledge ORDER BY created_at DESC LIMIT {limit}"
            ).fetchall()

            facts = []
            for row in result:
                facts.append({
                    "id": row[0],
                    "content": row[1],
                    "knowledge_type": row[2],
                    "source": row[3],
                    "created_at": row[4],
                    "metadata": row[5]
                })
            return facts
        else:
            print("[WARNING] list_all_facts only works with DuckDB backend")
            return []

    async def query(
        self,
        query_text: str,
        top_k: int = 5,
        threshold: float = 0.63,
        rerank: bool = True,
        user_id: str = None,
        guild_id: str = None
    ) -> List[dict]:
        """Query the memory system using hybrid search.

        Args:
            query_text: Natural language query
            top_k: Number of results to return
            threshold: Minimum similarity threshold (0.0-1.0)
            rerank: Whether to use Gemini reranking
            user_id: Optional filter by user ID
            guild_id: Optional filter by guild ID

        Returns:
            List of relevant facts with scores
        """
        # Generate embedding for query
        embedding_response = self.gemini_client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=query_text
        )
        query_embedding = embedding_response.embeddings[0].values

        # Build filters
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if guild_id:
            filters["guild_id"] = guild_id

        # Recall from Memory Alaya
        results = await self.memory.recall(
            query=query_text,
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters if filters else None,
            similarity_threshold=threshold,
            rerank=rerank
        )

        return results


async def interactive_mode():
    """Run in interactive query mode."""
    print("=" * 70)
    print("Memory Alaya - Interactive Query Mode")
    print("=" * 70)
    print("Commands:")
    print("  query <text>     - Query facts using hybrid search")
    print("  list [n]         - List all facts (optional limit)")
    print("  stats            - Show database statistics")
    print("  quit / exit      - Exit interactive mode")
    print("=" * 70)

    # Initialize
    try:
        mq = MemoryQuery()
    except Exception as e:
        print(f"[ERROR] Failed to initialize: {e}")
        return

    while True:
        try:
            user_input = input("\n> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            # Parse command
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if command == "query":
                if not args:
                    print("[ERROR] Usage: query <text>")
                    continue

                print(f"\nQuerying: '{args}'")
                results = await mq.query(args, top_k=5, rerank=True)

                if not results:
                    print("  No results found")
                else:
                    print(f"\nFound {len(results)} result(s):\n")
                    for i, result in enumerate(results, 1):
                        print(f"{i}. {result['content']}")
                        print(f"   Vector Score: {result.get('vector_score', 0.0):.4f}")
                        if 'rerank_score' in result:
                            print(f"   Rerank Score: {result['rerank_score']:.4f}")
                        print(f"   Type: {result.get('knowledge_type', 'N/A')}")
                        print(f"   Source: {result.get('source', 'N/A')}")
                        print()

            elif command == "list":
                limit = int(args) if args.isdigit() else 20
                print(f"\nListing up to {limit} facts...\n")

                facts = await mq.list_all_facts(limit=limit)

                if not facts:
                    print("  No facts found")
                else:
                    for i, fact in enumerate(facts, 1):
                        print(f"{i}. {fact['content'][:100]}")
                        print(f"   ID: {fact['id']}")
                        print(f"   Type: {fact['knowledge_type']}")
                        print(f"   Created: {fact['created_at']}")
                        print()

            elif command == "stats":
                stats = await mq.get_stats()
                print("\nDatabase Statistics:")
                print(f"  Total entries: {stats.get('total_entries', 0)}")
                print(f"  Backend: {stats.get('backend', 'N/A')}")
                print(f"  Database: {mq.db_path}")

            else:
                print(f"[ERROR] Unknown command: {command}")
                print("Type 'quit' to exit or use commands: query, list, stats")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"[ERROR] {e}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Query and inspect the Memory Alaya system"
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Query text (if not provided, enters interactive mode)"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to memory.duckdb file"
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of results to return (default: 5)"
    )
    parser.add_argument(
        "--no-rerank",
        action="store_true",
        help="Disable Gemini reranking"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all facts"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics"
    )

    args = parser.parse_args()

    # Initialize
    try:
        mq = MemoryQuery(db_path=args.db)
    except Exception as e:
        print(f"[ERROR] Failed to initialize: {e}")
        return

    # Handle commands
    if args.stats:
        stats = await mq.get_stats()
        print("\n=== Database Statistics ===")
        print(f"Total entries: {stats.get('total_entries', 0)}")
        print(f"Backend: {stats.get('backend', 'N/A')}")
        print(f"Database: {mq.db_path}")
        return

    if args.list:
        facts = await mq.list_all_facts(limit=100)
        print(f"\n=== All Facts ({len(facts)} total) ===\n")
        for i, fact in enumerate(facts, 1):
            print(f"{i}. {fact['content']}")
            print(f"   Type: {fact['knowledge_type']} | Source: {fact['source']}")
            print(f"   Created: {fact['created_at']}")
            print()
        return

    if args.query:
        query_text = " ".join(args.query)
        print(f"\n=== Query: '{query_text}' ===\n")

        results = await mq.query(
            query_text,
            top_k=args.top_k,
            rerank=not args.no_rerank
        )

        if not results:
            print("No results found")
        else:
            for i, result in enumerate(results, 1):
                print(f"{i}. {result['content']}")
                print(f"   Vector Score: {result.get('vector_score', 0.0):.4f}")
                if 'rerank_score' in result and not args.no_rerank:
                    print(f"   Rerank Score: {result['rerank_score']:.4f}")
                print(f"   Type: {result.get('knowledge_type', 'N/A')}")
                print()
        return

    # No arguments - enter interactive mode
    await interactive_mode()


if __name__ == "__main__":
    # Check for GEMINI_API_KEY
    if not os.getenv("GEMINI_API_KEY"):
        print("[ERROR] GEMINI_API_KEY environment variable not set!")
        print("Please set it in your .env file or environment")
        sys.exit(1)

    asyncio.run(main())
