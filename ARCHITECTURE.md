# Conversation Flow

This document explains how Astra processes each message.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SENDS MESSAGE                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Fetch Discord Context (Short-term)                 │
│  • Last 100 messages from channel with timestamps           │
│  • "[05:35 AM] [Hiep]: message..."                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Query RAG (Long-term Memory)                       │
│  • Embed user's message                                     │
│  • Find similar past conversations (cosine similarity)      │
│  • Returns: "Previous chat - Hiep: ... | Astra: ..."       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Router Decides Tools                               │
│  • Does this need a SEARCH? (factual, current events)       │
│  • Does this need VISION? (image attached)                  │
│  • Output: {search: true/false, vision: true/false}         │
└─────────────────────────────────────────────────────────────┘
                              │
                   ┌──────────┴──────────┐
                   ▼                      ▼
        ┌─────────────────┐    ┌─────────────────┐
        │  SEARCH = TRUE  │    │  SEARCH = FALSE │
        │  → SearXNG      │    │  → Skip search  │
        │  → Get results  │    │                 │
        └────────┬────────┘    └────────┬────────┘
                 │                       │
                 └───────────┬───────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Build Context Package                              │
│  • Discord history (short-term)                             │
│  • RAG memories (long-term)                                 │
│  • Search results (if triggered)                            │
│  → All injected into SYSTEM PROMPT                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: Generate Response                                  │
│  • Qwen3 VL 32B with personality prompt (via LM Studio)     │
│  • Few-shot examples injected                               │
│  • Context in system prompt                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: Store to RAG (After Response)                      │
│  • Save conversation with username, user_id                 │
│  • Save search results to knowledge (if any)                │
│  • Save image analysis (if vision triggered)                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 7: Send Response + Speak (if in voice)                │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `cogs/chat.py` | Orchestrates the entire flow |
| `ai/router.py` | Decides search/vision, generates response |
| `memory/rag.py` | Long-term memory storage & retrieval |
| `tools/searxng.py` | Web search integration |
| `tools/vision.py` | Image analysis with Qwen3 VL (Gemini fallback) |

## Context Types

### Short-term (Discord History)
- Last 100 messages from the current channel
- Includes timestamps: `[05:35 AM] [Hiep]: message`
- Refreshed every message

### Long-term (RAG)
- SQLite database with embeddings
- Stores: conversations, search results, image analyses, drawings
- Retrieved via cosine similarity to current query
- Persisted across restarts

### Search (SearXNG)
- Triggered for factual questions, current events
- Results stored to RAG for future reference
- Self-hosted, free, no API limits

## Memory Storage

Each conversation stores:
- `user_id` - Discord user ID
- `username` - Display name (e.g., "Hiep")
- `channel_id` - Where it was said
- `guild_id` - Which server
- `user_message` - What they said
- `gemgem_response` - What Astra replied
- `embedding` - Vector for similarity search
