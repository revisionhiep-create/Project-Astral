# 🔄 How to Change Models — Astra & GemGem

> **Purpose:** Step-by-step guide for switching the LLM models used by Astra (Project-Astral) and GemGem (Docker).
> All models run locally via **LM Studio** (OpenAI-compatible API at `host.docker.internal:1234`).

---

## Quick Summary

Both bots now use the **same method**:
1.  Edit `.env` file.
2.  Rebuild Docker.

---

## 💎 How to Change Models — Astra (Project-Astral)

### 1. Update `.env`

```bash
# Project-Astral/.env
LMSTUDIO_CHAT_MODEL=new-model-name-here
```

### 2. Rebuild

```bash
cd Project-Astral
docker-compose up -d --build astral-bot
```

### 3. (Optional) Update Fallbacks

The files `bot/ai/router.py`, `bot/memory/rag.py`, and `bot/tools/vision.py` have hardcoded fallbacks in case the env var is missing. You can update them to keep the code consistent, but it's not required for the change to take effect.

---

## 🍌 How to Change Models — GemGem (Docker)

### 1. Update `.env`

```bash
# GemGem-Docker-Live/.env
LMSTUDIO_CHAT_MODEL=new-model-name-here
```

### 2. Rebuild

```bash
cd GemGem-Docker-Live
docker-compose up -d --build gemgem-bot
```

---

## Common Gotchas

### Check Stop Sequences
Different model families use different stop tokens. If switching families (e.g., Qwen -> Llama), check `bot/ai/router.py` in Astra.

### Check `<think>` Tag Stripping
DeepSeek/Reasoning models output `<think>` tags. Ensure `_strip_think_tags()` is active in `router.py` (Astra) and `fact_agent.py` (GemGem).

---

## Current Models (as of 2026-02-11)

```
Astra Chat:     qwen3-vl-32b-instruct-heretic-v2-i1
GemGem Chat:    qwen3-vl-32b-instruct-heretic-v2-i1
Vision:         Gemini 3.0 Flash (cloud API)
```
