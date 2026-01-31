"""Google Embeddings Client - Free tier text embeddings."""
import os
import google.generativeai as genai
from typing import Optional


# Configure Google AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Get embedding vector for text using Google's free embedding model.
    
    Args:
        text: Text to embed
    
    Returns:
        768-dimensional embedding vector, or None on error
    """
    if not GEMINI_API_KEY:
        print("[Embeddings] No GEMINI_API_KEY set")
        return None
    
    try:
        # Use the embedding model
        result = genai.embed_content(
            model="models/text-embedding-004",
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
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_query"
        )
        return result["embedding"]
    except Exception as e:
        print(f"[Embeddings Error] {e}")
        return None
