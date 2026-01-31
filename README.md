# Project Astral 🌟

**Astra** is a Discord bot with a genuine, human-like personality powered by a local LLM. She's designed to feel like a real friend in your group chat, not an AI assistant.

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Brain** | Mistral Small 24B (via Ollama) |
| **Vision** | Gemini 2.0 Flash |
| **Image Gen** | Gemini Imagen / Flux |
| **TTS** | Kokoro TTS (af_heart / Hannah voice) |
| **Search** | SearXNG (self-hosted) |
| **Memory** | SQLite RAG (chromadb) |
| **Framework** | discord.py |
| **Deployment** | Docker Compose |

## Features

- **Natural Conversation** - Personality-driven responses, not assistant-speak
- **Voice Support** - `/join` and `/leave` to speak in voice channels
- **Vision** - Analyzes images shared in chat
- **Drawing** - `draw`, `gdraw` (guided), and `edit` commands with character references
- **Search** - Grounded answers via SearXNG
- **Long-term Memory** - RAG-based memory across conversations
- **Time Awareness** - Knows current date/time with timezone

## Project Structure

```
Project-Astral/
├── bot/
│   ├── main.py              # Entry point
│   ├── ai/
│   │   ├── personality.py   # Astra's character definition & examples
│   │   └── router.py        # LLM orchestration & tool routing
│   ├── cogs/
│   │   ├── chat.py          # Main message handling
│   │   ├── commands.py      # Slash commands
│   │   ├── draw.py          # Drawing commands
│   │   └── voice.py         # Voice channel commands
│   ├── tools/
│   │   ├── vision.py        # Gemini vision for images
│   │   ├── voice_handler.py # Kokoro TTS integration
│   │   ├── drawing.py       # Image generation logic
│   │   ├── characters.py    # Character reference system
│   │   ├── discord_context.py # Chat history fetching
│   │   └── time_utils.py    # Time/date utilities
│   ├── memory/
│   │   └── rag.py           # Long-term memory (ChromaDB)
│   └── data/
│       └── characters.json  # Known character definitions
├── docker-compose.yml
├── CHANGELOG.md
└── README.md
```

## Key Files

| File | Purpose |
|------|---------|
| `personality.py` | Astra's core character: backstory, interests, emotional intelligence, banned phrases |
| `router.py` | Decides when to search, use vision, or just chat. Injects few-shot examples |
| `chat.py` | Fetches last 100 messages with timestamps, handles mentions and DMs |
| `voice_handler.py` | Kokoro TTS integration for speaking in voice channels |
| `drawing.py` | Image generation with character refs, AI-enhanced prompts, critiques |

## Astra's Personality

- **Age**: 22
- **Vibe**: Smart but not pretentious, dry humor, night owl
- **Interests**: Tech, anime, VTubers, games, space
- **Tone**: Casual, lowercase okay, matches user energy
- **Emotional Intelligence**: Listens before problem-solving, celebrates wins

### What She Avoids
- Assistant phrases ("I'm here to help", "What can I do for you?")
- Bullet point lists (unless asked)
- Excessive emojis
- Words like: delve, utilize, facilitate, leverage

## Running Locally

### Prerequisites
- Docker & Docker Compose
- NVIDIA GPU (for Ollama + Kokoro)
- Ollama with `mistral-small:24b` pulled

### Environment Variables
```env
DISCORD_TOKEN=your_token
GEMINI_API_KEY=your_key
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=mistral-small-24b
KOKORO_TTS_URL=http://host.docker.internal:8000
SEARXNG_HOST=http://gemgem-searxng:8080
```

### Start
```bash
docker-compose up --build -d
docker logs gemgem-bot --tail 20
```

## Commands

| Command | Description |
|---------|-------------|
| `/join` | Astra joins your voice channel |
| `/leave` | Astra leaves the voice channel |
| `@Astra draw [prompt]` | Generate an image |
| `@Astra gdraw [prompt]` | AI-enhanced guided drawing |
| `@Astra edit [instruction]` | Edit the last generated image |
| `@Astra search [query]` | Force a web search |
| `@Astra [anything]` | Chat naturally |

## Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

---

*Built with ❤️ for natural AI conversation*
