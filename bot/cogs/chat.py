"""GemGem Discord Bot - Chat Handler Cog (Logic AI Architecture)"""
import discord
from discord.ext import commands
import re
import traceback
import os

from config import BotConfig
from ai.router import process_message

from memory import (
    retrieve_relevant_knowledge,
    store_conversation,
    store_full_search,  # Deprecated no-op
    format_knowledge_for_context
)
from memory.shared_memory import SharedMemoryManager
from tools.vision import get_recent_image_context
from tools.voice_handler import get_voice_handler
from tools.admin import whitelist, ADMIN_IDS
import asyncio

# Regex to strip deterministic footers from Astral's own messages in history
FOOTER_REGEX = re.compile(r'\n\n[💡🔍]\d+(?:\s[💡🔍]\d+)*$', re.DOTALL)


class ChatCog(commands.Cog):
    """Handles all chat interactions with Astral."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize shared memory manager
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.shared_memory = SharedMemoryManager(data_dir)
        # Note: Summarization is handled by GemGem, Astral just reads the summary
    
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

        # Debug: Log all messages that mention the bot
        print(f"[Chat] Received mention from {message.author.display_name} (ID: {message.author.id})")

        # 🛡️ AUTHORIZATION CHECK (Silent ignore for unauthorized users)
        if not whitelist.is_authorized(message.author.id):
            print(f"[Chat] ⚠️ Unauthorized user: {message.author.display_name} (ID: {message.author.id})")
            return
        
        # Clean the message (remove bot mention - handle both <@id> and <@!id> formats)
        # Use message.content instead of clean_content to preserve URLs
        try:
            content = re.sub(r'<@!?\d+>', '', message.content).strip()
            print(f"[Chat] Message content after cleaning: '{content[:100]}'")
        except Exception as e:
            print(f"[Chat] Error cleaning content: {e}")
            content = ""

        # Debug log to see what we received
        print(f"[Chat] Message from {message.author.display_name}: content='{content[:100] if content else '(empty)'}', attachments={len(message.attachments)}, embeds={len(message.embeds)}")
        # Handle 'access' mention commands (Admin only)
        content_lower = content.lower() if content else ""
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
                # Check for image attachments and Tenor GIF links
                image_url = None
                gif_url = None

                # First, check for direct image attachments
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        if attachment.content_type == "image/gif" or attachment.url.lower().endswith('.gif'):
                            gif_url = attachment.url
                        else:
                            image_url = attachment.url
                        break

                # Second, check for Tenor GIF links in message content or embeds
                # Discord's GIF button sends Tenor URLs as plain text or in embeds
                if not gif_url and not image_url:
                    # PRIORITY 1: Check embeds for direct media URLs (most accurate)
                    if message.embeds:
                        for embed in message.embeds:
                            # Discord gifv embeds have video.url with MP4
                            if embed.type == "gifv" and hasattr(embed, 'video') and embed.video and embed.video.url:
                                # Use the MP4 URL - Gemini can analyze video formats
                                gif_url = embed.video.url
                                print(f"[Chat] Using embed video URL: {gif_url}")
                                break
                            # Some embeds have thumbnail URLs
                            elif hasattr(embed, 'thumbnail') and embed.thumbnail and embed.thumbnail.url:
                                if 'tenor.com' in embed.thumbnail.url:
                                    gif_url = embed.thumbnail.url
                                    print(f"[Chat] Using embed thumbnail URL: {gif_url}")
                                    break

                    # PRIORITY 2: Parse message content for Tenor URLs
                    if not gif_url:
                        search_text = content

                        # Also collect embed URLs as fallback
                        if message.embeds:
                            for embed in message.embeds:
                                if embed.url:
                                    search_text += " " + embed.url

                        print(f"[Chat] Searching for Tenor URLs in text: {search_text[:200]}")

                        # Match various Tenor URL formats
                        tenor_patterns = [
                            r'https?://(?:www\.)?tenor\.com/view/[^\s]+',
                            r'https?://(?:www\.)?tenor\.com/[^\s]+\.gif',
                            r'https?://media\.tenor\.com/[^\s]+',
                            r'https?://c\.tenor\.com/[^\s]+'
                        ]

                        # Only look for direct media URLs - skip HTML scraping to avoid wrong GIFs
                        for pattern in tenor_patterns:
                            match = re.search(pattern, search_text)
                            if match:
                                tenor_url = match.group(0)
                                print(f"[Chat] Found Tenor URL in text: {tenor_url}")

                                # Only use direct media URLs (media.tenor.com or c.tenor.com)
                                if 'media.tenor.com' in tenor_url or 'c.tenor.com' in tenor_url:
                                    gif_url = tenor_url
                                    print(f"[Chat] Using direct media URL: {gif_url}")
                                    break
                                else:
                                    # For view pages, skip - we should have already gotten the embed URL
                                    print(f"[Chat] Skipping view page URL (embed should have direct media): {tenor_url}")
                                    break
                
                # ============ SHARED MEMORY LOGIC AI FLOW ============
                # Note: Summarization is handled by GemGem (single API call)
                # Astral just reads the summary from shared_summary.txt

                # Step 1: Load short-term context from shared_memory.json
                # Load all history, format_for_router will handle truncation to last 30 if summary exists
                shared_history = self.shared_memory.load_memory()
                formatted_history, summary_context = self.shared_memory.format_for_router(shared_history)

                print(f"[SharedMemory] Loaded {len(shared_history)} messages from shared_memory.json")
                if summary_context:
                    print(f"[SharedMemory] Using summary context ({len(summary_context)} chars)")

                # Step 2: Query long-term memory (RAG - conversations only)
                # Skip RAG for simple greetings or when image/GIF is attached (waste of context)
                is_greeting = len(content.split()) <= 3 and any(pattern in content.lower() for pattern in BotConfig.GREETING_PATTERNS)
                has_image = bool(image_url or gif_url)

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
                    long_term_knowledge = await retrieve_relevant_knowledge(content, limit=BotConfig.RAG_FACT_LIMIT)
                    memory_context = format_knowledge_for_context(long_term_knowledge, current_username=message.author.display_name)
                    rag_count = len(long_term_knowledge)  # Track for footer
                    if memory_context:
                        print(f"[RAG] Injecting {len(long_term_knowledge)} facts into context: {memory_context[:200]}")
                    else:
                        print(f"[RAG] No relevant memories found for: '{content[:50]}'")
                
                # Step 3: Vision analysis with Gemini (if image/GIF attached)
                # Use Gemini 3-flash-preview for accurate vision, then pass to Grok for response
                vision_response = None

                if image_url:
                    from tools.vision import describe_image
                    print(f"[Chat] Using Gemini 3-flash-preview for vision analysis")
                    vision_response = await describe_image(image_url=image_url, user_context=content)
                    if vision_response:
                        print(f"[Vision] Gemini analysis: {vision_response[:150]}...")
                elif gif_url:
                    from tools.vision import describe_gif
                    print(f"[Chat] Using Gemini 3-flash-preview for GIF analysis")
                    vision_response = await describe_gif(gif_url=gif_url, user_context=content)
                    if vision_response:
                        print(f"[Vision] GIF analysis: {vision_response[:150]}...")

                # Step 4: Grok handles search natively (but not vision)
                # Grok's /v1/responses endpoint searches automatically when needed
                search_context = ""  # Not needed - Grok searches internally
                search_count = 0  # Not tracked anymore - Grok handles citations
                
                # Step 5: Generate response

                # Build context for system prompt (search results and summaries)
                combined_context = ""

                # ⚠️ SEARCH RESULTS (if no image attached)
                if search_context:
                    combined_context += f"⚠️ [SEARCH RESULTS - YOU MUST USE THIS INFO]:\n{search_context}\n\n"

                # === PREVIOUS CONTEXT SUMMARY (from shared_memory) ===
                if summary_context and not (image_url or gif_url):
                    combined_context += f"⚠️ {summary_context}\n\n"

                # Inject cached image descriptions so Astral remembers what she saw (skip if current message has image/GIF)
                if not (image_url or gif_url):
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

                # Determine user message based on what was sent
                if content:
                    user_message = content
                elif gif_url:
                    user_message = "[attached a GIF]"
                elif image_url:
                    user_message = "[attached an image]"
                else:
                    user_message = ""

                # Skip processing if truly empty
                if not user_message and not vision_response:
                    return

                response = await process_message(
                    user_message=user_message,
                    current_speaker=speaker_name,  # Pass speaker separately for system prompt
                    search_context=combined_context,  # System prompt context (Search results, summaries)
                    conversation_history=formatted_history, # Full 30-message history (vision injected here for images)
                    memory_context=rag_context,  # RAG is deprioritized
                    has_vision=False,  # Disable Grok vision - using Gemini instead
                    image_url=None  # Don't pass image to Grok - Gemini handles vision
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
                    astra_response=clean_response,
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
        """Log when bot is ready."""
        print("[Chat] Astral ready - Reading summary from GemGem's shared_summary.txt...")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
