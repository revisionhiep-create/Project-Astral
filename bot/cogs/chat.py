"""GemGem Discord Bot - Chat Handler Cog (Logic AI Architecture)"""
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from ai.router import process_message, decide_tools_and_query
from ai.persona_manager import should_update, analyze_and_update
from memory.rag import (
    retrieve_relevant_knowledge, 
    store_conversation,
    store_image_knowledge,
    format_knowledge_for_context
)
from tools.search import search, format_search_results
from tools.vision import analyze_image, can_see_images, get_recent_image_context
from tools.discord_context import fetch_recent_messages, format_discord_context
from tools.voice_handler import get_voice_handler


class ChatCog(commands.Cog):
    """Handles all chat interactions with GemGem."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle incoming messages with Logic AI routing."""
        # Ignore own messages and bots
        if message.author.bot:
            return
        
        # Check if bot is mentioned or in DM
        is_mentioned = self.bot.user in message.mentions
        is_dm = isinstance(message.channel, discord.DMChannel)
        
        if not (is_mentioned or is_dm):
            return
        
        # Clean the message (remove bot mention)
        content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        if not content and not message.attachments:
            return
        
        # Skip if it looks like a draw request (let draw cog handle it)
        content_lower = content.lower()
        draw_keywords = ['draw ', 'gdraw ', 'sketch ', 'paint ', 'create an image', 'create a picture', 'guided draw']
        if any(content_lower.startswith(kw) or f' {kw}' in content_lower for kw in draw_keywords):
            return  # Draw cog will handle this
        
        async with message.channel.typing():
            try:
                # Check for image attachments
                image_url = None
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        image_url = attachment.url
                        break
                
                # ============ NEW LOGIC AI FLOW ============
                
                # Step 1: Fetch short-term context from Discord (last 50 msgs from THIS channel)
                # Use message.channel.history() directly (same as GemGem) for reliability
                discord_messages = []
                try:
                    async for msg in message.channel.history(limit=50):
                        author_name = msg.author.display_name
                        # Only label THIS bot as "Astra" - other bots (like GemGem) keep their names
                        if msg.author.id == self.bot.user.id:
                            author_name = "Astra"
                        # Format timestamp as relative or simple time
                        timestamp = msg.created_at.strftime("%I:%M %p")
                        discord_messages.append({
                            "author": author_name,
                            "content": msg.content[:500],
                            "time": timestamp
                        })
                    discord_messages.reverse()  # Chronological order
                except Exception as e:
                    print(f"[Chat] Failed to fetch channel history: {e}")
                
                short_term_context = format_discord_context(discord_messages)
                print(f"[Chat] Discord context: {len(discord_messages)} msgs, {len(short_term_context)} chars")
                # Debug: show first 5 authors
                authors = [m.get('author', '?') for m in discord_messages[:10]]
                print(f"[Chat] Sample authors: {authors}")
                
                # Step 2: Query long-term memory (RAG - conversations only)
                long_term_knowledge = await retrieve_relevant_knowledge(content, limit=5)
                memory_context = format_knowledge_for_context(long_term_knowledge)
                
                # Step 3: Ask Logic AI what tools are needed
                tool_decision = await decide_tools_and_query(
                    user_message=content,
                    has_image=bool(image_url),
                    conversation_context=short_term_context
                )
                
                # Step 4: Execute tools based on Logic AI decision
                search_context = ""
                vision_response = None
                
                # Search if Logic AI decided
                if tool_decision.get("search"):
                    search_query = tool_decision.get("search_query") or content
                    print(f"[Chat] Logic AI triggered search: '{search_query}'")
                    search_results = await search(search_query, num_results=5)
                    search_context = format_search_results(search_results)
                    print(f"[Chat] Got {len(search_results)} results")
                    # NOTE: No RAG storage for searches anymore!
                
                # Vision if image is attached (always analyze images)
                if image_url:
                    print(f"[Chat] Vision triggered (image attached from {message.author.display_name})")
                    vision_response = await analyze_image(
                        image_url, 
                        content if content else "",
                        conversation_context=short_term_context,
                        username=message.author.display_name
                    )
                    
                    # Store image knowledge for learning
                    await store_image_knowledge(
                        gemini_description=vision_response,
                        image_url=image_url,
                        user_context=content if content else None,
                        gemgem_response=vision_response,
                        user_id=str(message.author.id)
                    )
                
                # Step 5: Generate response
                if vision_response:
                    # Image was analyzed - use Gemini's vision response directly
                    # (Gemini already has GemGem personality for image analysis)
                    response = vision_response
                else:
                    # Regular chat with optional search/vision context
                    # Combine: search results + Discord short-term context
                    combined_context = ""
                    
                    # === CURRENT SPEAKER (TOP PRIORITY) ===
                    # This person is talking to you RIGHT NOW - respond to THEM specifically
                    speaker_name = message.author.display_name
                    combined_context += f">>> RESPONDING TO: {speaker_name} <<<\n"
                    combined_context += f"(This is who you're talking to. Address them specifically.)\n\n"
                    
                    if short_term_context:
                        combined_context += f"=== RECENT CHAT (last few minutes - YOU SAW THIS) ===\n{short_term_context}\n"
                        combined_context += f"\n--- END OF CHAT HISTORY ---\n"
                        combined_context += f"--- {speaker_name} IS NOW TALKING TO YOU ---\n\n"
                    
                    # Inject cached image descriptions so Astra remembers what she saw
                    image_context = get_recent_image_context()
                    if image_context:
                        combined_context += f"{image_context}\n\n"
                    
                    if search_context:
                        combined_context += f"[Search Results]:\n{search_context}"
                    
                    # RAG memory is separate - only use for things NOT in recent chat
                    rag_context = ""
                    if memory_context:
                        rag_context = f"[Old memories - only reference if not covered above]:\n{memory_context}"
                    
                    response = await process_message(
                        user_message=content,
                        current_speaker=speaker_name,  # Pass speaker separately for system prompt
                        search_context=combined_context,  # Discord context + search
                        conversation_history=None,
                        memory_context=rag_context  # RAG is deprioritized
                    )
                
                # Step 6: Store conversation to RAG (long-term memory)
                await store_conversation(
                    user_message=content,
                    gemgem_response=response,
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    channel_id=str(message.channel.id),
                    guild_id=str(message.guild.id) if message.guild else None
                )
                
                # Step 7: Check if we should update persona (every 10 messages)
                if should_update():
                    # Run in background - don't block the response
                    import asyncio
                    asyncio.create_task(analyze_and_update(discord_messages))
                    print("[Persona] Triggered background persona update")
                
                # ============ END LOGIC AI FLOW ============
                
                # Send response (split if too long) - use channel.send so other bots can see
                if len(response) > 2000:
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for chunk in chunks:
                        await message.channel.send(chunk)
                else:
                    await message.channel.send(response)
                
                # Speak response if in voice channel
                if message.guild and message.guild.voice_client:
                    try:
                        voice_handler = get_voice_handler(self.bot)
                        await voice_handler.speak_text(message.guild, response)
                    except Exception as ve:
                        print(f"[Voice] TTS error: {ve}")
                    
            except Exception as e:
                print(f"[Chat Error] {e}")
                import traceback
                traceback.print_exc()
                await message.channel.send("uh something broke lol, try again?")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
