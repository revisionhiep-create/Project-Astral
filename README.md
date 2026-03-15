# Project Astral 🌟

**Astra** is a Discord bot with a genuine, human-like personality powered by Grok 4.1 Fast Reasoning. She's designed to feel like a real friend in your group chat, not an AI assistant.

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Brain** | Grok 4.1 Fast Reasoning (xAI API) - 80-100 tokens/sec |
| **Vision** | Gemini 3.0 Flash Preview (image analysis + character recognition) ~36 calls/day |
| **Image Gen** | Nano Banana 2 (Gemini 3.1 Flash Image) / Imagen 4.0 / Gemini 2.5 Flash Art |
| **TTS** | Qwen3-TTS (streaming, Raiden voice clone) |
| **STT** | Gemini Cloud (primary) / faster-whisper (fallback) |
| **Search** | Grok built-in web_search (autonomous) + X/Twitter search |
| **Memory** | Memory Alaya (DuckDB, Gemini 2.5 Flash for fact extraction ~107 calls/day) |
| **Summarization** | Gemini 2.5 Flash (messages 31-200) ~10 calls/day |
| **Framework** | discord.py |
| **Deployment** | Docker Compose |

**API Usage**: RAG + Vision operations use ~210 calls/day on Gemini 2.5 Flash and ~70 calls/day on Gemini 3.0 Flash Preview, both fitting within free tier limits (250 RPD).

## Features

- **Natural Conversation** — Personality-driven responses with dry humor powered by Grok 4.1
- **Real-time Web Search** — Grok's built-in autonomous search with X/Twitter integration
- **Voice Support** — `/join` and `/leave` for voice channels with streaming Qwen3-TTS + STT
- **Vision** — Analyzes images via Gemini 3.0 Flash with character recognition
- **Drawing** — `draw`, `gdraw` (AI-enhanced), and `edit` commands with Nano Banana 2
- **Long-term Memory** — Memory Alaya DuckDB with hybrid search (vector + BM25 + questions)
- **Smart Summarization** — Gemini 2.5 Flash summarizes messages 31-200 for efficiency
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
│   │   └── router.py          # Grok API integration, response cleaning, citation stripping
│   ├── cogs/
│   │   ├── admin.py           # /access add/remove/list commands
│   │   ├── chat.py            # Main message handling & context assembly
│   │   ├── draw.py            # Drawing commands (draw, gdraw, edit)
│   │   └── voice.py           # Voice channel join/leave & STT
│   ├── tools/
│   │   ├── admin.py           # Whitelist manager & ADMIN_IDS
│   │   ├── characters.py      # Character reference system for drawings
│   │   ├── drawing.py         # Image generation logic (Nano Banana 2)
│   │   ├── image_gen.py       # Gemini image generation API client
│   │   ├── kokoro_tts.py      # Qwen3-TTS streaming client (Raiden voice)
│   │   ├── stt.py             # Speech-to-text (Gemini + whisper)
│   │   ├── time_utils.py      # PST time/date utilities
│   │   ├── vision.py          # Gemini 3.0 Flash image analysis
│   │   ├── voice_handler.py   # TTS playback & voice management
│   │   └── voice_receiver.py  # VAD + audio capture
│   ├── memory/
│   │   ├── memory_alaya/      # Memory Alaya framework (DuckDB vector database)
│   │   ├── memory_interface.py # Memory Alaya integration
│   │   └── shared_memory.py   # Shared memory manager (100-msg rolling window)
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
| `personality.py` | Astra's core character: backstory, interests, few-shot examples, DON'T rules, Grok-specific prompts |
| `router.py` | Grok API integration (/v1/responses endpoint), citation stripping, response cleaning |
| `chat.py` | Orchestrates full flow: Memory Alaya → Grok → response → TTS |
| `memory_interface.py` | Memory Alaya integration (DuckDB hybrid search + Gemini reranking) |
| `voice_handler.py` | Qwen3-TTS streaming integration and voice playback management |

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
- xAI API key (for Grok 4.1 Fast)
- Gemini API key (for vision + embeddings + summarization)
- Qwen3-TTS server (for voice synthesis)

### Environment Variables
```env
DISCORD_TOKEN=your_token
GEMINI_API_KEY=your_gemini_key
XAI_API_KEY=your_xai_key
XAI_MODEL=grok-4-1-fast-reasoning
XAI_HOST=https://api.x.ai
LLM_BACKEND=grok
QWEN_TTS_URL=http://host.docker.internal:8880
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
| `@Astra draw [prompt]` | Generate an image with Nano Banana 2 |
| `@Astra gdraw [prompt]` | AI-enhanced guided drawing |
| `@Astra edit [instruction]` | Edit the last generated image |
| `@Astra access [add/remove/list]` | Manage whitelist (admin only) |
| `@Astra [anything]` | Chat naturally with Grok 4.1 + auto web search |

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

---

*Built with ❤️ for natural AI conversation*
