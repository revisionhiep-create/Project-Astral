# Changelog

All notable changes to Project Astral will be documented in this file.


## [3.6.7] - 2026-02-24

### Fixed
- **Double-Entry History Loop** (`chat.py`): Fixed a context bug where the current message was added twice to the LLM prompt (once via history fetch and once via router append).
  - Added `before=message` to the history query to ensure only previous messages are fetched.
  - Prevents the bot from falsely flagging the user for "repeating themselves" and triggering the Loop Killer prematurely.
- **Voice Self-Hearing (Echo)** (`voice_receiver.py`): The bot was capturing its own audio output from the voice channel and attempting to process it as speech.
  - Added a filter to ignore audio from `self.voice_client.user.id` in the voice listener.
  - Eliminates feedback loops and "ghost" processing of the bot's own Japanese voice output.

---

## [3.6.6] - 2026-02-22

### Changed
- **Bot Renamed to Astral**: Name changed from Astra to Astral across core files (`personality.py`, `router.py`, `chat.py`, `characters.py`, `discord_context.py`) to match her Discord identity.
- **Personality Discord Tag Awareness** (`personality.py`): Explicitly instructed her that her Discord name is "Astral (LAB)" so she understands direct mentions using that suffix.

### Fixed
- **Raw Discord Tag Resolution** (`chat.py`, `discord_context.py`): The bot was seeing raw numeric IDs (like `<@123456>`) instead of human-readable names when users were mentioned.
  - Switched from `msg.content` to `msg.clean_content` to automatically resolve mentions into `@Username` format before feeding them to the LLM.
- **Vision API Mime Type Crash** (`vision.py`): Hardcoded `image/jpeg` in the Gemini API payload caused silent failures for PNG and WEBP discord attachments.
  - Dynamically extracts the actual `mime_type` from Discord's HTTP response headers (`resp.headers.get('Content-Type', mime_type)`) and passes it to Gemini.
  - Re-verified that `gemini-3-flash-preview` natively supports vision inputs.

---

## [3.6.5] - 2026-02-21

### Fixed
- **Unprompted Character Mentions** (`personality.py`): Astra was randomly namedropping other characters (Liddo, Hiep, Melon) to answer generic questions.
  - Added a strict `LORE & CONTEXT RULE` to the system prompt's character list.
  - Explicitly instructs Astra to use character lore only as background data unless the user asks about them, they are in the chat, or visible in an image.
  - Prevents the uncensored model from treating background lore as an active conversational topic.

---

## [3.6.4] - 2026-02-20

### Fixed
- **Pronoun Disambiguation** (`personality.py`): Astra was confusing "I/me/my" from the user as referring to herself.
  - Expanded the `current_speaker` injection in `build_system_prompt()` to explicitly clarify pronoun ownership per speaker.
  - When the current user says "I", "me", or "my" — the model now understands they mean themselves, not Astra.
  - Applies dynamically to all users (uses `current_speaker` at runtime, not hardcoded).

---

## [3.6.3] - 2026-02-17

### Fixed
- **User-Attached Images Ignored in Draw** (`drawing.py`): When a user attached an image to a draw/gdraw command, it was silently dropped — only pre-loaded character reference images were ever passed to the generator.
  - Root cause: `handle_draw_request` and `handle_guided_draw_request` never checked `message.attachments`.
  - Fix: Both handlers now iterate `message.attachments`, download any image attachments via `attachment.read()`, open them as PIL Images, and prepend them to `reference_images` (user image first, character refs after).
  - Result: "draw this in the style of Futurama" with an attached photo now works — the attached image is passed as a reference to Gemini alongside the prompt.

---

## [3.6.2] - 2026-02-17

### Changed
- **Few-Shot Examples Expanded** (`personality.py`): Added 9 new style anchor examples (5 → 14 total).
  - Covers gaps: fond-tease mode, genuine engagement, compliment deflection, dramatic empathy, longer response anchor, opinion framing.
  - All inputs are generic/situational (no named facts that could cause topic bleed or logic loops).
  - Response structures deliberately varied to prevent single-pattern anchoring.

---

## [3.6.1] - 2026-02-17

### Changed
- **Personality Tone** (`personality.py`): "Low-energy but sharp" → "Relaxed but sharp" — prevents model interpreting personality as apathetic.

---

## [3.6.0] - 2026-02-17

### Changed
- **Backend Switch: KoboldCpp → LM Studio** (`router.py`, `.env`, `docker-compose.yml`): Replaced KoboldCpp with LM Studio as the active inference backend.
  - GLM-4.7-Flash-Heretic had broken thinking mode (never outputs `</think>`) and weak instruction-following.
  - LM Studio runs on host, bot connects via `host.docker.internal:1234`.
- **Model**: `GLM-4.7-Flash-Uncensored-Heretic` → `Qwen3-30B-A3B-Thinking-2507-Abliterated` (huihui).
  - MoE 30.5B total, ~3.3B active per token — fast inference with strong reasoning.
  - Thinking mode enabled via `/think` soft switch in system prompt (LM Studio doesn't support `chat_template_kwargs`).
  - Qwen3 official thinking samplers: temp=0.6, top_p=0.95, top_k=20.
- **LM Studio Backend Config** (`router.py`): Added `"lmstudio"` entry to `BACKEND_CONFIGS`.
  - `LMSTUDIO_HOST` and `LMSTUDIO_CHAT_MODEL` env vars for Docker passthrough.
  - Default backend changed from `"tabby"` to `"lmstudio"`.
- **KoboldCpp Retained**: Container definition and config kept in `docker-compose.yml` for future use — just not started.

### How to Swap Backends
```bash
# In .env:
LLM_BACKEND=lmstudio  # Qwen3-30B-A3B via LM Studio (default)
LLM_BACKEND=tabby     # Qwen3-32B via TabbyAPI
LLM_BACKEND=kobold    # GLM-4.7 via KoboldCpp

# Then:
docker-compose restart astral-bot
```

---

## [3.5.1] - 2026-02-17

### Fixed
- **Appearance Hallucination** (`personality.py`): GLM-4.7 was inventing appearance details ("holographic crown", "crystal armor") not in Astra's character.
  - Added explicit appearance reinforcement to `_CRITICAL_RULES` (end of system prompt, highest recency weight).
  - Negative constraints: "No crowns, no armor, no crystals, no holographics" to block observed hallucinations.

---

## [3.5.0] - 2026-02-17

### Added
- **KoboldCpp Docker Backend** (`docker-compose.yml`): New `astral-koboldcpp` container for GGUF model inference.
  - Official `koboldai/koboldcpp:latest` image with NVIDIA CUDA GPU passthrough.
  - Model and config mounted from `koboldcpp/models/` and `koboldcpp/` volumes.
  - OpenAI-compatible API at `http://koboldcpp:5001/v1/` on the internal Docker network.
  - `KCPP_DONT_TUNNEL=true` — no Cloudflare tunnel (local-only).
- **Multi-Backend Router** (`router.py`): Swappable LLM backends via single `LLM_BACKEND` env var.
  - `BACKEND_CONFIGS` dict holds per-backend settings: host, model, API key, and full sampler presets.
  - `_get_backend()` resolves active config at startup and per-request.
  - Loop detection spikes are now relative to active backend baseline (not hardcoded).
  - `repetition_penalty` sent in payload when backend config includes `rep_pen`.
- **GLM-4.7 Chat Adapter** (`koboldcpp/glm47-nothink-adapter.json`): Custom chat completions adapter for GLM-4.7-Flash.
  - Suppresses thinking at the template level — `assistant_start` includes `</think>` to skip reasoning entirely.
  - Stop sequences: `<|user|>`, `<|observation|>`.
- **Backend Env Vars** (`.env`, `docker-compose.yml`): `KOBOLD_HOST`, `KOBOLD_MODEL`, `KOBOLD_MODEL_FILE`, `KOBOLD_ADAPTER`, `KOBOLD_CONTEXT`, `LLM_BACKEND`.

### Changed
- **Model**: Added `GLM-4.7-Flash-Uncensored-Heretic-NEO-CODE Q4_K_S` (DavidAU imatrix GGUF) as KoboldCpp backend option.
  - 30B-A3B MOE (mixture of experts) — ~2B params active, fits on single GPU (~17GB VRAM).
  - Creator-recommended samplers: temp=0.8, top_p=0.95, top_k=40, min_p=0.05, rep_pen=1.05.
  - Thinking disabled via adapter (no wasted tokens on reasoning).
- **`_strip_think_tags()` Hardened** (`router.py`): Now also catches orphaned `<think>` tags with no closing tag (model cut off mid-reasoning).
- **`MODEL_CHANGE_GUIDE.md`**: Rewritten to document multi-backend switching workflow.

### How to Swap Backends
```bash
# In .env:
LLM_BACKEND=kobold   # GLM-4.7 via KoboldCpp
LLM_BACKEND=tabby    # Qwen3-32B via TabbyAPI

# Then:
docker-compose restart astral-bot
```

---

## [3.4.1] - 2026-02-16

### Changed
- **Removed T/s Footer from Discord** (`chat.py`): Speed metric no longer shown in message footers.
  - T/s is already visible in Docker container logs — no need to clutter Discord messages.
  - Code commented out (not deleted) for easy re-enable if needed.
  - `FOOTER_REGEX` and strip regexes kept intact to handle any old messages still in history.

---

## [3.4.0] - 2026-02-16

### Changed
- **Thinking Mode Enabled** (`router.py`): Switched from `enable_thinking: False` to `enable_thinking: True`.
  - Official Qwen3 thinking samplers: temp=0.6, top_p=0.95, top_k=20, min_p=0.
  - Model now reasons in `<think>...</think>` blocks before responding — stripped by `_strip_think_tags()` before Discord.
  - Max tokens increased: 4000→8000 (normal), 1500→4000 (search) to accommodate thinking blocks.
  - Result: ~28 T/s on EXL2, significantly higher quality responses.
- **Personality v3.4** (`personality.py`): Tuned for thinking mode behavior.
  - "Low-energy but sharp" → "Relaxed but sharp" — prevents model interpreting personality as lazy/apathetic.
  - "Push back freely" → "Not stubborn, roll with corrections" — breaks doubling-down loop where thinking mode compounds aggression.
  - "Teasing is playful, not hostile" — clarifies boundary between snarky and mean.
  - "Snarky ≠ mean. You don't trash people unprovoked." — explicit ceiling on aggression.
  - Strengthened HONESTY: "Never fabricate fake descriptions of real people" and "don't make up negative traits to sound edgy."
  - Removed `/no_think` soft switch from `_CRITICAL_RULES`.
- **Model Switch**: `Qwen3-32B-exl3` (EXL3 4.0bpw) → `Qwen3-32B-4.25bpw-exl2` (EXL2 4.25bpw).
  - EXL3 uses compute-heavy trellis dequantization that bottlenecks on Ampere GPUs (RTX 3090), yielding only 8-10 T/s.
  - EXL2 keeps everything GPU-native with simpler dequantization — ~28 T/s on same hardware.
  - Slightly higher quality at 4.25bpw vs 4.0bpw.
- **TabbyAPI Config** (`config.yml`): Updated `model_name` to `Qwen3-32B-4.25bpw-exl2`, `cache_mode` from `4,4` (EXL3 syntax) to `Q4` (EXL2 syntax).
- **Speed Footer Emoji**: `⚡` → `🚗` for T/s display across `chat.py`, `discord_context.py`.

---

## [3.3.1] - 2026-02-15

### Changed
- **Model Switch**: `bullerwins/Qwen3-32B-exl3-4.83bpw` → `turboderp/Qwen3-32B-exl3` 4.0bpw (official turboderp quant).
  - EXL2 not viable for Qwen3 (ExLlamaV2 lacks Qwen3 architecture support).
  - 4.0bpw gives more VRAM headroom for KV cache on 3090.
- **Disabled Thinking Mode**: Added `/no_think` soft switch to system prompt and `chat_template_kwargs` to API payload to prevent hidden `<think>` token generation that halved throughput.

### Removed
- **Uncensored Model Roleplay Stripping** (`router.py`, `chat.py`): Removed all code added to fight the abliterated model's submissive RP meltdown.
  - `router.py`: Removed `master,`/`mistress,`/`senpai,`/`daddy,`/`onii-chan,` prefix strip and wrapping `"..."` quote strip from both primary and retry paths.
  - `chat.py`: Removed context poisoning cleanup (master/mistress, pussy/servant/maid patterns, gemgem dice hallucination, empty message skip).
  - Kept: `_strip_roleplay_actions()` (action narration) and `Astra:` prefix strip (useful for any model).

---

## [3.3.0] - 2026-02-15

### Changed
- **Model Switch**: `Qwen3-32B-abliterated-exl3-6.0bpw` → `bullerwins/Qwen3-32B-exl3-4.83bpw` (standard, non-abliterated).
  - Abliterated/uncensored fine-tunes destroyed instruction-following entirely (roleplay contamination, ignored system prompt, `<think>` leaking).
  - Standard model preserves Qwen3's native instruction-following while still being capable.
- **Official Qwen3 Samplers** (`router.py`): Switched to Qwen3's recommended non-thinking mode parameters.
  - `temperature`: 0.85 → 0.7 | `top_p`: 0.92 → 0.8 | `top_k`: 40 → 20 | `min_p`: 0.05 → 0
  - `presence_penalty`: 0.25 → 0.3 | `frequency_penalty`: 0.15 → 0.1
  - Removed `repeat_penalty` (was double-penalizing with presence_penalty), `typical_p`, `tfs`.
  - Loop spike params updated to match new baseline (temp 0.85, presence 0.5).
- **Flexible LLM Host** (`router.py`, `rag.py`): Supports both LM Studio and TabbyAPI seamlessly.
  - `LLM_HOST` falls back: `LMSTUDIO_HOST` → `TABBY_HOST` → localhost:1234.
  - `LLM_MODEL` falls back: `LMSTUDIO_CHAT_MODEL` → `TABBY_MODEL` → default.
- **TabbyAPI Config**: Context reduced to 10K tokens (from 12K), EXL3 cache mode `4,4`.
- **Docker**: Passes `TABBY_HOST`, `TABBY_API_KEY` env vars to container.

### Fixed
- **Context Poisoning Cleanup** (`chat.py`): Strips roleplay contamination (master/mistress/pussy) from Astra's own messages in history window.
  - Empty messages after cleanup are skipped entirely.
  - Fixed syntax error in gemgem regex (`\'` in raw string → `\u2019` unicode escape) that was silently breaking the chat cog.
- **Roleplay Stripping** (`router.py`): Post-processing strips `master,`/`mistress,`/`senpai,` prefixes and wrapping `"..."` quotes.
- **Personality Hardening** (`personality.py`): v3.3 — "sharp equal, not a servant", equality framing, anti-loop improvements, always lowercase enforcement.

---

## [3.2.1] - 2026-02-15

### Added
- **Generation Speed Footer** (`router.py`, `chat.py`): Tokens-per-second metric displayed in Discord footer.
  - `_call_lmstudio()` now tracks wall time via `time.perf_counter()` and reads `usage.completion_tokens` from TabbyAPI response.
  - Returns `{"text", "tokens", "tps"}` dict instead of raw string — propagated through `generate_response()` → `process_message()` → `chat.py`.
  - Footer shows `⚡24.1 T/s` alongside existing `💡` (RAG) and `🔍` (search) indicators.
  - Console logs: `[LMStudio] 142 tokens in 3.45s | 41.2 T/s`.
- **Output Loop Detection** (`router.py`): Post-generation similarity check to break bot-to-bot loops.
  - After generating, compares output to last bot message using `difflib.SequenceMatcher`.
  - If similarity >60%, regenerates with spiked params (temp 0.95, rep_penalty 1.15, presence 0.45, freq 0.3).
  - Catches loops where the bot repeats itself despite different user inputs (previous detector only caught user repetition).

### Fixed
- **"Astra:" Prefix in Responses** (`personality.py`, `router.py`): Astra was prefixing every response with her own name.
  - **Root Cause**: Few-shot examples used `Astra: response` format — model mimicked the label.
  - **Fix 1**: Removed `User:`/`Astra:` labels from few-shot examples. Now uses `>` quote style for user messages and bare text for responses.
  - **Fix 2**: Added regex safety net in `router.py` post-processing to strip `Astra:` / `[Astra]:` prefix.
- **Speed Footer Stripping**: Updated all footer-stripping regexes to handle new `⚡T/s` token.
  - `chat.py`: `FOOTER_REGEX` updated, inline copies replaced with shared regex.
  - `discord_context.py`: Added `_SPEED_RE` to `_strip_citations()` — prevents model from hallucinating speed stats.
  - `GemGem-Docker-Live/utils/memory_manager.py`: Added `⚡T/s` strip so GemGem doesn't copy Astra's speed footer.

---

## [3.2.0] - 2026-02-15

### Changed
- **Personality System v3.2** (`personality.py`): Comprehensive prompt overhaul.
  - **Merged ADULT MODE + UNCENSORED**: Two redundant sections (13 lines) merged into one lean TONE section (3 lines). Over-emphasizing "you're uncensored" to an already-uncensored model caused edginess fixation.
  - **Replaced Negative Instructions**: 4 "No X" speech rules replaced with positive framing: "Talk like a real person texting — casual, direct, unfiltered."
  - **Diversified Few-Shot Examples**: All 5 examples were ultra-terse snarky one-liners (caused "mhm" loops, single-word responses). Now includes substantive answer, subtle warmth, and art appreciation examples.
  - **Added IMAGE REACTIONS Section**: Self-recognition rules (star necklace + purple eyes = Astra, rainbow eyes + gems = GemGem), first-person usage, energy matching by content type.
  - **Added SEARCH RESULTS Section**: Instructions to use search results as primary source, weave facts naturally, don't dump raw data.
  - **Added Primacy-Recency Reinforcement**: Critical rules appended as absolute last element in system prompt (after search/memory context) for maximum Qwen3 attention weighting.
  - **Expanded Appearance**: Added gold star pendant necklace (key differentiator from GemGem) and explicit GemGem contrast line.

### Fixed
- **Removed Pink Elephant SYSTEM OVERRIDE** (`router.py`): Deleted hardcoded anti-loop hack that fed the model the exact phrases it shouldn't say ("you're not wrong", "debt", "pay up"). Dynamic temperature spiking already handles loops correctly.

---

## [3.1.1] - 2026-02-15

### Changed
- **Qwen3-32B-Uncensored EXL2 Sampler Optimization** (`router.py`):
  - Applied official recommended sampler preset for `Qwen3-32B-Uncensored` EXL2.
  - `temperature`: 0.75 → 0.85 (natural personality, not robotic).
  - `top_p`: 0.8 → 0.92 (prevents derailment).
  - `top_k`: 20 → 40 (improves coherence).
  - `min_p`: Added 0.05 (critical for Qwen3 stability — prevents flat/unstable personality).
  - `repeat_penalty`: 1.1 → 1.08 (Qwen3 recommended).
  - `presence_penalty`: 0.4 → 0.25 (Qwen3 responds well to this range).
  - `frequency_penalty`: Added 0.15 (prevents repeated phrases).
  - `typical_p`: Added 1.0, `tfs`: Added 1.0 (disabled — Qwen3 performs best without mirostat).
  - `max_tokens`: Kept at 4000/1500 (search responses capped, normal chat uncapped for longer lookups).
  - **Loop Breaker Tuned**: Spike values now stay within Qwen3 recommended range (temp 0.95, presence 0.35) instead of extreme chaos values (1.2/0.8) that caused hallucinations.

---

## [3.1.0] - 2026-02-15

### Added
- **TabbyAPI Integration**: Replaced LM Studio with TabbyAPI for faster EXL2 inference.
  - Updated `docker-compose.yml`, `.env`, and codebases (`router.py`, `rag.py`) to point to `TABBY_HOST`.
  - Configured TabbyAPI to listen on `0.0.0.0` for cross-container communication.
  - Resolved `requests` and `huggingface_hub` dependency conflicts in Tabby backend.

### Changed
- **Personality System v3.1** (`personality.py`):
  - **Uncensored Optimization**: Fully optimized for `Qwen3-32B-Uncensored` EXL2.
  - **Cleaner Hierarchy**: Restructured the system prompt into a more logical hierarchy for better instruction adherence.
  - **Reduced Conflict**: Stripped redundant and conflicting instructions that were causing reasoning drift.
  - **EXL2 Stability**: Adjusted formatting and examples to better suit the tokenization of quantized EXL2 models.
  - **Refined Appearance**: Simplified character descriptions for better focus on self-recognition.

---

## [3.0.8] - 2026-02-14

### Changed
- **Startup Context Summary** (`chat.py`):
  - Astra now generates a summary of the last **200 messages immediately on boot**.
  - **Fixes 3 AM Amnesia**: Previously, the bot would wake up with no memory of the day's conversation after the nightly Docker restart.
  - **Expanded Window**: Background summarizer window increased from 130 → 230 messages (keeping last 30 raw, summarizing 200).
  - Ensures seamless conversation continuity across restarts.

---

## [3.0.7] - 2026-02-14

### Fixed
- **RAG Drawing Pollution**: Cleaned up 70+ drawing-related facts that were causing "That's me" loops.
  - **Root Cause**: Every drawing generated an "objective description" fact stored in long-term memory.
  - **Fix 1**: Deleted all facts with `knowledge_type='drawing'` from `memory.db`.
  - **Fix 2**: Modified `draw.py` to stop storing drawing facts entirely (short-term cache is sufficient).
  - **Maintenance**: Re-embedded all 300+ remaining knowledge entries to ensure vector consistency.

### Changed
- **Personality Tweaks**:
  - **Removed "Pinky" Loop**: Generalised the art critique example to avoid obsessing over specific anatomy.
  - **Removed "Hydrate" Loop**: Swapped specific advice for generic dismissal to prevent repetitive solutions.
  - **Removed Negative Constraint**: Scrubs "star-spiders" example to prevent the "Pink Elephant" effect.

---

## [3.0.6] - 2026-02-14

### Fixed
- **Lexical Overfitting / "Pink Elephant" Loops** (`personality.py`):
  - **Issue**: Astra was obsessively referencing specific nouns from few-shot examples (e.g., "star-spider", "fix the pinky", "hydrate") regardless of context.
  - **Discovery**: LLMs pattern-match specific nouns in few-shot examples as "cheat codes" for the desired tone, leading to logic loops.
    - *Example*: "Don't talk about **star-spiders**" -> Model sees "star-spiders" -> Model talks about star-spiders.
    - *Example*: "Fix the **pinky**" (Art critique) -> Model critiques pinkies on box art.
  - **Fix**: Generalized all few-shot examples to remove specific "magnet words".
    - "Fix the pinky" -> "Anatomy implies you gave up" (Abstract critique)
    - "Tell him to hydrate" -> "Mute him or throw something" (Abstract solution)
    - "Like star-spider nests" -> Removed entirely (Negative constraint fixation)


### Fixed
- **Reverted Personality Regression**: Restored `personality.py` to full instruction-based version (v2.2.3 state).
  - The v3.0.0 LoRA optimization stripped instructions which caused personality degradation when the LoRA failed.
  - Restored full appearance, personality, and "how you talk" guidelines.

---

## [3.0.5] - 2026-02-13

### Changed
- **Re-enabled Thinking Mode**: Removed the "suppress internal thoughts" instruction from `personality.py`.
  - **Reasoning**: With the new Loop Killer (v3.0.4) active, we can safely allow Qwen3's chain-of-thought capabilities.
  - **Mechanism**: The model now generates internal `<think>` blocks for better reasoning and vision analysis.
  - **Safety**: `router.py` automatically strips these blocks before sending to Discord, preventing leakage.
  - **Status**: Enabled for `Qwen3-VL-32B-Instruct-Heretic-v2-i1`.

---

## [3.0.4] - 2026-02-13

### Added
- **Loop Killer (Dynamic Temperature Spiking)**: Implemented self-healing anti-repetition logic in `router.py`.
  - **Mechanism**: Checks if the bot's intended response is structurally similar to previous messages.
  - **Action**: If a loop is detected (e.g., "you're not wrong" pattern), `temperature` spikes to 1.2 and `presence_penalty` to 0.8 for that turn.
  - **Result**: Shatters repetition loops deterministically without needing hardcoded regex filters.

### Fixed
- **Vision Context Integration**: Fixed issue where image analysis bypassed the main chat personality.
  - **Root Cause**: Vision responses were returned directly from Gemini, skipping Qwen3's personality processing.
  - **Fix**: Gemini's image description is now injected into the main chat context as `[IMAGE ANALYSIS DATA]`.
  - **Result**: Astra now sees the image *and* the user's text, allowing for personality-rich responses that address both.

---

## [3.0.3] - 2026-02-13

### Changed
- **Infinite Context via Summarization**: Astral now uses a rolling context window (30 messages) + background summary of 100 older messages, powered by Gemini 2.0 Flash (`router.py`).
  - **No more cutoffs**: Summaries preserve key details indefinitely.
  - **Fixed Personality Drift**: The system prompt is always dominant because the raw chat history is kept short.
- **Latency Optimization**: Offloaded tool/search decision logic (`decide_tools_and_query`) to **Gemini 2.0 Flash**.
  - Eliminated the 3-5 second "short prompt" delay on local hardware.
  - Improved JSON formatting reliability for tool triggers.
- **Removed Mid-System Injection**: The `_inject_mid_context_reminder` was removed from `discord_context.py` as it's no longer needed with the rolling summary (and caused recursion loops).

---

## [3.0.1] - 2026-02-12

### Fixed

- **Hallucination Stripping**: Added regex stripper for "gemgem's rolling dice in the background" phrase loop.
  - **Root Cause**: Model latched onto a specific phrase (likely from training data or context leak) and repeated it compulsively.
  - **Fix**: Added `_strip_specific_hallucinations()` to `router.py` to aggressively remove this phrase and its variations from output.
  - **Refinement**: Regex updated to handle variations like "still rolling dice" and without "in the background".

---


- **Search Context Separation**: Fixed "forgot how to search" issue where Astra ignored search results
  - **Root Cause**: Chat history was being stuffed into the System Prompt's `[CONTEXT]` block along with search results, confusing the model about what was "external info" vs "conversation".
  - **Fix**: Decoupled chat history. History now goes into the User Message (Transcript), while `[CONTEXT]` is reserved exclusively for Search Results and Images.
  - **Updated** `personality.py` to explicitly link `[CONTEXT]` to real-time search results.

---

## [2.5.4] - 2026-02-12

### Added

- **Advanced RAG (Hybrid Search + Re-ranking)**: Upgraded memory retrieval pipeline to fix "Precision vs Recall" trade-off
  - **Hybrid Search**: Combines Vector Search (semantic) + BM25 (keyword) to catch specific terms like error codes
  - **Cross-Encoder Re-ranking**: Uses `ms-marco-MiniLM-L-6-v2` to strictly judge relevance of top candidates
  - **Query Normalization**: Uses LLM to rewrite "omg help python broken" -> "how to fix python installation" keyphrases
  - **Result**: Drastically improved recall for specific technical queries while maintaining semantic understanding

---

## [3.0.1] - 2026-02-12

### Fixed

- **Hallucination Stripping**: Added regex stripper for "gemgem's rolling dice in the background" phrase loop.
  - **Root Cause**: Model latched onto a specific phrase (likely from training data or context leak) and repeated it compulsively.
  - **Fix**: Added `_strip_specific_hallucinations()` to `router.py` to aggressively remove this phrase and its variations from output.
  - **Refinement**: Regex updated to handle variations like "still rolling dice" and without "in the background".

---

## [2.5.3] - 2026-02-11

### Changed

- **Centralized Model Configuration** (`docker-compose.yml`, `.env`):
  - Model selection is now controlled via a single `.env` variable: `LMSTUDIO_CHAT_MODEL`
  - `docker-compose.yml` passes this variable to the container
  - `router.py`, `rag.py` updated to use `os.getenv("LMSTUDIO_CHAT_MODEL")`
  - No more hardcoded model names in Python code
  - Default model remains: `qwen3-vl-32b-instruct-heretic-v2-i1`

---

## [2.5.2] - 2026-02-11

### Changed

- **Combined Voice Commands** (`voice.py`):
  - `/join` now automatically enables listening (STT) — no separate command needed
  - Removed independent `/listen` command (redundant)
  - `/leave` handles cleanup of both voice connection and listening state

---

## [2.5.1] - 2026-02-11

### Fixed

- **"Beach in 2004" Parrot Loop** (`personality.py`): Replaced sticky few-shot example that Qwen3 was repeating verbatim
  - **Root Cause**: Qwen3 latches onto vivid, specific imagery in few-shot examples and reproduces it as a signature phrase
  - **Fix**: Swapped "mentally? i'm on a beach in 2004" for "i'm never busy. that implies i have ambition" — same lazy energy, no catchphrase to parrot
- **Bot Impersonation in Group Chat** (`personality.py`, `discord_context.py`): Astra was speaking for GemGem ("gemgem would say...")
  - **Root Cause**: In 50-message context windows, Qwen3's attention dips mid-context ("lost in the middle"), causing identity drift
  - **Fix 1**: Added explicit rule to personality prompt: "NEVER speak FOR GemGem or any other bot. Don't write what they 'would say'"
  - **Fix 2**: `MID_CONTEXT_REMINDER` injected at the halfway point of chat history targets the exact "would say" pattern
  - Astra giving her OWN critique/opinions after search results is fine — just can't put words in other bots' mouths
- **Footer Emojis on Separate Lines** (`chat.py`): Attribution footers (💡, 🔍) now appear on the same line instead of stacking vertically
- **TTS Reading Citation Numbers** (`chat.py`): Kokoro TTS no longer reads citation markers (`[1]`, `[🔍1]`) or footer emojis aloud — stripped before sending to voice

---

## [2.5.0] - 2026-02-10

### Changed

- **Proper ChatML Role Separation** (`router.py`): Switched from single-message transcript format to proper `system`/`user` message roles
  - System message: personality + search results + memory (instruction-following priority)
  - User message: conversation transcript + current question
  - LM Studio's OpenAI API handles ChatML tokenization — no more manual prompt embedding
  - Previously everything was in one giant `user` message, making the model treat search results as conversational context rather than authoritative instructions
- **Removed Length-Based Search Reranking** (`search.py`): Stopped sorting results by snippet length
  - **Root Cause**: Longer snippets from low-quality SEO sites (e.g., `thetechylife.com`) were promoted over shorter but accurate snippets from reputable sources
  - **Evidence**: SearXNG returned "RX 6900 XT has 24GB VRAM" (wrong — it's 16GB) from a junk site with a long snippet, and Astra faithfully repeated it
  - Now uses SearXNG's native relevance ordering instead

---

## [2.4.1] - 2026-02-10

### Changed

- **STT Fallback Priority**: Swapped STT order — Gemini cloud is now primary, local faster-whisper is fallback
  - Mirrors GemGem's STT config for consistency across bots

### Fixed

- **Double Prompting on Voice**: Single utterances were split into multiple LLM prompts
  - **Root Cause**: VAD silence threshold (1.5s) too aggressive — natural breath pauses split speech into sub-second fragments (e.g. "The", "If you're not") that each triggered a full LLM call
  - **Fix 1**: Raised `SILENCE_THRESHOLD_SEC` 1.5→2.0s, `MIN_UTTERANCE_SEC` 0.5→1.5s in `voice_receiver.py`
  - **Fix 2**: Added 3-word minimum filter in `voice.py` `_on_utterance` — short fragments logged and dropped

---

## [2.3.4] - 2026-02-10

### Fixed

- **"That's me" Loop**: Astra was starting every response with "that's me." even without images
  - **Root Cause**: Image descriptions stored in RAG as permanent facts (e.g. "you, Astra, depicted as...") matched every query at 65%+ similarity
  - **Fix 1**: Disabled RAG storage of image descriptions in `vision.py` and `chat.py` — 5-minute short-term cache is sufficient
  - **Fix 2**: Purged all 30 `image_knowledge` entries from database
  - **Fix 3**: Added temp regex strip of "that's me" prefix in `router.py` until old messages roll out of chat history
- **RAG Noise**: Facts were injected into every response regardless of relevance
  - **Root Cause**: Similarity thresholds too low for `gemini-embedding-001` (3072-dim vectors score 50-70% even for unrelated text)
  - **Fix**: Raised threshold from 0.65 → 0.78 in `rag.py`

---

## [2.3.3] - 2026-02-10

### Fixed

- **RAG Retrieval Completely Broken**: 💡 footer never appeared because every retrieval crashed
  - **Root Cause**: v2.3.1 re-embedded `knowledge` table (768→3072 dim) but missed `image_knowledge` table — 2 old 768-dim entries remained
  - `retrieve_relevant_knowledge()` had one try/except wrapping ALL table scans, so one 768-dim image entry crashed the entire retrieval
  - **Fix 1**: Re-embedded all `image_knowledge` entries to 3072-dim (`reembed_images.py`)
  - **Fix 2**: Added per-entry try/except in `rag.py` — mismatched entries are now skipped with a warning, not a full crash

---

## [2.3.2] - 2026-02-09

### Changed

- **Deterministic Citation Footers**: Removed LLM-driven citation markers in favor of programmatic footers
  - `💡N` appended when RAG found N memory facts, `🔍N` when search returned N results
  - Removed `[🔍1]`, `[💡1]` citation instructions from personality prompt (`personality.py`)
  - Removed `[💡N]` prefix from RAG knowledge formatting (`rag.py`)
  - Removed `[🔍N]` prefix from search result formatting (`search.py`)
  - Footers added deterministically in `chat.py` after response generation
  - Footers stripped before RAG storage to prevent fact contamination
  - Footers stripped from Astra's own messages in Discord history context

---

## [2.3.1] - 2026-02-09

### Fixed

- **Embeddings Model Shutdown**: Google shut down `text-embedding-004` on Jan 14, 2026 — all RAG was silently broken
  - **Root Cause**: Every `genai.embed_content()` call returned 404, breaking both fact storage AND retrieval
  - **Fix**: Switched to `gemini-embedding-001` in `embeddings.py` (3072-dim vectors, same free API)
  - Re-embedded all 67 existing knowledge entries with new model (0 failures)
  - This was the real reason facts stopped storing since ~Feb 5 (not the Docker rename)

---

## [2.3.0] - 2026-02-09

### Added

- **Admin & Whitelist Access Control**: Ported from GemGem-Docker-Live
  - `tools/admin.py`: `ADMIN_IDS` (4 root admins) + `WhitelistManager` (file-backed `whitelist.txt`)
  - `cogs/admin.py`: `AdminCog` with `/access add`, `/access remove`, `/access list` slash commands
  - `@Astra access [add/remove/list]` mention commands for legacy text usage
  - Root Admins cannot be removed; only admins can add/remove users
  - Authorization gate added to `chat.py` and `draw.py` — unauthorized users are silently ignored
  - Whitelist persisted via `./bot:/app` volume mount (no docker-compose changes needed)

---

## [2.2.3] - 2026-02-08

### Changed

- **Qwen3-VL Personality Optimization**: Fixed "mhm" loop where Astra collapsed into one-word responses
  - **Root Cause**: `repeat_penalty: 1.15` was too aggressive for Qwen3 — model got penalized for common words and retreated to minimal tokens
  - **Sampler Fixes** (`router.py`):
    - `repeat_penalty`: 1.15 → 1.05 (Qwen3 recommended)
    - `temperature`: 0.65 → 0.7 (non-thinking mode optimal)
    - Added `top_p: 0.8`, `top_k: 20` (Qwen3 recommended)
    - Added `presence_penalty: 0.15` (vocabulary diversity)
  - **Personality Prompt Rewrite** (`personality.py`):
    - Added few-shot style examples to anchor "lazy but substantive" tone
    - Added explicit anti-loop instruction: "NEVER respond with just 'mhm' or single-word replies"
    - Added anti-repetition awareness: check recent messages and switch it up
    - Softened brevity from "1-4 sentences" to "concise but substantive"
    - Added `[SYSTEM NOTE]` to suppress `<think>` tag leakage (Qwen3 RP best practice)
    - Preserved: VIBE, ADULT/NSFW, HONESTY RULE, SEARCH PRIORITY, image self-recognition guardrails

---

## [2.2.2] - 2026-02-08

### Changed

- **Citation Emoji System**: Visual distinction for citation sources
  - Search citations: `[🔍1]`, `[🔍2]` — facts from live SearXNG search
  - Memory citations: `[💡1]`, `[💡2]` — facts from RAG knowledge base
  - Previously both used plain `[1]`, `[2]` with no way to tell the source
- **Anti-Hallucination Citation Stripping**: Astra no longer fakes citations
  - Strips `[🔍N]`, `[💡N]`, and `[N]` markers from Astra's own messages in chat history context
  - Model was seeing its own past citations and mimicking the pattern with no actual source
  - `discord_context.py`: Added `_strip_citations()` helper applied to Astra's messages
- **RAG Memory Formatting**: Knowledge facts now use numbered `[💡N]` format
  - Previously injected as unstructured `- [type] content` bullets
  - Now formatted as `MEMORY FACTS - Cite with [💡1], [💡2]` with numbered entries

---

## [2.2.1] - 2026-02-08

### Added

- **Search Results → RAG Storage**: Search results now stored as long-term knowledge facts
  - Every SearXNG search gets embedded and saved to `knowledge` + `search_knowledge` tables
  - Previously search results were ephemeral (used once and discarded)
  - Astra can now recall previously searched topics via RAG retrieval
- **RAG Debug Logging**: Added visibility into RAG memory hits
  - Logs when facts are injected: `[RAG] Injecting N facts into context: ...`
  - Logs when no matches found: `[RAG] No relevant memories found for: '...'`
  - Logs when search results are stored: `[RAG] Stored N search results as knowledge`

---

## [2.2.0] - 2026-02-08

### Removed

- **Slash Commands Cleanup**: Removed all slash commands except `/join` and `/leave`
  - Deleted: `/search`, `/time`, `/ping`, `/clear`, `/draw`, `/gdraw`
  - `@Astral draw` and `@Astral gdraw` mention commands still work as before
  - Deleted `commands.py` cog entirely (search, time, ping, clear)
  - Removed slash methods from `draw.py` (kept `on_message` draw/gdraw handlers)

---

## [2.1.0] - 2026-02-07

### Changed

- **Vision**: Stays on **Gemini 3.0 Flash** — Heretic fine-tune strips VL vision encoder from Qwen3
- **Text Attribution Prompt**: Added instruction to treat text in images as character dialogue/thoughts
  - "Treat text within the image as the character's dialogue, internal thoughts, or a message they are reacting to"
  - Better handling of memes, comics, and text-heavy images

### Fixed

- **RAG Image Storage**: Fixed parameter mismatch in `store_image_knowledge()` call (`description` → `gemini_description`)

---

## [2.0.0] - 2026-02-07

### Changed

- **Model Upgrade**: Switched chat brain from `Gemma3-27B-it-vl-GLM-4.7-Uncensored-Heretic-Deep-Reasoning` to `Qwen3-VL-32B-Instruct-Heretic-v2-i1`
  - Qwen3 VL 32B with vision-language capabilities
  - Updated `docker-compose.yml` with `LMSTUDIO_CHAT_MODEL` env var for centralized model config
  - Updated fallback defaults in `router.py` and `rag.py`
- **Context Window Expansion (16K)**: Optimized for Qwen3's larger context
  - Discord history: 25 → 50 messages (restored from 8K-era reduction)
  - Router context for search decisions: 1,500 → 3,000 chars
  - Default max_tokens: 2,048 → 4,000
  - Stop sequences updated from Gemma to Qwen3 format
  - `format_discord_context` expanded to match 50-message fetch

---

## [1.9.9] - 2026-02-06

### Changed

- **Vision Routed to Gemini 3.0 Flash**: Complete vision overhaul
  - All image analysis now uses `gemini-3-flash-preview` exclusively
  - Removed `describe_image_local()` and all LM Studio vision code
  - Gemini now does both image analysis AND character matching (can see and compare)
  - Astra only reacts to Gemini's analysis - no more hallucinated character matches
  - Stricter matching rules: requires multiple features to match, not just one
  - New comprehensive prompt covering all image types (art, photos, memes, screenshots)

- **Docker Container Renamed**: `gemgem-bot` → `astral-bot`
  - Service renamed from `gemgem-bot` to `astral-bot`
  - Container renamed from `gemgem-bot` to `astral-bot`
  - SearXNG container renamed from `gemgem-searxng` to `astral-searxng`
  - Network renamed from `gemgem-network` to `astral-network`

---

## [1.9.8] - 2026-02-05

### Fixed

- **Search Repetition Loop**: Astra was getting stuck repeating search citations in a loop
  - **Root Cause**: Model latching onto citation pattern and repeating same content
  - **Fix 1**: Added `repeat_penalty: 1.15` to LM Studio API calls
  - **Fix 2**: Added `_strip_repeated_content()` post-processing to dedupe output lines
  - **Fix 3**: Reduced `max_tokens` from 6000 → 1500 for search responses (less room for looping)

---

## [1.9.7] - 2026-02-05

### Fixed

- **Content Stripped with Bold Markers**: Fixed `_strip_roleplay_actions()` eating content between asterisks
  - **Root Cause**: Regex `\*[^*]+\*` was deleting `*text*` entirely (including the content)
  - **Fix**: Changed to `\*([^*]+)\*` → `\1` (preserves content, removes only asterisks)
  - Search results now display correctly: "5 feet 4 inches" instead of blank
- **Docker Volume Mount**: Fixed `./bot:/app/bot` not overlaying running code
  - Changed to `./bot:/app` so code changes are reflected without rebuild

---

## [1.9.6] - 2026-02-05

### Fixed

- **Search Result Markdown Pollution**: Stripped `**bold**` and `*italic*` markdown from search snippets
  - SearXNG sometimes returns content with markdown from source pages
  - Astra was echoing `**` or outputting empty bold markers
  - Now sanitized before feeding to LLM

---

## [1.9.5] - 2026-02-05

### Fixed

- **Chat History Timezone Bug**: Timestamps in chat context now display PST instead of UTC
  - Discord's `msg.created_at` was showing UTC times in context (e.g., 2:05 AM instead of 6:05 PM)
  - Now converts to PST using `astimezone(pytz.timezone("America/Los_Angeles"))`
  - Astra now sees correct Pacific time in conversation history

---

## [1.9.4] - 2026-02-05

### Changed

- **Anti-Hallucination Search Grounding**: Perplexity-style citation system
  - **Citation Format**: Search results now use `[1]`, `[2]` style numbering
  - **Grounding Constraint**: Model must only state facts from sources, no "extra" info from memory
  - **Confidence Fallback**: If search doesn't have the answer, says "couldn't find that" instead of guessing
  - **Result Reranking**: Search results sorted by content quality (longer snippets = more useful) before LLM sees them
- Personality preserved - citations only affect factual claims, not vibes/reactions

---

## [1.9.3] - 2026-02-04

### Changed

- **Search Intelligence Overhaul**: Smarter search routing and better results
  - **Query Rewriting**: Router now de-contextualizes pronouns (he/she/it → actual entities)
  - **Dynamic Time Range**: Searches use appropriate time filters (`day` for news, `null` for historical facts)
  - **User-Agent Headers**: Prevents search engines from blocking requests
  - **Improved Formatting**: Results now include numbered sources with URLs
  - Well-known concepts (Stoicism, basic science) skip search, use model knowledge
- **Search Priority Fix**: Search results now placed at TOP of context (high attention zone)
  - Fixes "Lost in the Middle" problem where model ignored search results
  - Added `SEARCH PRIORITY` rule: must use search results for factual questions
- **Anti-Hallucination Rule**: Added `HONESTY RULE` to personality
  - Never fabricate or paraphrase user quotes
  - Admit confusion instead of inventing statements to justify errors
- **Draw Commands**: Removed embeds from `draw`, `gdraw`, and `edit` commands
  - Embeds were cutting off enhanced prompts at 500 chars
  - Now uses plain text formatting with full prompt display

---

## [1.9.2] - 2026-02-04

### Changed

- **Transcript Format for Gemma 3 Reasoning**: Refactored prompt construction for group chat stability
  - Switched from ChatML message list to single-message transcript format
  - History expanded to 50 messages (up from 10)
  - Format: `[Username]: Message` per line, ending with instruction footer
  - Prevents reasoning model confusion in multi-user scenarios
- **Stop Sequences Added**: Prevents model from roleplaying other users
  - Stops on: `\n[`, `[Hiep]`, `[User]`, `<end_of_turn>`, `<start_of_turn>`
  - Crucial for uncensored models prone to user impersonation
- **Summary RAG**: Conversations stored as facts, not raw logs
  - Before: Raw "Hiep: hey\nAstra: sup" chat logs polluted memory
  - Now: LLM extracts meaningful facts like "Hiep is developing a Discord bot"
  - Chatter/small talk is discarded, only useful facts are stored
  - Prevents "context poisoning" and reasoning model confusion
- **Think Tag Stripping**: `<think>...</think>` blocks stripped from output (already existed)

---

## [1.9.1] - 2026-02-04

### Fixed

- **Wrong Time Reporting**: Astra was reporting UTC time instead of PST (8 hours ahead)
  - Root cause: Docker container had no timezone set, `datetime.now()` returned UTC
  - Fix: Added `ENV TZ=America/Los_Angeles` to Dockerfile
  - Astra now correctly reports Pacific time

---

## [1.9.0] - 2026-02-03

### Fixed

- **Username Confusion**: Astra no longer calls users by wrong names (e.g., calling Hiep "tei")
  - **Root Cause**: Speaker identity at START of context was getting diluted by 50 messages of chat history
  - **Fix 1**: Added speaker identity to SYSTEM PROMPT itself (highest priority)
  - **Fix 2**: Moved speaker reminder to END of context (recency bias)
  - **Fix 3**: Reduced context from 50→25 messages (less name pollution)

### Changed

- `ai/personality.py`: `build_system_prompt()` now accepts `current_speaker` param
- `ai/router.py`: Removed redundant speaker header, passes speaker to system prompt
- `cogs/chat.py`: Reduced history limit, restructured context with speaker at end

---

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
  - Focus on _why_ art is aesthetically striking, not just clinical descriptions

---

## [1.8.3] - 2026-02-02

### Changed

- **Image Reactions Reworked**: Astra now reacts like a "Man of Culture" to shared art
  - Genuine enthusiasm instead of stiff art critiques
  - Leads with the "Wow" factor - what catches her eye first
  - Natural language for aesthetics ("golden hour lighting feels cozy" not clinical descriptions)
  - Technical appreciation for rendering details (skin shading, fabric folds, eye detail)
  - Unapologetically appreciates spicy art - comments on _how_ the artist made it work

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
  - Handles markdown code blocks (`json {...}`)
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

## [v4.1.8] - 2026-02-13 (Fix - Vision Context & Loop Stability)

### 👁️ Vision System Upgrade
- **Context-Aware Vision**: Updated the Gemini 3.0 Vision pipeline to receive the user's specific question/comment alongside the image.
  - *Before*: Generates a generic description. (User: "Is this food?" -> Gemini: "It's a cat." -> Astra: "Why are you asking?")
  - *Now*: Generates a contextual answer. (User: "Is this food?" -> Gemini: "It's a cat, definitely not food." -> Astra: "No, it's a pet.")
- **Image-Only Message Fix**: Fixed a bug where sending an image without text caused Astra to complain about "blank messages".

### 🧠 Logic AI & Router Fixes
- **Loop Detector Code Fix**: Fixed a critical logic error in `router.py` where the bot flagged its own previous message in the *transcript* as a user repetition loop. This was causing `Temperature` to spike to near-max (1.2) on almost every turn, leading to hallucinations like the "star-spider nest" being forced into unrelated topics.
- **Topic Integrity Instruction**: Added a specific "TOPIC INTEGRITY" section to the system prompt in `personality.py`.
  - Explicit instruction to *ignore* unrelated background chatter from other users.
  - Explicit instruction to *drop* old topics when the user changes the subject (prevents forced callbacks to previous jokes like the star-spider).

---

## [4.1.7] - 2026-02-13

### Fixed
- **Context Loop Poisoning**: Fixed Astra getting stuck in a meta-loop where she kept asking "why do you keep asking about X?"
  - **Root Cause**: The background summarizer (Gemini 2.0 Flash) was capturing the *fact that a user was repeating themselves* as a "Current Topic". This summary was then fed back into the prompt, convincing Astra that the user was *still* asking about it, causing her to comment on it again, reinforcing the summary loop.
  - **Fix**: Updated `summarize_text` prompt to explicitly ignore repetition, "loops", and meta-commentary on user behavior. Focuses strictly on factual topics now.

---

## [4.1.6] - 2026-02-13

### 🐛 Fixes
- **Vision Identity Logic**: Fixed strict differentiation between Astra and GemGem in all art styles.
  - **Key Differentiator**: Astra = Purple eyes/Star necklace (Mature). GemGem = Rainbow eyes/Gem accessories (Chibi/Cute).
  - **Multi-Character Support**: Vision prompt now explicitly handles images where BOTH characters appear.
  - **Personality Fix**: Astra no longer claims "that's me" on GemGem's art just because of blue hair.

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
