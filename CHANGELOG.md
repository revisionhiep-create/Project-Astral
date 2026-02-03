# Changelog

All notable changes to Project Astral will be documented in this file.

## [1.8.9] - 2026-02-03

### Changed
- **Adaptive Image Reactions**: Now distinguishes between normal photos and artwork
  - Normal photos (food, pets, memes, screenshots): casual reactions like "nice", "lmao", "oof"
  - Art (anime, digital art, illustrations): aesthetic analysis with pose, lighting, rendering
  - Matches energy to what's shared instead of over-analyzing mundane images
  - Text/screenshots: comments on content, not the image itself

---

## [1.8.8] - 2026-02-03

### Fixed
- **Stripped Leading Names**: Removed unwanted `liddo.` style name prefixes from responses
  - Model was mimicking the `[Username]:` pattern from context injection
  - Added `_strip_leading_name()` helper to clean known usernames from response start
  - Covers: liddo, tei, hiep, jason, melon, revision, shiftstep

### Changed
- **Wiped RAG Memory**: Cleared `memory.db` for fresh start

---

## [1.8.7] - 2026-02-03

### Fixed
- **Stripped Roleplay Actions**: Removed unwanted `(pauses, blinks slowly)` style narration from responses
  - Root cause: Abliterated/roleplay-tuned models output action narration by default
  - Added `_strip_roleplay_actions()` helper to `router.py` to clean responses
  - Also strips `*action*` asterisk style actions
  - Astra now speaks directly without roleplay narration

---

## [1.8.6] - 2026-02-03

### Fixed
- **Exposed Think Tags**: Astra's internal `<think>` reasoning blocks were leaking into Discord messages
  - Root cause: Deep Reasoning model outputs chain-of-thought in `<think>...</think>` tags
  - Added `_strip_think_tags()` helper to `router.py` to clean responses before sending
  - Astra now keeps her thoughts to herself (as intended)

---

## [1.8.5] - 2026-02-03

### Changed
- **Personality Rewrite v3**: Tightened Astra's character for sharper, more consistent responses
  - Clearer structure: separated VIBE, ADULT/NSFW TONE, and IMAGE reactions into distinct sections
  - More deadpan energy: "You've seen enough shit to not be impressed easily"
  - Teasing reframed: "If you don't tease them, that's worse"
  - Explicit adult tone: No pearl-clutching, no fake shock
  - Streamlined image reactions: Lead with what hits first, talk aesthetics like a person
  - Response length: 1-4 sentences (down from 2-4), short dry responses are fine
  - New phrases: "rotting", "vibing" when asked what she's doing

---

## [1.8.4] - 2026-02-02

### Changed
- **Model Upgrade**: Switched to `Gemma3-27B-it-vl-GLM-4.7-Uncensored-Heretic-Deep-Reasoning`
  - Fine-tuned with GLM 4.7 reasoning dataset for enhanced "thinking"
  - Improved image intelligence and output generation
  - 128k context, temp stable 0.1-2.5
  - Recommended: Repeat Penalty 1.1-1.15 in LM Studio
- **Vision Prompt Enhanced**: Updated local vision prompt for richer descriptions
  - Now explicitly asks for vivid, uncensored detail on suggestive art
  - Art connoisseur vocabulary: alluring, provocative, sensual, etc.
  - Focus on *why* art is aesthetically striking, not just clinical descriptions

---

## [1.8.3] - 2026-02-02

### Changed
- **Image Reactions Reworked**: Astra now reacts like a "Man of Culture" to shared art
  - Genuine enthusiasm instead of stiff art critiques
  - Leads with the "Wow" factor - what catches her eye first
  - Natural language for aesthetics ("golden hour lighting feels cozy" not clinical descriptions)
  - Technical appreciation for rendering details (skin shading, fabric folds, eye detail)
  - Unapologetically appreciates spicy art - comments on *how* the artist made it work

---

## [1.8.2] - 2026-02-02

### Fixed
- **Identity Confusion on Truncation**: Astra now correctly identifies who's talking even when context is truncated
  - Added `[Username]:` prefix to user messages in router
  - Survives LM Studio context window truncation (8K limit was cutting speaker headers)
  - Fixes issue where Astra would respond to wrong person mid-conversation

---

## [1.8.1] - 2026-02-02

### Fixed
- **Image Context Bleed**: Astra no longer mentions old images unprompted
  - Added 5-minute expiry to image context cache
  - Images older than 5 minutes no longer injected into conversation context
  - Fixes issue where Astra would comment on past images during unrelated conversations

---

## [1.8.0] - 2026-02-02

### Changed
- **Unified Model Architecture**: Consolidated from two models to one
  - Chat brain: Mistral Small 24B → Gemma 3 27B (abliterated)
  - Vision: Already using Gemma 3 27B
  - Same model handles both chat and vision (no more RAM spill from swapping)
  - Anti-hallucination character recognition preserved (two-step flow intact)

### Fixed
- **Timezone Bug**: Image timestamps now use PST instead of container UTC
  - `vision.py` was using `datetime.now()` (UTC) instead of `pytz.timezone("America/Los_Angeles")`

---

## [1.7.2] - 2026-02-01

### Added
- **First-Person Self-Recognition**: Astra uses first person when seeing herself in images
  - "that's me", "my hair", "the spiral around me" - not third person
  - Personality prompt includes explicit first-person examples
- **Dynamic Character Loading**: `personality.py` loads from `characters.json` at runtime
- **Art Critique Mode**: Images get 3-5 sentence critiques (composition, colors, style)
  - Not just "nice" or "cute" - actual opinions on what works

### Changed
- **Vision/Recognition Separation** (KEY FIX):
  - Gemma 3 now outputs **objective descriptions only** (hair color, outfit, etc.)
  - Astra receives description + character list and **decides who matches**
  - Prevents false positives (claiming random anime girls are her)
- **Stricter Self-Recognition Rules**: Only claim "that's me" if description matches her specific features
  - Dark blue-black hair, teal highlights, purple-violet eyes, star necklace
  - Not just any anime girl in a school or with dark hair

### Fixed
- **False Self-Identification**: No longer claims non-matching characters are her
- **Image Context Bleed**: Clear separation between current vs previous images

---

## [1.7.1] - 2026-02-01

### Changed
- **Hybrid Personality**: Combined v1.6.6 lazy vibe with v1.7.0 substance
  - Brought back "low-energy texter" and "half-asleep on the couch" vibe
  - 2-4 sentences baseline still applies
  - No forced follow-up questions (only ask if you actually want to know)
  - No cheerleader validation ("Oh nice!", "always impressed by...")
  - No HR speak (compliments about work ethic/dedication)
  - It's okay to be unimpressed - not everything needs a reaction

### Fixed
- **TTS Routing**: Fixed Kokoro TTS routing to correct IP
  - Was: `host.docker.internal:8000` (localhost - wrong)
  - Now: `192.168.1.16:8000` (5090 GPU machine - correct)
- **Router JSON Parsing**: Added robust `_extract_json()` helper
  - Handles markdown code blocks (```json {...}```)
  - Finds JSON buried in LLM text responses
  - Reduces fallback to dumb heuristics

---

## [1.7.0] - 2026-02-01

### Changed
- **Personality System Rewrite v2**: Complete overhaul for natural conversation
  - 2-4 sentences baseline (flexible for deep topics)
  - Down-to-earth friend vibe - can tease, never condescending  
  - Medium energy like a normal person
  - Slang/emotes: understood, used rarely
  - Added self-appearance so Astra recognizes herself in images
  - Temperature: 0.5 → 0.65, max_tokens: 2048 → 6000
- **Character Recognition in Vision**: Both local Gemma 3 and Gemini now check for known characters
  - Only mentions characters if actually present (no "I don't see X")
- **TTS Emoji Stripping**: Kokoro TTS now removes all emotes before speaking
  - Discord emotes (`:joy:`, `:fire:`)
  - Unicode emoji (😂🔥💀)

### Removed
- **Persona Manager System**: Removed dynamic persona evolution
  - Deleted `persona_manager.py` and `persona_state.json`
  - Removed Gemini Flash analysis calls
  - Simplified system for more predictable behavior

---

## [1.6.7] - 2026-02-01

### Changed
- **Anti-Fabrication Rule**: Astra no longer invents fake hobbies/activities
  - Won't claim she was "gaming all night" or "coding"
  - Deflects vaguely ("nothing much", "just vibing") instead of fabricating

---

## [1.6.6] - 2026-02-01

### Changed
- **Chill Personality Rewrite**: Complete personality overhaul based on Gemini Pro 3 analysis
  - Removed "add substance" rule that caused walls of text
  - Removed strict "match energy" word count rules (was too restrictive)
  - Removed "be lazy" instruction (caused single-word responses)
  - Added "no cheerleader validation" (no "Oh nice!", "Wow!")
  - Added "no forced engagement" (no follow-up questions to keep chat going)
  - Temperature: 0.4 → 0.5 (slightly more natural variation)
- **Context Settings**: Chat history set to 50 messages

---

## [1.6.5] - 2026-02-01


### Changed
- **Anti-Copy Rule**: Astra will no longer rephrase GemGem's answers
  - Explicit instruction to form own opinion or react briefly
- **Proactive Search Trust**: Told model search happens automatically
  - "Don't guess or tell users to look it up themselves"
- **Voice Preservation**: Share search results in personality, not as summaries
- **Router Expansion**: More aggressive search triggering
  - Added rules for concepts, theories, philosophies
  - "When in doubt, search=true" principle
  - Added Zizek example for philosophical topics

---

## [1.6.4] - 2026-02-01

### Changed
- **Temperature Reduced**: 0.75 → 0.4 (reduces hallucinations)
- **Prose-Style Prompt**: Rewrote entire personality as paragraphs
  - Removed all bullet point lists
  - Removed INTERESTS section (was causing fabrication)
  - Removed few-shot example injection (caused context confusion)
  - Removed "night owl" reference
- **Startup Logging**: Added search system URL to boot messages

---

## [1.6.3] - 2026-02-01

### Added
- **Few-Shot Examples**: Injected conversation examples to guide response style
  - 6 curated examples showing ideal 2-3 sentence responses
  - 3 random examples injected before each response
  - Demonstrates empathy + engagement ("Yes, And..." principle)

### Changed
- **Personality Enhancements**: Updated ASTRA_PROMPT with new guidelines
  - Added "CONVERSATIONAL SUBSTANCE" section - no dead-end responses
  - "Yes, And..." rule: always add substance when agreeing
  - "Match VIBE, not LENGTH" - thoughtful replies even to short messages
  - Variable sentence length mixing
  - Active participant, not passive observer

---

## [1.6.2] - 2026-02-01

### Added
- **Unfiltered Personality Mode**: Added explicit instructions for abliterated model behavior
  - No refusals, no safety disclaimers, no hedging
  - Swearing, crude humor, controversial topics - all handled naturally
- **TTS Chunking System**: Ported streaming TTS from GemGem
  - Text split into 200-char chunks at sentence boundaries
  - Long responses now speak fully instead of failing silently
  - Markdown stripped before TTS (headers, bold, code blocks, etc.)

### Fixed
- **Router Search Decision**: Fixed LM Studio incompatibility with OpenAI's `json_mode`
  - Router was failing every request with `response_format` error
  - Astra now correctly triggers SearXNG for factual questions
- **Import Error**: Removed stale `GEMGEM_EXAMPLES` export that broke chat cog
- **Volume Mount**: Added `./bot:/app/bot` mount for live code reloading

### Changed
- **Personality Cleanup**: Removed dead code (unused few-shot examples)
  - Deleted `ASTRA_EXAMPLES`, `GEMGEM_EXAMPLES`, `get_all_examples()`
  - Removed specific VTuber names to prevent repetitive mentions
- **Typo Fix**: `tel` → `tei` in user identity section

---

## [1.6.1] - 2026-02-01

### Changed
- **TTS Routing to 5090**: Moved Kokoro TTS from CPU (localhost) to 5090 GPU (`192.168.1.16:8000`)
  - Faster voice synthesis with GPU acceleration
  - Reduced latency for voice responses

---

## [1.6.0] - 2026-02-01

### Changed
- **LM Studio Migration**: Switched from Ollama to LM Studio for all local model inference
  - Chat model: `huihui-ai/mistral-small-24b-instruct-2501-abliterated` (uncensored)
  - Vision model: `gemma-3-27b-it-abliterated` for uncensored image descriptions
  - Models stay loaded as long as LM Studio is open (no more random unloading)
  - Models stay loaded as long as LM Studio is open (no more random unloading)
- **Vision Priority Flip**: Local Gemma 3 is now primary for vision, Gemini is fallback
  - Ensures uncensored descriptions by default
  - Gemini only used if LM Studio is unreachable
- **Kokoro TTS CPU Mode**: Moved TTS from GPU to CPU, freeing ~2GB VRAM for LLMs

### Technical
- Router rewritten to use aiohttp + OpenAI API format instead of ollama library
- Vision uses `/v1/chat/completions` with base64 image data URI format
- LM Studio server accessible on local network (port 1234)

---

## [1.5.5] - 2026-01-31

### Changed
- **Vision Model Upgrade**: Switched from `llama3.2-vision:11b` to `huihui_ai/gemma3-abliterated:27b`
  - Better vision quality benchmarks
  - Fully uncensored image descriptions
  - Runs on 3090 desktop RAM (64GB available)

---

## [1.5.4] - 2026-01-31

### Changed
- **Voice Update**: Switched TTS voice from `af_heart` (Hannah) to `jf_tebukuro` (Japanese female anime voice)
  - Provides a more anime-style voice matching Astra's personality
  - Uses same Kokoro TTS container on 192.168.1.15:8000

---

## [1.5.3] - 2026-01-31

### Fixed
- **Vision Context Ignored**: Astra was seeing images but not using the descriptions in her response
  - **Root Cause**: Vision descriptions passed in `memory_context` had no label and said "DO NOT REPEAT"
  - **Fix**: Renamed to `[WHAT YOU SEE IN THE IMAGE]` with clear instructions to react to specific details
  - Added `[INTERNAL CONTEXT]` label to `memory_context` in `personality.py`
  - Changed user prompt from "don't describe" to "comment on specific things you notice"

---

## [1.5.2] - 2026-01-31

### Fixed
- **User Identity Confusion**: Astra now correctly distinguishes between different users
  - Current speaker prominently marked at top of system prompt
  - Visual separators between chat history and current message
  - Added "USER IDENTITY (CRITICAL)" section to personality prompt
  - `current_speaker` passed through router to reinforce who's talking

---

## [1.5.1] - 2026-01-31

### Added
- **Image Memory System**: Astra now remembers images she's seen
  - Short-term cache of last 5 images (injected into every response)
  - Long-term RAG storage for image descriptions
  - Context persists across searches and messages
- **Local Vision Fallback**: Llama 3.2 Vision 11B for uncensored descriptions
  - Gemini 3.0 Flash tries first (fast)
  - Falls back to local model if Gemini censors or fails
  - Runs on CPU/RAM to preserve VRAM for Mistral

### Changed
- **Upgraded Gemini Vision to 3.0 Flash** from 2.0
- **Brief Natural Reactions**: Astra now gives short reactions to images instead of dumping descriptions
- **Removed Generic Follow-ups**: No more "what's up with you?" or "got anything planned?"

---

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
