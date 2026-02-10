"""Google Embeddings Client - Free tier text embeddings."""
import os
import google.generativeai as genai
from typing import Optional


# Configure Google AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Model: gemini-embedding-001 (text-embedding-004 was shut down Jan 14 2026)
EMBEDDING_MODEL = "models/gemini-embedding-001"


async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Get embedding vector for text using Google's embedding model.
    
    Args:
        text: Text to embed
    
    Returns:
        Embedding vector, or None on error
    """
    if not GEMINI_API_KEY:
        print("[Embeddings] No GEMINI_API_KEY set")
        return None
    
    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document"
        )
        return result["embedding"]
    except Exception as e:
        print(f"[Embeddings Error] {e}")
        return None


async def get_query_embedding(text: str) -> Optional[list[float]]:
    """Get embedding optimized for search queries."""
    if not GEMINI_API_KEY:
        return None
    
    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_query"
        )
        return result["embedding"]
    except Exception as e:
        print(f"[Embeddings Error] {e}")
        return None
