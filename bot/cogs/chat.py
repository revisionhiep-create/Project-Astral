"""GemGem Discord Bot - Chat Handler Cog (Logic AI Architecture)"""
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import pytz
import re

from ai.router import process_message, decide_tools_and_query

from memory.rag import (
    retrieve_relevant_knowledge, 
    store_conversation,
    store_full_search,
    store_image_knowledge,
    format_knowledge_for_context
)
from tools.search import search, format_search_results
from tools.vision import analyze_image, can_see_images, get_recent_image_context
from tools.discord_context import fetch_recent_messages, format_discord_context
from tools.voice_handler import get_voice_handler
from tools.admin import whitelist, ADMIN_IDS

# Timezone for user-facing timestamps
PST = pytz.timezone("America/Los_Angeles")

# Regex to strip deterministic footers from Astra's own messages in history
FOOTER_REGEX = re.compile(r'\n\n[💡🔍🧠]\d+', re.DOTALL)


class ChatCog(commands.Cog):
    """Handles all chat interactions with Astra."""
    
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
        
        # 🛡️ AUTHORIZATION CHECK (Silent ignore for unauthorized users)
        if not whitelist.is_authorized(message.author.id):
            return
        
        # Clean the message (remove bot mention - handle both <@id> and <@!id> formats)
        content = re.sub(r'<@!?\d+>', '', message.content).strip()
        if not content and not message.attachments:
            return
        
        # Handle 'access' mention commands (Admin only)
        content_lower = content.lower()
        if content_lower.startswith("access") and message.author.id in ADMIN_IDS:
            admin_cog = self.bot.get_cog("AdminCog")
            if admin_cog:
                await admin_cog.handle_access_mention(message, content)
            else:
                await message.channel.send("⚠️ Access control module is currently unavailable.")
            return
        
        # Skip if it looks like a draw request (let draw cog handle it)
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
                
                # Step 1: Fetch short-term context from Discord (last 25 msgs - reduced from 50 to prevent name dilution)
                # Use message.channel.history() directly (same as GemGem) for reliability
                discord_messages = []
                try:
                    async for msg in message.channel.history(limit=50):
                        author_name = msg.author.display_name
                        msg_content = msg.content
                        # Only label THIS bot as "Astra" - other bots (like GemGem) keep their names
                        if msg.author.id == self.bot.user.id:
                            author_name = "Astra"
                            # Strip footers from Astra's own messages when adding to context
                            msg_content = FOOTER_REGEX.sub('', msg_content)
                        # Format timestamp as relative or simple time (convert UTC to PST)
                        timestamp = msg.created_at.astimezone(PST).strftime("%I:%M %p")
                        discord_messages.append({
                            "author": author_name,
                            "content": msg_content[:500],
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
                rag_count = len(long_term_knowledge)  # Track for footer
                if memory_context:
                    print(f"[RAG] Injecting {len(long_term_knowledge)} facts into context: {memory_context[:200]}")
                else:
                    print(f"[RAG] No relevant memories found for: '{content[:50]}'")
                
                # Step 3: Ask Logic AI what tools are needed
                tool_decision = await decide_tools_and_query(
                    user_message=content,
                    has_image=bool(image_url),
                    conversation_context=short_term_context
                )
                
                # Step 4: Execute tools based on Logic AI decision
                search_context = ""
                vision_response = None
                search_count = 0  # Track for footer
                
                # Search if Logic AI decided
                if tool_decision.get("search"):
                    search_query = tool_decision.get("search_query") or content
                    time_range = tool_decision.get("time_range")  # day/week/month/year/None
                    print(f"[Chat] Logic AI triggered search: '{search_query}' (time_range={time_range})")
                    search_results = await search(search_query, num_results=5, time_range=time_range)
                    search_context = format_search_results(search_results)
                    search_count = len(search_results)  # Track for footer
                    print(f"[Chat] Got {len(search_results)} results")
                    # Store search results as facts in RAG for long-term knowledge
                    if search_results:
                        await store_full_search(search_query, search_results)
                        print(f"[RAG] Stored {len(search_results)} search results as knowledge")
                
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
                    # Combine: search results FIRST (high attention zone), then Discord context
                    combined_context = ""
                    
                    # ⚠️ SEARCH RESULTS FIRST (highest priority - attention is strongest at start)
                    if search_context:
                        combined_context += f"⚠️ [SEARCH RESULTS - YOU MUST USE THIS INFO]:\n{search_context}\n\n"
                    
                    # Short-term context
                    if short_term_context:
                        combined_context += f"=== RECENT CHAT ===\n{short_term_context}\n"
                        combined_context += f"--- END OF CHAT ---\n\n"
                    
                    # Inject cached image descriptions so Astra remembers what she saw
                    image_context = get_recent_image_context()
                    if image_context:
                        combined_context += f"{image_context}\n\n"
                    
                    # === CURRENT SPEAKER (AT END for recency bias) ===
                    speaker_name = message.author.display_name
                    combined_context += f">>> {speaker_name} IS NOW TALKING TO YOU <<<"
                    
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
                
                # === DETERMINISTIC ATTRIBUTION FOOTERS ===
                # Build footer based on what tools actually ran
                footer = ""
                if rag_count > 0:
                    footer += f"\n\n💡{rag_count}"
                if tool_decision.get("search") and search_count > 0:
                    footer += f"\n\n🔍{search_count}"
                
                if footer:
                    # Truncate if needed to fit footer
                    if len(response) + len(footer) > 2000:
                        response = response[:2000 - len(footer) - 5] + "..."
                    response += footer
                
                # Step 6: Store conversation to RAG (long-term memory)
                # Strip footers before saving — they're display-only
                clean_response = re.sub(r'\n\n💡\d+$', '', response)
                clean_response = re.sub(r'\n\n🔍\d+$', '', clean_response)
                await store_conversation(
                    user_message=content,
                    gemgem_response=clean_response,
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    channel_id=str(message.channel.id),
                    guild_id=str(message.guild.id) if message.guild else None
                )
                

                
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
