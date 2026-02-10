"""AI Router - Single model orchestration with LM Studio (Mistral Small 24B)."""
import os
import json
import aiohttp
from typing import Optional

import re

from ai.personality import build_system_prompt
from tools.time_utils import get_date_context


def _strip_think_tags(text: str) -> str:
    """
    Strip <think>...</think> reasoning blocks from model output.
    The Deep Reasoning model outputs these for chain-of-thought, but we don't want to show them.
    """
    if not text:
        return text
    # Remove <think>...</think> blocks (including newlines within)
    cleaned = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
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


# LM Studio server (OpenAI-compatible API)
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "http://host.docker.internal:1234")

# Model identifiers from LM Studio
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "qwen3-vl-32b-instruct-heretic-v2-i1")


async def _call_lmstudio(messages: list, temperature: float = 0.7, max_tokens: int = 4000, stop: list = None, repeat_penalty: float = 1.05) -> str:
    """Make a request to LM Studio's OpenAI-compatible API."""
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "repeat_penalty": repeat_penalty,  # Qwen3: 1.05 (was 1.15, too aggressive)
        "top_p": 0.8,             # Qwen3 recommended nucleus sampling
        "top_k": 20,              # Qwen3 recommended top-k
        "presence_penalty": 0.15  # Encourages vocabulary diversity
    }
    # Add stop sequences if provided (prevents model from roleplaying users)
    if stop:
        payload["stop"] = stop
    # Note: LM Studio doesn't support json_mode like OpenAI
    # The prompt instructs JSON output directly

    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LMSTUDIO_HOST}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    print(f"[LMStudio] Error {resp.status}: {error[:200]}")
                    return None
                
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LMStudio] Request failed: {e}")
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
        response = await _call_lmstudio(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=256
        )
        
        if not response:
            raise Exception("No response from LM Studio")
        
        result = _extract_json(response)
        print(f"[Router] Decision: search={result.get('search')}, vision={result.get('vision')}, time_range={result.get('time_range')}, query='{result.get('search_query', '')[:50]}'")
        return result
        
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
) -> str:
    """
    Generate an Astra response using transcript format for Gemma 3 reasoning model.
    
    Uses single-message transcript format instead of ChatML to prevent confusion
    in group chat scenarios with reasoning models.
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
    
    # Build single-message prompt in transcript format
    full_prompt = f"""[System Prompt]
{system_prompt}

[Transcript - Last {len(transcript_lines)} Messages]
{transcript}

[Instruction]: Reply to the last message as Astra. Do not output internal thoughts."""
    
    messages = [{"role": "user", "content": full_prompt}]
    
    # Stop sequences to prevent roleplaying other users (crucial for uncensored models)
    stop_sequences = ["\n[", "[Hiep]", "[User]", "<|im_end|>", "<|endoftext|>"]

    
    try:
        print(f"[Router] Query: '{user_message[:50]}' | Search: {len(search_context)} chars | History: {len(transcript_lines)} msgs")
        
        # Use lower max_tokens if search context is present (less room for looping)
        tokens = 1500 if search_context else 4000
        
        response = await _call_lmstudio(
            messages=messages,
            temperature=0.7,
            max_tokens=tokens,
            stop=stop_sequences,
            repeat_penalty=1.05  # Qwen3 optimized (was 1.15, caused mhm loops)
        )
        
        if not response:
            return "something broke on my end, try again?"
        
        # Chain all post-processing: think tags -> roleplay -> dedup
        cleaned = _strip_think_tags(response)
        cleaned = _strip_roleplay_actions(cleaned)
        cleaned = _strip_repeated_content(cleaned)
        # TEMP: Strip "that's me" prefix until old messages roll out of history
        cleaned = re.sub(r'^that[\'\u2019]s me\.?\s*\n?', '', cleaned, flags=re.IGNORECASE).strip()
        return cleaned
    except Exception as e:
        print(f"[LMStudio Error] {e}")
        return "something broke on my end, try again?"


async def process_message(
    user_message: str,
    search_context: str,
    conversation_history: list[dict] = None,
    memory_context: str = "",
    current_speaker: str = None
) -> str:
    """
    Full message processing pipeline.
    Search context passed through from chat.py.
    """
    if search_context:
        print(f"[Router] Using search context ({len(search_context)} chars)")
    
    response = await generate_response(
        user_message=user_message,
        search_context=search_context,
        memory_context=memory_context,
        conversation_history=conversation_history,
        current_speaker=current_speaker
    )
    
    return response
