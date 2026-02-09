"""Admin Cog - Access control for Astra."""
import discord
from discord.ext import commands
from discord import app_commands
from tools.admin import whitelist, ADMIN_IDS


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def handle_access_mention(self, message, raw_content):
        """Legacy text command handler for access management."""
        parts = raw_content.split()
        if len(parts) < 2:
            await message.channel.send(
                "Usage: `@Astra access [add/remove/list] [@User]`"
            )
            return

        cmd = parts[1].lower()

        if cmd == "list":
            uids = whitelist.get_list()
            if not uids:
                await message.channel.send(
                    "The whitelist is currently empty (besides Root Admins)."
                )
            else:
                mentions = [f"<@{uid}>" for uid in uids]
                await message.channel.send(
                    f"### 🔑 Authorized Users:\n" + "\n".join(mentions)
                )
            return

        if not message.mentions or (
            len(message.mentions) == 1 and message.mentions[0] == self.bot.user
        ):
            await message.channel.send("Please mention a user to add/remove.")
            return

        # Get the first person mentioned who isn't the bot
        target = next((u for u in message.mentions if u != self.bot.user), None)
        if not target:
            await message.channel.send("Target user not found.")
            return

        if cmd == "add":
            whitelist.add_user(target.id)
            await message.channel.send(f"✅ Enabled access for {target.mention}!")
        elif cmd == "remove":
            if target.id in ADMIN_IDS:
                await message.channel.send("❌ Cannot remove a Root Admin.")
                return
            if whitelist.remove_user(target.id):
                await message.channel.send(f"❌ Revoked access for {target.mention}.")
            else:
                await message.channel.send(f"{target.mention} wasn't on the list.")

    # --- SLASH COMMAND GROUP ---
    access_group = app_commands.Group(
        name="access", description="Manage bot access (Admins Only)"
    )

    @access_group.command(name="add", description="Authorize a user to use Astra")
    async def access_add(self, interaction: discord.Interaction, user: discord.User):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message(
                "❌ Only Root Admins can add users.", ephemeral=True
            )
            return
        whitelist.add_user(user.id)
        await interaction.response.send_message(
            f"✅ Enabled access for **{user.name}**!", ephemeral=True
        )

    @access_group.command(name="remove", description="Revoke a user's access")
    async def access_remove(self, interaction: discord.Interaction, user: discord.User):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message(
                "❌ Only Root Admins can remove users.", ephemeral=True
            )
            return
        if user.id in ADMIN_IDS:
            await interaction.response.send_message(
                "❌ Cannot remove a Root Admin.", ephemeral=True
            )
            return
        if whitelist.remove_user(user.id):
            await interaction.response.send_message(
                f"❌ Revoked access for **{user.name}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ **{user.name}** was not on the whitelist.", ephemeral=True
            )

    @access_group.command(name="list", description="List all authorized users")
    async def access_list(self, interaction: discord.Interaction):
        if not whitelist.is_authorized(interaction.user.id):
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return
        uids = whitelist.get_list()
        mentions = [f"<@{uid}>" for uid in uids]
        admin_mentions = [f"<@{uid}> (Admin)" for uid in ADMIN_IDS]
        full_list = admin_mentions + mentions
        await interaction.response.send_message(
            f"### 🔑 Authorized Users:\n" + "\n".join(full_list), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
