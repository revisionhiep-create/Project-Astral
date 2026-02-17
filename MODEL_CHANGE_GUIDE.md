# How to Change Models — Astra & GemGem

> **Purpose:** Step-by-step guide for switching the LLM models used by Astra (Project-Astral) and GemGem (Docker).

---

## Quick Summary — Astra (Project-Astral)

Astra supports **multiple backends** via `LLM_BACKEND` env var:

| Backend | Engine | Format | Config Vars |
|---------|--------|--------|-------------|
| `tabby` | TabbyAPI | EXL2 | `TABBY_HOST`, `TABBY_MODEL`, `TABBY_API_KEY` |
| `kobold` | KoboldCpp | GGUF | `KOBOLD_HOST`, `KOBOLD_MODEL` |

### Swap backends (1 line):

```bash
# Project-Astral/.env
LLM_BACKEND=kobold   # or "tabby"
```

Then rebuild:

```bash
cd Project-Astral
docker-compose up -d --build astral-bot
```

Sampler settings (temperature, penalties, etc.) are **auto-configured per backend** in `bot/ai/router.py` — no manual tuning needed when swapping.

---

## Backend: TabbyAPI (EXL2)

```bash
TABBY_HOST=http://host.docker.internal:5000
TABBY_MODEL=Qwen3-32B-4.25bpw-exl2
TABBY_API_KEY=your-key
LLM_BACKEND=tabby
```

Runs on host machine. Samplers: temp=0.6, top_p=0.95, top_k=20 (Qwen3 thinking mode).

---

## Backend: KoboldCpp (GGUF)

```bash
KOBOLD_HOST=http://koboldcpp:5001
KOBOLD_MODEL=GLM-4.7-Flash-Uncen-Hrt-NEO-CODE-MAX-imat-D_AU-Q4_K_S
KOBOLD_MODEL_FILE=GLM-4.7-Flash-Uncen-Hrt-NEO-CODE-MAX-imat-D_AU-Q4_K_S.gguf
KOBOLD_ADAPTER=glm47-nothink-adapter.json
KOBOLD_CONTEXT=8192
LLM_BACKEND=kobold
```

Runs as Docker container. Samplers: temp=1.0, top_p=0.95, no rep pen (GLM-4.7 recommended).

### Adding a new GGUF model to KoboldCpp:
1. Place the `.gguf` file in `koboldcpp/models/`
2. Create a chat adapter JSON in `koboldcpp/` (or use existing)
3. Update `KOBOLD_MODEL_FILE` and `KOBOLD_ADAPTER` in `.env`
4. Rebuild: `docker-compose up -d --build koboldcpp`

---

## GemGem (Docker)

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
`_strip_think_tags()` in `router.py` catches `<think>...</think>` blocks as a safety net across all backends. For KoboldCpp, thinking is disabled at the template level via the adapter JSON.

### GLM-4.7 Rep Pen Sensitivity
GLM-4.7 is extremely sensitive to repetition penalties. The kobold backend config sets them to 0. Do not increase unless you see repetition issues.

---

## Current Models (as of 2026-02-17)

```
Astra Chat (tabby):   Qwen3-32B-4.25bpw-exl2 (TabbyAPI)
Astra Chat (kobold):  GLM-4.7-Flash-Heretic-NEO-CODE Q4_K_S (KoboldCpp)
GemGem Chat:          qwen3-vl-32b-instruct-heretic-v2-i1
Vision:               Gemini 3.0 Flash (cloud API)
```
