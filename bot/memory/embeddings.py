"""Google Embeddings Client - Free tier text embeddings."""
import os
from google import genai
from typing import Optional


# Configure Google AI Client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
    if not client:
        print("[Embeddings] No GEMINI_API_KEY set")
        return None

    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config={"task_type": "retrieval_document"}
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[Embeddings Error] {e}")
        return None


async def get_query_embedding(text: str) -> Optional[list[float]]:
    """Get embedding optimized for search queries."""
    if not client:
        return None

    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config={"task_type": "retrieval_query"}
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[Embeddings Error] {e}")
        return None
