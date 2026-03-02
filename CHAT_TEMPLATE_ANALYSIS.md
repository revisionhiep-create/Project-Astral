# Project-Astral Chat Template Analysis

## Executive Summary

**Current State:** Project-Astral does NOT currently use Jinja2 chat templates. Instead, it uses:
- Manual string formatting in Python with hardcoded ChatML message structure
- Direct OpenAI API format (system/user/assistant roles)
- Raw string concatenation for prompt construction

**Qwen Chat Template Relevance:** The provided Qwen Jinja2 template would NOT improve the current implementation because:

1. LM Studio already handles ChatML tokenization automatically
2. The project uses the OpenAI-compatible API, not raw model inference
3. Message formatting is already optimized for the current setup
4. The template would add unnecessary abstraction layer

---

## Current Message Handling Architecture

### 1. Chat Template Usage (or lack thereof)

Location: bot/ai/router.py (lines 159-377)

The project builds messages manually in Python:

```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
]
```

How it works:
- System prompt is built by build_system_prompt() in personality.py
- User prompt contains: conversation transcript + current message
- Messages are sent as OpenAI-compatible JSON to LM Studio
- LM Studio handles ChatML tokenization internally (no template needed)

### 2. Model Configuration & Inference

Current Setup:
```
Model:    Qwen3-Coder-30B-A3B-Instruct-Heretic (via LM Studio)
API:      OpenAI-compatible endpoint (http://host.docker.internal:1234/v1/chat/completions)
Backend:  LM Studio (supports multiple backends via env var switching)
```

Environment Variable Configuration:
```
LMSTUDIO_HOST=http://host.docker.internal:1234
LMSTUDIO_CHAT_MODEL=qwen3-coder-30b-a3b-instruct-heretic-i1
LLM_BACKEND=lmstudio  # Also supports: tabby, kobold
```

Sampler Settings (in router.py, lines 159-175):
```
temperature: 0.6
max_tokens: 8000
top_p: 0.8
top_k: 20
min_p: 0
repeat_penalty: 1.05
presence_penalty: 0.3
frequency_penalty: 0.1
```

---

## Tool/Function Calling Implementation

**Current Tool Architecture: RULE-BASED, NOT LLM-BASED**

Instead of OpenAI-style function calling (tools=[], tool_choice=auto), the project uses:

### 1. Decision Router (Gemini-Based)

Location: bot/ai/router.py (lines 208-315)

Process:
1. Uses Gemini 2.5 Flash (NOT the local model) to decide if tools are needed
2. Sends a structured prompt asking: Do we need search? Do we have an image?
3. Expects JSON response with: search, search_query, vision, time_range

Tools Decided:
- search: true -> run SearXNG web search
- vision: true -> run Gemini 3.0 Flash image analysis
- time_range sets the search scope (real-time vs. historical)

### 2. Tool Execution Pipeline

Location: bot/cogs/chat.py (lines 80-226)

NO OpenAI-style function calling:
- No tools array in message payload
- No function_call role in messages
- No iterative tool loops

---

## Message Formatting & Prompt Construction

### 1. System Prompt Construction

Location: bot/ai/personality.py (lines 231-267)

Components (in order):
1. Personality prompt - Character definition + few-shot examples
2. Current speaker identity - "You are talking to: {name}"
3. Vision analysis (if image attached) - Image description
4. Search context (if search results exist) - Web search results
5. Memory context - RAG long-term facts

Personality Prompt includes:
- Character definition: Astral (LAB), 22, she/her
- Visual description: Long dark blue-black hair, teal highlights, purple-violet eyes
- Character relationships
- Personality traits: dry humor, dark humor, blunt, low-energy
- Speech style: lowercase, concise, no markdown, no assistant tone
- Few-shot examples: 12 example exchanges

### 2. User Prompt Construction

Location: bot/ai/router.py (lines 368-377)

Built as:
- Transcript from last 50 messages with [Speaker]: prefix
- Instruction: Reply to the last message as Astral

Full message array sent to LM Studio:
```
{"role": "system", "content": system_prompt}
{"role": "user", "content": user_prompt}
```

---

## Key Differences from Using Jinja2 Templates

### What a Jinja2 Chat Template Would Do:

Would format messages into raw text like:
```
<|im_start|>system
{system content}<|im_end|>
<|im_start|>user
{user content}<|im_end|>
<|im_start|>assistant
```

### Why Project-Astral Doesn't Need This:

1. LM Studio Already Handles It: The OpenAI-compatible API endpoint automatically converts the JSON messages into proper ChatML format using the model's built-in template.

2. Decoupling from Model: By using OpenAI API format, the project can swap models (Qwen -> GLM-4.7 -> Llama) without changing code.

3. No Direct Tokenization: The project never interacts with tokenizers directly. Message formatting happens on the LM Studio server side.

4. Flexibility for Multiple Backends: Three backends are supported (TabbyAPI, KoboldCpp, LM Studio) - each has different internal chat templates.

---

## Post-Processing & Output Cleaning

Location: bot/ai/router.py (lines 20-104)

The local model output goes through 5 sequential cleaning passes:

1. _strip_think_tags() - Remove <think>...</think>
2. _strip_roleplay_actions() - Remove (pauses), *actions*
3. _strip_markdown() - Remove ##, ```, >
4. _strip_repeated_content() - Dedupe repeated lines
5. _strip_specific_hallucinations() - Fix double punctuation
6. Strip self-name prefix like "[Astral]: "

Why these steps?
- Qwen3-Coder is optimized for code, adds markdown
- Heretic/uncensored models add roleplay narration
- Chain-of-thought models output thinking blocks
- Local models can get stuck in repetition loops

---

## Current Limitations & Why Jinja2 Templates Won't Help

Issue: Output includes roleplay narration
Root Cause: Model style (Heretic tuning)
Jinja2 Template Fix?: NO - requires sampling adjustments

Issue: Repetition loops in long responses
Root Cause: Model stalling + lack of repeat_penalty
Jinja2 Template Fix?: NO - requires sampler tuning

Issue: Think tags appear in output
Root Cause: Chain-of-thought models default
Jinja2 Template Fix?: NO - already stripped post-inference

Issue: Identity drift in 50+ message history
Root Cause: Attention midpoint issues
Jinja2 Template Fix?: NO - requires context injection (already done)

Issue: Wrong tool decisions occasionally
Root Cause: Gemini 2.5 Flash limitations
Jinja2 Template Fix?: NO - requires better prompt engineering

---

## Recommendations for Template Consideration

When to adopt Jinja2 templates:
1. If migrating to raw model access (vLLM, Ollama with direct tokenization)
2. If supporting 10+ different models with incompatible chat formats
3. If you need exact control over BOS/EOS/separator tokens

For current Project-Astral setup: Jinja2 templates would add complexity without benefits.

---

## Files Involved in Message Handling

ai/router.py - Main inference orchestration (HIGH)
ai/personality.py - Prompt template construction (HIGH)
ai/query_enhance.py - Query de-contextualization (MEDIUM)
cogs/chat.py - Full orchestration pipeline (HIGH)
memory/rag.py - Knowledge retrieval (MEDIUM)
tools/search.py - Search execution (LOW)
tools/vision.py - Image analysis (LOW)

---

## Conclusion

**Current Chat Template Status:** None (not needed)

**Would Qwen Chat Template Help?** No

**What's Working Well:**
- OpenAI API abstraction allows backend flexibility
- ChatML handling is automatic via LM Studio
- Multi-pass output cleaning covers model-specific quirks
- Deterministic tool routing via Gemini eliminates hallucinated function calls

**What Could Be Improved (but not via Jinja2):**
- Fine-tune sampler values per backend
- Add adaptive temperature based on response length
- Improve Gemini decision prompts for edge cases
- Implement native OpenAI-style function calling (with streaming)

Analysis Date: 2026-03-02
Codebase: Project-Astral (Astral Discord Bot)
