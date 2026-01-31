"""AI Router - Single model orchestration with Mistral Small 24B."""
import os
import json
import ollama
from typing import Optional

from ai.personality import build_system_prompt
from tools.time_utils import get_date_context


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Single unified model for everything
UNIFIED_MODEL = os.getenv("OLLAMA_MODEL", "mistral-small-24b")

# Ollama client
client = ollama.AsyncClient(host=OLLAMA_HOST)


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
- search=true: factual questions, current events, looking up people/things
- search=false: casual chat, greetings, opinions, emotional support
- vision=true: image is attached OR user asks to look at something
- search_query: extract key terms, add context, remove filler words

Examples:
- "who is ironmouse" -> {{"search": true, "search_query": "Ironmouse VTuber", "vision": false, "reasoning": "looking up a person"}}
- "hey what's up" -> {{"search": false, "search_query": "", "vision": false, "reasoning": "casual greeting"}}
- "what's her real name" (context mentions Ironmouse) -> {{"search": true, "search_query": "Ironmouse real name VTuber", "vision": false, "reasoning": "follow-up question needs search"}}
- [image attached] "what is this" -> {{"search": false, "vision": true, "reasoning": "user wants image analyzed"}}"""

    try:
        response = await client.chat(
            model=UNIFIED_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,
                "num_ctx": 4096
            },
            format="json"
        )
        
        result = json.loads(response["message"]["content"])
        print(f"[Router] Decision: search={result.get('search')}, vision={result.get('vision')}, query='{result.get('search_query', '')[:50]}'")
        return result
        
    except json.JSONDecodeError as e:
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
    conversation_history: list[dict] = None
) -> str:
    """
    Generate a GemGem response.
    
    Search context goes in SYSTEM PROMPT to separate facts from conversation.
    """
    # Build system prompt with context
    system_prompt = build_system_prompt(search_context, memory_context)
    
    # Add date awareness
    system_prompt = f"{get_date_context()}\n\n{system_prompt}"
    
    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history (last 10 messages for context)
    if conversation_history:
        for msg in conversation_history[-10:]:
            messages.append(msg)
    
    # User message is clean - no search injection
    messages.append({"role": "user", "content": user_message})
    
    try:
        use_search = bool(search_context)
        print(f"[Router] Query: '{user_message[:50]}' | Search: {len(search_context)} chars")
        
        response = await client.chat(
            model=UNIFIED_MODEL,
            messages=messages,
            options={
                "temperature": 0.7,
                "repeat_penalty": 1.15,
                "top_p": 0.9,
                "top_k": 40,
                "num_ctx": 8192
            }
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"[Ollama Error] {e}")
        return "something broke on my end, try again?"


async def process_message(
    user_message: str,
    search_context: str,
    conversation_history: list[dict] = None,
    memory_context: str = ""
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
        conversation_history=conversation_history
    )
    
    return response
