# Memory module - Memory Alaya integration
# Now using unified Memory Alaya backend (v2.0.0)
from memory.memory_interface import (
    store_knowledge,
    store_conversation,
    store_full_search,
    store_image_knowledge,
    store_drawing_knowledge,
    retrieve_relevant_knowledge,
    format_knowledge_for_context,
    # Legacy compatibility
    store_memory,
    retrieve_memories,
    format_memories_for_context,
    close
)
from memory.embeddings import get_embedding, get_query_embedding

__all__ = [
    "store_knowledge",
    "store_conversation",
    "store_full_search",
    "store_image_knowledge",
    "store_drawing_knowledge",
    "retrieve_relevant_knowledge",
    "format_knowledge_for_context",
    "store_memory",
    "retrieve_memories",
    "format_memories_for_context",
    "get_embedding",
    "get_query_embedding",
    "close"
]
