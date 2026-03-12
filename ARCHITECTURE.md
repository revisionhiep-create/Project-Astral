# Conversation Flow

This document explains how Astra processes each message from start to finish.

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SENDS MESSAGE                        │
│  (must be @mention or DM + on whitelist)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Fetch Discord Context (Short-term)                 │
│  • Last 50 messages from channel with PST timestamps        │
│  • "[05:35 AM] [Hiep]: message..."                          │
│  • Mid-context identity reminder injected at message ~25    │
│  • Astra's own footer emojis stripped from context          │
│  • Citation markers stripped from Astra's past messages     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Query Memory Alaya (Long-term Memory)              │
│  • Embed user's message with Gemini Embedding 001 (3072d)   │
│  • Hybrid search: Vector + BM25 keyword + Question matching │
│  • Gemini reranking for relevance                           │
│  • Returns top facts from Memory Alaya DuckDB database      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Check for Vision Input                             │
│  • Does this have an IMAGE? (attachment check)              │
│  • If yes → Gemini 3.0 Flash analyzes image                │
│  • Gemini provides detailed description                     │
│  • Vision description injected into conversation history    │
│  • Note: Grok handles search autonomously (no routing)     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Build Context Package                              │
│                                                             │
│  SYSTEM MESSAGE (role: system):                             │
│  ┌─ Grok-specific personality (identity anchoring)         │
│  ├─ Capabilities section (web_search, x_search, vision)    │
│  ├─ Memory Alaya facts (XML <memory> tags)                 │
│  ├─ Vision descriptions (XML <vision_analysis> tags)       │
│  └─ Current speaker identity                               │
│                                                             │
│  USER MESSAGE (role: user):                                 │
│  ┌─ Discord chat transcript (50 msgs with timestamps)      │
│  ├─ Mid-context identity reminder (at midpoint)            │
│  ├─ Gemini vision descriptions (if any)                    │
│  └─ ">>> {Speaker} IS NOW TALKING TO YOU <<<"              │
│     + user's actual message                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: Generate Response                                  │
│  • Grok 4.1 Fast Reasoning via xAI /v1/responses endpoint  │
│  • Speed: 80-100 tokens/sec                                 │
│  • Native tool calling: web_search (up to 3 queries)       │
│  • Native tool calling: x_search (Twitter/X integration)   │
│  • Repetition penalty: 1.05 (dynamic adjustment for loops) │
│  • Post-processing: strip citations [[1]][[2]], clean      │
│    markdown, remove roleplay, deduplicate                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: Store to Memory Alaya (After Response)             │
│  • Extract facts from conversation via fact_agent.py        │
│  • Embed facts with Gemini Embedding 001 (3072-dim)        │
│  • Store in Memory Alaya DuckDB with metadata              │
│  • Note: Grok's search results handled internally          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 8: Send + Speak                                       │
│  • Send to Discord (split if >2000 chars)                   │
│  • If in voice: strip citations + footers, send to Kokoro   │
└─────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `cogs/chat.py` | Orchestrates the entire flow above |
| `ai/router.py` | Grok API integration, response cleaning, citation stripping |
| `ai/personality.py` | Character definition, few-shot examples, system prompt builder |
| `memory/memory_interface.py` | Memory Alaya integration (DuckDB hybrid search + Gemini reranking) |
| `memory/embeddings.py` | Gemini Embedding 001 client (3072-dim vectors) |
| `tools/vision.py` | Gemini 3.0 Flash image analysis |
| `tools/admin.py` | Whitelist & admin ID management |
| `tools/voice_handler.py` | Qwen3-TTS streaming integration and voice playback |
| `tools/voice_receiver.py` | VAD + audio capture for STT |

## Context Types

### Short-term (Discord History)
- Last 50 messages from the current channel
- PST timestamps: `[05:35 AM] [Hiep]: message`
- Mid-context system reminder at ~message 25 (prevents identity drift)
- Refreshed every message

### Long-term (Memory Alaya)
- DuckDB vector database with Gemini Embedding 001 vectors (3072-dim)
- Hybrid search: Vector similarity + BM25 keyword + Question matching
- Gemini 1.5 Flash reranking for relevance
- Stores: conversation facts with metadata (user_id, channel_id, guild_id)
- Retrieved via hybrid search (threshold ≥ 0.78)
- Persisted across restarts via Docker volume mount

### Search (Grok Native)
- Grok 4.1 Fast handles search autonomously via web_search tool
- X/Twitter search via x_search tool for social media queries
- No external routing needed — Grok decides when to search
- Results integrated directly into response generation

## Memory Storage

Each conversation stores:
- `user_id` — Discord user ID
- `username` — Display name (e.g., "Hiep")
- `channel_id` — Where it was said
- `guild_id` — Which server
- `user_message` — What they said
- `astra_response` — What Astra replied
- `embedding` — 3072-dim vector for similarity search
- `questions` — Hypothetical questions for improved retrieval

## Anti-Hallucination Measures

| Measure | Location | Purpose |
|---------|----------|---------|
| Mid-context reminder | `chat.py` | Prevents identity drift at attention midpoint |
| Anti-impersonation rule | `personality.py` | "NEVER speak FOR GemGem" in DON'T list |
| Citation stripping | `router.py` | Strips [[1]][[2]] markers from Grok responses |
| Footer stripping | `chat.py` | Keeps 💡/🔍 out of Memory Alaya storage and context |
| Think tag stripping | `router.py` | Removes `<think>` blocks from output |
| Roleplay stripping | `router.py` | Removes `*action*` narration |
| Repeat detection | `router.py` | Dedupes repeated content in output |
| Memory similarity threshold | `memory_interface.py` | 0.78 minimum prevents irrelevant fact injection |
