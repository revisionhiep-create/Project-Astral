"""Shared Memory System for Project Astral and GemGem
Unified RAG implementation with DuckDB FTS and optional pgvector support.
"""

from .memory_alaya import MemoryAlaya

__all__ = ["MemoryAlaya"]
__version__ = "1.0.0"
