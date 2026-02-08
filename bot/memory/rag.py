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
from datetime import datetime
from typing import Optional
import numpy as np

from memory.embeddings import get_embedding, get_query_embedding


DATABASE_PATH = os.getenv("RAG_DATABASE", "/app/data/memory.db")
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "http://host.docker.internal:1234")
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "qwen3-vl-32b-instruct-heretic-v2-i1")


async def _extract_fact_from_conversation(username: str, user_message: str, astra_response: str) -> Optional[str]:
    """
    Extract a factual statement from a conversation, or return None if it's just chatter.
    
    This is the core of Summary RAG - we only store meaningful facts, not raw logs.
    
    Examples:
    - "Hiep: I'm working on a Discord bot" → "Hiep is developing a Discord bot."
    - "Hiep: lol k" → None (no meaningful fact)
    - "Hiep: I prefer Korean food" → "Hiep prefers Korean food."
    """
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
        payload = {
            "model": CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,  # Low temp for consistent extraction
            "max_tokens": 100
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LMSTUDIO_HOST}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                result = data["choices"][0]["message"]["content"].strip()
                
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
    fact = await _extract_fact_from_conversation(name, user_message, gemgem_response)
    
    if not fact:
        print(f"[RAG] No meaningful fact in conversation with {name}")
        return None
    
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
        cursor.execute("SELECT id, user_message, gemgem_response, embedding, username FROM conversations")
        for row in cursor.fetchall():
            if row[3]:
                stored_embedding = json.loads(row[3])
                similarity = _cosine_similarity(query_embedding, stored_embedding)
                if similarity >= threshold:
                    username = row[4] or "Someone"
                    results.append({
                        "id": row[0],
                        "content": f"Previous chat - {username}: {row[1][:200]} | Astra: {row[2][:200]}",
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
    
    formatted = ["MEMORY FACTS - Cite with [💡1], [💡2] etc when using these:"]
    for i, item in enumerate(knowledge, 1):
        formatted.append(f"[💡{i}] {item['content']}")
    
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
