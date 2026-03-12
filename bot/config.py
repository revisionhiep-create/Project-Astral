"""
Configuration constants for Astra Discord Bot.
Centralizes magic numbers and configurable values.
"""
import os


class BotConfig:
    """Bot-wide configuration settings."""

    # ========== Memory & History Settings ==========
    SUMMARY_INTERVAL_MESSAGES = int(os.getenv("SUMMARY_INTERVAL", "40"))
    """Number of messages before triggering automatic summarization"""

    MAX_CONVERSATION_HISTORY = int(os.getenv("MAX_CONVERSATION_HISTORY", "100"))
    """Maximum number of messages to keep in rolling window"""

    # ========== RAG/Memory Settings ==========
    RAG_FACT_LIMIT = int(os.getenv("RAG_FACT_LIMIT", "3"))
    """Number of facts to retrieve from long-term memory"""

    DUPLICATE_SIMILARITY_THRESHOLD = float(os.getenv("DUPLICATE_THRESHOLD", "0.90"))
    """Similarity threshold for duplicate fact detection"""

    RETRIEVAL_SIMILARITY_THRESHOLD = float(os.getenv("RETRIEVAL_THRESHOLD", "0.78"))
    """Similarity threshold for knowledge retrieval"""

    # ========== AI Model Token Limits ==========
    TOOL_DECISION_TOKENS = int(os.getenv("TOOL_DECISION_TOKENS", "256"))
    """Token limit for tool decision making"""

    FACT_EXTRACTION_TOKENS = int(os.getenv("FACT_EXTRACTION_TOKENS", "100"))
    """Token limit for fact extraction from conversations"""

    SUMMARIZATION_TOKENS = int(os.getenv("SUMMARIZATION_TOKENS", "1200"))
    """Token limit for conversation summarization"""

    DEFAULT_RESPONSE_TOKENS = int(os.getenv("DEFAULT_RESPONSE_TOKENS", "8000"))
    """Default token limit for responses (with context)"""

    RESPONSE_TOKENS_NO_CONTEXT = int(os.getenv("RESPONSE_TOKENS_NO_CONTEXT", "4000"))
    """Token limit for responses without search context"""

    # ========== Greeting Detection ==========
    GREETING_PATTERNS = [
        'hi', 'hello', 'hey', 'sup', 'yo',
        'morning', 'evening', 'night',
        'honey', 'babe', 'love'
    ]
    """Patterns for detecting greeting messages"""

    GREETING_MIN_LENGTH = int(os.getenv("GREETING_MIN_LENGTH", "30"))
    """Minimum message length to avoid being classified as just a greeting"""

    # ========== Image & Vision Settings ==========
    IMAGE_ANALYSIS_TIMEOUT = int(os.getenv("IMAGE_ANALYSIS_TIMEOUT", "30"))
    """Timeout in seconds for image analysis"""

    MAX_RECENT_IMAGES = int(os.getenv("MAX_RECENT_IMAGES", "3"))
    """Maximum number of recent images to keep in context"""

    # ========== Admin Settings ==========
    ADMIN_IDS = {
        int(id_str) for id_str in os.getenv("ADMIN_IDS", "69353483425292288,1365378902301741071").split(",")
    }
    """Set of Discord user IDs with admin privileges"""

    GEMGEM_BOT_ID = int(os.getenv("GEMGEM_BOT_ID", "1458550716225425560"))
    """Discord ID of GemGem bot for cross-bot context awareness"""


class AIConfig:
    """AI-specific configuration."""

    # ========== Generation Config Defaults ==========
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "1.0"))
    """Default temperature for AI generation"""

    DEFAULT_TOP_P = float(os.getenv("DEFAULT_TOP_P", "0.95"))
    """Default top_p for AI generation"""

    # ========== Model Selection ==========
    GROK_MODEL = os.getenv("GROK_MODEL", "grok-2-1212")
    """Grok model to use for chat responses"""

    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    """Gemini model to use for vision and embeddings"""


class MemoryConfig:
    """Memory system configuration."""

    # ========== Fact Extraction Settings ==========
    MIN_USER_MESSAGE_LENGTH = int(os.getenv("MIN_USER_MESSAGE_LENGTH", "15"))
    """Minimum user message length for fact extraction"""

    MIN_RESPONSE_LENGTH = int(os.getenv("MIN_RESPONSE_LENGTH", "50"))
    """Minimum response length for fact extraction"""

    MAX_CONTEXT_WINDOW = int(os.getenv("MAX_CONTEXT_WINDOW", "5"))
    """Number of previous messages to include in fact extraction context"""

    # ========== DuckDB Settings ==========
    MEMORY_ALAYA_DB_PATH = os.getenv("MEMORY_ALAYA_DB_PATH", None)
    """Custom path for Memory Alaya DuckDB database (default: auto)"""
