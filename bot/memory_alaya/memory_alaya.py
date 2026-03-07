"""Memory Alaya - Unified memory abstraction layer for both bots.

Inspired by Project AIRI's architecture, this provides a clean interface
for knowledge storage and retrieval across multiple backends.

Architecture:
    User Query → Memory Alaya → Backend (DuckDB/pgvector) → Vector/FTS Search
                      ↓
              Hybrid Search + Rerank → Results
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
import numpy as np

# Backend imports
from .backends.duckdb_backend import DuckDBBackend

try:
    from .backends.pgvector_backend import PgVectorBackend
except ImportError:
    PgVectorBackend = None


class MemoryAlaya:
    """Unified memory interface for Project Astral and GemGem."""

    def __init__(
        self,
        backend: str = "duckdb",
        database_path: str = None,
        postgres_config: Dict[str, str] = None
    ):
        """Initialize Memory Alaya with specified backend.

        Args:
            backend: Either "duckdb" (local) or "pgvector" (production)
            database_path: Path to DuckDB file (for duckdb backend)
            postgres_config: Connection config for pgvector backend
        """
        self.backend_type = backend

        if backend == "duckdb":
            if database_path is None:
                database_path = os.path.join(
                    os.path.dirname(__file__), "memory.duckdb"
                )
            self.backend = DuckDBBackend(database_path)

        elif backend == "pgvector":
            if PgVectorBackend is None:
                raise ValueError("pgvector backend not available. Install: pip install psycopg2-binary pgvector")
            if postgres_config is None:
                # Try to load from config file
                config_path = os.path.join(
                    os.path.dirname(__file__), "postgres_config.json"
                )
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        postgres_config = json.load(f)
                else:
                    raise ValueError("pgvector backend requires postgres_config")
            self.backend = PgVectorBackend(postgres_config)

        else:
            raise ValueError(f"Unknown backend: {backend}")

        # Initialize Gemini for reranking
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_client = (
            genai.Client(api_key=self.gemini_api_key)
            if self.gemini_api_key else None
        )

        print(f"[OK] Memory Alaya initialized with {backend} backend")

    async def store(
        self,
        content: str,
        embedding: List[float],
        knowledge_type: str = "user_fact",
        source: str = None,
        metadata: Dict[str, Any] = None,
        user_id: str = None,
        guild_id: str = None,
        channel_id: str = None
    ) -> str:
        """Store knowledge with embedding.

        Args:
            content: The actual fact/knowledge text
            embedding: Pre-computed embedding vector (3072-dim)
            knowledge_type: Type of knowledge (default: user_fact)
            source: Origin of the knowledge
            metadata: Additional metadata as dict
            user_id: Discord user ID for filtering
            guild_id: Discord guild ID for filtering
            channel_id: Discord channel ID for filtering

        Returns:
            Knowledge ID (generated)
        """
        # Generate unique ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        knowledge_id = f"know_{content_hash}_{timestamp}"

        # Prepare metadata
        if metadata is None:
            metadata = {}
        metadata["created_at"] = datetime.now().isoformat()

        # Store in backend
        await self.backend.insert(
            id=knowledge_id,
            content=content,
            embedding=embedding,
            knowledge_type=knowledge_type,
            source=source,
            metadata=metadata,
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id
        )

        return knowledge_id

    async def recall(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        filters: Dict[str, str] = None,
        similarity_threshold: float = 0.63,
        rerank: bool = True
    ) -> List[Dict[str, Any]]:
        """Recall relevant knowledge using hybrid search.

        Args:
            query: User's query text
            query_embedding: Pre-computed query embedding
            top_k: Number of results to return
            filters: Optional filters (user_id, guild_id, channel_id)
            similarity_threshold: Minimum cosine similarity
            rerank: Whether to use Gemini reranking (default: True)

        Returns:
            List of knowledge dictionaries with content, score, metadata
        """
        # Step 1: Hybrid search (vector + keyword + questions)
        candidates = await self.backend.hybrid_search(
            query=query,
            query_embedding=query_embedding,
            top_k=top_k * 2,  # Get more for reranking
            filters=filters,
            similarity_threshold=similarity_threshold,
            search_questions=True  # Enable hypothetical question search
        )

        if not candidates:
            return []

        # Step 2: Rerank with Gemini (if enabled and available)
        if rerank and self.gemini_client and len(candidates) > 1:
            candidates = await self._gemini_rerank(query, candidates)
            # Filter by rerank score
            candidates = [c for c in candidates if c.get("rerank_score", 0) > 3.0]

        # Return top K
        return candidates[:top_k]

    async def _gemini_rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rerank candidates using Gemini 2.5 Flash as cross-encoder.

        Args:
            query: User's query
            candidates: List of candidate documents

        Returns:
            Reranked candidates with rerank_score added
        """
        if not candidates:
            return []

        # Build prompt
        doc_texts = []
        for i, cand in enumerate(candidates):
            content = cand.get("content", "")
            preview = content[:300] if len(content) > 300 else content
            doc_texts.append(f"Document [{i}]: {preview}")

        prompt = f"""You are a relevance ranking assistant. Rate how relevant each document is to the search query on a scale of 0.0 to 10.0.
10.0 means perfectly relevant, and 0.0 means completely irrelevant.
Provide ONLY the space-separated list of float scores, one per document, in order.

Query: {query}

{chr(10).join(doc_texts)}

Scores (space-separated floats):"""

        try:
            response = await self._generate_content_async(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=20 * len(candidates)
                )
            )

            # Parse scores
            scores_text = response.text.strip()
            scores = [float(s) for s in scores_text.split()]

            # Attach scores to candidates
            for i, cand in enumerate(candidates):
                if i < len(scores):
                    cand["rerank_score"] = scores[i]
                else:
                    cand["rerank_score"] = 0.0

            # Sort by rerank score
            candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

        except Exception as e:
            print(f"[WARN] Reranking failed: {e}")
            # Fall back to vector scores
            pass

        return candidates

    async def _generate_content_async(self, model: str, contents: str, config) -> Any:
        """Async wrapper for Gemini API."""
        import asyncio
        loop = asyncio.get_event_loop()

        def _sync_call():
            return self.gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )

        return await loop.run_in_executor(None, _sync_call)

    async def delete(self, knowledge_id: str) -> bool:
        """Delete knowledge by ID."""
        return await self.backend.delete(knowledge_id)

    async def count(self, filters: Dict[str, str] = None) -> int:
        """Count knowledge entries with optional filters."""
        return await self.backend.count(filters)

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        return await self.backend.get_stats()

    def close(self):
        """Close backend connection."""
        self.backend.close()
