"""AI Router - Multi-backend LLM orchestration (TabbyAPI / KoboldCpp)."""
import os
import json
import time
import aiohttp
from typing import Optional
import difflib

import re
import google.generativeai as genai

from ai.personality import build_system_prompt
from tools.time_utils import get_date_context

# Configure Google AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ── Backend Configuration ─────────────────────────────────────────────
# Switch via LLM_BACKEND env var: "tabby" | "kobold"
LLM_BACKEND = os.getenv("LLM_BACKEND", "tabby").lower()

# Per-backend defaults: (host, model, sampler overrides)
BACKEND_CONFIGS = {
    "tabby": {
        "host": os.getenv("TABBY_HOST", "http://host.docker.internal:5000"),
        "model": os.getenv("TABBY_MODEL", "Qwen3-32B-4.25bpw-exl2"),
        "api_key": os.getenv("TABBY_API_KEY"),
        # Qwen3 official thinking-mode samplers
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0,
        "presence_penalty": 0.3,
        "frequency_penalty": 0.1,
        "extra_payload": {"chat_template_kwargs": {"enable_thinking": True}},
    },
    "kobold": {
        "host": os.getenv("KOBOLD_HOST", "http://koboldcpp:5001"),
        "model": os.getenv("KOBOLD_MODEL", "GLM-4.7-Flash"),
        "api_key": None,  # KoboldCpp doesn't need auth
        # GLM-4.7 creator-recommended samplers (DavidAU screenshot)
        "temperature": 0.8,
        "top_p": 0.95,
        "top_k": 40,
        "min_p": 0.05,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "rep_pen": 1.05,
        "extra_payload": {},  # No thinking kwargs — adapter handles it
    },
}


def _get_backend():
    """Return the active backend config dict."""
    return BACKEND_CONFIGS.get(LLM_BACKEND, BACKEND_CONFIGS["tabby"])


def _strip_think_tags(text: str) -> str:
    """
    Strip <think>...</think> reasoning blocks from model output.
    Safety net — should rarely fire when thinking is disabled at the template level.
    """
    if not text:
        return text
    # Remove <think>...</think> blocks (including newlines within)
    cleaned = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
    # Also strip orphaned opening <think> with no closing tag (model started thinking but got cut off)
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL)
    return cleaned.strip()


def _strip_roleplay_actions(text: str) -> str:
    """
    Strip roleplay action narration from model output.
    The abliterated/roleplay-tuned models often output (pauses, blinks slowly) style actions.
    """
    if not text:
        return text
    # Remove (action) style narration - matches parentheses with lowercase text inside
    # Examples: (pauses), (blinks slowly), (sighs dramatically)
    cleaned = re.sub(r'\([a-z][^)]*\)\s*', '', text)
    # Strip asterisks from *italic* text but PRESERVE the content
    # This handles both roleplay (*sighs*) and formatted data (*162 cm*)
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
    # Strip any remaining orphaned asterisks (from **bold** markers etc)
    cleaned = re.sub(r'\*+', '', cleaned)
    # Clean up double spaces
    cleaned = re.sub(r'  +', ' ', cleaned)
    return cleaned.strip()


def _strip_repeated_content(text: str) -> str:
    """
    Remove repeated lines/paragraphs that indicate a generation loop.
    This catches the model getting stuck repeating search citations.
    """
    if not text:
        return text
    lines = text.split('\n')
    seen = set()
    result = []
    for line in lines:
        # Normalize for comparison (lowercase, strip whitespace)
        normalized = line.strip().lower()
        # Allow empty lines through, but dedupe content lines
        if normalized and normalized in seen:
            continue
        if normalized:
            seen.add(normalized)
        result.append(line)
    return '\n'.join(result)


def _strip_specific_hallucinations(text: str) -> str:
    """
    Generalized cleanup (no more hardcoded phrase stripping).
    Let the model handle itself via dynamic temperature.
    """
    if not text:
        return text
    
    # Cleanup any resulting double punctuation/spaces
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()



def _extract_json(text: str) -> dict:
    """
    Extract JSON from LLM response that may contain markdown or extra text.
    Handles: ```json {...}```, ```{...}```, raw JSON, or JSON buried in text.
    """
    if not text or not text.strip():
        raise ValueError("Empty response")
    
    text = text.strip()
    
    # Try 1: Direct parse (ideal case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try 2: Strip markdown code blocks
    # Matches ```json {...}``` or ```{...}```
    code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try 3: Find JSON object anywhere in text
    json_match = re.search(r'\{[^{}]*"search"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Try 4: More aggressive - find any {...} block
    brace_match = re.search(r'\{.*?\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Could not extract JSON from: {text[:100]}")


# ── Resolved backend settings ──────────────────────────────────────────
_backend = _get_backend()
LLM_HOST = _backend["host"]
LLM_MODEL = _backend["model"]
print(f"[Router] Active backend: {LLM_BACKEND} | Host: {LLM_HOST} | Model: {LLM_MODEL}")


async def _call_lmstudio(messages: list, temperature: float = None, max_tokens: int = 8000, stop: list = None, presence_penalty: float = None, frequency_penalty: float = None, model: str = None) -> dict:
    """Make a request to the active LLM backend (OpenAI-compatible API).

    Sampler defaults are pulled from the active backend config (TabbyAPI vs KoboldCpp).
    Returns dict with 'text', 'tokens', 'tps' keys (or None on failure).
    """
    backend = _get_backend()

    # Use backend defaults if caller didn't override
    if temperature is None:
        temperature = backend["temperature"]
    if presence_penalty is None:
        presence_penalty = backend["presence_penalty"]
    if frequency_penalty is None:
        frequency_penalty = backend["frequency_penalty"]

    payload = {
        "model": model or LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "top_p": backend["top_p"],
        "top_k": backend["top_k"],
        "min_p": backend["min_p"],
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
    }
    # Merge backend-specific payload (e.g. chat_template_kwargs for Qwen3)
    payload.update(backend.get("extra_payload", {}))

    # KoboldCpp repetition penalty (separate from OpenAI presence/frequency penalty)
    if backend.get("rep_pen"):
        payload["repetition_penalty"] = backend["rep_pen"]

    # Add stop sequences if provided (prevents model from roleplaying users)
    if stop:
        payload["stop"] = stop

    # Auth (TabbyAPI needs a key, KoboldCpp doesn't)
    headers = {"Content-Type": "application/json"}
    api_key = backend.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        start_time = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LLM_HOST}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    print(f"[{LLM_BACKEND}] Error {resp.status}: {error[:200]}")
                    return None

                data = await resp.json()
        elapsed = time.perf_counter() - start_time

        text = data["choices"][0]["message"]["content"]

        # Extract token count from usage stats (OpenAI-compatible)
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        tps = completion_tokens / elapsed if elapsed > 0 and completion_tokens else 0

        print(f"[{LLM_BACKEND}] {completion_tokens} tokens in {elapsed:.2f}s | {tps:.1f} T/s")

        return {"text": text, "tokens": completion_tokens, "tps": round(tps, 1)}
    except Exception as e:
        print(f"[{LLM_BACKEND}] Request failed: {e}")
        return None


async def decide_tools_and_query(
    user_message: str,
    has_image: bool,
    conversation_context: str = ""
) -> dict:
    """
    Decide which tools are needed and extract search query.
    Uses the same model as chat for consistency.
    
    Args:
        user_message: Current user message
        has_image: Whether an image is attached
        conversation_context: Recent chat context for follow-ups
    
    Returns:
        Dict with search, vision, search_query, reasoning
    """
    prompt = f"""Analyze this Discord message and decide what tools are needed.

Recent chat context:
{conversation_context[:3000] if conversation_context else "(no context)"}

Current message: {user_message}
Has image attachment: {has_image}

Respond with ONLY valid JSON:
{{
  "search": true or false,
  "search_query": "optimized search query if search is true, otherwise empty string",
  "time_range": "day/week/month/year or null for all-time",
  "vision": true or false,
  "reasoning": "brief one-line explanation"
}}

Rules:
- search=true: ANY question requiring CURRENT/REAL-TIME info (weather, prices, scores, news, "what's happening", recent events)
- search=true: factual questions about specific people, things, events, releases, updates
- search=true: questions with time words like "now", "today", "current", "latest", "recent", "will" (future)
- search=true: niche/technical topics, specific person details, current events
- search=true: when you're not 100% certain about the answer - better to search than guess
- search=false: well-known concepts you already know (Stoicism, basic science, common knowledge)
- search=false: casual chat, greetings, pure opinions, emotional support, questions answerable from chat context
- search=false: personal questions about the user or reactions to what they said
- vision=true: image is attached OR user asks to look at something

QUERY REWRITING (CRITICAL):
- De-contextualize: Replace ALL pronouns (he, she, it, they, him, her, this, that) with specific entities from chat context
- Bad: "How old is he?" → Good: "Tim Cook age" (if context mentioned Tim Cook)
- Bad: "What does it cost?" → Good: "iPhone 16 Pro price" (if context mentioned iPhone)
- Extract key terms, add context (city names, specific topics), remove filler words

TIME RANGE:
- "day" or "week": News, current events, scores, weather, "what's happening now"
- "month" or "year": Recent releases, updates, new products
- null: Historical facts, biographies, evergreen documentation, "who was", "what is"

Examples:
- "when will the snow melt in DC" → {{"search": true, "search_query": "Washington DC weather forecast snow", "time_range": "week", "vision": false, "reasoning": "weather is real-time"}}
- "who won the game" → {{"search": true, "search_query": "latest game score results", "time_range": "day", "vision": false, "reasoning": "sports scores are real-time"}}
- "who is ironmouse" → {{"search": true, "search_query": "Ironmouse VTuber", "time_range": null, "vision": false, "reasoning": "person lookup, evergreen info"}}
- "How old is he?" (context: discussed Tim Cook) → {{"search": true, "search_query": "Tim Cook age", "time_range": null, "vision": false, "reasoning": "resolved pronoun from context"}}
- "who was the first Roman Emperor" → {{"search": true, "search_query": "first Roman Emperor", "time_range": null, "vision": false, "reasoning": "historical fact, no time limit"}}
- "what is Stoicism" → {{"search": false, "search_query": "", "time_range": null, "vision": false, "reasoning": "well-known concept, use internal knowledge"}}
- "hey what's up" → {{"search": false, "search_query": "", "time_range": null, "vision": false, "reasoning": "casual greeting"}}
- [image attached] "what is this" → {{"search": false, "time_range": null, "vision": true, "reasoning": "user wants image analyzed"}}"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        # System instructions + user message for tool decision
        full_input = f"{prompt}\n\nCurrent message: {user_message}\nHas image attachment: {has_image}"
        
        response = await model.generate_content_async(
            full_input,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=256,
                response_mime_type="application/json"
            )
        )
        
        if not response or not response.text:
            raise Exception("No response from Gemini")
        
        # Extract and parse JSON
        decision = _extract_json(response.text)
        print(f"[Router] Decision (Gemini): search={decision.get('search')}, vision={decision.get('vision')}, time_range={decision.get('time_range')}, query='{decision.get('search_query', '')[:50]}'")
        return decision
        
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Router] JSON parse error: {e}")
        return {
            "search": len(user_message) > 15,
            "search_query": user_message,
            "time_range": None,
            "vision": has_image,
            "reasoning": "fallback due to parse error"
        }
    except Exception as e:
        print(f"[Router Error] {e}")
        return {
            "search": False,
            "search_query": "",
            "time_range": None,
            "vision": has_image,
            "reasoning": f"error: {e}"
        }


async def generate_response(
    user_message: str,
    search_context: str = "",
    memory_context: str = "",
    conversation_history: list[dict] = None,
    current_speaker: str = None
) -> dict:
    """
    Generate an Astra response using proper system/user ChatML roles.
    
    System message: personality + search results + memory (high instruction priority)
    User message: conversation transcript + current question
    
    LM Studio's OpenAI-compatible API handles ChatML tokenization automatically.
    """
    # Build system prompt with context AND speaker identity
    system_prompt = build_system_prompt(search_context, memory_context, current_speaker)
    
    # Add date awareness
    system_prompt = f"{get_date_context()}\n\n{system_prompt}"

    # Build transcript from conversation history (last 50 messages)
    transcript_lines = []
    if conversation_history:
        for msg in conversation_history[-50:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Extract speaker from content if formatted as [Speaker]: message
            if content.startswith("[") and "]:" in content:
                # Already formatted, use as-is
                transcript_lines.append(content)
            elif role == "assistant":
                transcript_lines.append(f"[Astra]: {content}")
            else:
                # Check for image indicator in content
                if "[shares an image]" in content or "[Image:" in content:
                    transcript_lines.append(content)
                else:
                    transcript_lines.append(f"[User]: {content}")
    
    # Add current message
    if current_speaker:
        transcript_lines.append(f"[{current_speaker}]: {user_message}")
    else:
        transcript_lines.append(f"[User]: {user_message}")
    
    transcript = "\n".join(transcript_lines)
    
    # Build user message with transcript only (system prompt is in system role)
    user_prompt = f"""[Transcript - Last {len(transcript_lines)} Messages]
{transcript}

Reply to the last message as Astra. Do not output internal thoughts."""
    
    # Proper system/user role separation — LM Studio handles ChatML tokenization
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # Stop sequences to prevent roleplaying other users (crucial for uncensored models)
    stop_sequences = ["\n[", "[Hiep]", "[User]"]

    
    try:
        print(f"[Router] Query: '{user_message[:50]}' | Search: {len(search_context)} chars | History: {len(transcript_lines)} msgs")
        
        # Thinking mode needs headroom for <think> blocks + final output
        tokens = 4000 if search_context else 8000

        # [DYNAMIC CREATIVITY]
        # Check if the last bot message was repetitive to break loops naturally
        # Start from backend defaults, spike if loop detected
        backend = _get_backend()
        temp = backend["temperature"]
        pres_pen = backend["presence_penalty"]
        freq_pen = backend["frequency_penalty"]
        
        last_bot_msg = ""
        for msg in reversed(conversation_history or []):
            if msg.get("role") == "assistant" or "[Astra]" in msg.get("content", ""):
                 # Extract content after [Astra]: if formatted
                 content = msg.get("content", "")
                 if "[Astra]:" in content:
                     last_bot_msg = content.split("[Astra]:", 1)[1].strip()
                 else:
                     last_bot_msg = content
                 break
        
        # If we have history, check similarity with previous bot output to catch loops early
        # (This is a heuristic: if she's stuck, she likely output similar structure last turn)
        is_stuck = False
        if last_bot_msg and len(last_bot_msg) > 10:
             # REAL LOOP CHECK: Did the user copy-paste the BOT'S last message?
             # (This happens if someone quotes the bot without adding new content)
             if user_message.strip() == last_bot_msg.strip():
                 is_stuck = True
             
             # Did the USER repeat themselves exactly?
             # Check last 3 user messages for identical content
             user_history = [m.get("content", "") for m in reversed(conversation_history or []) if m.get("role") == "user"]
             if len(user_history) >= 2:
                 if user_message.strip().lower() == user_history[0].strip().lower():
                     is_stuck = True

        if is_stuck:
            print("[Router] Loop detected! Spiking creativity parameters.")
            temp = min(backend["temperature"] + 0.15, 1.2)  # Spike above baseline (capped)
            pres_pen = min(backend["presence_penalty"] + 0.2, 0.5)  # Push for variety
            freq_pen = min(backend["frequency_penalty"] + 0.1, 0.25)  # Slightly elevated

        result = await _call_lmstudio(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            stop=stop_sequences,
            presence_penalty=pres_pen,
            frequency_penalty=freq_pen
        )

        if not result:
            return {"text": "something broke on my end, try again?", "tokens": 0, "tps": 0}

        # Chain all post-processing: think tags -> roleplay actions -> dedup -> name prefix
        cleaned = _strip_think_tags(result["text"])
        cleaned = _strip_roleplay_actions(cleaned)
        cleaned = _strip_repeated_content(cleaned)
        cleaned = _strip_specific_hallucinations(cleaned)
        # Strip self-name prefix (model mimics transcript format "[Astra]: ..." or "Astra: ...")
        cleaned = re.sub(r'^(?:\[?Astra\]?:\s*)', '', cleaned, flags=re.IGNORECASE).strip()

        # OUTPUT LOOP DETECTION: Compare with last bot message
        # If she generated nearly the same thing, regenerate with spiked creativity
        if last_bot_msg and len(last_bot_msg) > 10 and len(cleaned) > 10:
            similarity = difflib.SequenceMatcher(None, cleaned.lower(), last_bot_msg.lower()).ratio()
            if similarity > 0.6:
                print(f"[Router] Output loop detected (similarity={similarity:.2f}), regenerating with spiked params")
                retry = await _call_lmstudio(
                    messages=messages,
                    temperature=min(backend["temperature"] + 0.2, 1.2),
                    max_tokens=tokens,
                    stop=stop_sequences,
                    presence_penalty=min(backend["presence_penalty"] + 0.3, 0.6),
                    frequency_penalty=min(backend["frequency_penalty"] + 0.15, 0.25)
                )
                if retry:
                    cleaned = _strip_think_tags(retry["text"])
                    cleaned = _strip_roleplay_actions(cleaned)
                    cleaned = _strip_repeated_content(cleaned)
                    cleaned = _strip_specific_hallucinations(cleaned)
                    cleaned = re.sub(r'^(?:\[?Astra\]?:\s*)', '', cleaned, flags=re.IGNORECASE).strip()
                    result = retry  # use retry stats for T/s footer

        return {"text": cleaned, "tokens": result["tokens"], "tps": result["tps"]}

    except Exception as e:
        print(f"[LMStudio Error] {e}")
        return {"text": "something broke on my end, try again?", "tokens": 0, "tps": 0}


async def summarize_text(text: str) -> str:
    """
    Summarize text using Gemini 2.0 Flash.
    Focus on: Topics, Mood, Key Events.
    """
    if not text or not GEMINI_API_KEY:
        return ""
        
    system_prompt = (
        "You are a helpful assistant. Summarize the following conversation history concisely (3-4 sentences). "
        "Focus on: 1. Factual topics discussed 2. Concrete events. "
        "CRITICAL: Do NOT summarize repeated questions, 'loops', or meta-commentary on user behavior (e.g. 'user keeps asking about X'). "
        "Ignore repetitive phrasing. Just capture the core topic."
    )
    
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = await model.generate_content_async(
            f"{system_prompt}\n\nConversation History:\n{text}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=600
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"[Summarizer Error] {e}")
        return ""  # Fallback to empty summary on failure (safe fail)


async def process_message(
    user_message: str,
    search_context: str,
    conversation_history: list[dict] = None,
    memory_context: str = "",
    current_speaker: str = None
) -> dict:
    """
    Full message processing pipeline.
    Search context passed through from chat.py.

    Returns dict with 'text', 'tokens', 'tps' keys.
    """
    if search_context:
        print(f"[Router] Using search context ({len(search_context)} chars)")

    return await generate_response(
        user_message=user_message,
        search_context=search_context,
        memory_context=memory_context,
        conversation_history=conversation_history,
        current_speaker=current_speaker
    )
