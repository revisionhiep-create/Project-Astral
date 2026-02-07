# 🔄 How to Change Models — Project Astral

> **Purpose:** Step-by-step guide for switching the LLM model used by Astra.
> All models run locally via **LM Studio** (OpenAI-compatible API at `host.docker.internal:1234`).

---

## Quick Summary

The model name appears in **4 places**. Change all of them:

| # | File | Line | What It Does |
|---|------|------|-------------|
| 1 | `docker-compose.yml` | `LMSTUDIO_CHAT_MODEL=` | **Primary config** — env var read by all modules |
| 2 | `bot/ai/router.py` | `CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "...")` | Chat/personality responses (hardcoded fallback) |
| 3 | `bot/memory/rag.py` | `CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "...")` | RAG fact extraction from conversations |
| 4 | `bot/tools/vision.py` | `CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "...")` | Image analysis (vision) |

> [!TIP]
> If you only change `docker-compose.yml`, the bot will use the new model at runtime.
> The hardcoded fallbacks in files 2-4 are only used if the env var is missing — but keep them in sync to avoid confusion.

---

## Step-by-Step

### 1. Update `docker-compose.yml`

```yaml
environment:
  - LMSTUDIO_CHAT_MODEL=new-model-name-here
  - OLLAMA_MODEL=new-model-name-here  # Keep in sync (legacy)
```

### 2. Update Hardcoded Fallbacks

Search for the old model name in these 3 files and replace:

```python
# bot/ai/router.py (line ~116)
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "new-model-name-here")

# bot/memory/rag.py (line ~22)
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "new-model-name-here")

# bot/tools/vision.py (line ~25)
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "new-model-name-here")
```

### 3. Check Stop Sequences (Model-Specific!)

In `bot/ai/router.py`, the `generate_response()` function uses stop sequences to prevent the model from roleplaying as other users. These are **model-specific tokens**:

| Model Family | Stop Sequences |
|-------------|---------------|
| Gemma 3 | `<end_of_turn>`, `<start_of_turn>` |
| Qwen 3 | `<\|im_end\|>`, `<\|im_start\|>` |
| Llama 3 | `<\|eot_id\|>`, `<\|start_header_id\|>` |
| Mistral | `[INST]`, `[/INST]` |

Search for `stop` in `router.py` → `generate_response()` and update if switching model families.

### 4. Check `<think>` Tag Stripping

Reasoning/deep-thinking models output `<think>...</think>` blocks. Two functions strip these:

- `bot/ai/router.py` → `_strip_think_tags()` — strips from chat responses
- `bot/memory/rag.py` → `_extract_fact_from_conversation()` — strips from RAG extraction

If the new model uses different reasoning tags (e.g., `<reasoning>`, `<inner_thought>`), update the regex in both places.

### 5. Check Context Window Limits

These values should match the new model's capacity:

| Setting | File | Current Value | What to Adjust |
|---------|------|--------------|----------------|
| `max_tokens` (default) | `router.py` → `_call_lmstudio()` | 4000 | Response length budget |
| `max_tokens` (with search) | `router.py` → `generate_response()` | 1500 | Shorter when search eats context |
| Context truncation | `router.py` → `decide_tools_and_query()` | 3000 chars | How much chat history the router sees |
| Discord history fetch | `cogs/chat.py` | 50 messages | Raw messages fetched from Discord |
| `max_messages` format | `tools/discord_context.py` | 50 | Messages formatted into context string |
| Vision `max_tokens` | `tools/vision.py` | 800 | Image description length |
| RAG `max_tokens` | `memory/rag.py` | 100 | Fact extraction length |

### 6. Load Model in LM Studio

Make sure the new model is:
1. Downloaded in LM Studio
2. Loaded and serving on port `1234`
3. "Serve on Local Network" is enabled (so Docker can reach it)

### 7. Rebuild & Restart

```bash
cd Project-Astral
docker-compose up -d --build
docker logs astral-bot --tail 20  # Verify startup
```

### 8. Update CHANGELOG.md

Add a new version entry documenting the model switch.

---

## Vision System (Separate from Chat)

> [!CAUTION]
> **Heretic/abliterated fine-tunes strip the vision encoder!** Even if the base model is "VL" (vision-language), the Heretic abliteration process only operates on text layers — the GGUF output is **text-only**. Do NOT assume a model with "VL" in its heretic name supports images.

Vision uses **Gemini 3.0 Flash** (cloud) for image analysis. The chat model (Qwen3) is text-only due to Heretic abliteration.

The vision flow is:
```
Image → Gemini 3.0 Flash (describe, cloud) → text description → Qwen3 (personality response)
```

If you want local vision, you need a **non-heretic** VL model loaded separately in LM Studio.

---

## Files That Do NOT Need Changes

These files reference models by name in docs/comments only:

| File | Why It's Safe |
|------|--------------|
| `CHANGELOG.md` | Historical record, don't edit old entries |
| `ARCHITECTURE.md` | Flow diagram, may need updating separately |
| `ai/personality.py` | Personality prompt — model-agnostic |
| `tools/characters.py` | Character recognition — model-agnostic |
| `tools/discord_context.py` | Message formatting — model-agnostic |
| `tools/searxng.py` | Search — model-agnostic |
| `memory/embeddings.py` | Uses Gemini embedding API, not chat model |

---

## Current Model (as of 2026-02-07)

```
Chat:           qwen3-vl-32b-instruct-heretic-v2-i1 (text-only, Heretic strips VL)
Vision:         Gemini 3.0 Flash (gemini-3-flash-preview, cloud API)
Embeddings:     Gemini (gemini-embedding-001)
Search Agent:   N/A (delegated to router)
```
