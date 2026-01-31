"""RAG Vector Store - SQLite-based semantic memory with full knowledge storage."""
import os
import json
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional
import numpy as np

from memory.embeddings import get_embedding, get_query_embedding


DATABASE_PATH = os.getenv("RAG_DATABASE", "/app/data/memory.db")


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
            channel_id TEXT,
            guild_id TEXT,
            user_message TEXT NOT NULL,
            gemgem_response TEXT NOT NULL,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
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
        return knowledge_id
    except Exception as e:
        print(f"[RAG Store Error] {e}")
        return None
    finally:
        conn.close()


# ============== CONVERSATION STORAGE ==============

async def store_conversation(
    user_message: str,
    gemgem_response: str,
    user_id: str = None,
    channel_id: str = None,
    guild_id: str = None
) -> Optional[str]:
    """
    Store a complete conversation exchange for context and learning.
    
    Args:
        user_message: What the user said
        gemgem_response: What GemGem replied
        user_id: Discord user ID
        channel_id: Discord channel ID
        guild_id: Discord server ID
    
    Returns:
        Conversation ID if successful
    """
    # Create combined content for embedding
    combined = f"User: {user_message}\nGemGem: {gemgem_response}"
    embedding = await get_embedding(combined)
    
    conv_id = f"conv_{hashlib.md5(combined.encode()).hexdigest()[:12]}_{int(datetime.now().timestamp())}"
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO conversations 
               (id, user_id, channel_id, guild_id, user_message, gemgem_response, embedding) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (conv_id, user_id, channel_id, guild_id, user_message, gemgem_response, 
             json.dumps(embedding) if embedding else None)
        )
        conn.commit()
        print(f"[RAG] Stored conversation ({len(user_message)} + {len(gemgem_response)} chars)")
        return conv_id
    except Exception as e:
        print(f"[RAG Conversation Error] {e}")
        return None
    finally:
        conn.close()


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
    threshold: float = 0.65
) -> list[dict]:
    """
    Retrieve relevant knowledge from ALL tables for context.
    
    Args:
        query: Search query
        limit: Max results to return
        threshold: Minimum similarity score
    
    Returns:
        List of relevant knowledge items with scores
    """
    query_embedding = await get_query_embedding(query)
    if not query_embedding:
        return []
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    results = []
    
    try:
        # Search knowledge table
        cursor.execute("SELECT id, content, embedding, knowledge_type FROM knowledge")
        for row in cursor.fetchall():
            if row[2]:  # Has embedding
                stored_embedding = json.loads(row[2])
                similarity = _cosine_similarity(query_embedding, stored_embedding)
                if similarity >= threshold:
                    results.append({
                        "id": row[0],
                        "content": row[1][:500],  # Truncate for context
                        "type": row[3],
                        "source": "knowledge",
                        "score": similarity
                    })
        
        # Search conversations
        cursor.execute("SELECT id, user_message, gemgem_response, embedding FROM conversations")
        for row in cursor.fetchall():
            if row[3]:
                stored_embedding = json.loads(row[3])
                similarity = _cosine_similarity(query_embedding, stored_embedding)
                if similarity >= threshold:
                    results.append({
                        "id": row[0],
                        "content": f"Previous chat - User: {row[1][:200]} | GemGem: {row[2][:200]}",
                        "type": "conversation",
                        "source": "conversations",
                        "score": similarity
                    })
        
        # Search image knowledge
        cursor.execute("SELECT id, gemini_description, user_context, embedding FROM image_knowledge")
        for row in cursor.fetchall():
            if row[3]:
                stored_embedding = json.loads(row[3])
                similarity = _cosine_similarity(query_embedding, stored_embedding)
                if similarity >= threshold:
                    results.append({
                        "id": row[0],
                        "content": f"Image context: {row[1][:300]}",
                        "type": "image",
                        "source": "image_knowledge",
                        "score": similarity
                    })
        
        # Sort by score and return top results
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    except Exception as e:
        print(f"[RAG Retrieve Error] {e}")
        return []
    finally:
        conn.close()


def format_knowledge_for_context(knowledge: list[dict]) -> str:
    """Format retrieved knowledge for injection into LLM context."""
    if not knowledge:
        return ""
    
    formatted = []
    for item in knowledge:
        formatted.append(f"- [{item['type']}] {item['content']}")
    
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
