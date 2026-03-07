"""DuckDB Backend with Full-Text Search support.

Uses DuckDB's native FTS extension for fast keyword search
and vector operations for semantic search.
"""

import os
import json
import duckdb
import numpy as np
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi


class DuckDBBackend:
    """DuckDB-based storage backend with FTS and vector search."""

    def __init__(self, database_path: str):
        """Initialize DuckDB connection and schema.

        Args:
            database_path: Path to DuckDB database file
        """
        self.db_path = database_path

        # IMPORTANT: Each bot should use a separate database file
        # DuckDB does not support multiple processes accessing the same file
        self.conn = duckdb.connect(database_path)

        # Initialize schema
        self._init_schema()

        # BM25 index (in-memory for now)
        self.bm25_index = None
        self.bm25_corpus = []
        self.bm25_ids = []
        self._rebuild_bm25_index()

        print(f"[OK] DuckDB backend initialized at {database_path}")

    def _init_schema(self):
        """Create tables and indexes."""
        # Main knowledge table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                embedding FLOAT[3072],
                knowledge_type VARCHAR DEFAULT 'user_fact',
                source VARCHAR,
                metadata JSON,
                created_at TIMESTAMP DEFAULT now(),
                user_id VARCHAR,
                guild_id VARCHAR,
                channel_id VARCHAR
            )
        """)

        # Create indexes for filtering
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_user_id
            ON knowledge(user_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_guild_id
            ON knowledge(guild_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_channel_id
            ON knowledge(channel_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_type
            ON knowledge(knowledge_type)
        """)

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
            # Convert embedding to list if it's numpy array
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            # Convert metadata to JSON string
            metadata_json = json.dumps(metadata) if metadata else None

            self.conn.execute("""
                INSERT INTO knowledge
                (id, content, embedding, knowledge_type, source, metadata, user_id, guild_id, channel_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                id, content, embedding, knowledge_type, source,
                metadata_json, user_id, guild_id, channel_id
            ])

            # Rebuild BM25 index incrementally
            self.bm25_ids.append(id)
            self.bm25_corpus.append(content)
            self._rebuild_bm25_index()

            return True

        except Exception as e:
            print(f"[ERROR] Insert failed: {e}")
            return False

    async def hybrid_search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Dict[str, str] = None,
        similarity_threshold: float = 0.63,
        search_questions: bool = True
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining vector and keyword search.

        Args:
            query: User's query text
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filters: Optional filters (user_id, guild_id, channel_id)
            similarity_threshold: Minimum cosine similarity
            search_questions: Whether to also search hypothetical_questions in metadata

        Returns:
            List of results with scores
        """
        # Build WHERE clause for filters
        where_clauses = []
        params = []

        if filters:
            if filters.get("user_id"):
                where_clauses.append("user_id = ?")
                params.append(filters["user_id"])
            if filters.get("guild_id"):
                where_clauses.append("guild_id = ?")
                params.append(filters["guild_id"])
            if filters.get("channel_id"):
                where_clauses.append("channel_id = ?")
                params.append(filters["channel_id"])

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Step 1: Vector search
        vector_results = await self._vector_search(
            query_embedding, top_k * 2, where_clause, params, similarity_threshold
        )

        # Step 2: Keyword search (BM25)
        keyword_results = await self._keyword_search(
            query, top_k, where_clause, params
        )

        # Step 3: Hypothetical question search (if enabled)
        question_results = []
        if search_questions:
            question_results = await self._question_search(
                query, top_k, where_clause, params
            )

        # Step 4: Merge results (deduplication by ID)
        merged = self._merge_results(vector_results, keyword_results, question_results)

        return merged[:top_k]

    async def _vector_search(
        self,
        query_embedding: List[float],
        top_k: int,
        where_clause: str,
        params: List[Any],
        threshold: float
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search."""
        try:
            # Convert query embedding to numpy for computation
            query_vec = np.array(query_embedding)

            # Fetch all embeddings matching filters
            query_sql = f"""
                SELECT id, content, embedding, knowledge_type, source, metadata, user_id, guild_id, channel_id
                FROM knowledge
                WHERE {where_clause}
            """

            results = self.conn.execute(query_sql, params).fetchall()

            # Compute cosine similarity in Python
            scored_results = []
            for row in results:
                try:
                    emb = np.array(row[2])  # embedding column
                    similarity = self._cosine_similarity(query_vec, emb)

                    if similarity >= threshold:
                        scored_results.append({
                            "id": row[0],
                            "content": row[1],
                            "knowledge_type": row[3],
                            "source": row[4],
                            "metadata": json.loads(row[5]) if row[5] else {},
                            "user_id": row[6],
                            "guild_id": row[7],
                            "channel_id": row[8],
                            "vector_score": float(similarity),
                            "search_type": "vector"
                        })
                except Exception as e:
                    print(f"[WARN] Error computing similarity for {row[0]}: {e}")
                    continue

            # Sort by similarity
            scored_results.sort(key=lambda x: x["vector_score"], reverse=True)
            return scored_results[:top_k]

        except Exception as e:
            print(f"[ERROR] Vector search failed: {e}")
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

            # Fetch full records for top results
            results = []
            for idx in top_indices:
                if scores[idx] > 0:
                    doc_id = self.bm25_ids[idx]

                    # Fetch full record
                    row = self.conn.execute("""
                        SELECT id, content, knowledge_type, source, metadata, user_id, guild_id, channel_id
                        FROM knowledge
                        WHERE id = ?
                    """, [doc_id]).fetchone()

                    if row:
                        results.append({
                            "id": row[0],
                            "content": row[1],
                            "knowledge_type": row[2],
                            "source": row[3],
                            "metadata": json.loads(row[4]) if row[4] else {},
                            "user_id": row[5],
                            "guild_id": row[6],
                            "channel_id": row[7],
                            "bm25_score": float(scores[idx]),
                            "search_type": "keyword"
                        })

            return results[:top_k]

        except Exception as e:
            print(f"[ERROR] Keyword search failed: {e}")
            return []

    async def _question_search(
        self,
        query: str,
        top_k: int,
        where_clause: str,
        params: List[Any]
    ) -> List[Dict[str, Any]]:
        """Search hypothetical questions in metadata.

        Args:
            query: User's query text
            top_k: Number of results to return
            where_clause: SQL WHERE clause for filtering
            params: SQL parameters

        Returns:
            List of results with question_match_score
        """
        try:
            # Fetch all records matching filters
            query_sql = f"""
                SELECT id, content, knowledge_type, source, metadata, user_id, guild_id, channel_id
                FROM knowledge
                WHERE {where_clause}
            """

            results = self.conn.execute(query_sql, params).fetchall()
            print(f"[QUESTION SEARCH] Query: '{query}' | WHERE: {where_clause} | Params: {params} | DB rows fetched: {len(results)}")

            # Score based on question similarity
            scored_results = []
            query_lower = query.lower()

            for row in results:
                metadata_json = row[4]  # metadata column
                if not metadata_json:
                    continue

                try:
                    metadata = json.loads(metadata_json)
                    questions = metadata.get('hypothetical_questions', [])

                    if not questions:
                        continue

                    print(f"[QUESTION SEARCH] Checking {len(questions)} questions for fact: {row[1][:60]}")

                    # Calculate similarity to each question (simple keyword overlap)
                    max_score = 0.0
                    best_question = None
                    for question in questions:
                        question_lower = question.lower()

                        # Simple scoring: word overlap / total words
                        query_words = set(query_lower.split())
                        question_words = set(question_lower.split())

                        if query_words and question_words:
                            overlap = len(query_words & question_words)
                            score = overlap / max(len(query_words), len(question_words))
                            if score > max_score:
                                max_score = score
                                best_question = question

                    if best_question:
                        print(f"[QUESTION SEARCH]   Match: '{best_question[:50]}' (score: {max_score:.3f})")

                    # Only include if there's meaningful overlap
                    if max_score > 0.3:  # Threshold for question matching
                        print(f"[QUESTION SEARCH] PASS threshold! Adding to results")
                        scored_results.append({
                            "id": row[0],
                            "content": row[1],
                            "knowledge_type": row[2],
                            "source": row[3],
                            "metadata": metadata,
                            "user_id": row[5],
                            "guild_id": row[6],
                            "channel_id": row[7],
                            "question_match_score": float(max_score),
                            "search_type": "question"
                        })

                except Exception as e:
                    print(f"[WARN] Error parsing metadata for question search: {e}")
                    continue

            # Sort by score
            scored_results.sort(key=lambda x: x["question_match_score"], reverse=True)
            return scored_results[:top_k]

        except Exception as e:
            print(f"[ERROR] Question search failed: {e}")
            return []

    def _merge_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        question_results: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Merge and deduplicate results from vector, keyword, and question search.

        Priority order:
        1. Question matches (highest weight - 1.2x)
        2. Vector matches (semantic similarity)
        3. Keyword matches (BM25)
        """
        if question_results is None:
            question_results = []

        seen_ids = set()
        merged = []

        # Add question results first with boosted score (HIGHEST PRIORITY)
        for result in question_results:
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                # Boost question match scores
                result["boosted_score"] = result.get("question_match_score", 0) * 1.2
                merged.append(result)

        # Add vector results (they have embedding similarity)
        for result in vector_results:
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                result["boosted_score"] = result.get("vector_score", 0)
                merged.append(result)

        # Add keyword results that weren't in vector or question results
        for result in keyword_results:
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                # Normalize BM25 scores (they're typically 0-10)
                result["boosted_score"] = result.get("bm25_score", 0) / 10.0
                merged.append(result)

        # Re-sort by boosted score
        merged.sort(key=lambda x: x.get("boosted_score", 0), reverse=True)

        return merged

    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from database."""
        try:
            # Fetch all documents
            rows = self.conn.execute("""
                SELECT id, content FROM knowledge
                ORDER BY created_at DESC
            """).fetchall()

            self.bm25_ids = [r[0] for r in rows]
            self.bm25_corpus = [r[1] for r in rows]

            # Build BM25 index only if we have documents
            if self.bm25_corpus:
                # Tokenize corpus
                tokenized_corpus = [doc.lower().split() for doc in self.bm25_corpus]
                # Build BM25 index
                self.bm25_index = BM25Okapi(tokenized_corpus)
            else:
                self.bm25_index = None

        except Exception as e:
            print(f"[ERROR] BM25 rebuild failed: {e}")

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

    async def delete(self, knowledge_id: str) -> bool:
        """Delete knowledge by ID."""
        try:
            self.conn.execute("DELETE FROM knowledge WHERE id = ?", [knowledge_id])
            self._rebuild_bm25_index()
            return True
        except Exception as e:
            print(f"[ERROR] Delete failed: {e}")
            return False

    async def count(self, filters: Dict[str, str] = None) -> int:
        """Count knowledge entries with optional filters."""
        where_clauses = []
        params = []

        if filters:
            if filters.get("user_id"):
                where_clauses.append("user_id = ?")
                params.append(filters["user_id"])
            if filters.get("guild_id"):
                where_clauses.append("guild_id = ?")
                params.append(filters["guild_id"])

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        result = self.conn.execute(
            f"SELECT COUNT(*) FROM knowledge WHERE {where_clause}",
            params
        ).fetchone()

        return result[0] if result else 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        total = await self.count()

        # Count by type
        type_counts = {}
        rows = self.conn.execute("""
            SELECT knowledge_type, COUNT(*) as count
            FROM knowledge
            GROUP BY knowledge_type
        """).fetchall()

        for row in rows:
            type_counts[row[0]] = row[1]

        return {
            "backend": "duckdb",
            "database_path": self.db_path,
            "total_entries": total,
            "by_type": type_counts
        }

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
