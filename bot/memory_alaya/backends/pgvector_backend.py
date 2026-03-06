"""PostgreSQL + pgvector Backend with HNSW indexing.

Production-ready backend with native vector operations and HNSW indexing
for fast similarity search on large datasets (100k+ vectors).
"""

import json
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from pgvector.psycopg2 import register_vector
import numpy as np
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi


class PgVectorBackend:
    """PostgreSQL with pgvector extension for scalable vector search."""

    def __init__(self, config: Dict[str, str]):
        """Initialize PostgreSQL connection with pgvector.

        Args:
            config: Connection config with keys: host, port, database, user, password
        """
        self.config = config
        self.conn = psycopg2.connect(**config)
        register_vector(self.conn)

        # Initialize schema
        self._init_schema()

        # BM25 index (in-memory, could be optimized with PostgreSQL FTS)
        self.bm25_index = None
        self.bm25_corpus = []
        self.bm25_ids = []
        self._rebuild_bm25_index()

        print(f"✅ pgvector backend initialized at {config['host']}")

    def _init_schema(self):
        """Create tables, enable pgvector extension, and create indexes."""
        cursor = self.conn.cursor()

        # Enable pgvector extension
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # Main knowledge table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding vector(3072),
                knowledge_type VARCHAR DEFAULT 'user_fact',
                source VARCHAR,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT now(),
                user_id VARCHAR,
                guild_id VARCHAR,
                channel_id VARCHAR
            )
        """)

        # Create HNSW index for fast vector search
        # m=16 (connections), ef_construction=64 (search quality)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_embedding_hnsw
            ON knowledge
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)

        # Create indexes for filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_user_id
            ON knowledge(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_guild_id
            ON knowledge(guild_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_channel_id
            ON knowledge(channel_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_type
            ON knowledge(knowledge_type)
        """)

        # GIN index for JSONB metadata
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_metadata
            ON knowledge USING gin(metadata)
        """)

        self.conn.commit()
        cursor.close()

    async def insert(
        self,
        id: str,
        content: str,
        embedding: List[float],
        knowledge_type: str = "user_fact",
        source: str = None,
        metadata: Dict[str, Any] = None,
        user_id: str = None,
        guild_id: str = None,
        channel_id: str = None
    ) -> bool:
        """Insert knowledge entry."""
        try:
            cursor = self.conn.cursor()

            # Convert embedding to list if numpy array
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            cursor.execute("""
                INSERT INTO knowledge
                (id, content, embedding, knowledge_type, source, metadata, user_id, guild_id, channel_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                id, content, embedding, knowledge_type, source,
                Json(metadata) if metadata else None,
                user_id, guild_id, channel_id
            ))

            self.conn.commit()
            cursor.close()

            # Rebuild BM25 incrementally
            self.bm25_ids.append(id)
            self.bm25_corpus.append(content)
            self._rebuild_bm25_index()

            return True

        except Exception as e:
            self.conn.rollback()
            print(f"❌ Insert failed: {e}")
            return False

    async def hybrid_search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Dict[str, str] = None,
        similarity_threshold: float = 0.63
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining vector and keyword search.

        Args:
            query: User's query text
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filters: Optional filters (user_id, guild_id, channel_id)
            similarity_threshold: Minimum cosine similarity

        Returns:
            List of results with scores
        """
        # Build WHERE clause for filters
        where_clauses = ["1=1"]
        params = [query_embedding]

        if filters:
            if filters.get("user_id"):
                where_clauses.append("user_id = %s")
                params.append(filters["user_id"])
            if filters.get("guild_id"):
                where_clauses.append("guild_id = %s")
                params.append(filters["guild_id"])
            if filters.get("channel_id"):
                where_clauses.append("channel_id = %s")
                params.append(filters["channel_id"])

        where_clause = " AND ".join(where_clauses)

        # Step 1: Vector search using pgvector
        vector_results = await self._vector_search(
            query_embedding, top_k * 2, where_clause, params, similarity_threshold
        )

        # Step 2: Keyword search (BM25)
        keyword_results = await self._keyword_search(
            query, top_k, where_clause, params[1:]  # Skip embedding param
        )

        # Step 3: Merge results
        merged = self._merge_results(vector_results, keyword_results)

        return merged[:top_k]

    async def _vector_search(
        self,
        query_embedding: List[float],
        top_k: int,
        where_clause: str,
        params: List[Any],
        threshold: float
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search using pgvector."""
        try:
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)

            # Use pgvector's native cosine distance operator
            # <=> is cosine distance (0 = identical, 2 = opposite)
            # Similarity = 1 - distance
            query_sql = f"""
                SELECT
                    id, content, knowledge_type, source, metadata,
                    user_id, guild_id, channel_id,
                    1 - (embedding <=> %s::vector) as similarity
                FROM knowledge
                WHERE {where_clause}
                  AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """

            # Add embedding to params multiple times (for WHERE, ORDER BY)
            full_params = [query_embedding] + params + [
                query_embedding, threshold, query_embedding, top_k
            ]

            cursor.execute(query_sql, full_params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "knowledge_type": row["knowledge_type"],
                    "source": row["source"],
                    "metadata": row["metadata"] or {},
                    "user_id": row["user_id"],
                    "guild_id": row["guild_id"],
                    "channel_id": row["channel_id"],
                    "vector_score": float(row["similarity"]),
                    "search_type": "vector"
                })

            cursor.close()
            return results

        except Exception as e:
            print(f"❌ Vector search failed: {e}")
            return []

    async def _keyword_search(
        self,
        query: str,
        top_k: int,
        where_clause: str,
        params: List[Any]
    ) -> List[Dict[str, Any]]:
        """Perform BM25 keyword search."""
        try:
            if not self.bm25_index or not self.bm25_corpus:
                return []

            # Tokenize query
            query_tokens = query.lower().split()

            # Get BM25 scores
            scores = self.bm25_index.get_scores(query_tokens)

            # Get top K indices
            top_indices = np.argsort(scores)[::-1][:top_k * 2]

            # Fetch full records
            cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            results = []

            for idx in top_indices:
                if scores[idx] > 0:
                    doc_id = self.bm25_ids[idx]

                    cursor.execute("""
                        SELECT id, content, knowledge_type, source, metadata,
                               user_id, guild_id, channel_id
                        FROM knowledge
                        WHERE id = %s
                    """, [doc_id])

                    row = cursor.fetchone()
                    if row:
                        results.append({
                            "id": row["id"],
                            "content": row["content"],
                            "knowledge_type": row["knowledge_type"],
                            "source": row["source"],
                            "metadata": row["metadata"] or {},
                            "user_id": row["user_id"],
                            "guild_id": row["guild_id"],
                            "channel_id": row["channel_id"],
                            "bm25_score": float(scores[idx]),
                            "search_type": "keyword"
                        })

            cursor.close()
            return results[:top_k]

        except Exception as e:
            print(f"❌ Keyword search failed: {e}")
            return []

    def _merge_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge and deduplicate results."""
        seen_ids = set()
        merged = []

        for result in vector_results:
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                merged.append(result)

        for result in keyword_results:
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                merged.append(result)

        return merged

    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from database."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, content FROM knowledge
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            cursor.close()

            self.bm25_ids = [r[0] for r in rows]
            self.bm25_corpus = [r[1] for r in rows]

            tokenized_corpus = [doc.lower().split() for doc in self.bm25_corpus]
            self.bm25_index = BM25Okapi(tokenized_corpus)

        except Exception as e:
            print(f"❌ BM25 rebuild failed: {e}")

    async def delete(self, knowledge_id: str) -> bool:
        """Delete knowledge by ID."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM knowledge WHERE id = %s", [knowledge_id])
            self.conn.commit()
            cursor.close()
            self._rebuild_bm25_index()
            return True
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Delete failed: {e}")
            return False

    async def count(self, filters: Dict[str, str] = None) -> int:
        """Count knowledge entries with optional filters."""
        where_clauses = ["1=1"]
        params = []

        if filters:
            if filters.get("user_id"):
                where_clauses.append("user_id = %s")
                params.append(filters["user_id"])
            if filters.get("guild_id"):
                where_clauses.append("guild_id = %s")
                params.append(filters["guild_id"])

        where_clause = " AND ".join(where_clauses)

        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM knowledge WHERE {where_clause}",
            params
        )
        result = cursor.fetchone()
        cursor.close()

        return result[0] if result else 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        total = await self.count()

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT knowledge_type, COUNT(*) as count
            FROM knowledge
            GROUP BY knowledge_type
        """)
        rows = cursor.fetchall()
        cursor.close()

        type_counts = {row[0]: row[1] for row in rows}

        return {
            "backend": "pgvector",
            "database_host": self.config["host"],
            "total_entries": total,
            "by_type": type_counts
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
