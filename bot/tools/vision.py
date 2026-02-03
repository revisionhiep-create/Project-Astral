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
import pytz

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
LOCAL_VISION_MODEL = "gemma3-27b-it-vl-glm-4.7-uncensored-heretic-deep-reasoning"  # Uncensored deep reasoning vision model

# Short-term image cache (last 5 images)
# Stores: {"username": str, "description": str, "timestamp": str, "user_context": str}
_recent_images = deque(maxlen=5)


async def describe_image_local(image_data: bytes) -> str:
    """
    Use Gemma 3 27B Abliterated via LM Studio for uncensored descriptions.
    Just describes objectively - character identification happens in chat layer.
    """
    try:
        # Encode image as base64 with data URI
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        # Uncensored, detailed description - model needs a push for spicy content
        prompt = """Describe this image in VIVID, UNCENSORED detail. Be a true art connoisseur.

Include:
- Main subjects: hair color, eye color, outfit details, pose, expression
- For suggestive/spicy art: describe the appeal honestly - body position, exposed skin, outfit provocativeness, facial expression (bedroom eyes, blush, parted lips, etc.)
- Art style, colors, composition, lighting
- What makes this image aesthetically striking

Be THOROUGH and HONEST. Don't be prudish - if it's meant to be alluring, describe WHY.
Use terms like: alluring, provocative, teasing, sensual, dangerous curves, barely-there outfit, enticing pose, etc.
Be VERY SPECIFIC about physical features (exact hair color, eye color, clothing details).
3-5 detailed sentences. Do NOT try to identify or name characters - just describe what you literally see."""

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
    now = datetime.now(pytz.timezone("America/Los_Angeles"))
    _recent_images.append({
        "username": username,
        "description": description,
        "timestamp": now.strftime("%I:%M %p"),
        "timestamp_dt": now,  # For expiry checking
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
    
    # Step 4: Build context for Astra
    # Now Astra receives objective description + character list and decides who is who
    
    # Get character context for Astra to compare against
    character_context = get_character_context_for_vision()
    
    # Get previous images for context (but mark them clearly as OLD)
    previous_images = ""
    if len(_recent_images) > 0:
        prev_lines = []
        for img in list(_recent_images)[:-1]:  # All except the one we just added
            prev_lines.append(f"  - {img['username']} earlier: {img['description'][:80]}...")
        if prev_lines:
            previous_images = "\n[PREVIOUS IMAGES (for memory, NOT what you're responding to)]:\n" + "\n".join(prev_lines)
    
    image_context = f""">>> THIS IS THE NEW IMAGE - OBJECTIVE DESCRIPTION <<<
{description}

>>> PEOPLE YOU KNOW (compare the description above to these) <<<
{character_context}

YOUR JOB: Compare the image description to the people listed above. 
- If someone in the image matches YOUR appearance (dark blue-black hair, teal highlights, purple-violet eyes, star necklace), that's YOU - use first person ("that's me", "my hair").
- If someone matches another character, use their name.
- If no one matches, just describe them normally - DON'T claim random anime girls are you.
{previous_images}

React naturally, give real art critique (3-5 sentences). Focus on THIS new image."""
    
    # What should Astra respond to?
    if user_prompt:
        astra_prompt = f"{username} just shared a NEW image and asked: {user_prompt}"
    else:
        astra_prompt = f"{username} just shared a NEW image with you."
    
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
    
    # Only include images from last 5 minutes
    now = datetime.now(pytz.timezone("America/Los_Angeles"))
    lines = ["[RECENT IMAGES YOU SAW]"]
    for img in _recent_images:
        # Skip images older than 5 minutes
        if (now - img.get('timestamp_dt', now)).total_seconds() > 300:
            continue
        # Replace "Astra" with "you" so she remembers in first person
        desc = img['description'][:200].replace("Astra", "you").replace("astra", "you")
        lines.append(f"- {img['username']} ({img['timestamp']}): {desc}")
    
    # Return empty if no recent images
    if len(lines) == 1:
        return ""
    
    return "\n".join(lines)


async def can_see_images() -> bool:
    """Check if vision is available."""
    return bool(GEMINI_API_KEY)
