# Project Astral 🌟

**Astra** is a Discord bot with a genuine, human-like personality powered by a local LLM. She's designed to feel like a real friend in your group chat, not an AI assistant.

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Brain** | Qwen3-VL-32B Heretic v2 (via LM Studio) |
| **Vision** | Gemini 3.0 Flash (image analysis + character recognition) |
| **Image Gen** | FLUX.2 [dev] (self-hosted) / Gemini Imagen |
| **TTS** | Kokoro TTS (GPU-accelerated, anime voice) |
| **STT** | Gemini Cloud (primary) / faster-whisper (fallback) |
| **Search** | SearXNG (self-hosted, unlimited) |
| **Memory** | SQLite RAG with Gemini Embedding 001 (3072-dim vectors) |
| **Framework** | discord.py |
| **Deployment** | Docker Compose |

## Features

- **Natural Conversation** — Personality-driven responses with dry humor, not assistant-speak
- **Voice Support** — `/join` and `/leave` for voice channels with TTS + STT
- **Vision** — Analyzes images via Gemini 3.0 Flash with character recognition
- **Drawing** — `draw`, `gdraw` (AI-enhanced), and `edit` commands with character references
- **Search** — Grounded answers via SearXNG with deterministic attribution (🔍)
- **Long-term Memory** — RAG-based fact storage with citation footers (💡)
- **Mid-Context Identity Injection** — Prevents identity drift in long conversations
- **Admin & Whitelist** — Access control system with root admins and file-backed whitelist
- **Time Awareness** — PST timestamps throughout context and responses

## Project Structure

```
Project-Astral/
├── bot/
│   ├── main.py                # Entry point
│   ├── ai/
│   │   ├── personality.py     # Astra's character, few-shot examples, DON'T rules
│   │   ├── router.py          # LLM orchestration, tool routing, response cleaning
│   │   └── query_enhance.py   # Search query improvement
│   ├── cogs/
│   │   ├── admin.py           # /access add/remove/list commands
│   │   ├── chat.py            # Main message handling & context assembly
│   │   ├── draw.py            # Drawing commands (draw, gdraw, edit)
│   │   └── voice.py           # Voice channel join/leave & STT
│   ├── tools/
│   │   ├── admin.py           # Whitelist manager & ADMIN_IDS
│   │   ├── characters.py      # Character reference system for drawings
│   │   ├── discord_context.py # Chat history formatting + mid-context injection
│   │   ├── drawing.py         # Image generation logic (FLUX/Gemini)
│   │   ├── image_gen.py       # FLUX.2 API client
│   │   ├── kokoro_tts.py      # Kokoro TTS client
│   │   ├── search.py          # SearXNG integration
│   │   ├── stt.py             # Speech-to-text (Gemini + whisper)
│   │   ├── time_utils.py      # PST time/date utilities
│   │   ├── vision.py          # Gemini 3.0 Flash image analysis
│   │   ├── voice_handler.py   # TTS playback & voice management
│   │   └── voice_receiver.py  # VAD + audio capture
│   ├── memory/
│   │   ├── embeddings.py      # Gemini Embedding 001 (3072-dim)
│   │   └── rag.py             # SQLite RAG: store, retrieve, search knowledge
│   └── data/
│       └── characters.json    # Known character definitions for recognition
├── docker-compose.yml
├── CHANGELOG.md
├── ARCHITECTURE.md
└── README.md
```

## Key Files

| File | Purpose |
|------|---------|
| `personality.py` | Astra's core character: backstory, interests, few-shot examples, DON'T rules, anti-impersonation |
| `router.py` | Decides search/vision, builds ChatML messages, cleans response output (think tags, roleplay, repeats) |
| `chat.py` | Orchestrates the full flow: context → RAG → tools → response → footers → TTS |
| `discord_context.py` | Formats 50 messages with timestamps, injects mid-context identity reminder |
| `voice_handler.py` | Kokoro TTS integration and voice playback management |

## Astra's Personality

- **Age**: 22
- **Vibe**: Smart but not pretentious, dry humor, night owl, low-energy texter
- **Interests**: Tech, anime, VTubers, games, space
- **Tone**: Casual, lowercase, matches user energy
- **Emotional Intelligence**: Listens before problem-solving, celebrates wins
- **Voice**: Concise but substantive — never one-word, never walls of text

### What She Avoids
- Assistant phrases ("I'm here to help", "What can I do for you?")
- Bullet point lists (unless asked)
- Excessive emojis
- Speaking for other bots (GemGem) — her own opinions only
- Banned words: delve, utilize, facilitate, leverage

## Running Locally

### Prerequisites
- Docker & Docker Compose
- NVIDIA GPU on network (for LM Studio + Kokoro)
- LM Studio with `qwen3-vl-32b-instruct-heretic-v2-i1` loaded
- Gemini API key (for vision + embeddings)

### Environment Variables
```env
DISCORD_TOKEN=your_token
GEMINI_API_KEY=your_key
LMSTUDIO_HOST=http://host.docker.internal:1234
LMSTUDIO_CHAT_MODEL=qwen3-vl-32b-instruct-heretic-v2-i1
KOKORO_TTS_URL=http://host.docker.internal:8000
SEARXNG_HOST=http://searxng:8080
RAG_DATABASE=/app/data/db/memory.db
```

### Start
```bash
docker compose build --no-cache
docker compose up -d
docker logs astral-bot --tail 20
```

## Commands

| Command | Description |
|---------|-------------|
| `/join` | Astra joins your voice channel |
| `/leave` | Astra leaves the voice channel |
| `@Astra draw [prompt]` | Generate an image with FLUX/Gemini |
| `@Astra gdraw [prompt]` | AI-enhanced guided drawing |
| `@Astra edit [instruction]` | Edit the last generated image |
| `@Astra access [add/remove/list]` | Manage whitelist (admin only) |
| `@Astra [anything]` | Chat naturally |

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

---

*Built with ❤️ for natural AI conversation*
