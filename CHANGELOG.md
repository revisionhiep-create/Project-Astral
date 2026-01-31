# Changelog

All notable changes to Project Astral will be documented in this file.

## [1.2.0] - 2026-01-31

### Added
- **Voice Support**: Astra can now join voice channels and speak responses
  - `/join` - Astra joins your voice channel
  - `/leave` - Astra leaves the voice channel
  - Uses Kokoro TTS with `af_heart` (Hannah) voice
  - TTS speed set to 1.2x for natural conversation pace
- **Kokoro TTS Integration**: Local GPU-accelerated text-to-speech
  - Docker container with CUDA support
  - 54 voices available
- Increased chat history from 50 to 100 messages for better context with local LLM

### Changed
- `voice_handler.py`: New file for TTS and voice channel management
- `cogs/voice.py`: New cog with /join and /leave commands
- `Dockerfile`: Added ffmpeg and libopus for voice support
- `requirements.txt`: Added PyNaCl for Discord voice
- `docker-compose.yml`: Added Kokoro TTS URL environment variable

---

## [1.1.0] - 2026-01-31

### Added
- **Context Awareness**: Astra can now see and reference chat history from the current channel
- Direct channel history fetching (last 100 messages)
- Explicit personality instructions for context awareness
- "astral" keyword added to character recognition
- More GemGem nickname variations (geminibot, Geminibot, etc.)

### Fixed
- **Chat History Bug**: Bot messages were all labeled as "Astra" - now only THIS bot is labeled correctly, other bots (like GemGem) keep their real names
- **Privacy Refusal Override**: Model was incorrectly refusing to reference chat history due to "privacy" training - added explicit instructions that Astra is part of the conversation and CAN see messages
- Centralized personality prompt now properly used in drawing critiques and image analysis

### Changed
- `chat.py`: Uses `message.channel.history()` directly instead of separate fetch function
- `personality.py`: Added CONTEXT AWARENESS section with clear instructions
- `characters.json`: Added "astral" to Astra's keywords, more GemGem variations

## [1.0.0] - 2026-01-30

### Added
- Initial Project Astral setup (rebranded from GemGem-LABS)
- Mistral Small 24B as unified brain
- SearXNG integration for grounded search
- RAG-based long-term memory
- Drawing commands with Gemini Vision
- Centralized personality system
