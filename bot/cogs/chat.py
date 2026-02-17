"""GemGem Discord Bot - Chat Handler Cog (Logic AI Architecture)"""
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import pytz
import re

from ai.router import process_message, decide_tools_and_query, summarize_text

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
import asyncio

# Timezone for user-facing timestamps
PST = pytz.timezone("America/Los_Angeles")

# Regex to strip deterministic footers from Astra's own messages in history
# Matches: 💡3 🔍5 🚗24.1 T/s (any combo)
FOOTER_REGEX = re.compile(r'\n\n[💡🔍🚗][\d.]+(?:\s+T/s)?(?:\s+[💡🔍🚗][\d.]+(?:\s+T/s)?)*$')


class ChatCog(commands.Cog):
    """Handles all chat interactions with Astra."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.summary_cache = ""
        self.msgs_since_summary = 48  # Trigger soon (3rd msg) but not instantly
        self.is_summarizing = False  # Lock to prevent concurrent summaries
    
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
                
                # Step 0: Background Summary Update
                self.msgs_since_summary += 1
                if self.msgs_since_summary >= 100 and not self.is_summarizing:
                    print(f"[Chat] Triggering background summary update (msgs since: {self.msgs_since_summary})")
                    self.msgs_since_summary = 0
                    asyncio.create_task(self._update_summary(message.channel))

                # Step 1: Fetch short-term context from Discord
                # We fetch 30 messages for immediate context, but summarizer covers older history
                discord_messages = []
                try:
                    async for msg in message.channel.history(limit=30):
                        author_name = msg.author.display_name
                        msg_content = msg.content
                        if msg.author.id == self.bot.user.id:
                            author_name = "Astra"
                            msg_content = FOOTER_REGEX.sub('', msg_content)

                            msg_content = msg_content.strip()

                        # Format timestamp as relative or simple time (convert UTC to PST)
                        timestamp = msg.created_at.astimezone(PST).strftime("%I:%M %p")
                        discord_messages.append({
                            "author": author_name,
                            "content": msg_content[:500],
                            "time": timestamp
                        })
                    discord_messages.reverse()
                except Exception as e:
                    print(f"[Chat] Failed to fetch channel history: {e}")
                
                short_term_context = format_discord_context(discord_messages)
                
                # Step 2: Query long-term memory (RAG - conversations only)
                long_term_knowledge = await retrieve_relevant_knowledge(content, limit=5)
                memory_context = format_knowledge_for_context(long_term_knowledge)
                rag_count = len(long_term_knowledge)  # Track for footer
                if memory_context:
                    print(f"[RAG] Injecting {len(long_term_knowledge)} facts into context: {memory_context[:200]}")
                else:
                    print(f"[RAG] No relevant memories found for: '{content[:50]}'")
                
                # Step 3: Ask Logic AI what tools are needed (use lean 5-msg context for speed)
                decision_context_str = format_discord_context(discord_messages[-5:])
                tool_decision = await decide_tools_and_query(
                    user_message=content,
                    has_image=bool(image_url),
                    conversation_context=decision_context_str
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
                    
                    # Skip RAG image storage — descriptions pollute fact pool
                    # (caused "that's me" on every response)
                
                # Step 5: Generate response
                # Step 5: Generate response
                
                # Combine: search results FIRST (high attention zone), then Discord context
                combined_context = ""
                
                # Insert Vision Analysis (if any) - HIGH PRIORITY
                if vision_response:
                     combined_context += f"⚠️ [USER ATTACHED AN IMAGE - REACT TO THIS]:\n{vision_response}\n(Trust this analysis over your own memory)\n\n"

                # Regular chat with optional search/vision context
                # Combine: search results FIRST (high attention zone), then Discord context
                    
                # ⚠️ SEARCH RESULTS FIRST (highest priority - attention is strongest at start)
                if search_context:
                    combined_context += f"⚠️ [SEARCH RESULTS - YOU MUST USE THIS INFO]:\n{search_context}\n\n"
                
                # === PREVIOUS CONTEXT SUMMARY (High level recall) ===
                if self.summary_cache:
                    combined_context += f"⚠️ [PREVIOUS CONTEXT SUMMARY - READ THIS FIRST]:\n{self.summary_cache}\n\n"


                # Inject cached image descriptions so Astra remembers what she saw
                image_context = get_recent_image_context()
                if image_context:
                    combined_context += f"{image_context}\n\n"
                
                # === CURRENT SPEAKER (AT END for recency bias) ===
                speaker_name = message.author.display_name
                
                # RAG memory is separate - only use for things NOT in recent chat
                rag_context = ""
                if memory_context:
                    rag_context = f"[Old memories - only reference if not covered above]:\n{memory_context}"
                
                # Convert discord_messages to router-compatible history
                formatted_history = []
                for m in discord_messages:
                    # Format as [Name]: Message so router handles it correctly
                    formatted_content = f"[{m['author']}]: {m['content']}"
                    formatted_history.append({"role": "user", "content": formatted_content})

                result = await process_message(
                    user_message=content if content else "[attached an image]",
                    current_speaker=speaker_name,  # Pass speaker separately for system prompt
                    search_context=combined_context,  # System prompt context (Search + Images)
                    conversation_history=formatted_history, # Transcript (Chat History)
                    memory_context=rag_context  # RAG is deprioritized
                )
                response = result["text"]
                gen_tps = result.get("tps", 0)

                # === DETERMINISTIC ATTRIBUTION FOOTERS ===
                # Build footer based on what tools actually ran (same line)
                footer_parts = []
                if rag_count > 0:
                    footer_parts.append(f"💡{rag_count}")
                if tool_decision.get("search") and search_count > 0:
                    footer_parts.append(f"🔍{search_count}")
                # T/s visible in docker logs, no need to show in Discord
                # if gen_tps > 0:
                #     footer_parts.append(f"🚗{gen_tps} T/s")

                if footer_parts:
                    footer = "\n\n" + " ".join(footer_parts)
                    # Truncate if needed to fit footer
                    if len(response) + len(footer) > 2000:
                        response = response[:2000 - len(footer) - 5] + "..."
                    response += footer
                
                # Step 6: Store conversation to RAG (long-term memory)
                # Strip footers before saving — they're display-only
                clean_response = FOOTER_REGEX.sub('', response)
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
                        # Strip citation markers and footer emojis so TTS doesn't read them
                        tts_text = re.sub(r'\[(?:🔍|💡)?\d+\]', '', response)  # [1], [🔍1], [💡2]
                        tts_text = FOOTER_REGEX.sub('', tts_text)  # footer line
                        await voice_handler.speak_text(message.guild, tts_text.strip())
                    except Exception as ve:
                        print(f"[Voice] TTS error: {ve}")
                    
            except Exception as e:
                print(f"[Chat Error] {e}")
                import traceback
                traceback.print_exc()
                await message.channel.send("uh something broke lol, try again?")


    @commands.Cog.listener()
    async def on_ready(self):
        """Build initial summary on startup to fix amnesia."""
        print("[Chat] Bot ready - Initializing summary...")
        # Find the main chat channel (heuristic: most active or first available)
        # For now, we'll wait for the first message or try to find a default channel if configured
        # Since we don't know the main channel ID, we'll scan guilds
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).read_messages and channel.permissions_for(guild.me).read_message_history:
                    # found a readable channel, try to spark memory
                    # Ideally we'd persist the last active channel, but this is a good start
                    asyncio.create_task(self._initialize_summary(channel))
                    return

    async def _initialize_summary(self, channel):
        """Generate initial summary from history on boot."""
        print(f"[Summarizer] Bootstrapping summary from {channel.name}...")
        await self._update_summary(channel, initial=True)

    async def _update_summary(self, channel, initial=False):
        """Fetch older messages and update the summary cache."""
        try:
            self.is_summarizing = True
            if initial:
                 print("[Summarizer] Generating STARTUP summary (filling 3am gap)...")
            else:
                 print("[Summarizer] Starting background summary update...")
            
            # Fetch last 230 messages (was 130)
            # We skip the LAST 30 (which are covered by "Recent Chat")
            # We summarize messages 31-230 (up to 200 messages of context)
            limit = 230
            history = [msg async for msg in channel.history(limit=limit)]
            history.reverse()
            
            if len(history) <= 30:
                print(f"[Summarizer] Not enough history to summarize ({len(history)} msgs).")
                self.is_summarizing = False
                return
            
            # Slice: Remove the recent 30 messages that are in the immediate context window
            older_msgs = history[:-30]
            
            # Format generic transcript for summarizer
            transcript_lines = []
            for msg in older_msgs:
                if msg.content.strip():
                    name = msg.author.display_name
                    if msg.author.id == self.bot.user.id:
                        name = "Astra"
                    # Clean up Discord formatting for the summarizer
                    clean_content = msg.content.replace('\n', ' ').strip()
                    transcript_lines.append(f"{name}: {clean_content}")
            
            transcript = "\n".join(transcript_lines)
            
            # Generate summary with Gemini 2.0 Flash
            # It has a massive context window, so 200 messages is easy
            new_summary = await summarize_text(transcript)
            
            if new_summary:
                self.summary_cache = new_summary
                print(f"[Summarizer] Updated summary ({len(new_summary)} chars) | Covered {len(older_msgs)} messages")
            else:
                print("[Summarizer] Summary generation returned empty string.")
                
        except Exception as e:
            print(f"[Summarizer] Error updating summary: {e}")
        finally:
            self.is_summarizing = False


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
