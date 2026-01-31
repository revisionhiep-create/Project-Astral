"""Draw Commands - Discord cog for image generation."""
import discord
from discord.ext import commands
from discord import app_commands
import re

from tools.drawing import get_drawing_handler


class DrawCog(commands.Cog):
    """Image generation commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.handler = get_drawing_handler(bot)
    
    @app_commands.command(name="draw", description="Generate an image from your prompt")
    @app_commands.describe(prompt="What do you want me to draw?")
    async def draw_slash(self, interaction: discord.Interaction, prompt: str):
        """Slash command for drawing."""
        await interaction.response.defer(thinking=True)
        
        try:
            # Create a fake message for the handler
            image_data, engine_name, commentary = await self.handler.handle_draw_request(
                message=interaction,  # Will use interaction.user instead of message.author
                subject=prompt
            )
            
            if not image_data:
                await interaction.followup.send(commentary)
                return
            
            # Build embed
            embed = discord.Embed(
                title=f"✨ {engine_name}",
                description=f"**Prompt:** {prompt[:200]}",
                color=discord.Color.purple()
            )
            embed.set_footer(text=f"For {interaction.user.display_name}")
            
            # Send image FIRST
            file = discord.File(image_data, filename="drawing.png")
            embed.set_image(url="attachment://drawing.png")
            
            # Create edit button view
            view = EditButtonView(prompt, image_data.getvalue(), self.handler, interaction.user.id)
            
            # Send image, then commentary after (so comment appears BELOW image)
            await interaction.followup.send(
                embed=embed,
                file=file,
                view=view
            )
            
            # Send commentary as follow-up (appears after image)
            await interaction.followup.send(content=commentary)
            
        except Exception as e:
            print(f"[Draw Error] {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send("Something went wrong with the drawing, try again?")
    
    @app_commands.command(name="gdraw", description="AI-enhanced drawing - I'll improve your prompt!")
    @app_commands.describe(idea="Give me a basic idea and I'll enhance it")
    async def gdraw_slash(self, interaction: discord.Interaction, idea: str):
        """Guided draw with AI prompt enhancement."""
        await interaction.response.defer(thinking=True)
        
        try:
            image_data, engine_name, enhanced_prompt, commentary = await self.handler.handle_guided_draw_request(
                message=interaction,
                basic_prompt=idea
            )
            
            if not image_data:
                await interaction.followup.send(commentary)
                return
            
            # Build embed with enhanced prompt shown
            embed = discord.Embed(
                title=f"✨ {engine_name} | Guided Draw",
                color=discord.Color.purple()
            )
            embed.add_field(
                name="Your Idea",
                value=idea[:200],
                inline=False
            )
            embed.add_field(
                name="Enhanced Prompt",
                value=enhanced_prompt[:500] if enhanced_prompt else "N/A",
                inline=False
            )
            embed.set_footer(text=f"For {interaction.user.display_name}")
            
            # Send image FIRST
            file = discord.File(image_data, filename="drawing.png")
            embed.set_image(url="attachment://drawing.png")
            
            # Create edit button view
            view = EditButtonView(idea, image_data.getvalue(), self.handler, interaction.user.id)
            
            # Send image first
            await interaction.followup.send(
                embed=embed,
                file=file,
                view=view
            )
            
            # Then commentary (appears after image)
            await interaction.followup.send(content=commentary)
            
        except Exception as e:
            print(f"[GDraw Error] {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send("Something went wrong with the drawing, try again?")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for natural language draw commands."""
        if message.author.bot:
            return
        
        # Check if bot is mentioned
        if not self.bot.user.mentioned_in(message):
            return
        
        content = message.content.lower()
        
        # Remove bot mention to get clean content
        clean_content = re.sub(r'<@!?\d+>', '', content).strip()
        
        # Check for draw triggers - MUST be at START of message
        draw_patterns = [
            r'^draw\s+(.+)',
            r'^sketch\s+(.+)',
            r'^paint\s+(.+)',
            r'^create\s+(?:an?\s+)?(?:image|picture|art)\s+(?:of\s+)?(.+)',
        ]
        
        gdraw_patterns = [
            r'^gdraw\s+(.+)',
            r'^guided\s+draw\s+(.+)',
        ]
        
        # Check for gdraw first (more specific)
        for pattern in gdraw_patterns:
            match = re.search(pattern, clean_content)
            if match:
                subject = match.group(1).strip()
                async with message.channel.typing():
                    image_data, engine_name, enhanced, commentary = await self.handler.handle_guided_draw_request(
                        message=message,
                        basic_prompt=subject
                    )
                    
                    if image_data:
                        embed = discord.Embed(
                            title=f"✨ {engine_name} | Guided Draw",
                            color=discord.Color.purple()
                        )
                        embed.add_field(name="Your Idea", value=subject[:200], inline=False)
                        if enhanced:
                            embed.add_field(name="Enhanced", value=enhanced[:300], inline=False)
                        
                        file = discord.File(image_data, filename="drawing.png")
                        embed.set_image(url="attachment://drawing.png")
                        
                        view = EditButtonView(subject, image_data.getvalue(), self.handler, message.author.id)
                        # Send image first, then commentary
                        await message.reply(embed=embed, file=file, view=view)
                        await message.channel.send(content=commentary)
                    else:
                        await message.reply(commentary)
                return
        
        # Check for regular draw
        for pattern in draw_patterns:
            match = re.search(pattern, clean_content)
            if match:
                subject = match.group(1).strip()
                # Remove bot mention from subject
                subject = re.sub(r'<@!?\d+>', '', subject).strip()
                
                if not subject:
                    continue
                
                async with message.channel.typing():
                    image_data, engine_name, commentary = await self.handler.handle_draw_request(
                        message=message,
                        subject=subject
                    )
                    
                    if image_data:
                        embed = discord.Embed(
                            title=f"✨ {engine_name}",
                            description=f"**Prompt:** {subject[:200]}",
                            color=discord.Color.purple()
                        )
                        
                        file = discord.File(image_data, filename="drawing.png")
                        embed.set_image(url="attachment://drawing.png")
                        
                        view = EditButtonView(subject, image_data.getvalue(), self.handler, message.author.id)
                        # Send image first, then commentary
                        await message.reply(embed=embed, file=file, view=view)
                        await message.channel.send(content=commentary)
                    else:
                        await message.reply(commentary)
                return


class EditButtonView(discord.ui.View):
    """View with Edit button for drawings."""
    
    def __init__(self, original_subject: str, image_data: bytes, handler, user_id: int):
        super().__init__(timeout=3600)  # 1 hour timeout
        self.original_subject = original_subject
        self.image_data = image_data
        self.handler = handler
        self.user_id = user_id
    
    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle edit button click."""
        # Only allow the original user to edit
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who requested this drawing can edit it!",
                ephemeral=True
            )
            return
        
        # Show modal for edit instructions
        modal = EditModal(self.original_subject, self.image_data, self.handler)
        await interaction.response.send_modal(modal)


class EditModal(discord.ui.Modal, title="Edit Drawing"):
    """Modal for entering edit instructions."""
    
    edit_instruction = discord.ui.TextInput(
        label="What would you like to change?",
        style=discord.TextStyle.paragraph,
        placeholder="e.g., 'add a sunset background' or 'make it more colorful'",
        required=True,
        max_length=500
    )
    
    def __init__(self, original_subject: str, image_data: bytes, handler):
        super().__init__()
        self.original_subject = original_subject
        self.image_data = image_data
        self.handler = handler
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            image_data, engine_name, critique = await self.handler.handle_edit_request(
                original_image_data=self.image_data,
                edit_instruction=self.edit_instruction.value,
                user_id=str(interaction.user.id)
            )
            
            if not image_data:
                await interaction.followup.send(critique)
                return
            
            # Build embed
            embed = discord.Embed(
                title=f"✏️ {engine_name} | Edited",
                color=discord.Color.purple()
            )
            embed.add_field(name="Original", value=self.original_subject[:100], inline=True)
            embed.add_field(name="Edit", value=self.edit_instruction.value[:100], inline=True)
            embed.set_footer(text=f"For {interaction.user.display_name}")
            
            file = discord.File(image_data, filename="edited.png")
            embed.set_image(url="attachment://edited.png")
            
            # New edit view for chain editing
            view = EditButtonView(
                self.original_subject,
                image_data.getvalue(),
                self.handler,
                interaction.user.id
            )
            
            # Send edited image first
            await interaction.followup.send(
                embed=embed,
                file=file,
                view=view
            )
            
            # Then critique (appears after image)
            await interaction.followup.send(content=critique)
            
        except Exception as e:
            print(f"[Edit Error] {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send("Edit failed, try again?")


async def setup(bot: commands.Bot):
    await bot.add_cog(DrawCog(bot))
