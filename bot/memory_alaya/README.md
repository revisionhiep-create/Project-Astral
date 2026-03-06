# Memory Alaya - Unified Memory System

A unified RAG (Retrieval-Augmented Generation) system shared between **Project Astral** and **GemGem** Discord bots.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Memory Alaya                           │
│                 (Abstraction Layer)                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  • Hybrid Search (Vector + BM25 Keyword)                   │
│  • Gemini 2.5 Flash Reranking                              │
│  • Metadata Filtering (user_id, guild_id, channel_id)      │
│  • Unified API for both bots                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
        ┌─────────────────┴─────────────────┐
        ↓                                   ↓
   ┌─────────┐                        ┌──────────┐
   │ DuckDB  │                        │ pgvector │
   │ Backend │                        │ Backend  │
   └─────────┘                        └──────────┘
   (Default)                          (Production)
```

## How Memory Retrieval Works

### 1. **Fact Storage**

Both bots extract user facts using **Gemini 2.0 Flash**:

**Project Astral** (`memory/memory_interface.py`):
```python
await store_conversation(
    username="Alice",
    user_message="I love cats",
    astra_response="That's wonderful!",
    user_id="123",
    guild_id="456"
)
```

**GemGem** (`utils/memory_interface.py`):
```python
await memory.store_fact(
    fact="Alice loves cats",
    user_id="123",
    user_name="Alice",
    guild_id="456"
)
```

### 2. **Fact Retrieval - Hybrid Search**

When a user asks a question, the system performs **3-stage retrieval**:

#### Stage 1: Vector Search (Semantic)
- Generates embedding using `gemini-embedding-001` (3072-dim)
- Finds semantically similar facts using cosine similarity
- Threshold: 0.63 (default)

#### Stage 2: BM25 Keyword Search
- Tokenizes query and performs keyword matching
- Uses Okapi BM25 algorithm
- Combines with vector scores

#### Stage 3: Gemini Reranking
- Re-scores top candidates using **Gemini 2.5 Flash**
- Cross-encoder scoring (0.0-10.0 scale)
- Ensures best relevance

**Project Astral** (`memory/memory_interface.py`):
```python
facts = await retrieve_relevant_knowledge(
    query="What does Alice like?",
    limit=5,
    threshold=0.78,
    user_id="123"  # Optional filter
)
```

**GemGem** (`utils/memory_interface.py`):
```python
facts = await memory.recall_facts(
    message="What does Alice like?",
    user_id="123",
    n_results=3,
    similarity_threshold=0.63
)
```

### 3. **Context Injection**

Retrieved facts are formatted and injected into the LLM context:

```
<MEMORY>
Things you remember:
- Alice loves cats (vector_score: 0.89, rerank_score: 8.5)
- Alice has 3 cats named Whiskers, Mittens, and Shadow (vector_score: 0.82, rerank_score: 7.8)
</MEMORY>
```

## Scripts & Utilities

### Query Memories (New!)

Interactive tool to query and inspect the shared memory database:

```bash
# Interactive mode
cd shared_memory
python query_memories.py

# Direct query
python query_memories.py "What does Alice like?"

# List all facts
python query_memories.py --list

# Get statistics
python query_memories.py --stats

# Query without reranking
python query_memories.py --no-rerank "cats"
```

**Commands in Interactive Mode:**
- `query <text>` - Search for facts
- `list [n]` - List all facts (optional limit)
- `stats` - Show database statistics
- `quit` - Exit

### Test Scripts

**GemGem**:
```bash
cd GemGem-Docker-Live
python utils/test_memory_interface.py
```

Tests:
- ✅ Fact storage
- ✅ Fact recall (with/without filters)
- ✅ Legacy SearchCache interface compatibility
- ✅ Statistics retrieval

## Database Schema

**DuckDB**: `shared_memory/memory.duckdb`

```sql
CREATE TABLE knowledge (
    id VARCHAR PRIMARY KEY,
    content TEXT NOT NULL,
    embedding FLOAT[3072],
    knowledge_type VARCHAR,
    source VARCHAR,
    user_id VARCHAR,
    user_name VARCHAR,
    guild_id VARCHAR,
    channel_id VARCHAR,
    created_at TIMESTAMP,
    metadata JSON
);

CREATE INDEX idx_user_id ON knowledge(user_id);
CREATE INDEX idx_guild_id ON knowledge(guild_id);
```

## Configuration

### Environment Variables

Required:
- `GEMINI_API_KEY` - For embeddings and reranking

### Database Paths

**Inside Docker Containers**:
- Project Astral: `/app/shared_memory/memory.duckdb`
- GemGem: `/app/shared_memory/memory.duckdb`

**On Host** (volume mounted):
- `shared_memory/memory.duckdb`

## Migration from Old Systems

### Project Astral
- ❌ **Old**: `memory/rag.py` with SQLite
- ✅ **New**: `memory/memory_interface.py` with Memory Alaya
- **Imports**: All updated to use `from memory import ...`

### GemGem
- ❌ **Old**: `utils/search_cache.py` with ChromaDB
- ✅ **New**: `utils/memory_interface.py` with Memory Alaya
- **Import**: `from utils.memory_interface import MemoryInterface`

### What Changed?

**Removed** (deprecated):
- ❌ Image description storage
- ❌ Search result caching
- ❌ Drawing commentary storage
- ❌ Multiple knowledge types

**Kept** (streamlined):
- ✅ User facts ONLY
- ✅ Gemini-based fact extraction
- ✅ Hybrid search + reranking
- ✅ Metadata filtering

## Current Statistics

**Database**: `shared_memory/memory.duckdb`
- **Total Facts**: 29 (deduplicated from both bots)
- **Source Breakdown**:
  - Project Astral: 37 original → 29 unique
  - GemGem: 903 original → 0 unique (all duplicates)
- **Deduplication**: Cosine similarity > 0.90

## API Reference

### Memory Alaya Core

```python
from shared_memory import MemoryAlaya

# Initialize
memory = MemoryAlaya(
    backend="duckdb",
    database_path="/path/to/memory.duckdb"
)

# Store knowledge
await memory.store(
    content="User fact text",
    embedding=[...],  # 3072-dim vector
    knowledge_type="user_fact",
    user_id="123",
    guild_id="456"
)

# Recall knowledge
results = await memory.recall(
    query="query text",
    query_embedding=[...],
    top_k=5,
    filters={"user_id": "123"},
    similarity_threshold=0.63,
    rerank=True
)

# Get stats
stats = await memory.get_stats()
```

### Project Astral Interface

```python
from memory import (
    store_conversation,
    retrieve_relevant_knowledge,
    format_knowledge_for_context
)

# Store from conversation
await store_conversation(
    username="Alice",
    user_message="I love cats",
    astra_response="That's wonderful!",
    user_id="123"
)

# Retrieve
facts = await retrieve_relevant_knowledge(
    query="What does Alice like?",
    limit=5,
    threshold=0.78
)

# Format for context
context = format_knowledge_for_context(facts)
```

### GemGem Interface

```python
from utils.memory_interface import MemoryInterface

# Initialize
memory = MemoryInterface()

# Store fact
await memory.store_fact(
    fact="Alice loves cats",
    user_id="123",
    user_name="Alice"
)

# Recall facts
facts = await memory.recall_facts(
    message="What does Alice like?",
    n_results=3
)
```

## Performance

**Retrieval Speed**:
- Vector search: ~10-50ms (DuckDB)
- BM25 search: ~5-20ms
- Reranking: ~200-500ms per query (Gemini API)
- **Total**: ~300-700ms for hybrid search with reranking

**Scaling**:
- DuckDB: Good for <100k facts (current: 29)
- pgvector: Ready for millions of facts (production)

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'shared_memory'"

**Solution**: Ensure `shared_memory` directory is mounted in Docker:
```yaml
volumes:
  - ../shared_memory:/app/shared_memory
```

### Issue: "Cannot open file '/app/shared_memory/memory.duckdb'"

**Solution**: Database path is hardcoded to `/app/shared_memory/memory.duckdb` inside containers.
Check volume mount in `docker-compose.yml`.

### Issue: No facts returned

**Solutions**:
1. Check similarity threshold (try lowering to 0.5)
2. Verify facts exist: `python query_memories.py --list`
3. Test query: `python query_memories.py "test query"`

## Future Enhancements

- [ ] Automatic fact deduplication on insert
- [ ] Fact expiration/aging system
- [ ] User-specific memory isolation
- [ ] Fact importance scoring
- [ ] Multi-modal memory (images, audio)
- [ ] Distributed deployment with pgvector

## License

Shared between Project Astral and GemGem Discord bots.
