"""Backend implementations for Memory Alaya"""

from .duckdb_backend import DuckDBBackend

# Optional pgvector backend
try:
    from .pgvector_backend import PgVectorBackend
    __all__ = ["DuckDBBackend", "PgVectorBackend"]
except ImportError:
    PgVectorBackend = None
    __all__ = ["DuckDBBackend"]
