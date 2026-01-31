# Changelog

All notable changes to Project Astral will be documented in this file.

## [1.5.0] - 2026-01-31

### Added
- **Dynamic Persona System**: Astra's personality now evolves based on conversations
  - Three-layer tracking: Vibe (mood/obsessions), Bond (trust/jokes), Story (events)
  - Gemini Flash analyzes every 10 messages in background
  - Updates `persona_state.json` with evolved relationships
  - Persona context injected into system prompt automatically
  - Tracks: group mood, intimacy level, inside jokes, shared vocabulary, user preferences

### New Files
- `bot/ai/persona_manager.py` - Core persona evolution logic
- `bot/data/persona_state.json` - Persistent persona state

---

## [1.4.7] - 2026-01-31

### Changed
- **Vision Routes Through Astra's Brain**: Images now use two-step flow
  - Gemini describes what it sees objectively
  - Astra (Mistral) comments in her own voice via router
  - She can now "grow" from image knowledge (stored in RAG)
- **GemGem Visibility**: Astra can now see GemGem's messages in chat history
  - Added `GEMGEM_BOT_ID` for proper labeling
  - Messages labeled as "GemGem" instead of generic "Astra"
- **No More Replies**: Messages sent via `channel.send()` instead of `reply()`
  - Other bots can now see Astra's messages in history
- **Search Prefers Recent Results**: Added `time_range: year` filter
  - Prevents pulling outdated 2022 meta guides
  - Fixes Argent Knight Rita style legacy data issues

---

## [1.4.5] - 2026-01-31

### Fixed
- **Response Length Issue Resolved**: Astra now speaks naturally instead of ultra-short replies
  - **Root Cause**: Few-shot injection was training her to respond in 1-8 words
  - **Fix**: Removed few-shot injection from router, let system prompt guide personality
  - Removed "match response length to input length" rule that caused feedback loop
- **RAG Memory Priority**: Discord context (last 100 msgs) now prioritized over old RAG memory
  - Labels: "RECENT CHAT (last few minutes)" vs "Old memories"
  - Prevents confusion between immediate chat and 3-hour-old conversations

### Changed
- **Expanded Personality Restored**: Full backstory from d146cf0 commit
  - 22-year-old girl, she/her pronouns
  - GemGem context: "also female, like a sister to you"
  - Personality: dry humor, night owl, low-key supportive
  - Interests: VTubers, tech, anime, gaming, space
  - Emotional intelligence: match energy, read between lines
- Removed overly eager "curious about what people are working on" trait
- Deleted 778 Reddit entries from RAG (was causing confusion)

---

## [1.4.2] - 2026-01-31

### Added
- **Reddit Knowledge Scraper**: Pipeline to scrape and import knowledge from Reddit
  - `bot/tools/scraper.py`: Scrapes via public JSON endpoints (no API key needed)
  - `bot/tools/knowledge_processor.py`: Uses Gemini Flash to rephrase posts into facts
  - `bot/tools/import_knowledge.py`: Imports facts to RAG database
  - `bot/tools/run_pipeline.py`: All-in-one runner
  - Scraped 820 posts → 751 knowledge facts (VTuber, Tech, Gaming)
- **Initial Knowledge Base**: 783 entries covering VTubers, tech news, and gaming

### Fixed
- **Engagement Restored**: Added back ENGAGEMENT section that was removed in v1.3.0
  - "Follow natural conversation flow", "Answer directly first, then add personality"
  - Astra now more engaged instead of ultra-minimal

### Changed
- `personality.py`: Temperature bumped 0.7 → 0.75 for more expressive responses

---

## [1.4.1] - 2026-01-31

### Fixed
- **Smarter Search Triggering**: Router now explicitly triggers search for real-time data needs
  - Weather, prices, sports scores, news, current events → auto-search
  - Added time-word detection: "now", "today", "current", "latest", "recent", "will"
  - Added weather/score examples to router prompt
- **Context Awareness**: Astra now properly uses chat history when the answer is already visible
  - Won't deflect when someone asks about something just discussed
  - Knows her own tech stack (Mistral Small 24B, SearXNG, Gemini, Kokoro)
  - Will say "lemme check" when she needs real-time data instead of guessing
- **Response Length Balance**: No longer ultra-terse on every message
  - Matches energy, not just character count
  - Expands appropriately on factual questions, empathy moments, banter
- **Silent Response Bug**: Astra now always responds, even when uncertain
  - Added "WHEN YOU DON'T KNOW SOMETHING" guidance
  - Will say "idk tbh", "honestly no idea", or ask for clarification

### Changed
- `router.py`: Enhanced decision prompt with CRITICAL real-time data rule and better examples
- `personality.py`: Added "USING YOUR CONTEXT", "RESPONSE LENGTH", and "WHEN YOU DON'T KNOW" sections
- `personality.py`: Added 6 new few-shot examples for uncertainty, empathy, and factual expansion

---

## [1.4.0] - 2026-01-31

### Added
- **Username Memory**: Astra now remembers who said what by name, not just user ID
  - Stores display names with each conversation
  - Retrieval shows: "Previous chat - Hiep: ... | Astra: ..."
- **ARCHITECTURE.md**: Documentation of the conversation flow and system design

### Fixed
- **RAG Database Persistence**: Fixed volume mount path so memories persist across restarts
  - Database now stored at `./db/memory.db` (mounted to `/app/data/db`)

### Changed
- `memory/rag.py`: Added username column to conversations table, updated storage and retrieval
- `cogs/chat.py`: Now passes username to store_conversation
- `docker-compose.yml`: Fixed volume mount for RAG database

---

## [1.3.0] - 2026-01-31

### Added
- **Expanded Personality**: Full character profile with backstory, interests, and emotional intelligence
  - 22-year-old night owl with dry humor
  - Interests: tech, anime, VTubers, games, space
  - Emotional intelligence guidelines for genuine responses
- **Few-shot Example Injection**: 3 random conversation examples injected per response for better character consistency
- **Timestamps in Chat History**: Astra can now see when messages were sent (e.g., "[05:35 AM] [Hiep]: message")
- **Time Awareness**: Now shows current time with timezone, not just date

### Fixed
- **Vision Accuracy**: Lowered temperature from 0.85 to 0.6, added instruction to describe actual colors
  - Applied to both chat vision and drawing critiques (draw/gdraw/edit)
- **Assistant-speak Prevention**: Added explicit ban list ("I'm here to help", "What can I do for you?", etc.)

### Changed
- `personality.py`: Expanded from 40 to 90 lines with full character definition
- `time_utils.py`: Now includes time with timezone (PST)  
- `discord_context.py`: Formats messages with timestamps
- `vision.py`: More accurate image descriptions
- `router.py`: Injects few-shot examples as conversation history

---

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
