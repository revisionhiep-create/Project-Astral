"""Gemini Vision Integration - Two-step flow: Gemini describes, Astra comments.

Primary: Gemini 3.0 Flash (fast, but censored)
Fallback: LLaVA local (uncensored, runs on CPU/RAM)
"""
import os
import aiohttp
import base64
import google.generativeai as genai
from io import BytesIO
from datetime import datetime
from collections import deque

# Import character system for recognition
try:
    from tools.characters import get_character_context_for_vision
except ImportError:
    def get_character_context_for_vision():
        return ""


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Vision models
GEMINI_VISION_MODEL = "gemini-3-flash-preview"
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "http://host.docker.internal:1234")
LOCAL_VISION_MODEL = "gemma-3-27b-it-abliterated"  # Uncensored vision model in LM Studio

# Short-term image cache (last 5 images)
# Stores: {"username": str, "description": str, "timestamp": str, "user_context": str}
_recent_images = deque(maxlen=5)


async def describe_image_local(image_data: bytes) -> str:
    """
    Fallback: Use Gemma 3 27B Abliterated via LM Studio for uncensored descriptions.
    Uses OpenAI-compatible vision API.
    """
    try:
        # Encode image as base64 with data URI
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Get character context for recognition
        character_context = get_character_context_for_vision()
        
        prompt = """Describe this image in detail. Include:
- Main subjects (characters, people, objects)
- Their appearance, poses, expressions
- Art style, colors, composition
- Background and setting
- Any notable or suggestive elements

Be thorough and honest in your description (3-5 sentences)."""
        
        # Add character recognition if we have known characters
        if character_context:
            prompt += f"""\n\nKnown characters to look for:\n{character_context}\nIf you recognize any of these characters in the image, mention them by name. Only mention them if they're actually present - don't say you don't see them."""

        # LM Studio OpenAI-compatible vision format
        payload = {
            "model": LOCAL_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500,
            "temperature": 0.3,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{LMSTUDIO_HOST}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    print(f"[Vision] LM Studio error: {resp.status} - {error[:100]}")
                    return None
                
                data = await resp.json()
                description = data["choices"][0]["message"]["content"].strip()
                print(f"[Vision] Gemma 3 description: {description[:80]}...")
                return description
                
    except Exception as e:
        print(f"[Vision] LM Studio vision error: {e}")
        return None


async def describe_image(image_url: str = None, image_data: bytes = None) -> str:
    """
    Step 1: Try local Gemma 3 first (uncensored), fallback to Gemini if local fails.
    Returns a text description that can be passed to Astra.
    """
    # Get image data if URL provided
    if image_url and not image_data:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        return None
                    image_data = await resp.read()
        except Exception as e:
            print(f"[Vision] Failed to fetch image: {e}")
            return None
    
    if not image_data:
        return None
    
    description = None
    
    # Try local Gemma 3 first (uncensored, primary)
    try:
        description = await describe_image_local(image_data)
        if description:
            print(f"[Vision] Using local Gemma 3 (primary): {description[:80]}...")
    except Exception as e:
        print(f"[Vision] Local vision failed: {e}")
    
    # Fallback to Gemini if local failed
    if not description and GEMINI_API_KEY:
        try:
            print("[Vision] Falling back to Gemini...")
            description_prompt = """Describe this image objectively and thoroughly.
Include:
- Main subjects (people, characters, objects)
- Colors, art style, composition
- Actions, poses, expressions
- Background and setting
- Any text visible in the image

Be factual and detailed but concise (3-5 sentences).
Do NOT add personality or commentary - just describe what you see."""
            
            # Add character recognition context
            character_context = get_character_context_for_vision()
            if character_context:
                description_prompt += f"""\n\nKnown characters to look for:\n{character_context}\nIf you recognize any of these characters, mention them by name. Only mention them if they're actually present - don't say you don't see them."""
            
            model = genai.GenerativeModel(GEMINI_VISION_MODEL)
            
            response = await model.generate_content_async(
                [
                    {"mime_type": "image/jpeg", "data": image_data},
                    description_prompt
                ],
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 400
                }
            )
            
            description = response.text.strip()
            print(f"[Vision] Gemini description (fallback): {description[:80]}...")
                    
        except Exception as e:
            print(f"[Vision] Gemini fallback also failed: {e}")
    
    return description


async def analyze_image(image_url: str, user_prompt: str = "", conversation_context: str = "", username: str = "") -> str:
    """
    Two-step image analysis:
    1. Gemini describes the image
    2. Astra (Mistral) comments on the description
    
    Also stores in short-term cache and RAG for recall.
    """
    from ai.router import process_message
    from memory.rag import store_image_knowledge
    
    # Step 1: Get Gemini's objective description
    description = await describe_image(image_url=image_url)
    
    if not description:
        return "couldn't see that image, try again?"
    
    # Step 2: Store in short-term cache (last 5 images)
    _recent_images.append({
        "username": username,
        "description": description,
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "user_context": user_prompt or "shared an image"
    })
    print(f"[Vision] Cached image from {username} (total cached: {len(_recent_images)})")
    
    # Step 3: Store in RAG for long-term memory
    try:
        await store_image_knowledge(
            description=description,
            username=username,
            context=user_prompt
        )
        print(f"[Vision] Stored to RAG: {description[:50]}...")
    except Exception as e:
        print(f"[Vision] RAG storage failed: {e}")
    
    # Step 4: Build context for Astra (internal - she should USE this but not dump it)
    # Critical: This is what you SEE, respond based on it naturally
    image_context = f"""[WHAT YOU SEE IN THE IMAGE]
{description}

Note: This is what's actually in the image. React to it naturally, don't just describe it back."""
    
    # What should Astra respond to?
    if user_prompt:
        astra_prompt = f"{username} shared an image and asked: {user_prompt}\n\n(You can see exactly what's in the image above. Comment on specific things you notice, don't be generic.)"
    else:
        astra_prompt = f"{username} shared an image with you.\n\n(You can see exactly what's in the image above. React to something specific you notice, like a friend would.)"
    
    # Step 5: Let Astra respond naturally through her normal chat flow
    response = await process_message(
        user_message=astra_prompt,
        search_context="",  # Don't put image in search context (she was echoing it)
        conversation_history=None,
        memory_context=image_context  # Put in memory so she has context but doesn't echo
    )
    
    return response


def get_recent_image_context() -> str:
    """
    Get formatted context of recently shared images.
    Used to inject into Astra's context so she can recall what she saw.
    """
    if not _recent_images:
        return ""
    
    lines = ["[RECENT IMAGES YOU SAW]"]
    for img in _recent_images:
        lines.append(f"- {img['username']} ({img['timestamp']}): {img['description'][:200]}")
    
    return "\n".join(lines)


async def can_see_images() -> bool:
    """Check if vision is available."""
    return bool(GEMINI_API_KEY)
