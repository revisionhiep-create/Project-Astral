"""Drawing Handler - Image generation with character references and AI commentary.

Ported from Gemini Pi bot with same flow:
1. Detect character references
2. For gdraw: Enhance prompt with AI FIRST, show enhanced prompt
3. Generate image
4. Analyze generated image with vision
5. Generate personality critique
6. Send image + critique together
"""
import os
import io
import discord
import PIL.Image
import google.generativeai as genai
from io import BytesIO
from typing import Optional, List, Tuple

from tools.image_gen import generate_image
from tools.characters import detect_characters, load_character_image, get_all_character_descriptions
from memory.rag import store_drawing_knowledge
from ai.personality import ASTRA_PROMPT


# Configure Gemini for vision/text analysis
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class DrawingHandler:
    """Handles all drawing-related functionality for the bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self.last_draw_subjects = {}  # user_id -> last drawing subject
        self.last_draw_images = {}    # user_id -> last image bytes for editing
    
    async def handle_draw_request(
        self,
        message: discord.Message,
        subject: str
    ) -> Tuple[Optional[BytesIO], Optional[str], str]:
        """
        Handle a direct draw request.
        
        Flow:
        1. Detect character references
        2. Generate image
        3. Analyze image with vision
        4. Generate critique
        
        Returns:
            tuple: (image_data BytesIO, engine_name, critique)
        """
        print(f"[Draw] Processing: '{subject[:50]}...'")
        user_id = str(message.author.id)
        
        # Detect character references in the prompt
        matched_chars = detect_characters(subject)
        reference_images = []
        enhanced_prompt = subject
        
        # Load reference images for matched characters
        for char in matched_chars:
            ref_img = load_character_image(char["name"])
            if ref_img:
                reference_images.append(ref_img)
                # Append character description to prompt
                enhanced_prompt += f"\n\nCharacter reference for {char['name']}: {char['description']}"
                print(f"[Draw] Added reference: {char['name']}")
        
        # Store for potential edits
        self.last_draw_subjects[user_id] = subject
        
        # STEP 1: Generate the image
        print(f"[Draw] Generating image...")
        image_data, engine_name = await generate_image(enhanced_prompt, reference_images)
        
        if not image_data:
            return None, None, "couldn't generate that one, maybe try a different prompt?"
        
        # STEP 2: Analyze generated image and generate critique
        print(f"[Draw] Image generated, analyzing for critique...")
        critique = await self._generate_critique(
            image_data=image_data.getvalue(),
            original_prompt=subject,
            enhanced_prompt=enhanced_prompt,
            matched_chars=matched_chars,
            is_gdraw=False
        )
        
        # Store for editing
        self.last_draw_images[user_id] = io.BytesIO(image_data.getvalue())
        
        # STEP 3: Store to RAG for memory
        image_description = await self._generate_objective_description(image_data.getvalue(), subject)
        await store_drawing_knowledge(
            user_request=subject,
            enhanced_prompt=enhanced_prompt,
            image_description=image_description,
            gemgem_critique=critique,
            matched_characters=[c['name'] for c in matched_chars],
            user_id=user_id,
            is_gdraw=False
        )
        
        # Reset position for sending
        image_data.seek(0)
        
        return image_data, engine_name, critique
    
    async def handle_guided_draw_request(
        self,
        message: discord.Message,
        basic_prompt: str
    ) -> Tuple[Optional[BytesIO], Optional[str], Optional[str], str]:
        """
        Handle a guided draw (gdraw) request.
        
        Flow:
        1. Detect character references
        2. Enhance prompt with AI (show to user)
        3. Generate image with enhanced prompt
        4. Analyze image with vision
        5. Generate personality critique
        
        Returns:
            tuple: (image_data, engine_name, enhanced_prompt, critique)
        """
        print(f"[GDraw] Processing: '{basic_prompt[:50]}...'")
        user_id = str(message.author.id)
        
        # Detect character references
        matched_chars = detect_characters(basic_prompt)
        reference_images = []
        
        # Load reference images
        for char in matched_chars:
            ref_img = load_character_image(char["name"])
            if ref_img:
                reference_images.append(ref_img)
                print(f"[GDraw] Added reference: {char['name']}")
        
        # STEP 1: Enhance the prompt with AI
        print(f"[GDraw] Enhancing prompt...")
        enhanced_prompt = await self._enhance_prompt_with_ai(basic_prompt, matched_chars, reference_images)
        
        # Store for potential edits
        self.last_draw_subjects[user_id] = basic_prompt
        
        # STEP 2: Generate the image
        print(f"[GDraw] Generating image...")
        image_data, engine_name = await generate_image(enhanced_prompt, reference_images)
        
        if not image_data:
            return None, None, None, "couldn't generate that one, maybe try a different prompt?"
        
        # STEP 3: Analyze generated image and generate critique
        print(f"[GDraw] Image generated, analyzing for critique...")
        critique = await self._generate_critique(
            image_data=image_data.getvalue(),
            original_prompt=basic_prompt,
            enhanced_prompt=enhanced_prompt,
            matched_chars=matched_chars,
            is_gdraw=True
        )
        
        # Store for editing
        self.last_draw_images[user_id] = io.BytesIO(image_data.getvalue())
        
        # STEP 4: Store to RAG for memory
        image_description = await self._generate_objective_description(image_data.getvalue(), basic_prompt)
        await store_drawing_knowledge(
            user_request=basic_prompt,
            enhanced_prompt=enhanced_prompt,
            image_description=image_description,
            gemgem_critique=critique,
            matched_characters=[c['name'] for c in matched_chars],
            user_id=user_id,
            is_gdraw=True
        )
        
        # Reset position
        image_data.seek(0)
        
        return image_data, engine_name, enhanced_prompt, critique
    
    async def handle_edit_request(
        self,
        original_image_data: bytes,
        edit_instruction: str,
        user_id: str
    ) -> Tuple[Optional[BytesIO], Optional[str], str]:
        """
        Handle an edit request on an existing image.
        
        Returns:
            tuple: (image_data, engine_name, critique)
        """
        print(f"[Edit] Processing: '{edit_instruction[:50]}...'")
        
        # Detect if edit mentions characters
        matched_chars = detect_characters(edit_instruction)
        reference_images = []
        
        # Load character references if mentioned in edit
        for char in matched_chars:
            ref_img = load_character_image(char["name"])
            if ref_img:
                reference_images.append(ref_img)
        
        # Add the original image to references
        try:
            original_img = PIL.Image.open(BytesIO(original_image_data))
            reference_images.insert(0, original_img)  # Original first
        except Exception as e:
            print(f"[Edit] Error loading original: {e}")
        
        # Build edit prompt
        edit_prompt = f"Edit this image: {edit_instruction}"
        for char in matched_chars:
            edit_prompt += f"\n\nAdd {char['name']}: {char['description']}"
        
        # Generate edited image
        image_data, engine_name = await generate_image(edit_prompt, reference_images)
        
        if not image_data:
            return None, None, "edit failed, maybe try something else?"
        
        # Generate critique for the edit
        critique = await self._generate_critique(
            image_data=image_data.getvalue(),
            original_prompt=edit_instruction,
            enhanced_prompt=edit_prompt,
            matched_chars=matched_chars,
            is_edit=True
        )
        
        # Store for chain editing
        self.last_draw_images[user_id] = io.BytesIO(image_data.getvalue())
        
        # Store to RAG for memory
        image_description = await self._generate_objective_description(image_data.getvalue(), edit_instruction)
        await store_drawing_knowledge(
            user_request=edit_instruction,
            enhanced_prompt=edit_prompt,
            image_description=image_description,
            gemgem_critique=critique,
            matched_characters=[c['name'] for c in matched_chars],
            user_id=user_id,
            is_edit=True
        )
        
        # Reset position
        image_data.seek(0)
        
        return image_data, engine_name, critique
    
    async def _generate_objective_description(
        self,
        image_data: bytes,
        original_prompt: str
    ) -> str:
        """
        Generate an objective description of the generated image for RAG storage.
        This is factual, not personality-driven - used for memory retrieval.
        """
        if not GEMINI_API_KEY:
            return f"Drawing of: {original_prompt}"
        
        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            description_prompt = f"""Describe this AI-generated image objectively and factually.
Focus on:
- Main subjects and their key features (species, colors, style)
- Art style (anime, cartoon, realistic, etc.)
- Color palette
- Composition

Keep it to 1-2 sentences. No opinions or personality, just factual visual description.

Original prompt was: "{original_prompt}"
"""
            
            response = await model.generate_content_async(
                [
                    {"mime_type": "image/png", "data": image_data},
                    description_prompt
                ]
            )
            
            description = response.text.strip()
            print(f"[Draw] Objective description: {description[:60]}...")
            return description
            
        except Exception as e:
            print(f"[Draw] Description generation failed: {e}")
            return f"Drawing of: {original_prompt}"
    
    async def _enhance_prompt_with_ai(
        self,
        basic_prompt: str,
        matched_chars: List[dict],
        reference_images: List
    ) -> str:
        """
        Use AI to enhance a basic prompt into a detailed art prompt.
        Based on the Pi version's enhancement flow.
        """
        if not GEMINI_API_KEY:
            # Fallback: just add style keywords
            enhanced = basic_prompt
            for char in matched_chars:
                enhanced += f"\n\nInclude {char['name']}: {char['description']}"
            if not matched_chars:
                enhanced += "\n\nStyle: high quality, detailed, vibrant colors, professional artwork"
            return enhanced
        
        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            # Build enhancement prompt
            enhancement_prompt = """You are helping enhance an image generation prompt.

"""
            if matched_chars:
                # Add known character descriptions
                enhancement_prompt += "**Known Characters for Visual Accuracy:**\n"
                for char in matched_chars:
                    enhancement_prompt += f"- **{char['name'].title()}**: {char['description']}\n"
                enhancement_prompt += "\n"
            
            enhancement_prompt += f"""The user said: "{basic_prompt}"

Based on this, create a detailed, vivid image generation prompt that:
- Describes the style (e.g., anime, cyberpunk, watercolor, cinematic)
- Specifies lighting and atmosphere
- Suggests color palette
- Details composition
- Conveys mood/emotion

IMPORTANT: 
- Stay true to the user's idea
- If characters are mentioned, describe them accurately based on the known character info above
- DO NOT add cosmic, galaxy, gem, crystal, or sparkle themes unless specifically mentioned
- Return ONLY the image generation prompt itself, as if you're describing the scene directly

Keep it to 2-3 sentences maximum. Return ONLY the enhanced prompt, nothing else."""

            # Build inputs (text + reference images - Gemini 3 Pro supports up to 14)
            inputs = [enhancement_prompt]
            for img in reference_images[:14]:
                inputs.append(img)
            
            response = await model.generate_content_async(inputs)
            enhanced = response.text.strip()
            
            # Clean up markdown
            enhanced = enhanced.replace("**", "").replace("*", "").strip()
            
            # CRITICAL: Append character descriptions directly to the enhanced prompt
            # This ensures the image generator sees explicit character info
            if matched_chars:
                enhanced += "\n\n--- Character Reference Details ---"
                for char in matched_chars:
                    enhanced += f"\n{char['name'].title()}: {char['description']}"
            
            print(f"[GDraw] Enhanced: {enhanced[:100]}...")
            return enhanced
            
        except Exception as e:
            print(f"[GDraw] Enhancement failed: {e}")
            # Fallback
            enhanced = basic_prompt
            for char in matched_chars:
                enhanced += f"\n\nInclude {char['name']}: {char['description']}"
            return enhanced
    
    async def _generate_critique(
        self,
        image_data: bytes,
        original_prompt: str,
        enhanced_prompt: str,
        matched_chars: List[dict],
        is_gdraw: bool = False,
        is_edit: bool = False
    ) -> str:
        """
        Analyze the generated image with vision, then create a personality critique.
        
        This is the key flow from the Pi version:
         1. Load the generated image
        2. Send image + context to AI with Astra's personality
        3. Get witty critique based on what AI SEES
        """
        if not GEMINI_API_KEY:
            return self._simple_fallback(matched_chars, is_gdraw, is_edit)
        
        try:
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            # Build critique request using centralized personality
            critique_prompt = f"""{ASTRA_PROMPT}

You just created this image as an artist.

The person asked for: "{original_prompt}"
"""
            if enhanced_prompt != original_prompt:
                critique_prompt += f"\nYou enhanced it to: \"{enhanced_prompt[:200]}...\"\n"
            
            if matched_chars:
                char_names = ", ".join([c["name"].title() for c in matched_chars])
                critique_prompt += f"\nYou included these characters: {char_names}\n"
            
            critique_prompt += """
Look at this image you created and give your reaction/critique (1-2 sentences max).
Be like a friend showing off their art - casual, maybe a little proud.
React to what you ACTUALLY SEE in the image.
"""
            
            if is_edit:
                critique_prompt += "\nThis was an edit of an existing image - comment on the changes.\n"
            
            # Load image and send to vision
            response = await model.generate_content_async(
                [
                    {"mime_type": "image/png", "data": image_data},
                    critique_prompt
                ]
            )
            
            critique = response.text.strip()
            print(f"[Draw] Critique: {critique[:60]}...")
            return critique
            
        except Exception as e:
            print(f"[Draw] Critique generation failed: {e}")
            return self._simple_fallback(matched_chars, is_gdraw, is_edit)
    
    def _simple_fallback(self, matched_chars: List[dict], is_gdraw: bool = False, is_edit: bool = False) -> str:
        """Fallback simple messages without vision."""
        if matched_chars:
            char_names = [c["name"].title() for c in matched_chars]
            if len(char_names) == 1:
                return f"Here's {char_names[0]} for you! ✨"
            else:
                return f"Here's {', '.join(char_names[:-1])} and {char_names[-1]} together! ✨"
        
        if is_edit:
            return "Done! Here's the edited version ✏️"
        if is_gdraw:
            return "Here's what I came up with based on your idea! 🎨"
        
        return "Here you go! 🎨"


# Singleton instance
_drawing_handler = None


def get_drawing_handler(bot) -> DrawingHandler:
    """Get or create the drawing handler instance."""
    global _drawing_handler
    if _drawing_handler is None:
        _drawing_handler = DrawingHandler(bot)
    return _drawing_handler
