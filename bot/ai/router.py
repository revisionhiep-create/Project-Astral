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
    # Also remove *action* style if present
    cleaned = re.sub(r'\*[^*]+\*\s*', '', cleaned)
    return cleaned.strip()


def _strip_leading_name(text: str) -> str:
    """
    Strip known usernames from the start of responses.
    The model sometimes mimics the [Username]: pattern from context.
    """
    if not text:
        return text
    # Known usernames (case-insensitive) followed by punctuation
    # Matches: "liddo.", "Tei,", "hiep:", "Jason -", etc.
    cleaned = re.sub(r'^(liddo|tei|hiep|jason|melon|revision|shiftstep)[.,:\-\s]+', '', text, flags=re.IGNORECASE)
    return cleaned.strip()


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
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "gemma3-27b-it-vl-glm-4.7-uncensored-heretic-deep-reasoning")


async def _call_lmstudio(messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
    """Make a request to LM Studio's OpenAI-compatible API."""
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }
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
{conversation_context[:1500] if conversation_context else "(no context)"}

Current message: {user_message}
Has image attachment: {has_image}

Respond with ONLY valid JSON:
{{
  "search": true or false,
  "search_query": "optimized search query if search is true, otherwise empty string",
  "vision": true or false,
  "reasoning": "brief one-line explanation"
}}

Rules:
- search=true: ANY question requiring CURRENT/REAL-TIME info you don't have (weather, prices, scores, news, "what's happening", recent events)
- search=true: factual questions about people, things, events, releases, updates
- search=true: questions with time words like "now", "today", "current", "latest", "recent", "will" (future predictions)
- search=true: questions about concepts, theories, philosophies, or anything you'd need to look up to answer accurately
- search=true: when you're not 100% certain about the answer - better to search than guess
- search=true: "who is", "what is", "explain", "tell me about" questions about specific topics
- search=false: casual chat, greetings, pure opinions, emotional support, questions answerable from chat context
- search=false: personal questions about the user or reactions to what they said
- vision=true: image is attached OR user asks to look at something
- search_query: extract key terms, add context (city names, specific topics), remove filler words

CRITICAL: When in doubt, search=true. It's better to have accurate info than to guess and be wrong. If the question is about any real-world topic, concept, person, or event, search.

Examples:
- "when will the snow melt in DC" -> {{"search": true, "search_query": "Washington DC weather forecast snow", "vision": false, "reasoning": "weather is real-time data"}}
- "what's the weather like" -> {{"search": true, "search_query": "current weather", "vision": false, "reasoning": "weather needs real-time data"}}
- "who won the game" -> {{"search": true, "search_query": "latest game score results", "vision": false, "reasoning": "sports scores are real-time"}}
- "who is ironmouse" -> {{"search": true, "search_query": "Ironmouse VTuber", "vision": false, "reasoning": "looking up a person"}}
- "what does zizek think about freedom" -> {{"search": true, "search_query": "Slavoj Zizek philosophy freedom determinism", "vision": false, "reasoning": "philosophical topic needs accurate info"}}
- "hey what's up" -> {{"search": false, "search_query": "", "vision": false, "reasoning": "casual greeting"}}
- "what did Hiep say earlier" -> {{"search": false, "search_query": "", "vision": false, "reasoning": "can answer from chat context"}}
- "what's her real name" (context mentions Ironmouse) -> {{"search": true, "search_query": "Ironmouse real name VTuber", "vision": false, "reasoning": "follow-up question needs search"}}
- [image attached] "what is this" -> {{"search": false, "vision": true, "reasoning": "user wants image analyzed"}}"""

    try:
        response = await _call_lmstudio(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=256
        )
        
        if not response:
            raise Exception("No response from LM Studio")
        
        result = _extract_json(response)
        print(f"[Router] Decision: search={result.get('search')}, vision={result.get('vision')}, query='{result.get('search_query', '')[:50]}'")
        return result
        
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[Router] JSON parse error: {e}")
        return {
            "search": len(user_message) > 15,
            "search_query": user_message,
            "vision": has_image,
            "reasoning": "fallback due to parse error"
        }
    except Exception as e:
        print(f"[Router Error] {e}")
        return {
            "search": False,
            "search_query": "",
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
    Generate an Astra response.
    
    Search context goes in SYSTEM PROMPT to separate facts from conversation.
    """
    # Build system prompt with context
    system_prompt = build_system_prompt(search_context, memory_context)
    
    # Add current speaker at the VERY TOP if provided
    if current_speaker:
        speaker_header = f"[RESPONDING TO: {current_speaker}]\nYou are replying to {current_speaker} specifically. Keep this in mind.\n\n"
        system_prompt = speaker_header + system_prompt
    
    # Add date awareness
    system_prompt = f"{get_date_context()}\n\n{system_prompt}"
    
    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history (last 10 messages for context)
    if conversation_history:
        for msg in conversation_history[-10:]:
            messages.append(msg)
    
    # Few-shot injection disabled - was causing context confusion
    # from ai.personality import get_few_shot_examples
    # few_shot = get_few_shot_examples(count=3)
    # messages.extend(few_shot)
    
    # User message with speaker tag (survives truncation)
    if current_speaker:
        messages.append({"role": "user", "content": f"[{current_speaker}]: {user_message}"})
    else:
        messages.append({"role": "user", "content": user_message})
    
    try:
        use_search = bool(search_context)
        print(f"[Router] Query: '{user_message[:50]}' | Search: {len(search_context)} chars")
        
        response = await _call_lmstudio(
            messages=messages,
            temperature=0.65,
            max_tokens=6000
        )
        
        if not response:
            return "something broke on my end, try again?"
        
        return _strip_leading_name(_strip_roleplay_actions(_strip_think_tags(response)))
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
