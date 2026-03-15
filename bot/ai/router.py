"""AI Router - LM Studio orchestration (Qwen3-Coder-30B-A3B-Instruct-Heretic)."""
import os
import json
import time
import aiohttp
import difflib

import re
from google import genai
from google.genai import types

from ai.personality import build_system_prompt
from tools.time_utils import get_date_context

# Configure Google AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def _strip_think_tags(text: str) -> str:
    """
    Strip <think>...</think> reasoning blocks from model output.
    The Deep Reasoning model outputs these for chain-of-thought, but we don't want to show them.
    """
    if not text:
        return text
    # Remove <think>...</think> blocks (including newlines within)
    cleaned = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)
    # Also strip orphaned opening <think> with no closing tag (model cut off mid-reasoning)
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


def _strip_markdown(text: str) -> str:
    """Strip markdown formatting that code-focused models tend to add."""
    if not text:
        return text
    # Remove headers (# ## ### etc)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove code fences (```python, ``` etc)
    text = re.sub(r'```\w*\n?', '', text)
    # Remove blockquotes
    text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
    # Remove horizontal rules (---, ***, ___)
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Clean up resulting blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


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


def _strip_citations(text: str) -> str:
    """
    Strip citation brackets from Grok responses.
    Grok returns citations as [[1]][[2]][[3]] etc.
    """
    if not text:
        return text

    # Remove citation brackets like [[1]], [[2]], etc.
    text = re.sub(r'\[\[\d+\]\]', '', text)
    # Clean up any resulting double spaces
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


# LM Studio server (OpenAI-compatible API)
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "http://host.docker.internal:1234")
CHAT_MODEL = os.getenv("LMSTUDIO_CHAT_MODEL", "qwen3-coder-30b-a3b-instruct-heretic-i1")

# xAI Grok API
XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4-1-fast-reasoning")
XAI_HOST = os.getenv("XAI_HOST", "https://api.x.ai")
LLM_BACKEND = os.getenv("LLM_BACKEND", "lmstudio")

print(f"[Router] Backend: {LLM_BACKEND} | Host: {LMSTUDIO_HOST if LLM_BACKEND == 'lmstudio' else XAI_HOST} | Model: {CHAT_MODEL if LLM_BACKEND == 'lmstudio' else XAI_MODEL}")


async def _call_lmstudio(messages: list, temperature: float = 0.6, max_tokens: int = 8000, stop: list = None, presence_penalty: float = 0.3, frequency_penalty: float = 0.1, model: str = None) -> dict:
    """Make a request to LM Studio's OpenAI-compatible API.
    Returns dict with 'text', 'tokens', 'tps' keys (or None on failure).
    """
    payload = {
        "model": model or CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0,
        "repeat_penalty": 1.05,  # Qwen3-Coder recommended: helps with instruction following
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
    }
    if stop:
        payload["stop"] = stop

    try:
        start_time = time.perf_counter()
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
        elapsed = time.perf_counter() - start_time

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        tps = completion_tokens / elapsed if elapsed > 0 and completion_tokens else 0

        print(f"[LMStudio] {completion_tokens} tokens in {elapsed:.2f}s | {tps:.1f} T/s")

        return {"text": text, "tokens": completion_tokens, "tps": round(tps, 1)}
    except Exception as e:
        print(f"[LMStudio] Request failed: {e}")
        return None


async def _call_grok(messages: list, temperature: float = 0.7, max_tokens: int = 8000, stop: list = None, presence_penalty: float = 0.0, frequency_penalty: float = 0.0, repetition_penalty: float = 1.05, enable_search: bool = True, enable_vision: bool = False) -> dict:
    """Make a request to xAI Grok API using /v1/responses endpoint with tool support.
    Returns dict with 'text', 'tokens', 'tps', 'citations' keys (or None on failure).

    NOTE: Uses /v1/responses endpoint (NOT /v1/chat/completions) for tool support.
    Tool calling (web_search, vision) is handled server-side by xAI.

    Args:
        messages: Conversation history in OpenAI format
        temperature: Sampling temperature (0-2)
        max_tokens: Maximum tokens to generate
        repetition_penalty: Control repetition (1.0 = no penalty, >1.0 = penalize)
        enable_search: Enable web_search tool (auto-triggered by model)
        enable_vision: Enable image understanding in searches
    """
    if not XAI_API_KEY:
        print("[Grok] Error: XAI_API_KEY not set")
        return None

    # Convert messages format: "messages" -> "input" for /v1/responses endpoint
    # The /v1/responses endpoint uses "input" instead of "messages"
    input_messages = messages

    # Build tools array (server-side tools)
    tools = []
    if enable_search:
        tools.append({
            "type": "web_search",
            "web_search": {
                "enable_image_understanding": enable_vision
            }
        })

    payload = {
        "model": XAI_MODEL,
        "input": input_messages,  # Note: "input" not "messages" for /v1/responses
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "repetition_penalty": repetition_penalty,
    }

    # Add tools if any are enabled
    if tools:
        payload["tools"] = tools

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Debug: Log if vision input detected
    has_vision_content = any(isinstance(m.get("content"), list) for m in input_messages if isinstance(m, dict))
    if enable_vision or has_vision_content:
        print(f"[Grok] Vision mode detected - enable_vision={enable_vision}, has_vision_content={has_vision_content}")
        print(f"[Grok] First message content type: {type(input_messages[-1].get('content') if input_messages else None)}")

    # Use /v1/chat/completions for vision (OpenAI-compatible), /v1/responses for text+search
    endpoint = "/v1/chat/completions" if has_vision_content else "/v1/responses"

    # Adjust payload for endpoint type
    if endpoint == "/v1/chat/completions":
        # OpenAI format: "messages" not "input", no tools parameter
        payload = {
            "model": XAI_MODEL,
            "messages": input_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        print(f"[Grok] Using /v1/chat/completions for vision")

    try:
        start_time = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{XAI_HOST}{endpoint}",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=180)  # Increased timeout for tool execution
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    print(f"[Grok] Error {resp.status}: {error[:500]}")
                    return None

                data = await resp.json()
        elapsed = time.perf_counter() - start_time

        # Check for errors first
        if "error" in data and data["error"]:
            print(f"[Grok] API Error: {data['error']}")
            return None

        if "status" in data and data["status"] != "completed":
            print(f"[Grok] Incomplete response. Details: {data.get('incomplete_details', 'N/A')}")
            return None

        # Response format for /v1/responses endpoint
        # Extract text from response (may be in different location)
        text = None

        # Try the simple "text" field first (top-level in /v1/responses)
        # BUT: Skip if it's just metadata (e.g., {"format": {"type": "text"}})
        if "text" in data and data["text"]:
            text_field = data["text"]
            if isinstance(text_field, str):
                text = text_field
            elif isinstance(text_field, dict):
                # Check if it's just format metadata
                if text_field.keys() == {'format'} or (len(text_field) == 1 and 'format' in text_field):
                    text = None  # Force fallback to output array
                else:
                    text = text_field.get("content", text_field.get("text"))
            else:
                text = str(text_field)

        if not text and "choices" in data and len(data["choices"]) > 0:
            # Standard format
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # Multi-modal response - extract text parts
                text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
                text = " ".join(text_parts)
            else:
                text = str(content)
        if not text and "output" in data:
            # Alternative format for /v1/responses
            # Output is a list of tool calls + final message
            if isinstance(data["output"], str):
                text = data["output"]
            elif isinstance(data["output"], list) and len(data["output"]) > 0:
                # Find the last message (not tool call) in the output
                for item in reversed(data["output"]):
                    if isinstance(item, dict):
                        item_type = item.get("type")

                        # Check for output_text type (Grok's actual response format)
                        if item_type == "output_text" and "text" in item:
                            text = item["text"]
                            break
                        # Check if this is a message (has 'content' or 'text')
                        elif "content" in item:
                            content = item["content"]
                            if isinstance(content, str):
                                text = content
                            elif isinstance(content, list):
                                # Content is a list - could be multi-modal or have output_text items
                                for content_item in content:
                                    if isinstance(content_item, dict):
                                        content_type = content_item.get("type")
                                        # Check for output_text in content list
                                        if content_type == "output_text" and "text" in content_item:
                                            text = content_item["text"]
                                            break
                                        # Regular text content
                                        elif content_type == "text" and "text" in content_item:
                                            text = content_item.get("text", "")
                                if not text:
                                    # Fallback: join all text parts
                                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
                                    text = " ".join(text_parts) if text_parts else str(content)
                            else:
                                text = str(content)
                            if text:
                                break
                        elif "text" in item and item_type != "web_search_call":
                            text = item["text"]
                            break
                        elif item_type == "message" and "message" in item:
                            # Nested message format
                            text = item["message"].get("content", str(item))
                            break
                # Fallback: if no message found, try last item
                if not text:
                    last_msg = data["output"][-1]
                    text = last_msg.get("content", str(last_msg)) if isinstance(last_msg, dict) else str(last_msg)
            else:
                text = str(data["output"])

        if not text:
            print(f"[Grok] Could not extract text from response. Keys: {list(data.keys())}")
            print(f"[Grok] Response data: {json.dumps(data, indent=2)[:500]}")
            return None

        # Extract usage and citations
        usage = data.get("usage", {})
        # Grok uses "output_tokens" not "completion_tokens"
        completion_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        tps = completion_tokens / elapsed if elapsed > 0 and completion_tokens else 0

        # If text extraction failed (got a dict instead of string), convert to string
        if text and isinstance(text, dict):
            # Try to find actual message in output list
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if isinstance(item, dict):
                        item_type = item.get('type', 'unknown')

                        # Look for message type
                        if item_type == "message":
                            # Extract content from message
                            if "content" in item:
                                content = item["content"]
                                if isinstance(content, str):
                                    text = content
                                    break
                                elif isinstance(content, list):
                                    # Multi-modal content
                                    text_parts = []
                                    for part in content:
                                        if isinstance(part, dict) and part.get("type") == "text":
                                            text_parts.append(part.get("text", ""))
                                    text = " ".join(text_parts)
                                    break
                            elif "text" in item:
                                text = item["text"]
                                break

        # Extract citations if available
        citations = data.get("citations", [])

        return {
            "text": text,
            "tokens": completion_tokens,
            "tps": round(tps, 1),
            "citations": citations
        }
    except Exception as e:
        print(f"[Grok] Request failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_response(
    user_message: str,
    search_context: str = "",
    memory_context: str = "",
    conversation_history: list[dict] = None,
    current_speaker: str = None,
    has_vision: bool = False,
    image_url: str = None
) -> str:
    """
    Generate an Astral response using proper system/user ChatML roles.

    System message: personality + search results + memory (high instruction priority)
    User message: conversation transcript + current question (with optional image)

    For Grok: Uses /v1/responses endpoint with native vision support.
    For LM Studio: Uses /v1/chat/completions (OpenAI-compatible).
    """
    # Build system prompt with context AND speaker identity
    system_prompt = build_system_prompt(search_context, memory_context, current_speaker, has_vision)

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
                transcript_lines.append(f"[Astral]: {content}")
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
    # For images, use multi-modal content format
    if image_url and LLM_BACKEND == "grok":
        # Grok vision: Use /v1/chat/completions format (OpenAI-compatible)
        # /v1/responses with vision seems to hang - use simpler format
        user_content = [
            {"type": "text", "text": f"""[Transcript - Last {len(transcript_lines)} Messages]
{transcript}

Reply to the last message as Astral. Do not output internal thoughts."""},
            {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}
        ]
    else:
        # Text-only or LM Studio (no native vision)
        user_content = f"""[Transcript - Last {len(transcript_lines)} Messages]
{transcript}

Reply to the last message as Astral. Do not output internal thoughts."""

    # Proper system/user role separation
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    # Stop sequences to prevent roleplaying other users (crucial for uncensored models)
    stop_sequences = ["\n[", "[Hiep]", "[User]"]

    
    try:
        print(f"[Router] Query: '{user_message[:50]}' | Search: {len(search_context)} chars | History: {len(transcript_lines)} msgs")
        
        tokens = 4000 if search_context else 8000

        # [DYNAMIC CREATIVITY]
        # Check if the last bot message was repetitive to break loops naturally
        temp = 0.7
        pres_pen = 0.3
        freq_pen = 0.1
        
        last_bot_msg = ""
        for msg in reversed(conversation_history or []):
            if msg.get("role") == "assistant" or "[Astral]" in msg.get("content", ""):
                 # Extract content after [Astral]: if formatted
                 content = msg.get("content", "")
                 if "[Astral]:" in content:
                     last_bot_msg = content.split("[Astral]:", 1)[1].strip()
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
            temp = min(temp + 0.15, 1.2)
            pres_pen = min(pres_pen + 0.2, 0.5)
            freq_pen = min(freq_pen + 0.1, 0.25)

        # Select backend based on LLM_BACKEND env var
        if LLM_BACKEND == "grok":
            # Grok uses /v1/responses endpoint with native tool support
            # enable_search=True allows Grok to autonomously search when needed
            result = await _call_grok(
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                repetition_penalty=1.05 + (pres_pen * 0.1),  # Convert presence penalty to repetition penalty
                enable_search=True,  # Enable native web_search tool
                enable_vision=has_vision  # Enable image understanding if image attached
            )
        else:
            result = await _call_lmstudio(
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                stop=stop_sequences,
                presence_penalty=pres_pen,
                frequency_penalty=freq_pen
            )

        if not result:
            return "something broke on my end, try again?"

        # Chain all post-processing: think tags -> roleplay -> markdown -> dedup -> citations -> name prefix
        cleaned = _strip_think_tags(result["text"])
        cleaned = _strip_roleplay_actions(cleaned)
        cleaned = _strip_markdown(cleaned)
        cleaned = _strip_repeated_content(cleaned)
        cleaned = _strip_specific_hallucinations(cleaned)
        cleaned = _strip_citations(cleaned)
        # Strip self-name prefix (model mimics transcript format "[Astral]: ..." or "Astral: ...")
        cleaned = re.sub(r'^(?:\[?Astral\]?:\s*)', '', cleaned, flags=re.IGNORECASE).strip()

        # OUTPUT LOOP DETECTION: Compare with last bot message
        if last_bot_msg and len(last_bot_msg) > 10 and len(cleaned) > 10:
            similarity = difflib.SequenceMatcher(None, cleaned.lower(), last_bot_msg.lower()).ratio()
            if similarity > 0.6:
                print(f"[Router] Output loop detected (similarity={similarity:.2f}), regenerating with spiked params")

                if LLM_BACKEND == "grok":
                    retry = await _call_grok(
                        messages=messages,
                        temperature=min(temp + 0.2, 1.2),
                        max_tokens=tokens,
                        repetition_penalty=1.15,  # Higher penalty for retry to force variation
                        enable_search=True,
                        enable_vision=has_vision
                    )
                else:
                    retry = await _call_lmstudio(
                        messages=messages,
                        temperature=min(temp + 0.2, 1.2),
                        max_tokens=tokens,
                        stop=stop_sequences,
                        presence_penalty=min(pres_pen + 0.3, 0.6),
                        frequency_penalty=min(freq_pen + 0.15, 0.25)
                    )

                if retry:
                    cleaned = _strip_think_tags(retry["text"])
                    cleaned = _strip_roleplay_actions(cleaned)
                    cleaned = _strip_markdown(cleaned)
                    cleaned = _strip_repeated_content(cleaned)
                    cleaned = _strip_specific_hallucinations(cleaned)
                    cleaned = re.sub(r'^(?:\[?Astral\]?:\s*)', '', cleaned, flags=re.IGNORECASE).strip()

        return cleaned
    
    except Exception as e:
        print(f"[LMStudio Error] {e}")
        return "something broke on my end, try again?"


async def summarize_text(text: str) -> str:
    """
    Summarize text using Gemini 3.0 Flash.
    Focus on: Topics, Mood, Key Events, Participants.
    """
    if not text or not GEMINI_API_KEY:
        return ""

    system_prompt = (
        "Summarize this Discord conversation history in 8-12 sentences. This covers older messages (all except the last 30) that provide background context.\n\n"
        "Include:\n"
        "1. Main topics/events discussed and who was involved\n"
        "2. Key participants and their roles in the conversation\n"
        "3. Emotional context or tone if relevant (excitement, concern, casual chat, etc.)\n"
        "4. Any images shared and what they depicted\n"
        "5. Important decisions, plans, or outcomes\n\n"
        "Ignore:\n"
        "- Repeated questions or conversational loops\n"
        "- Meta-commentary about user behavior (e.g. 'user keeps asking about X')\n"
        "- Repetitive phrasing or filler\n\n"
        "Output: Factual summary focusing on what actually happened, organized chronologically or by topic."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{system_prompt}\n\nConversation History:\n{text}",
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1200  # Increased from 600 to allow longer summaries
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
    current_speaker: str = None,
    has_vision: bool = False,
    image_url: str = None
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
        current_speaker=current_speaker,
        has_vision=has_vision,
        image_url=image_url
    )

    return response
