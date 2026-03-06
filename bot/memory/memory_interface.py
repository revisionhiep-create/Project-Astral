"""Memory Interface - Clean integration wrapper for Memory Alaya.

This provides a drop-in replacement for the old rag.py, focusing ONLY on user facts.
Uses the unified Memory Alaya system with DuckDB backend.

Changes from rag.py:
- Uses Memory Alaya instead of direct SQLite
- Stores ONLY user facts (no search results, images, drawings)
- Same API as old rag.py for backward compatibility
- Cleaner architecture, shared backend

v2.0.0: Memory Alaya integration
"""

import os
import sys
import asyncio
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types

# Add parent directory to path to access shared_memory as a package
parent_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')
)
if parent_path not in sys.path:
    sys.path.insert(0, parent_path)

# Import Memory Alaya as a package (this handles relative imports correctly)
from shared_memory import MemoryAlaya
from memory.embeddings import get_embedding, get_query_embedding


# Initialize Gemini client for fact extraction
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Initialize Memory Alaya with DuckDB backend
# Use shared database location mounted from host
MEMORY_DB_PATH = "/app/shared_memory/memory.duckdb"

memory_alaya = None


def _init_memory():
    """Initialize Memory Alaya (lazy initialization)."""
    global memory_alaya
    if memory_alaya is None:
        memory_alaya = MemoryAlaya(
            backend="duckdb",
            database_path=MEMORY_DB_PATH
        )
        print(f"[Memory Interface] Initialized Memory Alaya at {MEMORY_DB_PATH}")


# Initialize on import
_init_memory()


# ============== FACT EXTRACTION ==============

async def _extract_fact_from_conversation(
    username: str,
    user_message: str,
    astra_response: str,
    conversation_context: str = None
) -> Optional[str]:
    """
    Extract a factual statement from a conversation using Gemini 2.0 Flash.

    This is the SAME logic as rag.py - we only extract meaningful, long-term facts.

    Args:
        username: User's display name
        user_message: Current user message
        astra_response: Current bot response
        conversation_context: Last 3-5 messages for better context (optional)

    Returns:
        Extracted fact or None if no meaningful fact
    """
    if not gemini_client:
        return None

    # Build prompt with optional context
    if conversation_context:
        prompt = f"""Extract ONE meaningful, long-term factual statement about {username} from this conversation, or respond with exactly "NONE" if there's nothing worth remembering.

Recent Conversation Context (for reference):
{conversation_context}

Current Exchange:
[{username}]: {user_message}
[Astra]: {astra_response}

ONLY extract facts that meet ALL these criteria:
1. DECLARATIVE & STABLE: Lasting information, not temporary reactions or emotions
2. ACTIONABLE & USEFUL: Information that will be relevant in future conversations
3. SPECIFIC & CONCRETE: Names, projects, skills, preferences with clear details

DO NOT extract:
❌ Emotional reactions ("likes X", "dislikes Y" from casual chat)
❌ Temporary states ("is typing", "said hi", "gave high five")
❌ Generic preferences without context ("enjoys pizza")
❌ Actions without lasting meaning ("showed something", "made a comment")
❌ Questions without answers
❌ Hypothetical statements ("might do X")
❌ Small talk, greetings, emojis, reactions

EXTRACT ONLY:
✅ Professional information (job title, company, projects)
✅ Technical skills and expertise
✅ Long-term hobbies with specific details
✅ Relationships and connections (team members, collaborators)
✅ Personal background (location, education, family structure)
✅ Specific preferences with context (programming language for backend)

Examples of GOOD facts:
- "{username} is a software engineer at Google working on search infrastructure"
- "{username} is developing a Discord bot called GemGem using Python"
- "{username} plays competitive chess and has a 2000 ELO rating"

Examples of BAD facts (return NONE):
- "{username} dislikes pigeons" (too trivial, from casual high five)
- "{username} showed Astral something" (no useful information)
- "{username} made a comment" (vague, no value)
- "{username} wants to see birds" (temporary desire)

Format: "{username} [substantial fact]"
If the conversation contains no substantial long-term information, respond with: NONE

Respond with the fact or NONE:"""
    else:
        # Single message mode (fallback)
        prompt = f"""Extract ONE meaningful, long-term factual statement about {username} from this conversation, or respond with exactly "NONE" if there's nothing worth remembering.

Conversation:
[{username}]: {user_message}
[Astra]: {astra_response}

ONLY extract facts that meet ALL these criteria:
1. DECLARATIVE & STABLE: Lasting information, not temporary reactions or emotions
2. ACTIONABLE & USEFUL: Information that will be relevant in future conversations
3. SPECIFIC & CONCRETE: Names, projects, skills, preferences with clear details

DO NOT extract:
❌ Emotional reactions ("likes X", "dislikes Y" from casual chat)
❌ Temporary states ("is typing", "said hi", "gave high five")
❌ Generic preferences without context ("enjoys pizza")
❌ Actions without lasting meaning ("showed something", "made a comment")
❌ Questions without answers
❌ Hypothetical statements ("might do X")
❌ Small talk, greetings, emojis, reactions

EXTRACT ONLY:
✅ Professional information (job title, company, projects)
✅ Technical skills and expertise
✅ Long-term hobbies with specific details
✅ Relationships and connections (team members, collaborators)
✅ Personal background (location, education, family structure)
✅ Specific preferences with context (programming language for backend)

Examples of GOOD facts:
- "{username} is a software engineer at Google working on search infrastructure"
- "{username} is developing a Discord bot called GemGem using Python"
- "{username} plays competitive chess and has a 2000 ELO rating"

Examples of BAD facts (return NONE):
- "{username} dislikes pigeons" (too trivial, from casual high five)
- "{username} showed Astral something" (no useful information)
- "{username} made a comment" (vague, no value)
- "{username} wants to see birds" (temporary desire)

Format: "{username} [substantial fact]"
If the conversation contains no substantial long-term information, respond with: NONE

Respond with the fact or NONE:"""

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
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

        print(f"[Memory Interface] Extracted fact: {result[:80]}...")
        return result

    except Exception as e:
        print(f"[Memory Interface] Fact extraction failed: {e}")
        return None


async def _is_duplicate_fact(
    new_fact: str,
    user_id: str,
    similarity_threshold: float = 0.90
) -> bool:
    """
    Check if a fact is a duplicate of an existing fact using vector similarity.

    Args:
        new_fact: The newly extracted fact
        user_id: User ID to scope the search
        similarity_threshold: Cosine similarity threshold (0.90 recommended)

    Returns:
        True if duplicate found, False otherwise
    """
    try:
        # Get embedding for new fact
        new_embedding = await get_embedding(new_fact)
        if not new_embedding:
            return False  # Can't check, assume not duplicate

        # Query existing facts for this user
        existing_facts = await memory_alaya.recall(
            query=new_fact,
            query_embedding=new_embedding,
            top_k=5,
            filters={"user_id": user_id},
            similarity_threshold=similarity_threshold,
            rerank=False  # Don't need reranking for duplicate detection
        )

        # Check if any result is above threshold
        for fact in existing_facts:
            if fact.get("vector_score", 0.0) >= similarity_threshold:
                print(f"[Memory Interface] Duplicate detected (similarity={fact['vector_score']:.2f}): '{fact['content'][:60]}...'")
                return True

        return False

    except Exception as e:
        print(f"[Memory Interface] Duplicate check error: {e}")
        return False  # Error, assume not duplicate to be safe


# ============== CONVERSATION STORAGE (SUMMARY RAG) ==============

async def store_conversation(
    user_message: str,
    gemgem_response: str,
    user_id: str = None,
    username: str = None,
    channel_id: str = None,
    guild_id: str = None,
    conversation_context: str = None
) -> Optional[str]:
    """
    Store a conversation exchange as a FACT, not a raw log.

    This is Summary RAG - we extract meaningful facts and discard chatter.
    Uses multi-message context window for better fact extraction.

    Args:
        user_message: What the user said (current message)
        gemgem_response: What Astra replied (current response)
        user_id: Discord user ID
        username: Discord display name
        channel_id: Discord channel ID
        guild_id: Discord server ID
        conversation_context: Last 3-5 messages for context (optional but recommended)

    Returns:
        Knowledge ID if a fact was stored, None if no meaningful fact
    """
    name = username or "User"

    # Skip very short messages (likely chatter)
    if len(user_message.strip()) < 15 and len(gemgem_response.strip()) < 50:
        print(f"[Memory Interface] Skipping short exchange (no facts to extract)")
        return None

    # Extract fact from conversation (with context if provided)
    context_preview = conversation_context[:60] if conversation_context else "single message"
    print(f"[Memory Interface] Attempting fact extraction for {name}: msg='{user_message[:60]}' | context='{context_preview}'")
    fact = await _extract_fact_from_conversation(name, user_message, gemgem_response, conversation_context)

    if not fact:
        print(f"[Memory Interface] No meaningful fact in conversation with {name}")
        return None

    # Check for duplicate before storing
    if user_id:
        is_duplicate = await _is_duplicate_fact(fact, user_id)
        if is_duplicate:
            print(f"[Memory Interface] Skipping duplicate fact: {fact[:80]}...")
            return None

    print(f"[Memory Interface] Extracted fact: {fact[:100]}")

    # Get embedding for the fact
    embedding = await get_embedding(fact)
    if not embedding:
        print(f"[Memory Interface] Failed to generate embedding for fact")
        return None

    # Store in Memory Alaya
    try:
        knowledge_id = await memory_alaya.store(
            content=fact,
            embedding=embedding,
            knowledge_type="user_fact",
            source=f"conversation_{name}",
            metadata={
                "username": name,
                "user_id": user_id,
                "channel_id": channel_id,
                "guild_id": guild_id,
                "original_message": user_message[:200]  # Keep truncated original for reference
            },
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id
        )

        print(f"[Memory Interface] Stored fact with ID: {knowledge_id}")
        return knowledge_id

    except Exception as e:
        print(f"[Memory Interface] Storage error: {e}")
        return None


# ============== RETRIEVAL ==============

async def retrieve_relevant_knowledge(
    query: str,
    limit: int = 5,
    threshold: float = 0.78,
    user_id: str = None,
    guild_id: str = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant knowledge using Hybrid Search + Re-ranking.

    This uses Memory Alaya's recall system with the same interface as old rag.py.

    Args:
        query: User's query or message
        limit: Maximum number of results
        threshold: Minimum similarity threshold (0.78 default like rag.py)
        user_id: Optional user ID filter
        guild_id: Optional guild ID filter

    Returns:
        List of knowledge items with content, score, metadata
    """
    try:
        # Get query embedding
        query_embedding = await get_query_embedding(query)
        if not query_embedding:
            return []

        # Build filters
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if guild_id:
            filters["guild_id"] = guild_id

        # Recall from Memory Alaya
        results = await memory_alaya.recall(
            query=query,
            query_embedding=query_embedding,
            top_k=limit,
            filters=filters if filters else None,
            similarity_threshold=threshold,
            rerank=True  # Use Gemini reranking
        )

        # Format results to match old rag.py structure
        formatted_results = []
        for result in results:
            formatted_results.append({
                "id": result.get("id"),
                "content": result.get("content"),
                "type": result.get("knowledge_type", "user_fact"),
                "source": result.get("source", "knowledge"),
                "vector_score": result.get("vector_score", 0.0),
                "rerank_score": result.get("rerank_score", 0.0),
                "metadata": result.get("metadata", {})
            })

        return formatted_results

    except Exception as e:
        print(f"[Memory Interface] Retrieval error: {e}")
        return []


def format_knowledge_for_context(
    knowledge: List[Dict[str, Any]],
    current_username: str = None
) -> str:
    """
    Format retrieved knowledge for injection into LLM context.

    Includes username labels to help the LLM distinguish between facts about
    different users, and system instructions for appropriate usage.

    Args:
        knowledge: List of knowledge items from retrieval
        current_username: The username of the person currently chatting (optional)

    Returns:
        Formatted string for LLM context
    """
    if not knowledge:
        return ""

    formatted = ["RELEVANT MEMORY FACTS:"]

    # Add system instruction for the LLM
    if current_username:
        formatted.append(
            f"(Current conversation is with {current_username}. "
            f"Use facts about other users only when directly relevant to the topic.)"
        )

    for i, item in enumerate(knowledge, 1):
        content = item['content']
        metadata = item.get('metadata', {})
        username = metadata.get('username', None)
        knowledge_type = item.get('type', 'general')

        # Label user-specific facts with username
        if knowledge_type == 'user_fact' and username:
            formatted.append(f"- [{username}] {content}")
        # General knowledge - no user label needed
        else:
            formatted.append(f"- {content}")

    return "\n".join(formatted)


# ============== REMOVED FUNCTIONS ==============
# These functions are NOT implemented - use only for user facts now

async def store_full_search(*args, **kwargs):
    """
    DEPRECATED: Search storage removed.
    Memory Alaya interface focuses ONLY on user facts.
    """
    print("[Memory Interface] WARNING: store_full_search() is deprecated and does nothing")
    return None


async def store_image_knowledge(*args, **kwargs):
    """
    DEPRECATED: Image storage removed.
    Memory Alaya interface focuses ONLY on user facts.
    """
    print("[Memory Interface] WARNING: store_image_knowledge() is deprecated and does nothing")
    return None


async def store_drawing_knowledge(*args, **kwargs):
    """
    DEPRECATED: Drawing storage removed.
    Memory Alaya interface focuses ONLY on user facts.
    """
    print("[Memory Interface] WARNING: store_drawing_knowledge() is deprecated and does nothing")
    return None


# ============== LEGACY COMPATIBILITY ==============

async def store_knowledge(
    content: str,
    knowledge_type: str = "user_fact",
    source: str = None,
    metadata: dict = None
) -> Optional[str]:
    """
    Legacy function for direct knowledge storage.

    Note: This bypasses fact extraction. Use store_conversation() for normal usage.
    """
    try:
        # Get embedding
        embedding = await get_embedding(content)
        if not embedding:
            return None

        # Store in Memory Alaya
        knowledge_id = await memory_alaya.store(
            content=content,
            embedding=embedding,
            knowledge_type=knowledge_type,
            source=source,
            metadata=metadata or {},
            user_id=metadata.get("user_id") if metadata else None,
            guild_id=metadata.get("guild_id") if metadata else None,
            channel_id=metadata.get("channel_id") if metadata else None
        )

        return knowledge_id

    except Exception as e:
        print(f"[Memory Interface] Store knowledge error: {e}")
        return None


async def store_memory(content: str, memory_type: str = "chat", metadata: dict = None) -> Optional[str]:
    """Legacy function - routes to store_knowledge."""
    return await store_knowledge(content, knowledge_type=memory_type, metadata=metadata)


async def retrieve_memories(query: str, limit: int = 5, memory_type: str = None, threshold: float = 0.7) -> List[Dict[str, Any]]:
    """Legacy function - routes to retrieve_relevant_knowledge."""
    return await retrieve_relevant_knowledge(query, limit, threshold)


def format_memories_for_context(memories: List[Dict[str, Any]]) -> str:
    """Legacy function - routes to format_knowledge_for_context."""
    return format_knowledge_for_context(memories)


# ============== CLEANUP ==============

def close():
    """Close Memory Alaya connection."""
    global memory_alaya
    if memory_alaya:
        memory_alaya.close()
        memory_alaya = None
        print("[Memory Interface] Closed Memory Alaya connection")
