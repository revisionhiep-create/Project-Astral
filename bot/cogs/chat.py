"""GemGem Discord Bot - Chat Handler Cog (Logic AI Architecture)"""
import discord
from discord.ext import commands
import pytz
import re
import traceback
import os

from ai.router import process_message, decide_tools_and_query, summarize_text

from memory.rag import (
    retrieve_relevant_knowledge,
    store_conversation,
    store_full_search,
    format_knowledge_for_context
)
from memory.shared_memory import SharedMemoryManager
from tools.search import search, format_search_results
from tools.vision import analyze_image, get_recent_image_context
from tools.voice_handler import get_voice_handler
from tools.admin import whitelist, ADMIN_IDS
import asyncio

# Timezone for user-facing timestamps
PST = pytz.timezone("America/Los_Angeles")

# Regex to strip deterministic footers from Astral's own messages in history
FOOTER_REGEX = re.compile(r'\n\n[💡🔍]\d+(?:\s[💡🔍]\d+)*$', re.DOTALL)


class ChatCog(commands.Cog):
    """Handles all chat interactions with Astral."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize shared memory manager
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.shared_memory = SharedMemoryManager(data_dir)
        self.msgs_since_summary = 0  # Start at 0, will trigger at 40
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
        content = re.sub(r'<@!?\d+>', '', message.clean_content).strip()
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
                
                # ============ SHARED MEMORY LOGIC AI FLOW ============

                # Step 0: Background Summary Update
                self.msgs_since_summary += 1
                if self.msgs_since_summary >= 40 and not self.is_summarizing:
                    print(f"[Chat] Triggering background summary update (msgs since: {self.msgs_since_summary})")
                    self.msgs_since_summary = 0
                    asyncio.create_task(self._update_summary())

                # Step 1: Load short-term context from shared_memory.json
                # Load all history, format_for_router will handle truncation to last 30 if summary exists
                shared_history = self.shared_memory.load_memory()
                formatted_history, summary_context = self.shared_memory.format_for_router(shared_history)

                print(f"[SharedMemory] Loaded {len(shared_history)} messages from shared_memory.json")
                if summary_context:
                    print(f"[SharedMemory] Using summary context ({len(summary_context)} chars)")

                # Step 2: Query long-term memory (RAG - conversations only)
                # Skip RAG for simple greetings or when image is attached (waste of context)
                greeting_patterns = ['hi', 'hello', 'hey', 'sup', 'yo', 'morning', 'evening', 'night', 'honey', 'babe', 'love']
                is_greeting = len(content.split()) <= 3 and any(pattern in content.lower() for pattern in greeting_patterns)
                has_image = bool(image_url)

                if is_greeting:
                    long_term_knowledge = []
                    memory_context = ""
                    rag_count = 0
                    print(f"[RAG] Skipping RAG for greeting: '{content[:50]}'")
                elif has_image:
                    long_term_knowledge = []
                    memory_context = ""
                    rag_count = 0
                    print(f"[RAG] Skipping RAG for image query (vision provides context): '{content[:50]}'")
                else:
                    long_term_knowledge = await retrieve_relevant_knowledge(content, limit=3)
                    memory_context = format_knowledge_for_context(long_term_knowledge, current_username=message.author.display_name)
                    rag_count = len(long_term_knowledge)  # Track for footer
                    if memory_context:
                        print(f"[RAG] Injecting {len(long_term_knowledge)} facts into context: {memory_context[:200]}")
                    else:
                        print(f"[RAG] No relevant memories found for: '{content[:50]}'")
                
                # Step 3: Tool routing - GROK HANDLES THIS NATIVELY
                # Grok's /v1/responses endpoint automatically decides when to search/use vision
                # No external tool routing needed!
                print(f"[Chat] Using Grok native tool routing (web_search + vision)")

                # Step 4: No external tool execution needed
                # Grok will handle search and vision internally via /v1/responses endpoint
                search_context = ""  # Not needed - Grok searches internally
                vision_response = None  # Not needed - Grok handles vision internally
                search_count = 0  # Not tracked anymore - Grok handles citations

                # REMOVED: Gemini tool routing (decide_tools_and_query)
                # REMOVED: SearXNG search execution
                # REMOVED: Gemini vision analysis
                # All tool calling is now handled by Grok's /v1/responses endpoint
                
                # Step 5: Generate response

                # Build context for system prompt (search results and summaries)
                combined_context = ""

                # ⚠️ SEARCH RESULTS (if no image attached)
                if search_context:
                    combined_context += f"⚠️ [SEARCH RESULTS - YOU MUST USE THIS INFO]:\n{search_context}\n\n"

                # === PREVIOUS CONTEXT SUMMARY (from shared_memory) ===
                if summary_context and not image_url:
                    combined_context += f"⚠️ {summary_context}\n\n"

                # Inject cached image descriptions so Astral remembers what she saw (skip if current message has image)
                if not image_url:
                    image_context = get_recent_image_context()
                    if image_context:
                        combined_context += f"{image_context}\n\n"

                # === CURRENT SPEAKER ===
                speaker_name = message.author.display_name

                # RAG memory is separate - only use for things NOT in recent chat
                rag_context = ""
                if memory_context:
                    rag_context = f"[Old memories - only reference if not covered above]:\n{memory_context}"

                # formatted_history is already built from shared_memory.load_memory()
                # For image queries, inject vision analysis as the most recent context
                if vision_response:
                    # Replace character name "Astra" with "you" so the LLM recognizes it's talking about herself
                    vision_self_aware = vision_response.replace("Astra", "you").replace("astra", "you")
                    # Add vision as a system message in history (appears right before current message)
                    formatted_history.append({
                        "role": "user",
                        "content": f"[Image Description]: {vision_self_aware}"
                    })

                response = await process_message(
                    user_message=content if content else "[attached an image]",
                    current_speaker=speaker_name,  # Pass speaker separately for system prompt
                    search_context=combined_context,  # System prompt context (Search results, summaries)
                    conversation_history=formatted_history, # Full 30-message history (vision injected here for images)
                    memory_context=rag_context,  # RAG is deprioritized
                    has_vision=bool(image_url),  # Enable vision mode for image queries
                    image_url=image_url  # Pass image URL for Grok's native vision
                )
                
                # === DETERMINISTIC ATTRIBUTION FOOTERS ===
                # Build footer based on what tools actually ran (same line)
                footer_parts = []
                if rag_count > 0:
                    footer_parts.append(f"💡{rag_count}")
                # Note: Grok handles search internally, citations are in response
                # search_count is always 0 for Grok (no external search tracking)
                
                if footer_parts:
                    footer = "\n\n" + " ".join(footer_parts)
                    # Truncate if needed to fit footer
                    if len(response) + len(footer) > 2000:
                        response = response[:2000 - len(footer) - 5] + "..."
                    response += footer
                
                # Step 6: Store conversation to shared_memory.json
                # Strip footers before saving — they're display-only
                clean_response = re.sub(r'\n\n[💡🔍]\d+(?:\s[💡🔍]\d+)*$', '', response)

                # For images, store the vision description with the response
                if vision_response:
                    # Store format: "Image shows: [description]\n\n[Astral's response]"
                    memory_response = f"Image shows: {vision_response}\n\n{clean_response}"
                else:
                    memory_response = clean_response

                # Append to shared_memory.json
                self.shared_memory.append_conversation_turn(
                    user_message=content if content else "[attached an image]",
                    bot_response=memory_response,
                    username=message.author.display_name
                )
                print(f"[SharedMemory] Stored conversation turn for {message.author.display_name}")

                # Also store to RAG for long-term fact extraction
                context_for_rag = "\n".join([msg["content"] for msg in formatted_history[-5:]]) if len(formatted_history) > 1 else None
                await store_conversation(
                    user_message=content if content else "[attached an image]",
                    gemgem_response=clean_response,
                    user_id=str(message.author.id),
                    username=message.author.display_name,
                    channel_id=str(message.channel.id),
                    guild_id=str(message.guild.id) if message.guild else None,
                    conversation_context=context_for_rag
                )



                # ============ END SHARED MEMORY LOGIC AI FLOW ============
                
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
                        tts_text = re.sub(r'\n\n[💡🔍]\d+(?:\s[💡🔍]\d+)*$', '', tts_text)  # footer line
                        await voice_handler.speak_text(message.guild, tts_text.strip())
                    except Exception as ve:
                        print(f"[Voice] TTS error: {ve}")
                    
            except Exception as e:
                print(f"[Chat Error] {e}")
                traceback.print_exc()
                await message.channel.send("uh something broke lol, try again?")


    @commands.Cog.listener()
    async def on_ready(self):
        """Build initial summary on startup to fix amnesia."""
        print("[Chat] Bot ready - Initializing summary from shared_memory.json...")
        asyncio.create_task(self._initialize_summary())

    async def _initialize_summary(self) -> None:
        """Generate initial summary from shared_memory.json on boot."""
        print(f"[Summarizer] Bootstrapping summary from shared_memory.json...")
        await self._update_summary(initial=True)

    async def _update_summary(self, initial: bool = False) -> None:
        """Generate summary from shared_memory.json for older messages."""
        try:
            self.is_summarizing = True
            if initial:
                 print("[Summarizer] Generating STARTUP summary from shared memory...")
            else:
                 print("[Summarizer] Starting background summary update...")

            # Load all messages from shared_memory.json
            history = self.shared_memory.load_memory()

            # Only summarize if we have enough history (need more than 30 messages)
            if len(history) <= 30:
                print(f"[Summarizer] Not enough history to summarize ({len(history)} msgs).")
                self.is_summarizing = False
                return

            # Summarize messages 0 to -30 (everything except last 30)
            # For local model: limit to last 200 messages max (messages 31-200 if history > 200)
            if len(history) > 200:
                older_msgs = history[-200:-30]  # Messages 31-200 from the end
            else:
                older_msgs = history[:-30]  # All except last 30

            # Format transcript for summarizer
            transcript_lines = []
            for msg in older_msgs:
                role = msg.get("role", "unknown")
                username = msg.get("username", "User")
                parts = msg.get("parts", [""])
                content = parts[0] if parts else ""

                if role == "model":
                    transcript_lines.append(f"Astral: {content}")
                else:
                    transcript_lines.append(f"{username}: {content}")

            transcript = "\n".join(transcript_lines)

            # Generate summary with Gemini 2.0 Flash
            new_summary = await summarize_text(transcript)

            if new_summary:
                # Save summary to shared_summary.txt
                self.shared_memory.save_summary(new_summary)
                print(f"[Summarizer] Updated summary ({len(new_summary)} chars) | Covered {len(older_msgs)} messages")
            else:
                print("[Summarizer] Summary generation returned empty string.")

        except Exception as e:
            print(f"[Summarizer] Error updating summary: {e}")
        finally:
            self.is_summarizing = False


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
