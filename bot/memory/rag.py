"""RAG Vector Store - SQLite-based semantic memory with Summary RAG (facts, not logs).

v1.9.2: Summary RAG - conversations are summarized to facts before storage.
Instead of storing raw chat logs like "Hiep: hey\nAstra: sup", we extract
meaningful facts like "Hiep is working on a Discord bot called GemGem."
This prevents context pollution and reasoning model confusion.
"""
import os
import json
import sqlite3
import hashlib
import aiohttp
import google.generativeai as genai
from datetime import datetime
from typing import Optional
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from memory.embeddings import get_embedding, get_query_embedding


DATABASE_PATH = os.getenv("RAG_DATABASE", "/app/data/memory.db")
LLM_HOST = os.getenv("LMSTUDIO_HOST") or os.getenv("TABBY_HOST", "http://host.docker.internal:1234")
LLM_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL") or os.getenv("TABBY_MODEL", "qwen3-vl-32b-instruct-heretic-v2-i1")

# Search Models
BM25_INDEX = None
BM25_CORPUS = []
BM25_IDS = []
CROSS_ENCODER = None


async def _extract_fact_from_conversation(username: str, user_message: str, astra_response: str) -> Optional[str]:
    """
    Extract a factual statement from a conversation using Gemini 2.0 Flash.
    """
    if not os.getenv("GEMINI_API_KEY"):
        return None

    prompt = f"""Extract ONE factual statement about {username} from this conversation, or respond with exactly "NONE" if there's no meaningful fact to remember.

Conversation:
[{username}]: {user_message}
[Astra]: {astra_response}

Rules:
- Extract facts about the USER, not about Astra
- Facts should be useful for future reference (preferences, projects, relationships, interests)
- "lol", "k", "brb", greetings, and small talk are NOT facts - return NONE
- Generic statements like "User is chatting" are NOT useful - return NONE
- Format: "{username} [fact about them]" (e.g., "Hiep is developing a Discord bot called GemGem")
- One fact only, or NONE

Respond with the fact or NONE:"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=100
            )
        )
        result = response.text.strip()
        
        # Check if it's a valid fact (not NONE or empty)
        if not result or result.upper() == "NONE" or len(result) < 10:
            return None
        
        # Clean up any think tags that might leak through
        import re
        result = re.sub(r'<think>.*?</think>\s*', '', result, flags=re.DOTALL)
        result = result.strip()
        
        if result.upper() == "NONE" or len(result) < 10:
            return None
            
        print(f"[RAG] Extracted fact: {result[:80]}...")
        return result
                
    except Exception as e:
        print(f"[RAG] Fact extraction failed: {e}")
        return None


def _init_search_models():
    """Initialize CrossEncoder and build BM25 index."""
    global CROSS_ENCODER
    try:
        # Load Cross-Encoder (fast, small model)
        CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        print("[RAG] Cross-Encoder loaded successfully")
    except Exception as e:
        print(f"[RAG] Failed to load Cross-Encoder: {e}")
    
    # Build BM25 from existing DB
    _rebuild_bm25_index()


def _rebuild_bm25_index():
    """Rebuild BM25 index from knowledge table."""
    global BM25_INDEX, BM25_CORPUS, BM25_IDS
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Fetch all textual knowledge (facts, search results, drawings)
        cursor.execute("SELECT id, content FROM knowledge WHERE content IS NOT NULL")
        rows = cursor.fetchall()
        
        if not rows:
            print("[RAG] No knowledge found for BM25 index.")
            return

        BM25_IDS = [r[0] for r in rows]
        BM25_CORPUS = [r[1] for r in rows]
        
        # Tokenize (simple whitespace split is fine for BM25)
        tokenized_corpus = [doc.lower().split() for doc in BM25_CORPUS]
        BM25_INDEX = BM25Okapi(tokenized_corpus)
        
        print(f"[RAG] Rebuilt BM25 index with {len(rows)} documents")
        
    except Exception as e:
        print(f"[RAG] BM25 Build Error: {e}")
    finally:
        if 'conn' in locals(): conn.close()


async def _standardize_query(query: str) -> str:
    """Use Gemini 2.0 Flash to rewrite query for better retrieval."""
    if not os.getenv("GEMINI_API_KEY"):
        return query

    prompt = f"""Rewrite this user search into a concise, standard keyword query.
Remove conversational filler ("omg help", "can you tell me").
Keep specific error codes, version numbers, and technical terms.
Output ONLY the rewritten query.

Input: {query}
Output:"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=50
            )
        )
        clean = response.text.strip().replace('"', '')
        if len(clean) < 3 or len(clean) > len(query) * 2:
            return query
        return clean
    except:
        return query


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _init_db():
    """Initialize the SQLite database with required tables."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Main knowledge table - stores ALL learnable content
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            knowledge_type TEXT DEFAULT 'general',
            source TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Conversations table - full conversation history for context
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            username TEXT,
            channel_id TEXT,
            guild_id TEXT,
            user_message TEXT NOT NULL,
            gemgem_response TEXT NOT NULL,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add username column if it doesn't exist (for existing databases)
    try:
        cursor.execute("ALTER TABLE conversations ADD COLUMN username TEXT")
    except:
        pass  # Column already exists
    
    # Search results table - stores FULL search results for knowledge building
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS search_knowledge (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            full_results TEXT NOT NULL,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Image descriptions table - stores Gemini vision analysis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_knowledge (
            id TEXT PRIMARY KEY,
            image_url TEXT,
            user_context TEXT,
            gemini_description TEXT NOT NULL,
            gemgem_response TEXT,
            embedding TEXT,
            user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
    # Initialize search models (BM25 + Cross-Encoder)
    _init_search_models()


# Initialize on import
_init_db()


# ============== KNOWLEDGE STORAGE ==============

async def store_knowledge(
    content: str,
    knowledge_type: str = "general",
    source: str = None,
    metadata: dict = None
) -> Optional[str]:
    """
    Store any knowledge (search results, facts, etc.) for GemGem to learn from.
    
    Args:
        content: Full text content to store
        knowledge_type: Type (search, fact, wiki, etc.)
        source: Where this knowledge came from
        metadata: Additional metadata dict
    
    Returns:
        Knowledge ID if successful
    """
    embedding = await get_embedding(content[:2000])  # Embed first 2000 chars for relevance
    if not embedding:
        return None
    
    knowledge_id = f"know_{hashlib.md5(content.encode()).hexdigest()[:12]}_{int(datetime.now().timestamp())}"
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO knowledge 
               (id, content, embedding, knowledge_type, source, metadata) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (knowledge_id, content, json.dumps(embedding), knowledge_type, source, json.dumps(metadata or {}))
        )
        conn.commit()
        print(f"[RAG] Stored knowledge: {knowledge_type} ({len(content)} chars)")
        _rebuild_bm25_index()  # Keep keyword index fresh
        return knowledge_id
    except Exception as e:
        print(f"[RAG Store Error] {e}")
        return None
    finally:
        conn.close()


# ============== CONVERSATION STORAGE (SUMMARY RAG) ==============

async def store_conversation(
    user_message: str,
    gemgem_response: str,
    user_id: str = None,
    username: str = None,
    channel_id: str = None,
    guild_id: str = None
) -> Optional[str]:
    """
    Store a conversation exchange as a FACT, not a raw log.
    
    This is Summary RAG - we extract meaningful facts and discard chatter.
    
    Args:
        user_message: What the user said
        gemgem_response: What Astra replied
        user_id: Discord user ID
        username: Discord display name
        channel_id: Discord channel ID
        guild_id: Discord server ID
    
    Returns:
        Knowledge ID if a fact was stored, None if no meaningful fact
    """
    name = username or "User"
    
    # Skip very short messages (likely chatter)
    if len(user_message.strip()) < 15 and len(gemgem_response.strip()) < 50:
        print(f"[RAG] Skipping short exchange (no facts to extract)")
        return None
    
    # Extract fact from conversation
    print(f"[RAG] Attempting fact extraction for {name}: msg='{user_message[:60]}' resp='{gemgem_response[:60]}'")
    fact = await _extract_fact_from_conversation(name, user_message, gemgem_response)
    
    if not fact:
        print(f"[RAG] No meaningful fact in conversation with {name}")
        return None
    
    print(f"[RAG] ✅ Extracted fact: {fact[:100]}")
    
    # Store the fact as knowledge (not raw conversation)
    return await store_knowledge(
        content=fact,
        knowledge_type="user_fact",
        source=f"conversation_{name}",
        metadata={
            "username": name,
            "user_id": user_id,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "original_message": user_message[:200]  # Keep truncated original for reference
        }
    )


# ============== SEARCH STORAGE ==============

async def store_full_search(query: str, results: list[dict]) -> Optional[str]:
    """
    Store FULL search results (not just summary) for knowledge building.
    
    Args:
        query: Original search query
        results: List of search result dicts with title, url, content
    
    Returns:
        Search knowledge ID if successful
    """
    # Build full results string
    full_results = f"Search Query: {query}\n\n"
    for i, r in enumerate(results, 1):
        full_results += f"Result {i}:\n"
        full_results += f"Title: {r.get('title', 'N/A')}\n"
        full_results += f"URL: {r.get('url', 'N/A')}\n"
        full_results += f"Content: {r.get('content', 'N/A')}\n\n"
    
    # Also store as general knowledge for future retrieval
    await store_knowledge(
        content=full_results,
        knowledge_type="search",
        source="searxng",
        metadata={"query": query, "result_count": len(results)}
    )
    
    # Store in search-specific table too
    embedding = await get_embedding(f"Search about: {query}")
    search_id = f"search_{hashlib.md5(query.encode()).hexdigest()[:12]}_{int(datetime.now().timestamp())}"
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO search_knowledge 
               (id, query, full_results, embedding) 
               VALUES (?, ?, ?, ?)""",
            (search_id, query, full_results, json.dumps(embedding) if embedding else None)
        )
        conn.commit()
        print(f"[RAG] Stored full search: '{query}' ({len(results)} results)")
        return search_id
    except Exception as e:
        print(f"[RAG Search Error] {e}")
        return None
    finally:
        conn.close()


# ============== IMAGE STORAGE ==============

async def store_image_knowledge(
    gemini_description: str,
    image_url: str = None,
    user_context: str = None,
    gemgem_response: str = None,
    user_id: str = None
) -> Optional[str]:
    """
    Store Gemini vision analysis for knowledge building.
    
    Args:
        gemini_description: What Gemini saw in the image
        image_url: URL of the image
        user_context: What the user asked about the image
        gemgem_response: GemGem's response about the image
        user_id: Discord user ID
    
    Returns:
        Image knowledge ID if successful
    """
    # Create content for embedding
    content = f"Image analysis: {gemini_description}"
    if user_context:
        content = f"User asked about image: {user_context}\nImage shows: {gemini_description}"
    
    embedding = await get_embedding(content)
    
    img_id = f"img_{hashlib.md5(content.encode()).hexdigest()[:12]}_{int(datetime.now().timestamp())}"
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO image_knowledge 
               (id, image_url, user_context, gemini_description, gemgem_response, embedding, user_id) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (img_id, image_url, user_context, gemini_description, gemgem_response,
             json.dumps(embedding) if embedding else None, user_id)
        )
        conn.commit()
        print(f"[RAG] Stored image knowledge ({len(gemini_description)} chars)")
        return img_id
    except Exception as e:
        print(f"[RAG Image Error] {e}")
        return None
    finally:
        conn.close()


# ============== DRAWING STORAGE ==============

async def store_drawing_knowledge(
    user_request: str,
    enhanced_prompt: str,
    image_description: str,
    gemgem_critique: str,
    matched_characters: list = None,
    user_id: str = None,
    is_gdraw: bool = False,
    is_edit: bool = False
) -> Optional[str]:
    """
    Store drawing context for knowledge building.
    
    This allows GemGem to remember what she drew for follow-up questions like:
    "What kind of dog was that?" -> "I drew a Shiba Inu for you!"
    
    Args:
        user_request: Original user request (e.g., "draw a kitten")
        enhanced_prompt: AI-enhanced prompt used for generation
        image_description: Objective description of what was generated
        gemgem_critique: GemGem's reaction/comment about the drawing
        matched_characters: List of character names that were included
        user_id: Discord user ID who requested
        is_gdraw: Whether this was a guided draw
        is_edit: Whether this was an edit
        
    Returns:
        Drawing knowledge ID if successful
    """
    # Build comprehensive content for embedding
    draw_type = "edited" if is_edit else ("guided draw" if is_gdraw else "drew")
    
    content = f"I {draw_type} something for the user.\n"
    content += f"They asked for: {user_request}\n"
    
    if matched_characters:
        char_names = ", ".join(matched_characters)
        content += f"I included these characters: {char_names}\n"
    
    if image_description:
        content += f"The result shows: {image_description}\n"
    
    if gemgem_critique:
        content += f"My reaction: {gemgem_critique}"
    
    embedding = await get_embedding(content)
    
    draw_id = f"draw_{hashlib.md5(content.encode()).hexdigest()[:12]}_{int(datetime.now().timestamp())}"
    
    # Store in knowledge table with drawing type
    metadata = {
        "user_request": user_request,
        "enhanced_prompt": enhanced_prompt[:500] if enhanced_prompt else None,
        "characters": matched_characters or [],
        "is_gdraw": is_gdraw,
        "is_edit": is_edit
    }
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO knowledge 
               (id, content, embedding, knowledge_type, source, metadata) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (draw_id, content, json.dumps(embedding) if embedding else "[]", 
             "drawing", f"user_{user_id}", json.dumps(metadata))
        )
        conn.commit()
        print(f"[RAG] Stored drawing knowledge: '{user_request[:40]}...'")
        return draw_id
    except Exception as e:
        print(f"[RAG Drawing Error] {e}")
        return None
    finally:
        conn.close()


# ============== RETRIEVAL ==============


async def retrieve_relevant_knowledge(
    query: str,
    limit: int = 5,
    threshold: float = 0.78
) -> list[dict]:
    """
    Retrieve relevant knowledge using Hybrid Search + Re-ranking.
    
    1. Standardize Query (LLM rewrite)
    2. Vector Search (Semantic)
    3. Keyword Search (BM25)
    4. RRF Merge (Reciprocal Rank Fusion)
    5. Re-rank (Cross-Encoder)
    """
    # 1. Standardize Query
    clean_query = await _standardize_query(query)
    # print(f"[RAG] Raw: '{query}' -> Clean: '{clean_query}'")
    
    query_embedding = await get_query_embedding(clean_query)
    if not query_embedding: return []
    
    candidates = {}  # Map ID -> Item
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # --- VECTOR SEARCH (Semantic) ---
        # Scan Knowledge
        cursor.execute("SELECT id, content, embedding, knowledge_type FROM knowledge")
        for row in cursor.fetchall():
            if row[2]:
                try:
                    score = _cosine_similarity(query_embedding, json.loads(row[2]))
                    if score >= threshold - 0.15: # Lower threshold for hybrid candidates
                        candidates[row[0]] = {
                            "id": row[0],
                            "content": row[1],
                            "type": row[3],
                            "source": "knowledge",
                            "vector_score": score
                        }
                except: pass
                
        # Scan Conversations (Summary RAG)
        cursor.execute("SELECT id, user_message, gemgem_response, embedding, username FROM conversations")
        for row in cursor.fetchall():
            if row[3]:
                try:
                    score = _cosine_similarity(query_embedding, json.loads(row[3]))
                    if score >= threshold - 0.15:
                        username = row[4] or "Someone"
                        content = f"Chat - {username}: {row[1]} | Astra: {row[2]}"
                        candidates[row[0]] = {
                            "id": row[0],
                            "content": content,
                            "type": "conversation",
                            "source": "conversations",
                            "vector_score": score
                        }
                except: pass

        # --- KEYWORD SEARCH (BM25) ---
        if BM25_INDEX:
            tokenized_query = clean_query.lower().split()
            bm25_scores = BM25_INDEX.get_scores(tokenized_query)
            top_n = np.argsort(bm25_scores)[::-1][:20] # Top 20 BM25
            
            for idx in top_n:
                score = bm25_scores[idx]
                if score > 0:
                    doc_id = BM25_IDS[idx]
                    # Fetch content if not in candidates
                    if doc_id not in candidates:
                        content = BM25_CORPUS[idx]
                        candidates[doc_id] = {
                            "id": doc_id,
                            "content": content,
                            "type": "knowledge", # BM25 only tracks knowledge table
                            "source": "bm25",
                            "vector_score": 0.0 # No vector match
                        }
                    candidates[doc_id]["bm25_score"] = score

        # --- RE-RANKING (Cross-Encoder) ---
        if not candidates: return []
        
        final_results = list(candidates.values())
        
        if CROSS_ENCODER:
            pairs = [[clean_query, item["content"]] for item in final_results]
            rerank_scores = CROSS_ENCODER.predict(pairs)
            
            for i, item in enumerate(final_results):
                item["rerank_score"] = float(rerank_scores[i])
                
            # Filter by Re-rank Score (Logits > 0 means likely relevant)
            final_results = [item for item in final_results if item["rerank_score"] > 0.0]
            
            # Sort by Re-rank Score
            final_results.sort(key=lambda x: x["rerank_score"], reverse=True)
            
            # print(f"[RAG] Re-ranked top match: {final_results[0]['rerank_score']:.2f} | {final_results[0]['content'][:50]}")
        else:
            # Fallback to Vector Score
            final_results.sort(key=lambda x: x.get("vector_score", 0), reverse=True)

        return final_results[:limit]
    
    except Exception as e:
        print(f"[RAG Retrieve Error] {e}")
        return []
    finally:
        conn.close()


def format_knowledge_for_context(knowledge: list[dict]) -> str:
    """Format retrieved knowledge for injection into LLM context."""
    if not knowledge:
        return ""
    
    formatted = ["MEMORY FACTS:"]
    for i, item in enumerate(knowledge, 1):
        formatted.append(f"- {item['content']}")
    
    return "\n".join(formatted)


# ============== LEGACY COMPATIBILITY ==============

async def store_memory(content: str, memory_type: str = "chat", metadata: dict = None) -> Optional[str]:
    """Legacy function - routes to store_knowledge."""
    return await store_knowledge(content, knowledge_type=memory_type, metadata=metadata)


async def retrieve_memories(query: str, limit: int = 5, memory_type: str = None, threshold: float = 0.7) -> list[dict]:
    """Legacy function - routes to retrieve_relevant_knowledge."""
    return await retrieve_relevant_knowledge(query, limit, threshold)


async def store_search_result(query: str, results: str) -> bool:
    """Legacy function - for backward compatibility."""
    # Parse old format and convert
    await store_knowledge(f"Search: {query}\n{results}", knowledge_type="search", source="legacy")
    return True


def format_memories_for_context(memories: list[dict]) -> str:
    """Legacy function - routes to format_knowledge_for_context."""
    return format_knowledge_for_context(memories)
