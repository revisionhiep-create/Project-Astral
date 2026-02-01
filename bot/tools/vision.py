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
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
LOCAL_VISION_MODEL = "llama3.2-vision:11b"  # Less filtered than LLaVA

# Short-term image cache (last 5 images)
# Stores: {"username": str, "description": str, "timestamp": str, "user_context": str}
_recent_images = deque(maxlen=5)


async def describe_image_local(image_data: bytes) -> str:
    """
    Fallback: Use LLaVA locally for uncensored descriptions.
    Runs on CPU/RAM to avoid VRAM usage.
    """
    try:
        # Encode image as base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        
        prompt = """Describe this image in detail. Include:
- Main subjects (characters, people, objects)
- Their appearance, poses, expressions
- Art style, colors, composition
- Background and setting
- Any notable or suggestive elements

Be thorough and honest in your description (3-5 sentences)."""

        payload = {
            "model": LOCAL_VISION_MODEL,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "temperature": 0.3
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_HOST}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    print(f"[Vision] LLaVA error: {resp.status}")
                    return None
                
                data = await resp.json()
                description = data.get("response", "").strip()
                print(f"[Vision] LLaVA description: {description[:80]}...")
                return description
                
    except Exception as e:
        print(f"[Vision] LLaVA error: {e}")
        return None


async def describe_image(image_url: str = None, image_data: bytes = None) -> str:
    """
    Step 1: Try Gemini first, fallback to LLaVA for uncensored descriptions.
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
    
    # Try Gemini first (fast, but may censor)
    if GEMINI_API_KEY:
        try:
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
                description_prompt += f"""

Known characters to identify if present:
{character_context}
If you recognize any of these characters, mention them by name."""
            
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
            print(f"[Vision] Gemini description: {description[:80]}...")
            
            # If Gemini gave a very short response, it might have censored - try LLaVA
            if len(description) < 100:
                print("[Vision] Gemini response short, trying LLaVA fallback...")
                llava_desc = await describe_image_local(image_data)
                if llava_desc and len(llava_desc) > len(description):
                    description = llava_desc
                    print("[Vision] Using LLaVA description instead")
                    
        except Exception as e:
            print(f"[Vision] Gemini error: {e}, trying LLaVA fallback...")
            description = await describe_image_local(image_data)
    else:
        # No Gemini API, use LLaVA directly
        description = await describe_image_local(image_data)
    
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
