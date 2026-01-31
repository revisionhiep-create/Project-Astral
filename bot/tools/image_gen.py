"""Image Generation - Gemini 3 Pro Image API for drawing."""
import os
import io
import asyncio
import google.generativeai as genai


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


async def generate_image(prompt: str, reference_images: list = None) -> tuple:
    """
    Generate an image using Gemini 3 Pro Image API.
    
    Args:
        prompt: Text description of what to generate
        reference_images: Optional list of PIL images for references
        
    Returns:
        tuple: (image_data BytesIO, model_name) or (None, None)
    """
    if not GEMINI_API_KEY:
        print("[Draw] No Gemini API key configured")
        return None, None
    
    # Model priority list
    models_to_try = [
        ("models/gemini-3-pro-image-preview", "Gemini 3 Pro Art"),
        ("models/gemini-2.0-flash-exp-image", "Gemini 2.0 Art"),
        ("models/imagen-3.0-generate-001", "Imagen 3 Pro"),
    ]
    
    # Relaxed safety for artistic content
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    loop = asyncio.get_event_loop()
    
    for model_id, display_name in models_to_try:
        try:
            print(f"[Draw] Trying {display_name}...")
            model = genai.GenerativeModel(model_id, safety_settings=safety_settings)
            
            # Build generation inputs
            generation_inputs = [prompt]
            if reference_images:
                generation_inputs.extend(reference_images)
                print(f"[Draw] Using {len(reference_images)} reference images")
            
            # Run in executor (blocking API)
            response = await loop.run_in_executor(
                None, lambda: model.generate_content(generation_inputs)
            )
            
            # Handle Imagen-style response
            if hasattr(response, "images") and response.images:
                img = response.images[0]
                data = io.BytesIO()
                img.save(data, format="PNG")
                data.seek(0)
                print(f"[Draw] {display_name} success!")
                return data, display_name
            
            # Handle Gemini Pro/Flash Image response
            if response.candidates:
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if part.inline_data:
                            data = io.BytesIO(part.inline_data.data)
                            print(f"[Draw] {display_name} success!")
                            return data, display_name
                            
        except Exception as e:
            print(f"[Draw] {display_name} failed: {e}")
            continue
    
    return None, None


async def can_generate_images() -> bool:
    """Check if image generation is available."""
    return bool(GEMINI_API_KEY)
