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
│  STEP 2: Query RAG (Long-term Memory)                       │
│  • Embed user's message with Gemini Embedding 001 (3072d)   │
│  • Cosine similarity search (threshold ≥ 0.78)             │
│  • Returns top 5 facts from conversations + search cache    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Router Decides Tools                               │
│  • Does this need a SEARCH? (factual, current events)       │
│  • Does this have an IMAGE? (attachment check)              │
│  • Rewrites search query (de-contextualizes pronouns)       │
│  • Sets time_range (day/week/month/year/null)               │
│  • Output: {search: bool, search_query: str, time_range}    │
└─────────────────────────────────────────────────────────────┘
                              │
                   ┌──────────┴──────────┐
                   ▼                      ▼
        ┌─────────────────┐    ┌─────────────────┐
        │  SEARCH = TRUE  │    │  IMAGE ATTACHED │
        │  → SearXNG      │    │  → Gemini 3.0   │
        │  → 5 results    │    │  → Flash Vision │
        │  → Store to RAG │    │  → 5-min cache  │
        └────────┬────────┘    └────────┬────────┘
                 │                       │
                 └───────────┬───────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Build Context Package                              │
│                                                             │
│  SYSTEM MESSAGE (ChatML role: system):                      │
│  ┌─ Personality prompt (character, DON'Ts, few-shot)       │
│  ├─ Search results (⚠️ MUST USE, highest priority)         │
│  ├─ RAG memory facts (deprioritized, old memories only)    │
│  └─ Current speaker identity                               │
│                                                             │
│  USER MESSAGE (ChatML role: user):                          │
│  ┌─ Discord chat transcript (50 msgs with timestamps)      │
│  ├─ Mid-context identity reminder (at midpoint)            │
│  ├─ Cached image descriptions (if any, 5-min window)       │
│  └─ ">>> {Speaker} IS NOW TALKING TO YOU <<<"              │
│     + user's actual message                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: Generate Response                                  │
│  • Qwen3-VL-32B Heretic v2 via LM Studio OpenAI API       │
│  • Proper ChatML [system, user] separation                  │
│  • Samplers: temp=0.7, top_p=0.8, top_k=20                │
│  • repeat_penalty=1.05, presence_penalty=0.15              │
│  • Post-processing: strip <think> tags, roleplay actions,  │
│    repeated content, leading names                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: Deterministic Attribution Footers                  │
│  • 💡N = RAG facts used (N = count)                        │
│  • 🔍N = Search results used (N = count)                   │
│  • Both on same line, appended after response               │
│  • Stripped before RAG storage (display-only)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 7: Store to RAG (After Response)                      │
│  • Save conversation as fact (LLM extracts meaningful info) │
│  • Save search results to knowledge table (if any)          │
│  • Footers stripped before embedding                        │
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
| `ai/router.py` | Decides search/vision, generates response, cleans output |
| `ai/personality.py` | Character definition, few-shot examples, system prompt builder |
| `memory/rag.py` | Long-term memory storage & retrieval (SQLite + embeddings) |
| `memory/embeddings.py` | Gemini Embedding 001 client (3072-dim vectors) |
| `tools/search.py` | SearXNG web search integration |
| `tools/vision.py` | Gemini 3.0 Flash image analysis |
| `tools/discord_context.py` | Chat history formatting + mid-context identity injection |
| `tools/admin.py` | Whitelist & admin ID management |
| `tools/voice_handler.py` | Kokoro TTS playback |
| `tools/voice_receiver.py` | VAD + audio capture for STT |

## Context Types

### Short-term (Discord History)
- Last 50 messages from the current channel
- PST timestamps: `[05:35 AM] [Hiep]: message`
- Mid-context system reminder at ~message 25 (prevents identity drift)
- Refreshed every message

### Long-term (RAG)
- SQLite database with Gemini Embedding 001 vectors (3072-dim)
- Stores: conversation facts, search results
- Retrieved via cosine similarity (threshold ≥ 0.78)
- Persisted across restarts via Docker volume mount

### Search (SearXNG)
- Triggered by router for factual questions, current events
- Results stored to RAG for future reference
- Self-hosted, free, no API limits
- Placed at TOP of system prompt (highest attention zone)

## Memory Storage

Each conversation stores:
- `user_id` — Discord user ID
- `username` — Display name (e.g., "Hiep")
- `channel_id` — Where it was said
- `guild_id` — Which server
- `user_message` — What they said
- `gemgem_response` — What Astra replied
- `embedding` — 3072-dim vector for similarity search

## Anti-Hallucination Measures

| Measure | Location | Purpose |
|---------|----------|---------|
| Mid-context reminder | `discord_context.py` | Prevents identity drift at attention midpoint |
| Anti-impersonation rule | `personality.py` | "NEVER speak FOR GemGem" in DON'T list |
| Citation stripping | `discord_context.py` | Stops Astra copying her own citation markers |
| Footer stripping | `chat.py` | Keeps 💡/🔍 out of RAG storage and context |
| Think tag stripping | `router.py` | Removes `<think>` blocks from output |
| Roleplay stripping | `router.py` | Removes `*action*` narration |
| Repeat detection | `router.py` | Dedupes repeated content in output |
| RAG similarity threshold | `rag.py` | 0.78 minimum prevents irrelevant fact injection |
