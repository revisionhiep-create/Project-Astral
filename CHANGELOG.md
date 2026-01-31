# Changelog

All notable changes to Project Astral will be documented in this file.

## [1.1.0] - 2026-01-31

### Added
- **Context Awareness**: Astra can now see and reference chat history from the current channel
- Direct channel history fetching (last 50 messages)
- Explicit personality instructions for context awareness
- "astral" keyword added to character recognition

### Fixed
- **Chat History Bug**: Bot messages were all labeled as "Astra" - now only THIS bot is labeled correctly, other bots (like GemGem) keep their real names
- **Privacy Refusal Override**: Model was incorrectly refusing to reference chat history due to "privacy" training - added explicit instructions that Astra is part of the conversation and CAN see messages
- Centralized personality prompt now properly used in drawing critiques and image analysis

### Changed
- `chat.py`: Uses `message.channel.history()` directly instead of separate fetch function
- `personality.py`: Added CONTEXT AWARENESS section with clear instructions
- `characters.json`: Added "astral" to Astra's keywords

## [1.0.0] - 2026-01-30

### Added
- Initial Project Astral setup (rebranded from GemGem-LABS)
- Mistral Small 24B as unified brain
- SearXNG integration for grounded search
- RAG-based long-term memory
- Drawing commands with Gemini Vision
- Centralized personality system
